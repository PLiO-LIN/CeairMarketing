import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.database import SessionLocal
from app.db_models import (UserRecord, CampaignRecord, CampaignVersionRecord, ContentAssetRecord, OntologyEntityRecord, OntologyRelationRecord, AgentRunRecord, RuntimeEventRecord, ModelProviderRecord, ProductPackageRecord)
from app.main import app
from app.seed import seed_competition_workspace, normalize_default_models
from app.campaign_readiness import campaign_readiness
from fixtures_business import complete_campaign


@pytest.fixture
def demo():
    with SessionLocal() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.username == "admin"))
        tid = seed_competition_workspace(session, user.id)
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"}).json()
        headers = {"Authorization": "Bearer " + login["access_token"], "X-Tenant-ID": str(tid)}
        yield client, headers, tid


def test_seed_covers_domains_and_restart_preserves_operated_state(demo):
    client, headers, tid = demo
    summary = client.get("/api/competition/demo", headers=headers).json()
    assert summary["synthetic"] and summary["business_date"].startswith("2026-09-18")
    assert sum(r["value"] for r in summary["profile"]["regions"]) == summary["profile"]["population"]
    assert summary["profile"]["funnel"][-2]["value"] - summary["profile"]["excluded"] == summary["profile"]["population"]
    assert round(sum(c["score"] * c["weight"] / 100 for c in summary["score_components"])) == 92
    assert summary["attribution"]["revenue"] is None and summary["attribution"]["roi"] is None
    runs = client.get("/api/agent-runs", headers=headers).json()
    assert len({r["domain_id"] for r in runs}) == 6
    review = client.get("/api/agent-runs/RUN-DEMO-5", headers=headers).json()
    assert review["output"]["context"]["campaign"]["id"] == "ACT-DEMO-MEMBER"
    assert review["output"]["context"]["audience"]["estimated_size"] == 9840
    assert review["output"]["structured"]["delivered_events"] == 9644
    with SessionLocal() as session:
        before = {model.__name__: session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tid)) for model in (CampaignRecord, OntologyEntityRecord, OntologyRelationRecord, AgentRunRecord)}
        member = session.get(CampaignRecord, (tid, "ACT-DEMO-MEMBER"))
        member.status = "已归档"
        session.commit()
        user = session.scalar(select(UserRecord).where(UserRecord.username == "admin"))
        seed_competition_workspace(session, user.id)
        assert session.get(CampaignRecord, (tid, "ACT-DEMO-MEMBER")).status == "已归档"
        after = {model.__name__: session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tid)) for model in (CampaignRecord, OntologyEntityRecord, OntologyRelationRecord, AgentRunRecord)}
        assert before == after
        member.status = "已完成"
        session.commit()
    graph = client.get("/api/campaigns/ACT-2026-0921/graph", headers=headers).json()
    assert all(n["type"] != "Campaign" or n["id"] == "ACT-2026-0921" for n in graph["nodes"])
    assert {"KnowledgeDocument", "KnowledgeChunk", "Evidence", "MarketSignal", "AgentRun", "StrategyPlan"} <= {n["type"] for n in graph["nodes"]}


def test_readiness_blocks_missing_channel_and_stale_product(demo):
    client, headers, tid = demo
    blocked = client.get("/api/campaigns/ACT-DEMO-BLOCKED/readiness", headers=headers).json()
    assert not blocked["ready"]
    assert not next(c["passed"] for c in blocked["checks"] if c["key"] == "product")
    campaign = client.post("/api/campaigns", headers=headers, json={"name": "门禁测试活动"}).json()
    materials = complete_campaign(client, headers, campaign["id"], ["App", "微信"])
    ready = client.get(f"/api/campaigns/{campaign['id']}/readiness", headers=headers).json()
    assert ready["ready"]
    with SessionLocal() as session:
        version = session.get(CampaignVersionRecord, ready["version_id"])
        version.content_asset_ids_json = json.dumps(materials["content_asset_ids"][:1])
        session.commit()
    missing = client.get(f"/api/campaigns/{campaign['id']}/readiness", headers=headers).json()
    assert missing["missing_channels"] == ["微信"] and not missing["ready"]
    assert client.post(f"/api/campaigns/{campaign['id']}/versions/{ready['version_id']}/approval", headers=headers).status_code == 409
    with SessionLocal() as session:
        version = session.get(CampaignVersionRecord, ready["version_id"])
        version.content_asset_ids_json = json.dumps(materials["content_asset_ids"])
        product = session.get(ProductPackageRecord, materials["product_package_id"])
        product.valid_to = datetime(2026, 9, 18, 9, tzinfo=timezone(timedelta(hours=8)))
        assert not campaign_readiness(session, tid, version)["ready"]
        session.rollback()


