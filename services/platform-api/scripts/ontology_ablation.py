"""Offline ontology ablation experiment.

Measures what the production semantic gates actually block. The harness imports the
real gate functions and never re-implements their rules, so every number it prints can
be reproduced with one command:

    python -B scripts/ontology_ablation.py --json

Tiers:
  A  registry legality      semantic_model.py          no third-party imports at all
  B  admission gate         data_pipeline.py           needs the API requirements only
  C  publish gate          campaign_readiness.py      in-memory SQLite, no server, no model
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TOKEN_SECRET", "ablation-only-token-secret")
os.environ.setdefault("ENCRYPTION_KEY", "wrxE4kMm60hSu103lUo7KQdZrF4alZpqaJO1Y0gHg5s=")
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(API_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(API_ROOT / "scripts"))

import ontology_ablation_cases as cases  # noqa: E402


def _load_registry_module():
    """Load the registry file directly; it imports nothing, so Tier A runs in bare Python."""
    path = API_ROOT / "app" / "ontology" / "semantic_model.py"
    spec = importlib.util.spec_from_file_location("ablation_semantic_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


registry = _load_registry_module()
model = registry.semantic_model()
FARE_PATH = ["has_cabin", "has_fare", "uses_product"]


def registry_stats() -> dict[str, Any]:
    attributes = registry.ATTRIBUTE_DEFINITIONS
    constrained = [item for item in model["relation_types"] if item.get("from_types") and item.get("to_types")]
    return {
        "semantic_model_version": model["version"],
        "object_types": len(model["object_types"]),
        "relation_types": len(model["relation_types"]),
        "relations_with_declared_endpoints": len(constrained),
        "attribute_definitions": len(attributes),
        "registered_attributes": sum(len(items) for items in attributes.values()),
        "actions": len(model["actions"]),
        "functions": len(model["functions"]),
        "agent_contracts": len(model["agent_contracts"]),
        "principles": len(model["principles"]),
        "lifecycle_stages": len(model["lifecycle"]),
    }


def _reachable(relations: list[dict[str, Any]], start_types: set[str], target_type: str, entities_by_id: dict[str, str]) -> tuple[bool, int]:
    """Breadth-first walk over admitted relations; returns reachability and hop count."""
    seen = {key for key, kind in entities_by_id.items() if kind in start_types}
    frontier = set(seen)
    hops = 0
    while frontier:
        hops += 1
        nxt = set()
        for item in relations:
            if item["source_external_id"] in frontier and item["target_external_id"] not in seen:
                if entities_by_id.get(item["target_external_id"]) == target_type:
                    return True, hops
                nxt.add(item["target_external_id"])
        seen |= nxt
        frontier = nxt
    return False, 0


def tier_a() -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    rows = []
    for case in cases.registry_cases(model):
        began = time.perf_counter()
        message = registry.validate_relation_endpoints(case["relation"], case["source_type"], case["target_type"])
        rows.append({
            "id": case["id"],
            "family": case["family"],
            "name": case["name"],
            "tier": "A",
            "target": "validate_relation_endpoints",
            "must_block": case["must_block"],
            "blocked": message is not None,
            "reason": message or "",
            "localized": bool(message) and "requires" in message and "got" in message,
            "latency_ms": round((time.perf_counter() - began) * 1000, 4),
        })
    return rows, round((time.perf_counter() - started) * 1000, 2)


def _admit(candidates: dict[str, Any]) -> dict[str, Any]:
    from app.data_pipeline import apply_ontology_admission

    return apply_ontology_admission(candidates)


def _describe(result: dict[str, Any]) -> dict[str, Any]:
    entities = result.get("entities") or []
    relations = result.get("relations") or []
    admitted_entities = [item for item in entities if item.get("ontology_eligible")]
    admitted_relations = [item for item in relations if item.get("ontology_eligible")]
    by_id = {item["external_id"]: item["entity_type"] for item in admitted_entities}
    path_ok, hops = _reachable(admitted_relations, {"Flight"}, "Product", by_id)
    ancillary_ok, ancillary_hops = _reachable(admitted_relations, {"Flight"}, "AncillaryProduct", by_id)
    gate = result.get("ontology_gate") or {}
    reasons = [item.get("reason", "") for item in result.get("rejected_items") or []]
    return {
        "gate_eligible": bool(gate.get("eligible")),
        "gate_decision": gate.get("decision", ""),
        "accepted_entities": len(admitted_entities),
        "accepted_relations": len(admitted_relations),
        "admitted_relation_types": sorted({item["relation_type"] for item in admitted_relations}),
        "rejected_count": len(result.get("rejected_items") or []),
        "path_flight_to_product": path_ok,
        "eligibility_hops": hops,
        "ancillary_hops": ancillary_hops,
        "reasons": reasons,
        "matched_entity_types": gate.get("matched_entity_types") or [],
    }


def _observed_block(view: str, result: dict[str, Any]) -> bool:
    if view == "gate":
        return not result["gate_eligible"]
    if view == "path":
        return not result["path_flight_to_product"]
    if view == "relation_any":
        return result["accepted_relations"] == 0
    if view.startswith("relation:"):
        wanted = view.split(":", 1)[1]
        return wanted not in result["admitted_relation_types"]
    raise ValueError(f"unknown view {view}")


def tier_b() -> tuple[list[dict[str, Any]], dict[str, Any], float]:
    from app.flight_product_pipeline import normalize_flight_product_payload

    started = time.perf_counter()
    base = normalize_flight_product_payload(cases.build_snapshot())
    twice = normalize_flight_product_payload(cases.build_snapshot())

    def fingerprint(payload: dict[str, Any]) -> str:
        # Collection timestamps legitimately differ between runs; identity is the semantic part.
        stable = {
            "entities": [{key: value for key, value in item.items() if key != "valid_time"} for item in payload["entities"]],
            "relations": payload["relations"],
        }
        return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    baseline_fingerprint = fingerprint(base)
    _admit(base)  # warm up so the import and first-pass cost stay out of the per-case timing
    rows = []
    for case in cases.cases(base):
        began = time.perf_counter()
        result = _admit(case["payload"])
        detail = _describe(result)
        blocked = _observed_block(case["view"], detail)
        gate = result.get("ontology_gate") or {}
        rows.append({
            "id": case["id"],
            "family": case["family"],
            "name": case["name"],
            "tier": "B",
            "target": case["target"],
            "view": case["view"],
            "must_block": case["must_block"],
            "blocked": blocked,
            "localized": bool(detail["reasons"]) or not gate.get("eligible") or detail["gate_decision"] == "knowledge_only",
            "latency_ms": round((time.perf_counter() - began) * 1000, 3),
            **detail,
        })
    evidence_profile = {
        "baseline_entities": len(base["entities"]),
        "baseline_relations": len(base["relations"]),
        "entities_with_evidence": sum(1 for item in base["entities"] if item.get("evidence")),
        "entities_with_source_refs": sum(1 for item in base["entities"] if item.get("source_refs")),
        "relations_with_evidence": sum(1 for item in base["relations"] if item.get("evidence")),
        "avg_source_refs_per_entity": round(sum(len(item.get("source_refs") or []) for item in base["entities"]) / max(1, len(base["entities"])), 2),
        "deterministic_adapter": fingerprint(twice) == baseline_fingerprint,
        "baseline_fingerprint": baseline_fingerprint[:16],
    }
    return rows, evidence_profile, round((time.perf_counter() - started) * 1000, 2)


def tier_c() -> tuple[list[dict[str, Any]], float]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.campaign_readiness import campaign_readiness
    from app.competition_demo import DEMO_DATE
    from app.database import Base
    from app.db_models import AudiencePackageRecord, AudienceSnapshotRecord, CampaignVersionRecord, ContentAssetRecord, ProductPackageRecord, TenantRecord, UserRecord

    def mutate(kind, product, snapshot, version, contents):
        if kind == "expire_product":
            product.valid_to = DEMO_DATE - timedelta(days=1)
        elif kind == "draft_product":
            product.status = "草稿"
        elif kind == "unfrozen_snapshot":
            snapshot.status = "草稿"
        elif kind == "missing_channel_content":
            contents[1].channel = "App"
        elif kind == "zero_budget":
            version.budget_yuan = 0
        elif kind == "draft_content":
            contents[0].status = "草稿"

    started = time.perf_counter()
    rows = []
    for case in cases.readiness_cases():
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as session:
            tenant = TenantRecord(code="ABL-TIERC", name="消融实验工作区", status="active")
            session.add(tenant)
            session.flush()
            operator = UserRecord(username="ablation", display_name="消融实验操作员", password_hash="ablation-only-hash")
            session.add(operator)
            session.flush()
            package = AudiencePackageRecord(tenant_id=tenant.id, external_id="PKG-ABL-1", name="三亚高意向未购客群", selection_mode="tags", estimated_size=36420, status="已冻结", created_by=operator.id)
            session.add(package)
            session.flush()
            snapshot = AudienceSnapshotRecord(tenant_id=tenant.id, package_id=package.id, external_id="SNAP-ABL-1", estimated_size=36420, status="已冻结", source="消融实验构造", created_by=operator.id)
            product = ProductPackageRecord(tenant_id=tenant.id, external_id="PROD-ABL-1", name="早鸟家庭出行包", product_type="组合产品", description="含行李与座位权益", eligibility="实名旅客", status="已审批", valid_from=DEMO_DATE - timedelta(days=30), valid_to=DEMO_DATE + timedelta(days=30))
            session.add_all([snapshot, product])
            session.flush()
            contents = [
                ContentAssetRecord(tenant_id=tenant.id, external_id="CON-ABL-APP", name="App 推送", channel="App", title="三亚亲子出行", body="行李权益与早鸟价格以审核后产品规则为准。", status="已审核", audience_package_id=package.id, product_package_id=product.id, campaign_id="ABL-C1"),
                ContentAssetRecord(tenant_id=tenant.id, external_id="CON-ABL-SMS", name="短信提醒", channel="短信", title="三亚出行提醒", body="辅营权益以审核后产品规则为准。", status="已审核", audience_package_id=package.id, product_package_id=product.id, campaign_id="ABL-C1"),
            ]
            session.add_all(contents)
            session.flush()
            version = CampaignVersionRecord(tenant_id=tenant.id, campaign_id="ABL-C1", external_id="VER-ABL-1", audience_snapshot_id=snapshot.id, product_package_id=product.id, content_asset_ids_json=json.dumps([item.id for item in contents]), budget_yuan=50000, channels_json=json.dumps(["App", "短信"]), status="待审批")
            session.add(version)
            if case["mutate"]:
                mutate(case["mutate"], product, snapshot, version, contents)
            session.commit()
            began = time.perf_counter()
            result = campaign_readiness(session, tenant.id, version, DEMO_DATE)
            failed = [item["key"] for item in result["checks"] if not item["passed"]]
            rows.append({
                "id": case["id"],
                "family": case["family"],
                "name": case["name"],
                "tier": "C",
                "target": "campaign_readiness",
                "must_block": case["must_block"],
                "blocked": not result["ready"],
                "localized": bool(case["check"]) is False or (case["check"] in failed),
                "expected_check": case["check"] or "",
                "failed_checks": failed,
                "sellability_status": result["sellability_status"],
                "latency_ms": round((time.perf_counter() - began) * 1000, 3),
            })
        engine.dispose()
    return rows, round((time.perf_counter() - started) * 1000, 2)


def _latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["latency_ms"] for row in rows]
    if not values:
        return {}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * len(ordered)) - 1))]
    return {"count": len(values), "avg_ms": round(statistics.fmean(values), 3), "p50_ms": round(statistics.median(values), 3), "p95_ms": p95, "max_ms": round(max(values), 3)}


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    must_block = [row for row in rows if row["must_block"]]
    must_pass = [row for row in rows if not row["must_block"]]
    caught = [row for row in must_block if row["blocked"]]
    return {
        "cases": len(rows),
        "must_block": len(must_block),
        "blocked": len(caught),
        "block_rate": round(len(caught) / len(must_block), 4) if must_block else None,
        "false_accept": len(must_block) - len(caught),
        "over_block": sum(1 for row in must_pass if row["blocked"]),
        "must_pass": len(must_pass),
        "localization_rate": round(sum(1 for row in caught if row["localized"]) / len(caught), 4) if caught else None,
        "latency": _latency(rows),
    }


def run_all(include_tier_c: bool = True) -> dict[str, Any]:
    rows_a, wall_a = tier_a()
    rows_b, evidence, wall_b = tier_b()
    rows_c, wall_c = tier_c() if include_tier_c else ([], 0.0)
    all_rows = rows_a + rows_b + rows_c
    must_block = [row for row in all_rows if row["must_block"]]
    caught = [row for row in must_block if row["blocked"]]
    baseline = next(row for row in rows_b if row["id"] == "B0")
    summary = {
        "experiment": "ontology-ablation-v1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": "构造的东航航班与产品快照（四条 MU 航线），判定全部来自生产门禁函数",
        "registry": registry_stats(),
        "tiers": {
            "A_registry_legality": {**score(rows_a), "wall_ms": wall_a},
            "B_admission_gate": {**score(rows_b), "wall_ms": wall_b},
            "C_publish_gate": {**score(rows_c), "wall_ms": wall_c} if include_tier_c else {"skipped": True},
        },
        "overall": {
            "cases": len(all_rows),
            "must_block": len(must_block),
            "blocked": len(caught),
            "block_rate": round(len(caught) / len(must_block), 4) if must_block else None,
            "false_accept": len(must_block) - len(caught),
            "over_block": sum(1 for row in all_rows if not row["must_block"] and row["blocked"]),
            "localization_rate": round(sum(1 for row in caught if row["localized"]) / len(caught), 4) if caught else None,
            "latency": _latency(all_rows),
        },
        "baseline": {
            "gate_eligible": baseline["gate_eligible"],
            "accepted_entities": baseline["accepted_entities"],
            "accepted_relations": baseline["accepted_relations"],
            "path_flight_to_product": baseline["path_flight_to_product"],
            "eligibility_hops": baseline["eligibility_hops"],
            "ancillary_hops": baseline["ancillary_hops"],
            "evidence": evidence,
        },
        "reason_distribution": _reason_distribution(rows_b),
        "cases": rows_a + rows_b + rows_c,
        "definitions": {
            "blocked": "按用例声明的观察面判定：gate=本体门禁不再放行写入；path=航班到产品的资格路径在已准入关系中不可达；relation_any=没有任何关系被准入；relation:<type>=该类型关系全部未被准入；publish=campaign_readiness 返回 ready=false",
            "false_accept": "应当拦截却被放行的用例数，即不可售或非法语义仍进入可执行流程",
            "over_block": "不应拦截却被拦截的用例数，即合法语义被误杀，衡量门禁是否过苛",
            "localization_rate": "被拦截用例中，生产函数返回值同时给出可定位依据（逐条拒因、失败门禁项或门禁整体拒绝决策）的比例",
            "eligibility_hops": "已准入关系图上从 Flight 到 Product 的最短跳数，即一次资格判定需要贯通的关系层数",
        },
        "notes": [
            "输入为构造的东航航班与产品快照，用于验证语义门禁行为，不代表东航真实经营数据。",
            "P1a 与 P1b 属于整批删除必要关系，生产函数不产生逐条拒因，因此不计入可定位率分子；其拦截由路径不可达与发布门禁共同保证。",
            "本实验不覆盖模型生成质量、并发容量与经营增量；三者分别见智能体稳健性报告与企业试点计划。",
        ],
        "provenance": {
            "validate_relation_endpoints": "services/platform-api/app/ontology/semantic_model.py:230",
            "apply_ontology_admission": "services/platform-api/app/data_pipeline.py:394",
            "normalize_flight_product_payload": "services/platform-api/app/flight_product_pipeline.py:52",
            "campaign_readiness": "services/platform-api/app/campaign_readiness.py:14",
            "fixture": "services/platform-api/scripts/ontology_ablation_cases.py",
        },
    }
    return summary


def _reason_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if not row["must_block"] or not row["blocked"]:
            continue
        key = row["family"]
        out[key] = out.get(key, 0) + 1
    return out


def to_markdown(summary: dict[str, Any]) -> str:
    registry = summary["registry"]
    overall = summary["overall"]
    lines = [
        f"# 本体约束消融实验 {summary['experiment']}",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 输入：{summary['input']}",
        f"- 本体版本：`{registry['semantic_model_version']}`｜{registry['object_types']} 对象类型｜{registry['relation_types']} 关系类型｜{registry['registered_attributes']} 注册属性",
        "",
        "## 结论",
        "",
        f"- 用例 {overall['cases']} 条，应拦截 {overall['must_block']} 条，实际拦截 {overall['blocked']} 条，拦截率 {overall['block_rate'] * 100:.1f}%",
        f"- 误放行（不可售被判可推荐）：{overall['false_accept']}；过度拦截（合法被判非法）：{overall['over_block']}",
        f"- 阻断原因可定位率：{overall['localization_rate'] * 100:.1f}%",
        f"- 单次判定耗时：平均 {overall['latency']['avg_ms']} ms，p95 {overall['latency']['p95_ms']} ms",
        "",
        "## 分层结果",
        "",
        "| 层 | 判定函数 | 用例 | 应拦截 | 拦截率 | 误放行 | 过度拦截 | 平均耗时 ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    labels = {"A_registry_legality": "A 注册表合法性", "B_admission_gate": "B 本体准入", "C_publish_gate": "C 发布门禁"}
    targets = {"A_registry_legality": "validate_relation_endpoints", "B_admission_gate": "apply_ontology_admission", "C_publish_gate": "campaign_readiness"}
    for key, label in labels.items():
        tier = summary["tiers"][key]
        if tier.get("skipped"):
            lines.append(f"| {label} | {targets[key]} | 未运行 |  |  |  |  |  |")
            continue
        rate = "-" if tier["block_rate"] is None else f"{tier['block_rate'] * 100:.1f}%"
        latency = tier["latency"].get("avg_ms", "-")
        lines.append(f"| {label} | `{targets[key]}` | {tier['cases']} | {tier['must_block']} | {rate} | {tier['false_accept']} | {tier['over_block']} | {latency} |")
    baseline = summary["baseline"]
    evidence = baseline["evidence"]
    lines += [
        "",
        "## 基线与语义完整度",
        "",
        f"- 基线准入 {baseline['accepted_entities']} 对象／{baseline['accepted_relations']} 关系，航班到产品资格路径可走通，遍历 {baseline['eligibility_hops']} 跳（辅营 {baseline['ancillary_hops']} 跳）",
        f"- 实体证据字段 {evidence['entities_with_evidence']}/{evidence['baseline_entities']}，关系证据字段 {evidence['relations_with_evidence']}/{evidence['baseline_relations']}，平均每实体来源引用 {evidence['avg_source_refs_per_entity']} 条",
        f"- 适配器幂等（两次解析指纹一致）：{'是' if evidence['deterministic_adapter'] else '否'}，指纹 `{evidence['baseline_fingerprint']}`",
        "",
        "## 用例明细",
        "",
        "| 用例 | 族 | 名称 | 层 | 判定函数 | 应拦截 | 实际拦截 | 判定 | 耗时 ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary["cases"]:
        verdict = "拦截正确" if row["must_block"] and row["blocked"] else "放行正确" if not row["must_block"] and not row["blocked"] else "误放行" if row["must_block"] else "过度拦截"
        lines.append(f"| {row['id']} | {row['family']} | {row['name']} | {row['tier']} | `{row['target']}` | {'是' if row['must_block'] else '否'} | {'是' if row['blocked'] else '否'} | {verdict} | {row['latency_ms']} |")
    lines += ["", "## 指标定义", ""]
    for key, text in summary["definitions"].items():
        lines.append(f"- **{key}**：{text}")
    lines += ["", "## 扰动族覆盖", "", "| 族 | 含义 | 用例 | 拦截 |", "| --- | --- | --- | --- |"]
    family_rows: dict[str, dict[str, int]] = {}
    for row in summary["cases"]:
        bucket = family_rows.setdefault(row["family"], {"cases": 0, "must": 0, "blocked": 0})
        bucket["cases"] += 1
        if row["must_block"]:
            bucket["must"] += 1
            bucket["blocked"] += 1 if row["blocked"] else 0
    for family, label in {**cases.FAMILIES, "B0": "完整语义图基线", "C": "发布门禁对照"}.items():
        bucket = family_rows.get(family)
        if not bucket:
            continue
        lines.append(f"| {family} | {label} | {bucket['cases']} | {bucket['blocked']}/{bucket['must']} |")
    lines += ["", "## 口径与边界", ""]
    for note in summary["notes"]:
        lines.append(f"- {note}")
    lines.append("- 判定全部来自生产函数，harness 不重写规则。")
    lines += ["", "## 代码出处", ""]
    for name, path in summary["provenance"].items():
        lines.append(f"- `{name}`：{path}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline ontology ablation experiment.")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.add_argument("--markdown", action="store_true", help="print the report body")
    parser.add_argument("--write", action="store_true", help="write docs/实验 artifacts and exit")
    parser.add_argument("--no-tier-c", action="store_true", help="skip the publish gate tier")
    args = parser.parse_args(argv)
    summary = run_all(include_tier_c=not args.no_tier_c)
    if args.write:
        target = REPO_ROOT / "docs" / "实验"
        target.mkdir(parents=True, exist_ok=True)
        (target / "ontology-ablation-v1.0.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "ontology-ablation-v1.0.md").write_text(to_markdown(summary), encoding="utf-8")
        print(f"written: {target / 'ontology-ablation-v1.0.md'}")
        return 0
    if args.markdown:
        print(to_markdown(summary))
        return 0
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
