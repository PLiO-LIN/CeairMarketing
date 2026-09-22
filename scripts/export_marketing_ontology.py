"""Export the registry and a read-only SQLite ontology snapshot as OWL/RDF XML.

Run from the repo root: python scripts/export_marketing_ontology.py
Requires rdflib. This script does not import the API app or initialize a database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef
from rdflib.collection import Collection
from rdflib.compare import isomorphic

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://ceair.example/ontology/marketing/"
ONT = URIRef(BASE.rstrip("/"))
C = Namespace(BASE + "class/")
P = Namespace(BASE + "relation/")
D = Namespace(BASE + "attribute/")
M = Namespace(BASE + "metadata/")
I = Namespace(BASE + "instance/")
EXPORT_VERSION = "v1.0"
CN_NAMES = {
    "ProductLabel": "产品标签", "ProductGroup": "产品分组",
    "FlightSegment": "航段", "Cabin": "舱位", "Fare": "运价",
    "AncillaryProduct": "辅营产品",
}
AGENT_NAMES = {
    "opportunity-insight": "机会洞察智能域", "audience-insight": "客群洞察智能域",
    "product-match": "产品匹配智能域", "activity-orchestration": "活动编排智能域",
    "content-generation": "内容生成智能域", "effect-analysis": "效果分析智能域",
}
ATTR_NAMES = {
    "id": "标识", "name": "名称", "status": "状态", "source": "来源",
    "confidence": "置信度", "description": "描述", "type": "类型",
    "price": "价格", "budget": "预算", "version": "版本", "rules": "规则",
    "flight_no": "航班号", "flight_date": "航班日期", "route_code": "航线编码",
    "origin": "出发地", "destination": "目的地", "valid_from": "生效时间",
    "valid_to": "失效时间", "created_at": "创建时间", "updated_at": "更新时间",
    "content": "内容", "title": "标题", "source_name": "来源名称",
    "product_code": "产品编码", "total_price": "总价", "pipeline_status": "处理状态",
}
META_LABELS = {
    "module": "所属业务模块", "registryId": "注册编码", "registryName": "原始名称",
    "schemaStatus": "定义来源", "declaresAttribute": "声明属性", "fieldName": "原始字段名",
    "tenantId": "租户标识", "tenantName": "租户名称", "rowId": "数据库行标识",
    "externalId": "外部稳定标识", "entityType": "原始对象类型", "source": "数据来源",
    "confidence": "置信度", "importJobId": "导入任务标识", "updatedAt": "原始更新时间",
    "createdAt": "原始创建时间", "rawAttributesJson": "完整原始属性 JSON",
    "rawEntityRecordJson": "完整实体记录 JSON", "rawRelationRecordJson": "完整关系记录 JSON",
    "evidence": "关系证据", "exportVersion": "导出版本", "semanticModelVersion": "语义模型版本",
    "exportedAt": "导出时间", "databasePath": "本地数据源相对路径", "scope": "导出范围",
    "tenantManifestJson": "租户清单", "actionDefinition": "动作声明 JSON",
    "functionDefinition": "函数声明 JSON", "agentContract": "智能域契约 JSON",
    "principle": "设计原则", "lifecycleJson": "生命周期阶段",
    "readByAgent": "读取此类的智能域", "writtenByAgent": "写入此类的智能域",
    "registryJson": "完整语义注册表 JSON", "warning": "导出检查提示",
    "unassertedRelationJson": "未形成断言的关系原始记录", "valueEncoding": "值编码方式",
}
BUSINESS_TABLES = [
    "campaigns", "campaign_versions", "marketing_opportunities", "audience_packages",
    "audience_snapshots", "audience_tags", "product_packages", "content_assets",
    "approval_tasks", "execution_batches", "knowledge_documents", "knowledge_chunks",
    "market_hotspots", "data_pipeline_jobs",
]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(value):
    """Keep registry names readable while providing legal RDF/XML predicate names."""
    value = str(value)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", value):
        return "escaped_" + value.encode("utf-8").hex() if value.startswith("escaped_") else value
    return "escaped_" + value.encode("utf-8").hex()


def class_uri(name):
    return C[identifier(name)]


def attribute_uri(kind, name):
    return D[identifier(kind) + "/" + identifier(name)]


def instance_uri(row):
    return I[str(row["tenant_id"]) + "/" + quote(str(row["external_id"]), safe="")]


def load_model(path=None):
    path = path or ROOT / "services/platform-api/app/ontology/semantic_model.py"
    spec = importlib.util.spec_from_file_location("ceair_owl_export_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.semantic_model()


def read_snapshot(path):
    path = path.resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("tenants", "ontology_entities", "ontology_relations"):
            if required not in tables:
                raise ValueError(f"Missing required table: {required}")
        data = {key: [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                for key, table in [("tenants", "tenants"), ("entities", "ontology_entities"),
                                   ("relations", "ontology_relations")]}
        data["business_counts"] = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                                   for t in BUSINESS_TABLES if t in tables}
        conn.rollback()
    data["database_path"] = str(path)
    return data


def union_class(graph, names):
    values = [class_uri(v) for v in names]
    if len(values) == 1:
        return values[0]
    node, head = BNode(), BNode()
    graph.add((node, RDF.type, OWL.Class))
    graph.add((node, OWL.unionOf, head))
    Collection(graph, head, values)
    return node


def build_graph(model, snapshot, exported_at=None, export_version=EXPORT_VERSION):
    g = Graph()
    for prefix, ns in [("owl", OWL), ("rdf", RDF), ("rdfs", RDFS), ("xsd", XSD),
                       ("ce", C), ("rel", P), ("attr", D), ("meta", M), ("inst", I)]:
        g.bind(prefix, ns)
    warnings, extensions, null_fields, complex_fields = [], [], 0, 0
    types = {item["id"]: item for item in model["object_types"]}
    relation_defs = {item["id"]: item for item in model["relation_types"]}
    names = {k: CN_NAMES.get(k, v["name"]) for k, v in types.items()}
    for key, label in META_LABELS.items():
        g.add((M[key], RDF.type, OWL.AnnotationProperty))
        g.add((M[key], RDFS.label, Literal(label, lang="zh")))
    g.add((ONT, RDF.type, OWL.Ontology))
    g.add((ONT, RDFS.label, Literal("东方航空营销本体与实例 " + export_version, lang="zh")))
    g.add((ONT, OWL.versionInfo, Literal(export_version)))
    g.add((ONT, OWL.versionIRI, URIRef(BASE + "export/" + export_version)))
    g.add((ONT, M.exportVersion, Literal(export_version)))
    g.add((ONT, M.semanticModelVersion, Literal(model["version"])))
    stamp = exported_at or datetime.now().astimezone().isoformat(timespec="seconds")
    g.add((ONT, M.exportedAt, Literal(stamp, datatype=XSD.dateTime)))
    db_path = Path(snapshot.get("database_path", "local.db"))
    try:
        db_label = db_path.relative_to(ROOT).as_posix()
    except ValueError:
        db_label = db_path.name
    g.add((ONT, M.databasePath, Literal(db_label)))
    g.add((ONT, M.scope, Literal("本地数据库全部租户的 ontology_entities 与 ontology_relations；不包含线上数据库或未投影的业务记录。", lang="zh")))
    g.add((ONT, RDFS.comment, Literal("离线评审快照。IRI 使用保留示例域名，仅作标识，不要求联网。动作、函数及智能域契约为注释，不是可执行 OWL 推理规则。属性原定义不含严格数据类型、必填或基数约束，因此不擅自添加。", lang="zh")))
    tenant_names = {t["id"]: t["name"] for t in snapshot["tenants"]}
    g.add((ONT, M.tenantManifestJson, Literal(json_text(snapshot["tenants"]))))
    g.add((ONT, M.registryJson, Literal(json_text(model))))
    g.add((ONT, M.lifecycleJson, Literal(json_text(model.get("lifecycle", [])))))
    for principle in model.get("principles", []):
        g.add((ONT, M.principle, Literal(principle, lang="zh")))
    for key, predicate in [("actions", M.actionDefinition), ("functions", M.functionDefinition)]:
        for item in model.get(key, []):
            g.add((ONT, predicate, Literal(json_text(item))))
    for domain, contract in model.get("agent_contracts", {}).items():
        g.add((ONT, M.agentContract, Literal(json_text({"id": domain, "name": AGENT_NAMES.get(domain, domain), **contract}))))
        for key, pred in [("reads", M.readByAgent), ("writes", M.writtenByAgent)]:
            for kind in contract.get(key, []):
                g.add((class_uri(kind), pred, Literal(domain)))

    def declare_type(kind):
        node = class_uri(kind)
        if (node, RDF.type, OWL.Class) in g:
            return
        definition = types.get(kind)
        g.add((node, RDF.type, OWL.Class))
        g.add((node, RDFS.label, Literal(names.get(kind, kind), lang="zh" if kind in names else None)))
        g.add((node, M.registryId, Literal(kind)))
        if definition:
            g.add((node, M.registryName, Literal(definition["name"])))
            g.add((node, RDFS.comment, Literal(definition.get("description", ""))))
            g.add((node, M.module, Literal(definition.get("module", ""))))
            g.add((node, M.schemaStatus, Literal("registered")))
        else:
            g.add((node, M.schemaStatus, Literal("observed-unregistered")))
            warnings.append({"code": "unregistered_type", "entity_type": kind})

    def declare_attribute(kind, field, declared):
        prop = attribute_uri(kind, field)
        if (prop, RDF.type, OWL.DatatypeProperty) in g:
            return prop
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        label = f"{ATTR_NAMES.get(field, field)}（{names.get(kind, kind)}）"
        g.add((prop, RDFS.label, Literal(label, lang="zh")))
        g.add((prop, RDFS.domain, class_uri(kind)))
        g.add((prop, RDFS.range, RDFS.Literal))
        g.add((prop, M.fieldName, Literal(field)))
        g.add((prop, M.schemaStatus, Literal("registered" if declared else "observed-extension")))
        g.add((class_uri(kind), M.declaresAttribute, prop))
        if not declared:
            extensions.append({"entity_type": kind, "attribute": field})
        return prop

    for kind, definition in types.items():
        declare_type(kind)
        for field in definition["attributes"]:
            declare_attribute(kind, field, True)
    for definition in model["relation_types"]:
        prop = P[identifier(definition["id"])]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(definition["name"], lang="zh")))
        g.add((prop, M.registryId, Literal(definition["id"])))
        g.add((prop, M.schemaStatus, Literal("registered")))
        for key, predicate in [("from_types", RDFS.domain), ("to_types", RDFS.range)]:
            if definition.get(key):
                g.add((prop, predicate, union_class(g, definition[key])))
    by_id = {}
    for row in snapshot["entities"]:
        key = (row["tenant_id"], row["id"])
        if key in by_id:
            raise ValueError(f"Duplicate entity row: {key}")
        by_id[key] = row
        node = instance_uri(row)
        if (node, RDF.type, OWL.NamedIndividual) in g:
            raise ValueError("Duplicate external ID within one tenant")
        kind = row["entity_type"]
        declare_type(kind)
        g.add((node, RDF.type, OWL.NamedIndividual))
        g.add((node, RDF.type, class_uri(kind)))
        g.add((node, RDFS.label, Literal(row["label"])))
        g.add((node, M.rawEntityRecordJson, Literal(json_text(row))))
        g.add((node, M.rawAttributesJson, Literal(row.get("attributes_json") or "{}")))
        for key, target in [("id", "rowId"), ("tenant_id", "tenantId"), ("external_id", "externalId"),
                            ("entity_type", "entityType"), ("source", "source"), ("confidence", "confidence"),
                            ("import_job_id", "importJobId"), ("updated_at", "updatedAt")]:
            if row.get(key) is not None:
                g.add((node, M[target], Literal(row[key])))
        g.add((node, M.tenantName, Literal(tenant_names.get(row["tenant_id"], str(row["tenant_id"])))))
        try:
            attrs = json.loads(row.get("attributes_json") or "{}")
        except (ValueError, TypeError):
            attrs = None
        if not isinstance(attrs, dict):
            warnings.append({"code": "invalid_attributes_json", "entity_id": row["id"]})
            continue
        for field, value in attrs.items():
            prop = declare_attribute(kind, field, field in types.get(kind, {}).get("attributes", []))
            if value is None:
                null_fields += 1
                continue
            if isinstance(value, (dict, list)):
                complex_fields += 1
                literal = Literal(json_text(value), datatype=XSD.string)
                g.add((prop, M.valueEncoding, Literal("JSON values retained as xsd:string; see rawAttributesJson")))
            else:
                literal = Literal(value)
            g.add((node, prop, literal))

    asserted, rejected, distinct_edges = 0, 0, set()
    for row in snapshot["relations"]:
        source = by_id.get((row["tenant_id"], row["source_entity_id"]))
        target = by_id.get((row["tenant_id"], row["target_entity_id"]))
        if source is None or target is None:
            warnings.append({"code": "missing_or_cross_tenant_endpoint", "relation_id": row["id"]})
            g.add((ONT, M.unassertedRelationJson, Literal(json_text(row))))
            rejected += 1
            continue
        kind = row["relation_type"]
        prop = P[identifier(kind)]
        definition = relation_defs.get(kind)
        if definition is None:
            if (prop, RDF.type, OWL.ObjectProperty) not in g:
                g.add((prop, RDF.type, OWL.ObjectProperty))
                g.add((prop, RDFS.label, Literal(kind)))
                g.add((prop, M.registryId, Literal(kind)))
                g.add((prop, M.schemaStatus, Literal("observed-unregistered")))
                warnings.append({"code": "unregistered_relation", "relation_type": kind})
        elif source["entity_type"] not in definition["from_types"] or target["entity_type"] not in definition["to_types"]:
            warnings.append({"code": "endpoint_type_mismatch", "relation_id": row["id"], "relation_type": kind,
                             "source_type": source["entity_type"], "target_type": target["entity_type"]})
        triple = (instance_uri(source), prop, instance_uri(target))
        g.add(triple)
        distinct_edges.add(triple)
        axiom = BNode(f"assertion-{row['tenant_id']}-{row['id']}")
        g.add((axiom, RDF.type, OWL.Axiom))
        g.add((axiom, OWL.annotatedSource, triple[0]))
        g.add((axiom, OWL.annotatedProperty, prop))
        g.add((axiom, OWL.annotatedTarget, triple[2]))
        g.add((axiom, M.rawRelationRecordJson, Literal(json_text(row))))
        for key, target_key in [("id", "rowId"), ("tenant_id", "tenantId"), ("evidence", "evidence"),
                                ("source", "source"), ("confidence", "confidence"),
                                ("import_job_id", "importJobId"), ("created_at", "createdAt")]:
            if row.get(key) is not None:
                g.add((axiom, M[target_key], Literal(row[key])))
        asserted += 1
    for warning in warnings:
        g.add((ONT, M.warning, Literal(json_text(warning))))
    summary = {
        "export_version": export_version, "semantic_model_version": model["version"], "exported_at": stamp,
        "database_path": db_label, "tenant_count": len(snapshot["tenants"]),
        "tenants": [{"id": t["id"], "name": t["name"]} for t in snapshot["tenants"]],
        "registered_class_count": len(types), "registered_relation_count": len(relation_defs),
        "registered_attribute_count": sum(len(x["attributes"]) for x in types.values()),
        "owl_named_class_count": sum(isinstance(x, URIRef) for x in g.subjects(RDF.type, OWL.Class)),
        "owl_object_property_count": len(set(g.subjects(RDF.type, OWL.ObjectProperty))),
        "owl_data_property_count": len(set(g.subjects(RDF.type, OWL.DatatypeProperty))),
        "entity_count": len(snapshot["entities"]), "relation_row_count": len(snapshot["relations"]),
        "asserted_relation_row_count": asserted, "distinct_relation_assertion_count": len(distinct_edges),
        "unasserted_relation_row_count": rejected, "null_attribute_values_in_raw_json": null_fields,
        "json_encoded_attribute_values": complex_fields, "triple_count": len(g),
        "action_count": len(model.get("actions", [])), "function_count": len(model.get("functions", [])),
        "agent_contract_count": len(model.get("agent_contracts", {})),
        "instance_type_counts": dict(sorted(Counter(x["entity_type"] for x in snapshot["entities"]).items())),
        "observed_attribute_extensions": extensions, "warnings": warnings,
        "business_table_counts_not_directly_exported": snapshot.get("business_counts", {}),
        "entity_inventory": [{k: r[k] for k in ("id", "tenant_id", "external_id", "entity_type", "label", "source")}
                             for r in snapshot["entities"]],
    }
    return g, summary


def write_report(path, output, model, summary):
    names = {x["id"]: CN_NAMES.get(x["id"], x["name"]) for x in model["object_types"]}
    s = summary
    lines = [
        "# 东方航空营销本体与实例导出说明 " + s["export_version"], "", f"导出时间：{s['exported_at']}", "",
        f"主文件：{output.name}", "", "## 导出范围", "",
        f"本次导出当前本地数据库 \x60{s['database_path']}\x60 中所有租户的本体实体与关系，以及当前代码语义注册表。未访问服务器，未混入测试数据库，也没有新造实例。",
        "本次只读取数据，没有回写数据库。账号、密码、模型 API Key、会话信息等表不在导出范围中。",
        "本地现有实例的关系证据包含 fixture-flight-products，属于已有的航班产品样例；不是全部线上经营数据。",
        "", "## 数量", "", "| 项目 | 数量 |", "| --- | --- |",
        f"| 租户 | {s['tenant_count']} |", f"| 已注册业务类 | {s['registered_class_count']} |",
        f"| 已注册关系类型 | {s['registered_relation_count']} |",
        f"| 已注册的类属性（按类分别定义） | {s['registered_attribute_count']} |",
        f"| 实例中的扩展属性（按类去重） | {len(s['observed_attribute_extensions'])} |",
        f"| OWL 数据属性总数 | {s['owl_data_property_count']} |",
        f"| 业务实例 | {s['entity_count']} |", f"| 数据库关系记录 | {s['relation_row_count']} |",
        f"| 独立关系断言 | {s['distinct_relation_assertion_count']} |",
        f"| 动作 / 函数 / 智能域契约声明 | {s['action_count']} / {s['function_count']} / {s['agent_contract_count']} |",
        f"| RDF 三元组 | {s['triple_count']} |", f"| 导出校验提示 | {len(s['warnings'])} |",
        "", "## 在本体编辑器中如何查看", "",
        "用支持 OWL RDF/XML 的编辑器打开主文件即可，例如 Protege。不需要启动平台或访问 IRI 对应的网站。",
        "1. Classes：查看全部业务类及中文名称；某些类当前没有实例，仍保留完整定义。",
        "2. Object properties：查看关系名称及 Domain/Range；多个允许类型使用 unionOf 并集。",
        "3. Data properties：查看每类对象的属性；同名字段按对象类型分别定义，避免错误混用领域。",
        "4. Individuals：查看实际实例及其数据属性、对象关系。原数据库中的英文实例名称保持原样。",
        "5. Annotations：查看来源、租户、置信度、任务标识、原始 JSON 和更新时间；关系证据保存在 OWL 断言注释中。",
        "6. Ontology annotations：查看 actionDefinition、functionDefinition、agentContract 和完整 registryJson。",
        "", "## 映射和边界", "",
        "- 对象类型导出为 owl:Class，关系导出为 owl:ObjectProperty，属性导出为 owl:DatatypeProperty，实际实例导出为 owl:NamedIndividual。",
        "- 实例 IRI 包含租户 ID 和 external_id，不会合并不同租户的同名对象。OWL 文件本身没有平台访问控制，请按内部资料管理。",
        "- 不额外创造类继承、互斥、唯一性、必填、逆关系、传递性或基数约束；当前注册表没有定义这些 OWL 公理。",
        "- Domain/Range 用于 OWL 推理，不等同于闭世界数据校验。此导出不意味着已经完成 DL 一致性推理或 SHACL 校验。",
        "- 属性定义未声明强类型，所以 Range 为 rdfs:Literal；实际数值、布尔值按 JSON 原类型写入。日期字符串不猜测时区。",
        "- 嵌套对象、数组保持 JSON 字符串，不擅自拆成新实体；null 不生成虚假数值，完整原始值保存在 rawAttributesJson。",
        "- 同一关系有多条来源记录时，关系断言按 RDF 去重，各记录的来源、证据和置信度分别保留为 owl:Axiom 注释。",
        "- 只有属性里出现对象 ID，不等于数据库已有明确关系；不推测补边，也不把所有业务表自动转换成本体。",
        "- 实例中出现的未注册属性会作为 observed-extension 保留，不能误认为已完成标准化建模。",
        "- 动作、函数、智能域契约作为注释保留，而不是伪装成可执行规则或额外业务实例。",
        "- RDF/XML 序列化完成后会重新解析并验证图同构，检查序列化没有丢失三元组。",
        "", "## 当前实例清单", "", "| 租户 | 类型 | 实例名称 | external_id |", "| --- | --- | --- | --- |",
    ]
    for row in s["entity_inventory"]:
        label = str(row["label"]).replace("|", " / ").replace("\n", " ")
        lines.append(f"| {row['tenant_id']} | {names.get(row['entity_type'], row['entity_type'])} | {label} | {row['external_id']} |")
    lines += ["", "## 没有实例的业务类", "", "、".join(names[k] + f"（{k}）" for k in names if k not in s["instance_type_counts"]),
              "", "这些类已经定义，但当前本地图谱表没有对应实例，因此没有伪造个体来填满全流程。",
              "", "## 导出检查提示", ""]
    if s["warnings"]:
        lines.extend("- " + json_text(x) for x in s["warnings"])
    else:
        lines.append("未发现关系端点缺失、跨租户引用、未注册类型或关系端点类型不符。")
    lines += ["", "## 业务表范围对照", "", "| 业务表 | 本地记录数 |", "| --- | --- |"]
    lines.extend(f"| {table} | {count} |" for table, count in s["business_table_counts_not_directly_exported"].items())
    lines += ["", "上述计数仅帮助判断本地图谱是否覆盖业务，业务表行不会被重复或推测性投影成本体实例。",
              "", "## 重新生成", "", "在项目根目录执行（需要安装 rdflib）：", "", "\x60\x60\x60powershell",
              "python scripts/export_marketing_ontology.py", "\x60\x60\x60", "",
              "脚本默认拒绝覆盖现有文件。新一版可使用 --version v1.1；确需重新生成同一快照可使用 --overwrite。",
              "", "## 版本记录", "", "| 版本 | 内容 |", "| --- | --- |",
              f"| {s['export_version']} | 从本地语义注册表和本体数据库导出完整 OWL 评审快照 |", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "services/platform-api/ceair-marketing.db")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", default=EXPORT_VERSION)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", args.version):
        parser.error("Version must look like v1.0 or v1.0.1")
    output = (args.output or ROOT / "docs/本体导出" / ("东方航空营销本体与实例_" + args.version + ".owl")).resolve()
    summary_path = output.with_suffix(".summary.json")
    report_path = output.with_suffix(".说明.md")
    if not args.overwrite and any(p.exists() for p in (output, summary_path, report_path)):
        parser.error("Output exists. Choose a new version filename or pass --overwrite.")
    snapshot = read_snapshot(args.database)
    model = load_model()
    graph, summary = build_graph(model, snapshot, export_version=args.version)
    xml = graph.serialize(format="xml", encoding="utf-8")
    loaded = Graph().parse(data=xml, format="xml")
    if not isomorphic(graph, loaded):
        raise RuntimeError("OWL RDF/XML round-trip lost graph information")
    summary["validation"] = {"rdf_xml_round_trip": "passed", "graph_isomorphic": True,
                             "owl_dl_reasoner_run": False, "shacl_run": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(xml)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(report_path, output, model, summary)
    print(json.dumps({"output": str(output), "classes": summary["registered_class_count"],
                      "instances": summary["entity_count"], "relations": summary["relation_row_count"],
                      "triples": len(graph), "warnings": len(summary["warnings"])}))


if __name__ == "__main__":
    main()
