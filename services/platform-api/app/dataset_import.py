"""Atomic, versioned source-data import and aviation ontology projection.

Run with explicit database and tenant arguments; never guesses a production DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session

from .database import Base
from .db_models import (AudiencePackageRecord, AudienceSnapshotRecord, CampaignRecord,
    CampaignVersionRecord, ContentAssetRecord, DataSourceConfigRecord, DatasetRecord,
    DatasetRowRecord, ImportJobRecord, OntologyEntityRecord, OntologyRelationRecord,
    ProductPackageRecord, TenantMembershipRecord, TenantRecord, UserRecord)
from .ontology.projection import sync_business_graph
from .ontology.semantic_model import object_type_ids, relation_type_ids, validate_relation_endpoints


SHEET_KEYS = dict(zip([
    "来源清单", "机场目录", "航线目录", "企业客户", "客户画像", "产品目录", "航班计划",
    "营销活动", "内容素材", "搜索行为", "客票订单", "产品曝光", "辅营交易",
    "航班库存与预测样本", "触达回执", "订单归因", "购买倾向训练样本", "营销增量实验样本",
    "市场日历", "本体实体", "本体关系", "爬取航班原始明细", "爬取文件清单",
    "爬取航班标准目录", "爬取票价产品目录", "爬取单航段标准报价", "模拟航班报价_爬取结构",
    "爬取字段映射", "爬取质量说明"], [
    "sources", "airports", "routes", "enterprises", "customers", "products", "flights",
    "campaigns", "contents", "events", "orders", "exposures", "ancillaries", "inventory",
    "touches", "attribution", "propensity", "experiment", "calendar", "entities", "relations",
    "crawl-raw", "crawl-files", "crawl-flights", "crawl-products", "crawl-offers", "sim-offers",
    "field-mapping", "crawl-quality"]))


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def validate_dataset(data):
    """Reject malformed inputs before any writes, including unresolved foreign keys."""
    sheets = {s["name"]: s for s in data["sheets"]}
    if len(sheets) != len(data["sheets"]):
        raise ValueError("重复数据集名称")
    indexes = {}
    for name, sheet in sheets.items():
        if name not in SHEET_KEYS:
            raise ValueError(f"未配置的数据集: {name}")
        pk = sheet["pk"]
        keys = [r.get(pk) for r in sheet["rows"]]
        if any(k is None or k == "" for k in keys) or len(set(keys)) != len(keys):
            raise ValueError(f"{name} 主键缺失或重复")
        indexes[name, pk] = set(keys)
        declared = {f["code"] for f in sheet["fields"]}
        if any(set(row) - declared for row in sheet["rows"]):
            raise ValueError(f"{name} 包含未声明字段")
    for name, sheet in sheets.items():
        for field, target in sheet.get("fks", {}).items():
            target_name, target_field = target.rsplit(".", 1)
            valid = indexes.get((target_name, target_field))
            if valid is None:
                other = sheets.get(target_name)
                if other is None:
                    raise ValueError(f"{name} 缺少关联数据集 {target_name}")
                valid = {r.get(target_field) for r in other["rows"]}
            if any(r.get(field) not in (None, "") and r[field] not in valid for r in sheet["rows"]):
                raise ValueError(f"{name}.{field} 存在无效外键")
        for row in sheet["rows"]:
            if all(k in row for k in ("paid_yuan", "refund_yuan", "net_yuan")):
                if abs(row["paid_yuan"] - row["refund_yuan"] - row["net_yuan"]) > .005:
                    raise ValueError(f"{name} 实付、退款和净实付不平衡")
            if all(k in row for k in ("base_fare_yuan", "tax_yuan", "total_fare_yuan")):
                if abs(row["base_fare_yuan"] + row["tax_yuan"] - row["total_fare_yuan"]) > .005:
                    raise ValueError(f"{name} 票价与税费不平衡")
    actual = sum(len(s["rows"]) for s in sheets.values())
    if actual != data["metadata"]["total_data_rows"]:
        raise ValueError("记录总数与元数据不一致")
    if any(c[2] != "通过" for c in data.get("checks", [])):
        raise ValueError("源数据质量检查未全部通过")
    return sheets


def bulk(session, model, rows, size=1000):
    for start in range(0, len(rows), size):
        session.execute(insert(model), rows[start:start + size])


def import_dataset(session: Session, data: dict, tenant_code: str, username: str,
                   namespace: str, fingerprint: str, progress=lambda message: None):
    """Caller commits or rolls back the whole import. Identical versions are a no-op."""
    if not re.fullmatch(r"[A-Za-z0-9-]{1,12}", namespace):
        raise ValueError("版本前缀必须为 1–12 位字母、数字或连字符")
    tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == tenant_code))
    user = session.scalar(select(UserRecord).where(UserRecord.username == username))
    membership = session.scalar(select(TenantMembershipRecord).where(
        TenantMembershipRecord.tenant_id == tenant.id, TenantMembershipRecord.user_id == user.id)) if tenant and user else None
    if not tenant or tenant.status != "active" or not user or not user.enabled or not membership or membership.role not in {"admin", "manager", "analyst"}:
        raise ValueError("工作区、账号或导入权限无效")
    existing = list(session.scalars(select(DatasetRecord).where(
        DatasetRecord.tenant_id == tenant.id, DatasetRecord.dataset_key.startswith(namespace + "-", autoescape=True))))
    if existing:
        meta = json.loads(existing[0].metadata_json)
        if meta.get("fingerprint") != fingerprint:
            raise ValueError("同版本已导入其他内容，请使用新版本前缀")
        report = meta.get("import_report")
        if not report or len(existing) != report["dataset_count"]:
            raise ValueError("已有导入版本不完整")
        return {**report, "idempotent": True}
    sheets = validate_dataset(data)
    tid, uid = tenant.id, user.id
    key = lambda name: namespace + "-" + SHEET_KEYS[name]
    xid = lambda raw: namespace + "-" + str(raw)
    get = lambda name: sheets.get(name, {}).get("rows", [])
    now = datetime.now(timezone.utc)
    job = ImportJobRecord(id="DS-" + hashlib.sha256(f"{tid}:{namespace}".encode()).hexdigest()[:28],
        tenant_id=tid, created_by=uid, dataset_type="bundle", file_name=namespace + ".json",
        file_format="json", status="completed", total_rows=data["metadata"]["total_data_rows"],
        accepted_rows=data["metadata"]["total_data_rows"], rejected_rows=0, completed_at=now)
    session.add(job)
    session.flush()
    datasets = []
    for name, sheet in sheets.items():
        stats = {}
        if name == "客票订单": stats = {k: v for k, v in data.get("statistics", {}).items() if k.startswith("orders_")}
        if name == "辅营交易": stats = {"net_yuan": data.get("statistics", {}).get("anc_net")}
        if name == "购买倾向训练样本": stats = {k: v for k, v in data.get("statistics", {}).items() if k.startswith("purchase_")}
        if name == "营销增量实验样本": stats = {"experiment": data.get("statistics", {}).get("experiment"), "analysis": "随机分配、ITT；非送达子样本"}
        if name == "客户画像": stats = {"segment_counts": dict(Counter(r["business_segment"] for r in sheet["rows"]))}
        if name == "爬取单航段标准报价":
            prices = [r["total_fare_yuan"] for r in sheet["rows"]]
            stats = {"min_total_fare_yuan": min(prices), "max_total_fare_yuan": max(prices),
                "counting_unit": "报价，非乘客或成交订单", "captured_at": "未知，不能作历史票价时间序列"} if prices else {}
        modes = sorted({r.get("data_mode", "资料/元数据") for r in sheet["rows"]})
        record = DatasetRecord(tenant_id=tid, dataset_key=key(name), name=name, row_count=len(sheet["rows"]),
            grain=sheet.get("grain", ""), source=sheet.get("source", ""), data_mode=" / ".join(modes)[:80],
            description=sheet.get("description", ""), usage=sheet.get("use", ""), schema_json=dumps(sheet["fields"]),
            metadata_json=dumps(dict(fingerprint=fingerprint, namespace=namespace, pk=sheet["pk"], fks=sheet.get("fks", {}),
                as_of=data["metadata"].get("as_of"), data_modes=modes, statistics=stats)), import_job_id=job.id)
        session.add(record)
        session.flush()
        for start in range(0, len(sheet["rows"]), 1000):
            rows = sheet["rows"][start:start + 1000]
            bulk(session, DatasetRowRecord, [dict(tenant_id=tid, dataset_id=record.id, record_key=str(r[sheet["pk"]]),
                source_id=r.get("source_id", ""), data_mode=r.get("data_mode", "资料/元数据"),
                route_id=r.get("route_id"), flight_id=r.get("flight_id") or r.get("crawl_flight_id"),
                customer_id=r.get("customer_id"), payload_json=dumps(r)) for r in rows])
        datasets.append(record)
        progress(f"明细入库 {name}: {record.row_count:,}")
    # Source registrations describe uploaded material; they are not live connectors.
    for source in get("来源清单"):
        session.add(DataSourceConfigRecord(tenant_id=tid, source_id=xid(source["source_id"]),
            display_name=source["name"], source_type="file", enabled=False, schedule="manual",
            endpoint=source.get("url_or_file", "")[:400], mapping_json=dumps(source), last_sync_at=now))
    audiences = {}
    segments = Counter(r["business_segment"] for r in get("客户画像"))
    for i, (segment, count) in enumerate(sorted(segments.items()), 1):
        expression = dict(dataset_key=key("客户画像"), field="business_segment", operator="eq", value=segment,
            as_of=data["metadata"].get("as_of"), synthetic=True, counting_unit="去重客户")
        a = AudiencePackageRecord(tenant_id=tid, external_id=xid(f"SEG-{i}"), name=segment,
            selection_mode="expression", expression_json=dumps(expression), estimated_size=count, status="已冻结", created_by=uid)
        session.add(a); session.flush()
        audiences[segment] = a
        session.add(AudienceSnapshotRecord(tenant_id=tid, package_id=a.id, external_id=xid(f"SEG-{i}-V1"),
            estimated_size=count, expression_json=dumps(expression), source=namespace + ":SIM-CRM", created_by=uid))
    products = {}
    for r in get("产品目录"):
        p = ProductPackageRecord(tenant_id=tid, external_id=xid("PP-" + r["product_id"]), name=r["product_name"],
            product_type=r["category"], description=f"{r['product_name']}，参考价格 {r['price_yuan']} 元/{r['unit']}；待上游核验。来源 {key('产品目录')} / {r['product_id']}", eligibility=r["eligibility"], status="草稿",
            valid_from=datetime.fromisoformat(r["valid_from"]), valid_to=datetime.fromisoformat(r["valid_to"] + "T23:59:59"), created_by=uid)
        session.add(p); session.flush(); products[r["product_id"]] = p
    touches = defaultdict(list)
    content_rows = defaultdict(list)
    for r in get("触达回执"): touches[r["campaign_id"]].append(r)
    for r in get("内容素材"): content_rows[r["campaign_id"]].append(r)
    versions, historical_snapshots = {}, {}
    for r in get("营销活动"):
        cid = xid(r["campaign_id"])
        universe = {t["customer_id"] for t in touches[r["campaign_id"]]}
        expr = dict(dataset_key=key("触达回执"), field="campaign_id", operator="eq", value=r["campaign_id"],
            counting_unit="历史触达尝试的去重客户，含排除和失败", synthetic=True, historical=True)
        a = AudiencePackageRecord(tenant_id=tid, external_id=xid("AUD-" + r["campaign_id"]),
            name=r["name"] + " · 历史范围", selection_mode="expression", expression_json=dumps(expr),
            estimated_size=len(universe), status="历史归档", created_by=uid)
        session.add(a); session.flush()
        sn = AudienceSnapshotRecord(tenant_id=tid, package_id=a.id, external_id=xid("SN-" + r["campaign_id"]),
            estimated_size=len(universe), expression_json=dumps(expr), source=namespace + ":SIM-MKT", status="历史归档", created_by=uid)
        session.add(sn); session.flush(); historical_snapshots[r["campaign_id"]] = sn
        linked = content_rows[r["campaign_id"]]
        p = products.get(linked[0]["product_id"]) if linked else None
        session.add(CampaignRecord(tenant_id=tid, id=cid, name=r["name"], stage="效果复盘", status="已完成",
            version=r["version"], owner="数据导入", audience_size=len(universe), product_package=p.name if p else "",
            budget_yuan=r["budget_yuan"], roi_target=0))
        v = CampaignVersionRecord(tenant_id=tid, campaign_id=cid, external_id=xid(r["campaign_id"] + "-" + r["version"]),
            version=r["version"], audience_snapshot_id=sn.id, product_package_id=p.id if p else None,
            budget_yuan=r["budget_yuan"], channels_json=dumps(sorted({c["channel"] for c in linked})),
            status="历史归档", created_by=uid)
        session.add(v); session.flush(); versions[r["campaign_id"]] = v
    for r in get("内容素材"):
        p = products.get(r["product_id"])
        c = ContentAssetRecord(tenant_id=tid, external_id=xid(r["content_id"]), campaign_id=xid(r["campaign_id"]),
            product_package_id=p.id if p else None, name=r["title"] + " " + r["channel"], title=r["title"], body=r["body"],
            channel=r["channel"], version=r["version"], status="历史归档", generated_by="dataset-import", created_by=uid,
            generation_context_json=dumps(dict(dataset_key=key("内容素材"), record_key=r["content_id"], synthetic=True)))
        session.add(c); session.flush()
        v = versions.get(r["campaign_id"])
        if v: v.content_asset_ids_json = dumps(json.loads(v.content_asset_ids_json or "[]") + [c.id])
    sync_business_graph(session, tid)
    progress("业务客群、产品、活动和内容已映射")
    # Build typed ontology objects with explicit source-row references.
    nodes, edges = {}, {}
    def node(raw, kind, label, attrs, sheet=None, record=None, source="SIM-KG"):
        if kind not in object_type_ids(): raise ValueError(f"未注册本体类型 {kind}")
        external_id = xid(raw)
        props = dict(attrs, import_namespace=namespace)
        if sheet: props.update(dataset_key=key(sheet), record_key=str(record))
        previous = nodes.get(external_id)
        if previous and previous["entity_type"] != kind: raise ValueError(f"本体类型冲突 {raw}")
        nodes[external_id] = dict(tenant_id=tid, external_id=external_id, entity_type=kind, label=label[:200],
            attributes_json=dumps({**(json.loads(previous["attributes_json"]) if previous else {}), **props}),
            source=namespace + ":" + source, confidence=1.0, import_job_id=job.id)
        return external_id
    def edge(a, relation, b, evidence="源记录字段关联"):
        edges[a, relation, b] = evidence
    for r in get("本体实体"):
        raw = r["external_id"]
        attrs = {**json.loads(r["attributes_json"]), "data_mode": r["data_mode"]}
        if r["entity_type"] in {"Campaign", "CampaignVersion", "ContentAsset"}:
            attrs.update(status="历史归档", historical=True)
        if r["entity_type"] == "CustomerAggregate" and r["label"] in audiences:
            raw = audiences[r["label"]].external_id[len(namespace) + 1:]
        node(raw, r["entity_type"], r["label"], attrs,
            "本体实体", r["external_id"], r["source_id"])
    aggregate_alias = {xid(r["external_id"]): audiences[r["label"]].external_id for r in get("本体实体")
        if r["entity_type"] == "CustomerAggregate" and r["label"] in audiences}
    for r in get("本体关系"):
        a, b = xid(r["source_external_id"]), xid(r["target_external_id"])
        edge(aggregate_alias.get(a, a), r["relation_type"], aggregate_alias.get(b, b), r["evidence"])
    routes = {r["route_id"]: r for r in get("航线目录")}
    for r in get("机场目录"):
        node(r["airport_code"], "Airport", r["airport_name"], r, "机场目录", r["airport_code"], r["source_id"])
    for r in routes.values():
        n = node(r["route_id"], "Route", r["origin_city"] + "—" + r["destination_city"], r, "航线目录", r["route_id"], r["source_id"])
        edge(n, "departs_from", xid(r["origin"])); edge(n, "arrives_at", xid(r["destination"]))
    def flight(raw, r, name, number):
        n = node(raw, "Flight", number + " " + r["departure_at"][:10], r, name, raw, r["source_id"])
        route = routes[r["route_id"]]
        seg = node("SEG-" + raw, "FlightSegment", number + " · 单航段", dict(flight_id=raw, route_id=r["route_id"],
            departure_at=r["departure_at"], arrival_at=r["arrival_at"], data_mode=r["data_mode"]), name, raw, r["source_id"])
        edge(n, "operates_on", xid(r["route_id"])); edge(n, "has_segment", seg)
        edge(seg, "departs_from", xid(route["origin"])); edge(seg, "arrives_at", xid(route["destination"]))
    for r in get("航班计划"): flight(r["flight_id"], r, "航班计划", r["flight_no"])
    for r in get("爬取航班标准目录"): flight(r["crawl_flight_id"], r, "爬取航班标准目录", r["marketing_flight_no"])
    for r in get("产品目录"):
        n = node("ANC-" + r["product_id"], "AncillaryProduct", r["product_name"], dict(r, synthetic=True, sellability_status="待核验"),
            "产品目录", r["product_id"], r["source_id"])
        edge(xid("PP-" + r["product_id"]), "includes_ancillary", n)
    for r in get("爬取票价产品目录"):
        node(r["fare_product_id"], "Product", r["source_product_label"] or r["source_product_name"],
            dict(r, sellability_status="待上游核验"), "爬取票价产品目录", r["fare_product_id"], r["source_id"])
    def offer(r, name, f, code, label, attrs, product):
        cabin_raw = "CAB-" + f + "-" + (code or "UNKNOWN")
        cabin_id = xid(cabin_raw)
        if cabin_id not in nodes:
            node(cabin_raw, "Cabin", label or code or "未知舱位", dict(cabin_code=code, available_seats=None,
                data_mode=r["data_mode"], flight_id=f), name, r["offer_id"], r["source_id"])
            edge(xid(f), "has_cabin", cabin_id)
        fare = node(r["offer_id"], "Fare", label + " · " + str(attrs["total_fare_yuan"]) + " CNY", attrs,
            name, r["offer_id"], r["source_id"])
        edge(cabin_id, "has_fare", fare); edge(fare, "uses_product", product)
    for r in get("爬取单航段标准报价"):
        offer(r, "爬取单航段标准报价", r["crawl_flight_id"], r["cabin_code"], r["cabin_name"], r, xid(r["fare_product_id"]))
    for r in get("模拟航班报价_爬取结构"):
        product_raw = "SIMFARE-" + r["产品代码"]
        if xid(product_raw) not in nodes:
            node(product_raw, "Product", r["产品标签"], dict(synthetic=True, source_product_code=r["产品代码"],
                eligibility=r["产品说明"], sellability_status="待核验"), "模拟航班报价_爬取结构", r["offer_id"], r["source_id"])
        attrs = dict(offer_id=r["offer_id"], flight_id=r["flight_id"], route_id=r["route_id"],
            captured_at=r["captured_at"], currency="CNY", base_fare_yuan=r["票价(不含税)"], tax_yuan=r["税费"],
            total_fare_yuan=r["含税总价"], baggage_allowance_text=r["免费行李额"], price_basis=r["price_basis"],
            data_mode=r["data_mode"], synthetic=True)
        offer(r, "模拟航班报价_爬取结构", r["flight_id"], r["舱位代码"], r["舱位等级"], attrs, xid(product_raw))
    for r in get("航班库存与预测样本"):
        n = node(r["snapshot_id"], "MetricObservation", r["flight_id"] + " · 库存快照", dict(r, synthetic=True),
            "航班库存与预测样本", r["snapshot_id"], r["source_id"])
        edge(xid(r["flight_id"]), "has_metric", n)
    for r in get("营销活动"):
        cid, ts = r["campaign_id"], touches[r["campaign_id"]]
        summary = dict(campaign_id=xid(cid), synthetic=True, attempts=len(ts), unique_customers=len({t["customer_id"] for t in ts}),
            delivered=sum(bool(t["delivered_at"]) for t in ts), clicked=sum(bool(t["clicked_at"]) for t in ts),
            statuses=dict(Counter(t["status"] for t in ts)), source_dataset=key("触达回执"), counting_unit="触达事件；unique_customers为去重客户")
        feedback = node("FB-" + cid, "Feedback", r["name"] + " · 触达结果", summary)
        edge(xid(cid), "produces_feedback", feedback)
        at = [a for a in get("订单归因") if a["campaign_id"] == cid]
        result = node("AT-" + cid, "AttributionResult", r["name"] + " · 规则归因", dict(campaign_id=xid(cid), synthetic=True,
            attributed_orders=len(at), attributed_net_yuan=sum(a["net_yuan"] for a in at), attribution_model="7日末次点击",
            causal_effect=False, source_dataset=key("订单归因"), counting_unit="订单", monetary_basis="含税净实付，非会计收入"))
        edge(xid(cid), "produces_attribution", result); edge(result, "attributes_to", xid(cid))
        if cid in historical_snapshots: edge(result, "attributes_to", historical_snapshots[cid].external_id)
    existing_nodes = {r.external_id: r for r in session.scalars(select(OntologyEntityRecord).where(
        OntologyEntityRecord.tenant_id == tid, OntologyEntityRecord.external_id.startswith(namespace + "-", autoescape=True)))}
    types = {k: v.entity_type for k, v in existing_nodes.items()}
    types.update({k: v["entity_type"] for k, v in nodes.items()})
    for (a, relation, b), evidence in edges.items():
        if a not in types or b not in types: raise ValueError(f"缺少本体端点: {a} {relation} {b}")
        if relation not in relation_type_ids(): raise ValueError(f"未注册本体关系: {relation}")
        problem = validate_relation_endpoints(relation, types[a], types[b])
        if problem: raise ValueError(problem)
    new = []
    for external, row in nodes.items():
        if external in existing_nodes:
            rec = existing_nodes[external]
            rec.attributes_json = dumps({**json.loads(rec.attributes_json), **json.loads(row["attributes_json"])})
            rec.source = row["source"]
            rec.import_job_id = job.id
        else: new.append(row)
    bulk(session, OntologyEntityRecord, new)
    session.flush()
    ids = dict(session.execute(select(OntologyEntityRecord.external_id, OntologyEntityRecord.id).where(
        OntologyEntityRecord.tenant_id == tid, OntologyEntityRecord.external_id.startswith(namespace + "-", autoescape=True))).all())
    already = set(session.execute(select(OntologyRelationRecord.source_entity_id, OntologyRelationRecord.relation_type,
        OntologyRelationRecord.target_entity_id).where(OntologyRelationRecord.tenant_id == tid,
            OntologyRelationRecord.source_entity_id.in_(select(OntologyEntityRecord.id).where(
                OntologyEntityRecord.tenant_id == tid, OntologyEntityRecord.external_id.startswith(namespace + "-", autoescape=True))))).all())
    relations = [dict(tenant_id=tid, source_entity_id=ids[a], target_entity_id=ids[b], relation_type=rel,
        evidence=evidence, source=namespace, confidence=1.0, import_job_id=job.id)
        for (a, rel, b), evidence in edges.items() if (ids[a], rel, ids[b]) not in already]
    bulk(session, OntologyRelationRecord, relations)
    report = dict(namespace=namespace, fingerprint=fingerprint, tenant_id=tid, tenant_code=tenant_code,
        dataset_count=len(datasets), source_rows=sum(r.row_count for r in datasets), import_job_id=job.id,
        imported_at=now.isoformat(), business=dict(segment_packages=len(segments), segment_population=sum(segments.values()),
            historical_audiences=len(versions), product_packages=len(products), campaigns=len(versions), contents=len(get("内容素材"))),
        ontology_entities=len(ids), ontology_relations=len(already) + len(relations),
        entity_types=dict(Counter(types.values())), relation_types=dict(Counter(r for a, r, b in already) + Counter(r["relation_type"] for r in relations)),
        datasets=[dict(dataset_key=r.dataset_key, name=r.name, row_count=r.row_count, source=r.source, data_mode=r.data_mode,
            grain=r.grain, usage=r.usage, pk=sheets[r.name]["pk"], fks=sheets[r.name].get("fks", {})) for r in datasets], idempotent=False)
    for record in datasets:
        meta = json.loads(record.metadata_json); meta["import_report"] = report; record.metadata_json = dumps(meta)
    progress(f"本体入库: {len(ids):,} 对象、{report['ontology_relations']:,} 关系")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--tenant-code", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    raw = Path(args.input).read_bytes()
    data = json.loads(raw)
    engine = create_engine(args.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            report = import_dataset(session, data, args.tenant_code, args.username, args.namespace,
                hashlib.sha256(raw).hexdigest(), lambda message: print(message, flush=True))
            session.commit()
        except Exception:
            session.rollback()
            raise
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "datasets"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