@pytest.mark.parametrize("run_id,kind", [("RUN-DEMO-0", "Recommendation"), ("RUN-DEMO-2", "ValueProposition"), ("RUN-DEMO-3", "StrategyPlan"), ("RUN-DEMO-5", "Review")])
def test_typed_acceptance_is_idempotent_and_links_human_evidence(demo, run_id, kind):
    client, headers, _ = demo
    saved = client.post(f"/api/agent-runs/{run_id}/accept", headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["type"] == kind
    assert client.post(f"/api/agent-runs/{run_id}/accept", headers=headers).json() == saved.json()
    detail = client.get(f"/api/agent-runs/{run_id}", headers=headers).json()
    assert detail["status"] == "completed" and detail["applied_object"] == saved.json()
    graph = client.get("/api/graph", headers=headers).json()
    node = next(n for n in graph["nodes"] if n["id"] == saved.json()["external_id"])
    assert node["type"] == kind and node["attributes"]["status"] == "草稿"
    assert any(e["source"] == node["id"] and e["relation"] == "confirmed_by_human" for e in graph["edges"])
    assert any(e["source"] == run_id and e["relation"] == "has_evidence" for e in graph["edges"])
    if kind == "StrategyPlan":
        assert any(e["source"] == node["id"] and e["relation"] == "uses_touchpoint_plan" for e in graph["edges"])
    if kind == "Review":
        assert node["attributes"]["revenue"] is None and node["attributes"]["roi"] is None


def test_content_review_and_projection_detect_flushed_changes(demo):
    client, headers, tid = demo
    asset = client.post("/api/content-assets", headers=headers, json={"name": "视觉草稿", "title": "出行推荐", "body": "产品规则为准", "status": "待审核", "generation_context": {"visual": {"theme": "family"}}}).json()
    approved = client.post(f"/api/content-assets/{asset['id']}/review", headers=headers, json={"decision": "approve", "comment": "事实核验"}).json()
    assert approved["status"] == "已审核"
    changed = client.put(f"/api/content-assets/{asset['id']}", headers=headers, json={**approved, "generation_context": {"visual": {"theme": "business"}}})
    assert changed.status_code == 200 and changed.json()["status"] == "草稿"
    with SessionLocal() as session:
        campaign = session.get(CampaignRecord, (tid, "ACT-DEMO-ANCILLARY"))
        original = campaign.status
        campaign.status = "已暂停"
        session.flush()
        session.commit()
        node = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tid, OntologyEntityRecord.external_id == campaign.id))
        assert json.loads(node.attributes_json)["status"] == "已暂停"
        campaign.status = original
        session.commit()
    graph = client.get("/api/graph", headers=headers).json()
    assert any(n["id"] == asset["external_id"] for n in graph["nodes"])
    assert client.delete(f"/api/content-assets/{asset['id']}", headers=headers).status_code == 204
    assert not any(n["id"] == asset["external_id"] for n in client.get("/api/graph", headers=headers).json()["nodes"])


def test_default_model_repair_and_failed_inference_source(demo, monkeypatch):
    from app.opportunity_insight import _agent_result
    from app.llm import LLMConfig
    from app.agents.agentscope_runtime import AgentScopeRuntime
    _, _, tid = demo
    with SessionLocal() as session:
        providers = session.scalars(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tid)).all()
        session.add(ModelProviderRecord(tenant_id=tid, display_name="重复默认", provider_type="mock", model_name="mock", is_default=True, enabled=True))
        session.flush()
        normalize_default_models(session)
        assert sum(p.is_default for p in session.scalars(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tid))) == 1
        session.rollback()
    def fail(*args, **kwargs):
        raise RuntimeError("test model unavailable")
    monkeypatch.setattr(AgentScopeRuntime, "run_sync", fail)
    result = _agent_result("market", "opportunity-insight", "test-source", tid, "三亚", [], LLMConfig("mock", "", "mock", "", 1, 0, 100))
    assert result["execution"] == "deterministic-fallback" and result["model_error"] == "RuntimeError"
