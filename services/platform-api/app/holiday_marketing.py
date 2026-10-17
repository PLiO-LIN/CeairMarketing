"""Evidence-driven holiday planning. Only public calculations are exposed.

Source rows supply observations; typed ontology paths gate their composition.
Unknown facts stay unknown. Planning never sends channel messages.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from .auth import get_tenant_context, require_write
from .database import get_session
from .db_models import (DatasetRecord, DatasetRowRecord, OntologyEntityRecord,
    OntologyRelationRecord, AudiencePackageRecord, AudienceSnapshotRecord,
    ProductPackageRecord, ContentAssetRecord)
from .ontology.semantic_model import validate_relation_endpoints

router = APIRouter(prefix="/api/holiday-marketing", tags=["holiday-marketing"])
SEGMENTS = ["家庭出游", "休闲探索", "价格敏感", "商务高频", "企业差旅", "会员沉默"]
CHANNELS = {"App": "app_consent", "短信": "sms_consent", "微信": "wechat_consent"}
RELATIONS = {"operates_on": "执飞航线", "has_segment": "包含航段", "departs_from": "出发机场",
    "arrives_at": "到达机场", "has_cabin": "提供舱位", "has_fare": "对应票价",
    "uses_product": "使用票价产品", "includes_ancillary": "包含辅营", "has_metric": "库存观测"}


class HolidayParameters(BaseModel):
    start: date = date(2026, 10, 1)
    end: date = date(2026, 10, 7)
    as_of: datetime = datetime(2026, 9, 30, 23, 59, 59)
    segment: str = "家庭出游"
    route_id: str = ""
    channel: str = "App"
    product_id: str = "P-FLEX"
    budget_yuan: int = Field(default=20000, ge=0, le=10000000)
    frequency_7d: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.as_of.tzinfo is not None:
            raise ValueError("请使用数据集的本地业务时点，不带时区")
        if self.segment not in SEGMENTS or self.channel not in CHANNELS:
            raise ValueError("客群或渠道不在支持范围")
        if not re.fullmatch(r"P-[A-Z0-9]+", self.product_id):
            raise ValueError("产品代码无效")
        if self.end < self.start or (self.end - self.start).days > 31:
            raise ValueError("出行窗口应为1至32天")
        if self.as_of.date() >= self.start:
            raise ValueError("营销观测时点必须早于出行窗口")
        return self


def holiday_intent(message):
    return bool(re.search(r"国庆|节假日|假期|五一|春节|中秋|节日营销", message)) and bool(re.search(r"营销|活动|出行|方案|本体|图谱", message))


def parameters_from_message(message, session=None, tenant_id=None, previous=None):
    """Explicit dates win; unsupported future holidays never silently become National Day."""
    values = dict(previous or {})
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", message)
    if len(dates) >= 2:
        values.update(start=dates[0], end=dates[1])
    elif dates:
        values.update(start=dates[0], end=dates[0])
    elif re.search(r"五一|春节|中秋", message) and "国庆" not in message:
        raise ValueError("该节假日尚未指定出行日期，请补充 YYYY-MM-DD 至 YYYY-MM-DD；已有完整演示窗口为2026-10-01至2026-10-07")
    for s in SEGMENTS:
        if s in message: values["segment"] = s
    for c in CHANNELS:
        if c in message: values["channel"] = c
    route = re.search(r"R-[A-Z]{3}-[A-Z]{3}", message.upper())
    if route: values["route_id"] = route.group()
    elif session is not None:
        ds = session.scalar(select(DatasetRecord).where(DatasetRecord.tenant_id == tenant_id,
            DatasetRecord.name == "航线目录").order_by(DatasetRecord.id.desc()).limit(1))
        if ds:
            choices = [json.loads(r) for r in session.scalars(select(DatasetRowRecord.payload_json).where(
                DatasetRowRecord.tenant_id == tenant_id, DatasetRowRecord.dataset_id == ds.id))]
            hits = [r for r in choices if r.get("origin_city") in message and r.get("destination_city") in message
                and message.index(r["origin_city"]) < message.index(r["destination_city"])]
            if not hits and previous and previous.get("route_id"):
                origin = previous["route_id"].split("-")[1]
                hits = [r for r in choices if r.get("origin") == origin and r.get("destination_city") in message]
            if hits:
                # Chinese city names can refer to several airports: require a supported simulated route.
                simulated = {r for r in session.scalars(select(DatasetRowRecord.route_id).join(DatasetRecord, DatasetRecord.id == DatasetRowRecord.dataset_id).where(
                    DatasetRowRecord.tenant_id == tenant_id, DatasetRecord.name == "航班计划").distinct())}
                matched = sorted([r for r in hits if r["route_id"] in simulated], key=lambda r:r["route_id"])
                if not matched: raise ValueError("所述航线尚无模拟航班计划，请导入对应数据或选择可用航线")
                values["route_id"] = matched[0]["route_id"]
    product = re.search(r"P-[A-Z0-9]+", message.upper())
    if product: values["product_id"] = product.group()
    if "家庭邻座" in message: values["product_id"] = "P-FAMILY"
    if "机上网络" in message or "Wi-Fi" in message: values["product_id"] = "P-WIFI"
    if "接送" in message: values["product_id"] = "P-PICKUP"
    budget = re.search(r"预算\s*(?:改为|改成|设为|调整为|为|是)?\s*([\d.]+)\s*(万)?", message)
    if budget: values["budget_yuan"] = int(float(budget[1]) * (10000 if budget[2] else 1))
    return HolidayParameters(**values)


def analyze_holiday(session, tenant_id, params, publish=None, emit=None, omitted_relation=None):
    p = params if isinstance(params, HolidayParameters) else HolidayParameters(**params)
    cards = []
    def begin(key, title):
        if emit: emit("marketing/stage-started", dict(stage=key, title=title))
    def stage(key, title, summary, **body):
        card = dict(type="scenario", id="holiday-" + key, title=title, summary=summary, **body)
        cards.append(card)
        if publish: publish(card, "scenario")
        if emit: emit("marketing/stage-completed", dict(stage=key, title=title, summary=summary,
            evidence=body.get("evidence", []), checks=body.get("checks", [])))

    begin("scope", "确认场景与数据版本")
    # One version/namespace for the complete bundle. No mixing imports or tenants.
    customer_ds = session.scalar(select(DatasetRecord).where(DatasetRecord.tenant_id == tenant_id,
        DatasetRecord.name == "客户画像").order_by(DatasetRecord.id.desc()).limit(1))
    if not customer_ds: raise ValueError("当前工作区未导入客户画像，请先导入航空营销数据集")
    meta = json.loads(customer_ds.metadata_json)
    namespace = meta.get("namespace")
    if not namespace: raise ValueError("数据集缺少本体命名空间，无法关联业务证据")
    datasets = {d.name: d for d in session.scalars(select(DatasetRecord).where(
        DatasetRecord.tenant_id == tenant_id, DatasetRecord.import_job_id == customer_ds.import_job_id))}
    required = ["客户画像", "航线目录", "航班计划", "搜索行为", "客票订单", "触达回执", "产品目录"]
    missing = [n for n in required if n not in datasets]
    if missing: raise ValueError("场景缺少数据：" + "、".join(missing))
    asof = p.as_of.isoformat(sep=" ")
    profile_time = str(meta.get("as_of", ""))
    if not profile_time or profile_time > asof:
        raise ValueError("画像版本晚于观测时点或缺少时点，不能用于历史营销回放")
    used = set()
    def rows(name, route=None, flights=None):
        if name not in datasets: return []
        used.add(name)
        stmt = select(DatasetRowRecord.payload_json).where(DatasetRowRecord.tenant_id == tenant_id,
            DatasetRowRecord.dataset_id == datasets[name].id)
        if route: stmt = stmt.where(DatasetRowRecord.route_id == route)
        if flights is not None:
            if not flights: return []
            stmt = stmt.where(DatasetRowRecord.flight_id.in_(flights))
        return [json.loads(r) for r in session.scalars(stmt)]
    routes = {r["route_id"]: r for r in rows("航线目录")}
    flights = [f for f in rows("航班计划") if str(p.start) <= f["departure_at"][:10] <= str(p.end)]
    if not flights: raise ValueError("所选窗口没有模拟航班计划，请选择已导入的2026年10月出行窗口或补充数据")
    customers = rows("客户画像")
    cohort = {c["customer_id"]: c for c in customers if c.get("business_segment") == p.segment}
    events = [e for e in rows("搜索行为") if asof[:10] >= e["event_at"][:10] >= (p.as_of - timedelta(days=30)).isoformat(sep=" ")[:10]
        and e["event_at"] <= asof and str(p.start) <= e.get("departure_date", "") <= str(p.end)]
    intents = defaultdict(set)
    parties = {}
    for e in events:
        intents[e["route_id"]].add(e["customer_id"])
        if e.get("passenger_count", 0) >= 2: parties[e["customer_id"], e["route_id"]] = True
    score = Counter()
    for route in {f["route_id"] for f in flights}:
        score[route] = sum(c.get("preferred_route") == route or cid in intents[route] for cid, c in cohort.items())
    route_id = p.route_id or sorted(score, key=lambda r: (-score[r], r))[0]
    if route_id not in routes: raise ValueError("航线目录缺少所选航线")
    route = routes[route_id]
    def route_label(r):
        return r["origin_city"] + "—" + r["destination_city"] + "（" + r["origin"] + "→" + r["destination"] + "）"
    flight_list = [f for f in flights if f["route_id"] == route_id]
    if not flight_list: raise ValueError("该航线在所选窗口没有模拟航班计划")
    selected_ids = {f["flight_id"] for f in flight_list}
    p = p.model_copy(update={"route_id": route_id})
    scope = p.model_dump(mode="json")
    stage("scope", "出行窗口", "按历史观测时点回放，航班与营销数据均为模拟。", params=scope,
        controls={"routes": [{"value": r, "label": route_label(routes[r])} for r in sorted(score)], "segments": SEGMENTS, "channels": list(CHANNELS), "products": [{"value":pr["product_id"], "label":pr["product_name"]} for pr in rows("产品目录")]},
        metrics=[{"label": "出行窗口", "value": str(p.start) + " 至 " + str(p.end)}, {"label": "观测时点", "value": asof}, {"label": "画像客户", "value": len(customers)}])
    begin("demand", "计算需求与航线")
    stage("demand", "需求与航线", "画像偏好与近30天搜索取并集；这是候选需求，不是购买预测。",
        chart={"title": "候选需求人数", "labels": [route_label(routes[r]) for r in score], "values": list(score.values()), "unit": "人", "source": datasets["客户画像"].dataset_key + " + " + datasets["搜索行为"].dataset_key + "；同一客户可关注多航线"},
        evidence=["画像版本：" + profile_time, "仅使用观测时点之前的搜索；出行日期限定场景窗口", "当前航线：" + route["origin_city"] + "—" + route["destination_city"]])

    begin("audience", "校验客群资格")
    candidates = {cid: c for cid, c in cohort.items() if c.get("preferred_route") == route_id or cid in intents[route_id]}
    booked = {o["customer_id"] for o in rows("客票订单", flights=selected_ids)
        if o.get("issued_at") and o["issued_at"] <= asof and (not o.get("cancelled_at") or o["cancelled_at"] > asof)
        and (not o.get("refund_at") or o["refund_at"] > asof)}
    touches = Counter(t["customer_id"] for t in rows("触达回执") if t.get("delivered_at")
        and (p.as_of - timedelta(days=7)).isoformat(sep=" ") <= t["delivered_at"] <= asof)
    exclusions = Counter(); eligible = []
    for cid, c in candidates.items():
        reason = ("画像时点无效" if not c.get("profile_as_of") or c["profile_as_of"] > asof else
            "保护名单" if c.get("protected") != 0 else "渠道未授权" if c.get(CHANNELS[p.channel]) != 1 else
            "同航班已出票" if cid in booked else "达到7天频控上限" if touches[cid] >= p.frequency_7d else "")
        if reason: exclusions[reason] += 1
        else: eligible.append(cid)
    stage("audience", "客群资格", f"{len(candidates)}人候选，{len(eligible)}人通过本轮触达条件。",
        chart={"title": "客群筛选", "labels": ["候选客群", "通过触达校验", *exclusions], "values": [len(candidates), len(eligible), *exclusions.values()], "unit": "人", "source": "同一窗口、同一航线；排除按首个原因互斥计数，候选与通过人数不能相加"},
        checks=[{"name": k, "status": "已排除", "detail": str(v) + "人"} for k, v in exclusions.items()],
        evidence=[datasets[n].dataset_key for n in ("客户画像", "客票订单", "触达回执")])

    begin("supply", "校验航班与本体供给关系")
    # Traverse actual persisted typed relations, including fare and product versions.
    nodes = {}; links = []; adjacency = defaultdict(lambda: defaultdict(list))
    def load_nodes(external_ids):
        records = list(session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id,
            OntologyEntityRecord.external_id.in_(external_ids)))) if external_ids else []
        for n in records: nodes[n.id] = n
        return records
    flight_nodes = load_nodes([namespace + "-" + f for f in selected_ids])
    products = rows("产品目录")
    package_nodes = load_nodes([namespace + "-PP-" + pr["product_id"] for pr in products])
    frontier = [n.id for n in [*flight_nodes, *package_nodes]]
    for _ in range(3):
        if not frontier: break
        edges = list(session.scalars(select(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id,
            OntologyRelationRecord.source_entity_id.in_(frontier), OntologyRelationRecord.relation_type.in_(RELATIONS))))
        target_ids = {e.target_entity_id for e in edges}
        targets = list(session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id,
            OntologyEntityRecord.id.in_(target_ids)))) if target_ids else []
        new_ids = [n.id for n in targets if n.id not in nodes]
        nodes.update({n.id: n for n in targets})
        for e in edges:
            if e.relation_type == omitted_relation: continue
            a, b = nodes.get(e.source_entity_id), nodes.get(e.target_entity_id)
            if not a or not b or validate_relation_endpoints(e.relation_type, a.entity_type, b.entity_type): continue
            adjacency[a.id][e.relation_type].append(b.id); links.append(e)
        frontier = new_ids
    attrs = {n.id: json.loads(n.attributes_json) for n in nodes.values()}
    by_external = {n.external_id: n for n in nodes.values()}
    def targets(n, rel, kind):
        return [nodes[i] for i in adjacency[n.id][rel] if nodes[i].entity_type == kind]
    checks = []; good = []; path_examples = []; latest_inventory = []
    for f in flight_list:
        fn = by_external.get(namespace + "-" + f["flight_id"])
        if not fn or fn.entity_type != "Flight":
            checks.append({"name": f["flight_no"], "status": "阻断", "detail": "缺少Flight本体对象"}); continue
        rs = targets(fn, "operates_on", "Route")
        rnode = next((n for n in rs if attrs[n.id].get("route_id") == route_id), None)
        segments = targets(fn, "has_segment", "FlightSegment")
        sn = next((n for n in segments if attrs[n.id].get("flight_id") == f["flight_id"]), None)
        airports_ok = bool(rnode and sn and any(attrs[n.id].get("airport_code") == route["origin"] for n in targets(rnode, "departs_from", "Airport"))
            and any(attrs[n.id].get("airport_code") == route["destination"] for n in targets(rnode, "arrives_at", "Airport"))
            and any(attrs[n.id].get("airport_code") == route["origin"] for n in targets(sn, "departs_from", "Airport"))
            and any(attrs[n.id].get("airport_code") == route["destination"] for n in targets(sn, "arrives_at", "Airport")))
        fare_path = None
        for cabin in targets(fn, "has_cabin", "Cabin"):
            for fare in targets(cabin, "has_fare", "Fare"):
                a = attrs[fare.id]
                pp = targets(fare, "uses_product", "Product")
                if pp and a.get("captured_at") and a["captured_at"] <= asof and a.get("currency") == "CNY" and a.get("synthetic") is True:
                    fare_path = [fn, cabin, fare, pp[0]]; break
            if fare_path: break
        consistent = attrs[fn.id].get("wifi_supported") == f.get("wifi_supported") and attrs[fn.id].get("departure_at") == f["departure_at"]
        ok = bool(rnode and airports_ok and fare_path and consistent)
        if ok:
            good.append(f)
            if len(path_examples) < 2: path_examples.append(fare_path)
        else:
            reasons = [label for cond, label in [(rnode, "operates_on"), (airports_ok, "航段机场关系"), (fare_path, "有效票价产品链"), (consistent, "源数据与本体属性一致性")] if not cond]
            checks.append({"name": f["flight_no"] + " " + f["departure_at"][:10], "status": "阻断", "detail": "缺少或无效：" + "、".join(reasons)})
        metrics = [attrs[n.id] for n in targets(fn, "has_metric", "MetricObservation") if attrs[n.id].get("observed_at", "~") <= asof
            and attrs[n.id].get("flight_id") == f["flight_id"] and attrs[n.id].get("synthetic") is True]
        if ok and metrics: latest_inventory.append(max(metrics, key=lambda a: a["observed_at"]))
    available = sum(m.get("available_seats", 0) for m in latest_inventory)
    crawl = [r for r in rows("爬取单航段标准报价", route_id) if str(p.start) <= r.get("departure_at", "")[:10] <= str(p.end)]
    reference_quotes = sorted(crawl, key=lambda r:r.get("total_fare_yuan", 0))[:6]
    stage("supply", "航班与本体校验", f"{len(good)}/{len(flight_list)}个航班具备有效关联；其余停止组合。",
        metrics=[{"label": "关系链通过", "value": len(good)}, {"label": "链路阻断", "value": len(flight_list)-len(good)},
            {"label": "模拟可售座位", "value": available if len(latest_inventory) == len(good) and good else "未完整观测"}],
        table={"columns": ["航班", "出发日期", "Wi-Fi", "本体组合"], "rows": [[f["flight_no"], f["departure_at"][:10], {1:"支持",0:"不支持"}.get(f.get("wifi_supported"), "未知"), "通过" if f in good else "阻断"] for f in flight_list[:32]]},
        checks=checks[:12], reference={"columns":["爬取报价参考", "计划日期", "含税报价(CNY假设)", "时效"], "rows":[[r.get("marketing_flight_no"),r.get("departure_at", "")[:10],r.get("total_fare_yuan"),"抓取时间未知，待核验"] for r in reference_quotes]},
        evidence=["Flight→Route；Flight→FlightSegment→Airport；Flight→Cabin→Fare→Product",
            "库存仅取观测时点前最后一次模拟快照；不使用未来乘机标签；爬取报价不推算库存"])

    begin("ontology", "传播产品与行程约束")
    product_checks = []; qualified_products = []; graph_paths = []; product_audience_counts = {}
    for path in path_examples:
        graph_paths.append({"title": "票价产品证据", "nodes": [n.external_id for n in path], "relations": ["has_cabin", "has_fare", "uses_product"]})
        fn = path[0]
        rn = next(iter(targets(fn, "operates_on", "Route")), None)
        if rn:
            an = next(iter(targets(rn, "arrives_at", "Airport")), None)
            if an: graph_paths.append({"title": "目的地适用范围", "nodes": [fn.external_id, rn.external_id, an.external_id], "relations": ["operates_on", "arrives_at"]})
        metric_nodes = [n for n in targets(fn, "has_metric", "MetricObservation") if attrs[n.id].get("observed_at", "~") <= asof]
        if metric_nodes:
            mn = max(metric_nodes, key=lambda n: attrs[n.id]["observed_at"])
            graph_paths.append({"title": "观测时点前库存", "nodes": [fn.external_id, mn.external_id], "relations": ["has_metric"]})
    for pr in sorted(products, key=lambda pr:pr["product_id"] != p.product_id):
        pn = by_external.get(namespace + "-PP-" + pr["product_id"])
        anc = targets(pn, "includes_ancillary", "AncillaryProduct") if pn and pn.entity_type == "ProductPackage" else []
        an = next((n for n in anc if attrs[n.id].get("product_id") == pr["product_id"]), None)
        state, detail, count = "待核验", "产品上游可售、旅客及舱位资格尚未接入", len(good)
        if not an or not good: state, detail, count = "阻断", "缺少产品包→辅营或航班完整关系链", 0
        elif any(attrs[an.id].get(k) != pr.get(k) for k in ("valid_from", "valid_to", "eligibility")):
            state, detail, count = "阻断", "本体产品版本与源数据不一致", 0
        elif not (pr.get("valid_from", "~") <= str(p.start) and pr.get("valid_to", "") >= str(p.end)):
            state, detail, count = "排除", "产品有效期未覆盖出行窗口", 0
        elif pr["product_id"] == "P-WIFI":
            count = sum(f.get("wifi_supported") == 1 for f in good)
            state, detail = ("候选", f"仅{count}个支持Wi-Fi航班可匹配；未知与不支持排除") if count else ("排除", "没有已标记支持Wi-Fi的航班")
        elif pr["product_id"] == "P-PICKUP":
            state, detail, count = ("候选", "本体到达机场匹配模拟接送范围，待上游核验", len(good)) if route["destination"] in {"SYX", "KMG"} else ("排除", "本体到达机场不在产品适用范围", 0)
        elif pr["product_id"] == "P-FAMILY":
            family_count = sum(bool(parties.get((cid, route_id))) for cid in eligible)
            product_audience_counts[pr["product_id"]] = family_count
            state, detail = ("候选", f"{family_count}人存在2人以上同行搜索证据，出票时需再核验") if family_count else ("待核验", "家庭标签不能证明同行≥2人，需补充行程人数")
        elif pr["product_id"] == "P-MILES":
            tier_count = sum(candidates[cid].get("member_tier") in {"普通", "银卡"} for cid in eligible)
            product_audience_counts[pr["product_id"]] = tier_count
            state, detail = ("候选", f"{tier_count}人会员等级符合模拟条件，待产品版本核验") if tier_count else ("排除", "没有普通或银卡客户")
        if count and state in {"候选", "待核验"}: qualified_products.append(pr)
        product_checks.append({"name": pr["product_name"], "status": state, "detail": detail, "flights": count})
        if an and len(graph_paths) < 8:
            graph_paths.append({"title": pr["product_name"] + "产品版本", "nodes": [pn.external_id, an.external_id], "relations": ["includes_ancillary"]})
    graph_ids = {i for path in graph_paths for i in path["nodes"]}
    graph_nodes = [{"id": n.external_id, "type": n.entity_type, "label": n.label,
        "source": n.source, "dataset": attrs[n.id].get("dataset_key", "业务投影"), "record": attrs[n.id].get("record_key", n.external_id),
        "facts": {k: v for k,v in attrs[n.id].items() if k in {"wifi_supported", "valid_from", "valid_to", "eligibility", "captured_at", "observed_at", "available_seats", "total_fare_yuan", "currency", "sellability_status", "source_product_code", "airport_code", "departure_at"}}}
        for n in nodes.values() if n.external_id in graph_ids]
    selected_product = next((pr for pr in qualified_products if pr["product_id"] == p.product_id), None)
    all_pass = bool(good and eligible and selected_product)
    stage("ontology", "关系约束与证据", "建议必须经过类型、关系、有效期和资格校验；未知条件保留待核验。",
        params=scope, checks=product_checks, graph={"nodes": graph_nodes, "paths": graph_paths},
        comparison=[{"relation": "operates_on", "with": f"{len(good)}个航班具备完整关系链", "without": "移除全部航线归属边：0个航班通过，不生成触达方案"},
            {"relation": "uses_product", "with": f"{len(good)}个航班可追溯票价产品版本", "without": "移除全部票价产品边：0个航班通过，不生成触达方案"},
            {"relation": "includes_ancillary", "with": f"{len(qualified_products)}项权益进入候选核验", "without": "移除全部辅营包含边：0项权益可组合，不生成触达方案"}],
        evidence=["以上图谱来自后台存量关系，不是模型生成的关系", "类型约束统一跨表含义；多跳关系传播适用条件；任一关键边缺失即停止组合",
            "SQL或规则系统也可实现，但需逐个重建关联、语义约束与证据追踪。本平台统一由本体承担"])

    begin("plan", "编排活动与内容草稿")
    # Budget is a transparent assumption, not an inferred historic cost or ROI.
    unit_cost = {"App": 0.10, "短信": 0.30, "微信": 0.08}[p.channel]
    product_audience = product_audience_counts.get(selected_product["product_id"], len(eligible)) if selected_product else 0
    planned = min(product_audience, math.floor(p.budget_yuan / unit_cost)) if all_pass else 0
    planned_cost = round(planned * unit_cost, 2)
    title = "假期出行 · " + route["origin_city"] + "—" + route["destination_city"]
    content = {"title": title, "body": f"{p.start:%m月%d日}至{p.end:%m月%d日}，关注{route['origin_city']}至{route['destination_city']}出行计划。"
        + (f"可了解{selected_product['product_name']}，适用资格、余量与最终价格以预订页核验为准。" if selected_product else "产品资格确认后提供出行权益。")}
    proposal = dict(name=f"{p.start}假期-{route['origin_city']}{route['destination_city']}-{p.segment}",
        audience_size=planned, budget_yuan=p.budget_yuan, channels=[p.channel], product=selected_product["product_name"] if selected_product else "",
        content=content, status="候选草稿" if all_pass and planned else "阻断", planned_cost_yuan=planned_cost)
    stage("plan", "活动方案", "生成候选方案，保存草稿后进入平台审批流程。", params=scope, proposal=proposal,
        metrics=[{"label": "触达条件通过", "value": len(eligible)}, {"label": "产品候选上限", "value": product_audience}, {"label": "计划触达", "value": planned}, {"label": "触达成本假设", "value": str(unit_cost) + "元/次"}, {"label": "预估触达开销", "value": str(planned_cost) + "元"}],
        table={"columns": ["节点", "动作", "条件"], "rows": [["T-7", "意向客户提醒", "授权、保护名单、频控通过"], ["T-3", "对未出票者复查", "重新查票、库存、产品版本；本轮不自动二次发送"], ["出行后", "效果回收", "渠道回执和实际订单关联后复盘"]]},
        evidence=["预算仅约束本轮一次触达；不包含优惠补贴与权益采购", "产品均为模拟候选，未形成可售承诺；未发送渠道消息"],
        actions=[{"label": "保存活动草稿", "kind": "draft"}] if planned else [])

    begin("measurement", "计算历史实验评估口径")
    experiment = [r for r in rows("营销增量实验样本") if r.get("label_complete") == 1 and r.get("outcome_window_end", "~") <= asof]
    arms = {}
    for arm in (0, 1):
        group = [r for r in experiment if r.get("treatment") == arm]
        arms[arm] = dict(n=len(group), issued=sum(r.get("outcome_issued_7d", 0) for r in group))
    rates = [round(100 * arms[a]["issued"] / arms[a]["n"], 3) if arms[a]["n"] else 0 for a in (0, 1)]
    delta = round(rates[1] - rates[0], 3) if all(arms[a]["n"] for a in (0,1)) else None
    used.update(n for n in ("机场目录", "模拟航班报价_爬取结构", "航班库存与预测样本") if n in datasets)
    source_manifest = [{"name": n, "dataset": datasets[n].dataset_key, "rows": datasets[n].row_count, "mode": datasets[n].data_mode, "source": datasets[n].source} for n in sorted(used)]
    stage("measurement", "效果与复盘", "当前活动尚未执行；历史实验仅作为评估方法参考。",
        chart={"title": "历史随机实验7日出票率", "labels": ["对照组", "干预组"], "values": rates, "unit": "%", "source": "完整结果窗口的随机分组ITT；模拟历史，不代表本活动预期效果"},
        table={"columns": ["分组", "分配人数", "出票人数"], "rows": [["对照组", arms[0]["n"], arms[0]["issued"]], ["干预组", arms[1]["n"], arms[1]["issued"]]]},
        metrics=[{"label": "历史差值", "value": (str(delta) + "个百分点") if delta is not None else "缺少成熟标签"}, {"label": "本次ROI", "value": "待执行与成本回收"}],
        evidence=["历史差值不是本次效果预测；样本不足与显著性需另行检验", "触达、点击、订单、退款按活动版本回收；净实付不等同利润", "建议随机留出对照组，按分配组测量增量而非只看已送达者"], sources=source_manifest)
    fingerprint = hashlib.sha256(json.dumps({"params":scope, "proposal":proposal, "checks":product_checks, "flights":checks}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return dict(params=scope, proposal=proposal, ready=bool(planned), fingerprint=fingerprint,
        rule_summary=product_checks, eligible_count=len(eligible), graph_node_count=len(graph_nodes), sources=source_manifest,
        qualified_flights=len(good), qualified_products=len(qualified_products),
        selected_product_id=selected_product["product_id"] if selected_product else None, cards=cards)


@router.post("/analyze")
def analyze_endpoint(payload: HolidayParameters, context=Depends(get_tenant_context), session=Depends(get_session)):
    try: return analyze_holiday(session, context.tenant_id, payload)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


class OntologyComparison(BaseModel):
    params: HolidayParameters
    relation: str


@router.post("/compare")
def compare_endpoint(payload: OntologyComparison, context=Depends(get_tenant_context), session=Depends(get_session)):
    if payload.relation not in {"operates_on", "uses_product", "includes_ancillary"}:
        raise HTTPException(422, "不支持该关系对照")
    try:
        baseline = analyze_holiday(session, context.tenant_id, payload.params)
        omitted = analyze_holiday(session, context.tenant_id, payload.params, omitted_relation=payload.relation)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    fields = ["qualified_flights", "qualified_products", "ready"]
    return {"relation": payload.relation, "baseline": {k:baseline[k] for k in fields}, "omitted": {k:omitted[k] for k in fields},
        "summary": "后台重新计算时忽略选中关系；原始本体未修改", "checks": omitted["rule_summary"]}


def prepare_draft_task(session, context, conversation_id, params):
    from .assistant_store import task_view, scoped_conversation
    from .db_models import AssistantTaskRecord
    if context.role not in {"admin", "manager", "analyst"}: raise HTTPException(403, "当前角色不能创建活动草稿")
    scoped_conversation(session, context, conversation_id)
    body = HolidayParameters(**params).model_dump_json()
    item = session.scalar(select(AssistantTaskRecord).where(AssistantTaskRecord.tenant_id == context.tenant_id,
        AssistantTaskRecord.user_id == context.user_id, AssistantTaskRecord.conversation_id == conversation_id,
        AssistantTaskRecord.path == "/api/holiday-marketing/drafts", AssistantTaskRecord.payload_json == body,
        AssistantTaskRecord.status.in_(["pending_confirmation", "running", "completed"])))
    if item is None:
        item = AssistantTaskRecord(id="TASK-"+uuid4().hex[:20], tenant_id=context.tenant_id, user_id=context.user_id,
            conversation_id=conversation_id, title="保存假期营销活动、客群与内容草稿", method="POST", path="/api/holiday-marketing/drafts", payload_json=body)
        session.add(item); session.commit()
    return task_view(item)


@router.post("/drafts", status_code=201)
def save_draft(payload: HolidayParameters, context=Depends(require_write), session=Depends(get_session)):
    # Re-run all gates at confirmation time. Never trust client-provided totals.
    try: report = analyze_holiday(session, context.tenant_id, payload)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    if not report["ready"]: raise HTTPException(409, "本体关联、客群资格或预算未通过，不能保存活动方案")
    from .ontology.projection import sync_business_graph, put_entity, put_relation
    from .db_models import CampaignRecord, CampaignVersionRecord
    prefix = "HOL-" + uuid4().hex[:12]
    product_dataset = next(s["dataset"] for s in report["sources"] if s["name"] == "产品目录")
    namespace = product_dataset.rsplit("-", 1)[0]
    selected = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == context.tenant_id,
        ProductPackageRecord.external_id == namespace + "-PP-" + report["selected_product_id"]))
    if not selected: raise HTTPException(409, "本体产品缺少平台产品包映射")
    expression = dict(type="holiday-eligibility", params=report["params"], counting_unit="去重客户",
        rules=["画像时点", "航线偏好或近30天搜索", "保护名单", "渠道授权", "同航班出票排除", "7天频控", "产品资格", "预算"],
        product_id=report["selected_product_id"],
        source_datasets=report["sources"], fingerprint=report["fingerprint"], synthetic=True)
    audience = AudiencePackageRecord(tenant_id=context.tenant_id, external_id=prefix, name=report["proposal"]["name"] + "客群",
        selection_mode="expression", expression_json=json.dumps(expression, ensure_ascii=False), estimated_size=report["proposal"]["audience_size"], status="已冻结", created_by=context.user_id)
    session.add(audience); session.flush()
    snapshot = AudienceSnapshotRecord(tenant_id=context.tenant_id, package_id=audience.id, external_id=prefix+"-V1",
        estimated_size=audience.estimated_size, expression_json=audience.expression_json, source="holiday-planner:模拟", created_by=context.user_id)
    session.add(snapshot); session.flush()
    campaign = CampaignRecord(tenant_id=context.tenant_id, id="ACT-"+prefix, name=report["proposal"]["name"] + " " + prefix[-6:],
        stage="机会", status="草稿", version="V1", owner=context.display_name, audience_size=audience.estimated_size,
        product_package=selected.name, budget_yuan=payload.budget_yuan, roi_target=0)
    session.add(campaign); session.flush()
    content = ContentAssetRecord(tenant_id=context.tenant_id, external_id=prefix+"-CONTENT", campaign_id=campaign.id,
        product_package_id=selected.id, name=report["proposal"]["content"]["title"], title=report["proposal"]["content"]["title"],
        body=report["proposal"]["content"]["body"], channel=payload.channel, version="V1", status="草稿",
        generated_by="holiday-evidence-planner", generation_context_json=json.dumps(expression, ensure_ascii=False), created_by=context.user_id)
    session.add(content); session.flush()
    version = CampaignVersionRecord(tenant_id=context.tenant_id, campaign_id=campaign.id, external_id=campaign.id+"-V1", version="V1",
        audience_snapshot_id=snapshot.id, product_package_id=selected.id, content_asset_ids_json=json.dumps([content.id]),
        budget_yuan=payload.budget_yuan, channels_json=json.dumps([payload.channel], ensure_ascii=False), status="草稿", created_by=context.user_id)
    session.add(version); session.flush()
    sync_business_graph(session, context.tenant_id)
    cn = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.external_id == campaign.id))
    recommendation = put_entity(session, context.tenant_id, prefix+"-REC", "Recommendation", "假期营销候选方案",
        dict(synthetic=True, params=report["params"], fingerprint=report["fingerprint"], status="草稿待核验",
            public_checks=report["rule_summary"], proposal=report["proposal"]), source="holiday-evidence-planner")
    evidence = put_entity(session, context.tenant_id, prefix+"-EVIDENCE", "Evidence", "假期营销观测与规则证据",
        dict(synthetic=True, source_datasets=report["sources"], as_of=report["params"]["as_of"], fingerprint=report["fingerprint"],
            paths=next(c["graph"]["paths"] for c in report["cards"] if c["id"] == "holiday-ontology")), source="holiday-evidence-planner")
    put_relation(session, context.tenant_id, recommendation, "supports_campaign", cn, "候选方案保存为活动草稿")
    put_relation(session, context.tenant_id, recommendation, "has_evidence", evidence, "观测、公开检查和关系路径")
    session.commit()
    return {"campaign_id": campaign.id, "audience_snapshot_id": snapshot.id, "content_asset_id": content.id,
        "summary": "活动、冻结客群、内容草稿与本体关系已保存，待产品核验和人工审批", "fingerprint": report["fingerprint"]}
