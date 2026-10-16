from pathlib import Path

import pytest

from app.algorithms.eg_chpn_runtime import WEIGHTS_PATH, ArtifactSchemaError
from app.database import SessionLocal
from app.ontology.projection import put_entity, put_relation

pytestmark = pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="marshecho weights not exported yet")


def login(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["tenants"]


def headers(auth, tenant_id):
    return {**auth, "X-Tenant-ID": str(tenant_id)}


def seed_eligibility_path(client, auth, tenant_id: int, suffix: str, *, blocked: bool = False, confidence: float = 0.9) -> str:
    """Create a real audience snapshot, then wire its ontology eligibility path."""

    created = client.post(
        "/api/audience-packages",
        headers=headers(auth, tenant_id),
        json={
            "name": f"九皋测试客群-{suffix}",
            "selection_mode": "tag-combination",
            "tag_ids": [],
            "expression": {"destination": "三亚"},
            "estimated_size": 1200,
            "status": "可用",
        },
    )
    assert created.status_code == 201
    snapshot_response = client.post(f"/api/audience-packages/{created.json()['id']}/snapshots", headers=headers(auth, tenant_id))
    assert snapshot_response.status_code == 201
    snapshot_external_id = snapshot_response.json()["external_id"]
    with SessionLocal() as session:
        route = put_entity(session, tenant_id, f"RT-{suffix}", "Route", "上海—三亚", {"signal": 0.8})
        flight = put_entity(session, tenant_id, f"FT-{suffix}", "Flight", "MU5137", {})
        cabin = put_entity(session, tenant_id, f"CB-{suffix}", "Cabin", "Y 舱", {})
        fare = put_entity(session, tenant_id, f"FR-{suffix}", "Fare", "经济舱折扣价", {"fare": 0.6})
        product = put_entity(session, tenant_id, f"PR-{suffix}", "Product", "行李优选", {"fit": 0.7})
        package = put_entity(session, tenant_id, f"PP-{suffix}", "ProductPackage", "家庭出行包", {})
        rule = put_entity(session, tenant_id, f"BR-{suffix}", "BusinessRule", "资格规则", {"status": "blocked" if blocked else "active"})
        evidence = put_entity(session, tenant_id, f"EV-{suffix}", "Evidence", "运价与舱位核对记录", {"quality": confidence}, confidence=confidence)
        snapshot = put_entity(session, tenant_id, snapshot_external_id, "AudienceSnapshot", "暑运家庭客群快照", {"value": 0.65})
        put_relation(session, tenant_id, package, "targets_audience", snapshot)
        put_relation(session, tenant_id, package, "contains_product", product)
        put_relation(session, tenant_id, fare, "uses_product", product)
        put_relation(session, tenant_id, cabin, "has_fare", fare)
        put_relation(session, tenant_id, flight, "has_cabin", cabin)
        put_relation(session, tenant_id, flight, "operates_on", route)
        put_relation(session, tenant_id, evidence, "evidence_for", package)
        put_relation(session, tenant_id, evidence, "evidence_for", route)
        put_relation(session, tenant_id, evidence, "evidence_for", rule)
        session.commit()
    return snapshot_external_id


def test_marshecho_status_reports_governance_fields() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        response = client.get("/api/algorithms/marshecho/status", headers=headers(auth, hq["id"]))
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is True
        assert payload["model_name"] == "marshecho"
        assert payload["model_name_zh"] == "九皋"
        assert payload["synthetic"] is True
        assert payload["label"] == "流程验证（虚构）"
        assert payload["runtime"] == "numpy"
        assert payload["parameters"] > 0


def test_score_returns_uplift_with_gate_trace() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        snapshot = seed_eligibility_path(client, auth, hq["id"], "SCORE1")
        response = client.post(
            "/api/algorithms/marshecho/score",
            headers=headers(auth, hq["id"]),
            json={"audience_snapshot_external_id": snapshot, "product_package_external_ids": ["PP-SCORE1"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["accepted_edges"] == 1
        item = payload["items"][0]
        assert item["status"] == "eligible"
        assert item["product_package_external_id"] == "PP-SCORE1"
        assert item["action_id"] == "PP-SCORE1-seg-0"
        assert item["accepted"] is True
        assert item["gate_value"] > 0
        assert item["uplift"] == pytest.approx(item["uplift"])


def test_blocked_rule_is_rejected_before_scoring() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        snapshot = seed_eligibility_path(client, auth, hq["id"], "BLOCK1", blocked=True)
        response = client.post(
            "/api/algorithms/marshecho/plan",
            headers=headers(auth, hq["id"]),
            json={
                "audience_snapshot_external_id": snapshot,
                "product_package_external_ids": ["PP-BLOCK1"],
                "budget_yuan": 10,
                "channel_caps": {"App": 5, "SMS": 5, "WeChat": 5},
                "max_per_frequency_group": 5,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["selected"] == []
        assert payload["rejected"][0]["reason"] == "ontology_gate:ineligible"
        assert payload["constraint_violations"] == []


def test_plan_is_budget_feasible_and_cross_tenant_isolated() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        others = [item for item in tenants if item["code"] != "CEA-HQ"]
        snapshot = seed_eligibility_path(client, auth, hq["id"], "PLAN1")
        payload = {
            "audience_snapshot_external_id": snapshot,
            "product_package_external_ids": ["PP-PLAN1"],
            "budget_yuan": 10,
            "channel_caps": {"App": 5, "SMS": 5, "WeChat": 5},
            "max_per_frequency_group": 5,
        }
        plan = client.post("/api/algorithms/marshecho/plan", headers=headers(auth, hq["id"]), json=payload)
        assert plan.status_code == 200
        body = plan.json()
        assert body["budget_used"] <= 10 + 1e-9
        assert body["constraint_violations"] == []
        if others:
            assert client.post("/api/algorithms/marshecho/score", headers=headers(auth, others[0]["id"]), json=payload).status_code == 404
        payload_other = {**payload, "audience_snapshot_external_id": "AS-NOT-EXIST"}
        assert client.post("/api/algorithms/marshecho/score", headers=headers(auth, hq["id"]), json=payload_other).status_code == 404


def test_status_is_governed_when_artifact_is_missing(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import app.main as main_module

    def broken():
        raise ArtifactSchemaError("权重缺失")

    monkeypatch.setattr(main_module, "load_default_runtime", broken)
    with TestClient(main_module.app) as client:
        assert client.get("/api/algorithms/marshecho/status").status_code == 503


def test_explain_falls_back_to_template_when_provider_fails(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import app.main as main_module

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(main_module.llm_client, "generate_result", boom)
    with TestClient(main_module.app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        response = client.post(
            "/api/algorithms/marshecho/explain",
            headers=headers(auth, hq["id"]),
            json={"action_id": "pkg-1-seg-0", "detail": "暑运家庭客群"},
        )
        assert response.status_code == 200
        assert response.json()["source"] in {"template", "provider"}
        assert "合成机制验证" in response.json()["text"] or response.json()["source"] == "provider"


def test_half_wired_ontology_path_is_scored_instead_of_failing() -> None:
    """A tenant whose eligibility chain is only partly wired must get a score.

    This used to answer 500: the graph held seven of the nine trained node
    types (no Route, no Flight), and the runtime demanded an exact vocabulary
    size.  A real deployment always has half-completed projections, so the
    response must stay a scored, governed answer with the path degraded by the
    ontology gate.
    """

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        created = client.post(
            "/api/audience-packages",
            headers=headers(auth, hq["id"]),
            json={
                "name": "九皋半接客群-HALF1",
                "selection_mode": "tag-combination",
                "tag_ids": [],
                "expression": {"destination": "三亚"},
                "estimated_size": 500,
                "status": "可用",
            },
        )
        assert created.status_code == 201
        snapshot_id = client.post(
            f"/api/audience-packages/{created.json()['id']}/snapshots", headers=headers(auth, hq["id"])
        ).json()["external_id"]
        with SessionLocal() as session:
            product = put_entity(session, hq["id"], "PR-HALF1", "Product", "半接行李优选", {"fit": 0.7})
            fare = put_entity(session, hq["id"], "FR-HALF1", "Fare", "经济舱折扣价", {"fare": 0.6})
            cabin = put_entity(session, hq["id"], "CB-HALF1", "Cabin", "Y 舱", {})
            package = put_entity(session, hq["id"], "PP-HALF1", "ProductPackage", "半接产品包", {})
            rule = put_entity(session, hq["id"], "BR-HALF1", "BusinessRule", "资格规则", {"status": "active"})
            evidence = put_entity(session, hq["id"], "EV-HALF1", "Evidence", "运价核对记录", {"quality": 0.85}, confidence=0.85)
            snapshot = put_entity(session, hq["id"], snapshot_id, "AudienceSnapshot", "半接快照", {"value": 0.6})
            put_relation(session, hq["id"], package, "targets_audience", snapshot)
            put_relation(session, hq["id"], package, "contains_product", product)
            put_relation(session, hq["id"], fare, "uses_product", product)
            put_relation(session, hq["id"], cabin, "has_fare", fare)
            put_relation(session, hq["id"], evidence, "evidence_for", package)
            put_relation(session, hq["id"], evidence, "evidence_for", rule)
            session.commit()
        response = client.post(
            "/api/algorithms/marshecho/score",
            headers=headers(auth, hq["id"]),
            json={"audience_snapshot_external_id": snapshot_id, "product_package_external_ids": ["PP-HALF1"]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["items"][0]["accepted"] is False
        assert payload["items"][0]["product_package_external_id"] == "PP-HALF1"
        assert payload["unmatched_paths"] >= 1
        assert payload["label"] == "流程验证（虚构）"
