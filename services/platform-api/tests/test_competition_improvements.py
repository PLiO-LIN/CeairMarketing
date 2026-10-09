import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.db_models import CampaignRecord, ModelProviderRecord, UserRecord
from app.main import app
from app.seed import seed_competition_workspace


@pytest.fixture
def competition():
    with SessionLocal() as session:
        admin = session.scalar(select(UserRecord).where(UserRecord.username == "admin"))
        tenant_id = seed_competition_workspace(session, admin.id)
        seed_competition_workspace(session, admin.id)
        provider = session.scalar(select(ModelProviderRecord.id).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.provider_type == "mock"))
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"}).json()
        hq = next(item["id"] for item in login["tenants"] if item["code"] == "CEA-HQ")
        headers = {"Authorization": "Bearer " + login["access_token"], "X-Tenant-ID": str(tenant_id)}
        yield client, headers, provider, {**headers, "X-Tenant-ID": str(hq)}


def test_competition_seed_is_idempotent_isolated_and_approval_gated(competition):
    client, headers, _, hq = competition
    campaigns = client.get("/api/campaigns", headers=headers).json()
    assert len(campaigns) == 4
    assert len(client.get("/api/knowledge/documents", headers=headers).json()) == 3
    assert len(client.get("/api/audience-packages", headers=headers).json()) == 4
    assert len(client.get("/api/execution-batches", headers=headers).json()) == 2
    approval = next(a for a in client.get("/api/approvals", headers=headers).json() if a["campaign_id"]=="ACT-2026-0921")
    assert client.post(f"/api/approvals/{approval['id']}/decision", headers=hq, json={"decision": "approve"}).status_code == 404
    assert client.post(f"/api/approvals/{approval['id']}/decision", headers=headers, json={"decision": "approve"}).status_code == 200
    batches = client.get("/api/execution-batches", headers=headers).json()
    assert len(batches) == 3
    batch = next(b for b in batches if b["campaign_id"]=="ACT-2026-0921")
    paused = client.post(f"/api/execution-batches/{batch['id']}/status", headers=headers, json={"status": "已暂停"})
    assert paused.status_code == 200
    assert paused.json()["delivered_count"] == 0
    assert paused.json()["feedback_count"] == 0
    result = client.post(f"/api/execution-batches/{batch['id']}/run", headers=headers)
    assert result.status_code == 200
    assert result.json()["delivered_count"] > 0
    assert client.post(f"/api/execution-batches/{batch['id']}/run", headers=headers).status_code == 409
    assert client.post(f"/api/execution-batches/{batch['id']}/status", headers=headers, json={"status": "已暂停"}).status_code == 409
    summary = client.get("/api/campaigns/ACT-2026-0921/effect-summary", headers=headers).json()
    assert summary["execution_mode"] == "synthetic"
    assert summary["converted_count"] > 0
    with SessionLocal() as session:
        assert session.get(CampaignRecord, (int(headers["X-Tenant-ID"]), "ACT-2026-0921")).stage == "复盘"


def test_content_result_survives_reads_and_acceptance_is_idempotent(competition):
    client, headers, provider, hq = competition
    audience = next(a for a in client.get("/api/audience-packages", headers=headers).json() if a["external_id"]=="AUD-DEMO-SANYA")
    product = next(p for p in client.get("/api/product-packages", headers=headers).json() if p["external_id"]=="PKG-DEMO-SANYA")
    before = client.get("/api/content-assets", headers=headers).json()
    response = client.post("/api/agent-runs", headers=headers, json={
        "campaign_id": "ACT-2026-0921", "domain_id": "content-generation", "provider_id": provider,
        "audience_package_id": audience["id"], "product_package_id": product["id"], "instruction": "强调行李权益",
    })
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "needs_approval"
    assert product["name"] in run["output"]["body"]
    assert len(client.get("/api/content-assets", headers=headers).json()) == len(before)
    assert client.get(f"/api/agent-runs/{run['id']}", headers=headers).json()["output"] == run["output"]
    assert client.post(f"/api/agent-runs/{run['id']}/accept", headers=hq).status_code == 404
    accepted = client.post(f"/api/agent-runs/{run['id']}/accept", headers=headers)
    assert accepted.status_code == 200
    again = client.post(f"/api/agent-runs/{run['id']}/accept", headers=headers)
    assert again.json() == accepted.json()
    assets = client.get("/api/content-assets", headers=headers).json()
    assert len(assets) == len(before) + 1
    asset = next(item for item in assets if item["id"] == accepted.json()["id"])
    assert asset["body"] == run["output"]["body"]
    assert asset["status"] == "待审核"
    assert client.get(f"/api/agent-runs/{run['id']}", headers=headers).json()["applied_object"] == accepted.json()


def test_invalid_content_context_has_no_writes(competition):
    client, headers, provider, _ = competition
    before = client.get("/api/content-assets", headers=headers).json()
    run = client.post("/api/agent-runs", headers=headers, json={"campaign_id": "ACT-2026-0921", "domain_id": "content-generation", "provider_id": provider, "product_package_id": 999999}).json()
    assert run["status"] == "failed"
    assert client.post(f"/api/agent-runs/{run['id']}/accept", headers=headers).status_code == 409
    assert client.get("/api/content-assets", headers=headers).json() == before


def test_audience_candidate_does_not_invent_a_measured_population(competition):
    client, headers, provider, _ = competition
    run = client.post("/api/agent-runs", headers=headers, json={"campaign_id": "ACT-2026-0921", "domain_id": "audience-insight", "provider_id": provider, "instruction": "选择关注三亚的家庭旅客"}).json()
    saved = client.post(f"/api/agent-runs/{run['id']}/accept", headers=headers).json()
    package = next(item for item in client.get("/api/audience-packages", headers=headers).json() if item["id"] == saved["id"])
    assert package["estimated_size"] == 0
    assert package["status"] == "草稿"
    assert package["expression"]["requires_calculation"] is True


def test_standard_sync_validates_and_preserves_tenant_scope(competition):
    client, headers, _, hq = competition
    dimensions = client.get("/api/persona-dimensions", headers=headers).json()
    field = next(item["field_code"] for item in dimensions if item["field_code"] not in {"member_id", "full_name"})
    source = "test_" + uuid4().hex[:8]
    payload = {"source_id": source, "records": [{"external_id": "A1", "name": "上游聚合客群", "estimated_size": 100, "conditions": [{"field_code": field, "operator": "eq", "value": "test"}]}]}
    first = client.post("/api/integrations/profile/audiences", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["created"] == 1
    assert client.post("/api/integrations/profile/audiences", headers=headers, json=payload).json()["unchanged"] == 1
    payload["records"][0]["estimated_size"] = 120
    assert client.post("/api/integrations/profile/audiences", headers=headers, json=payload).json()["updated"] == 1
    assert not any(item["name"] == "上游聚合客群" for item in client.get("/api/audience-packages", headers=hq).json())
    payload["records"][0]["passengers"] = [{"name": "个人明细"}]
    assert client.post("/api/integrations/profile/audiences", headers=headers, json=payload).status_code == 422
    del payload["records"][0]["passengers"]
    payload["records"][0]["conditions"][0]["field_code"] = "unregistered"
    assert client.post("/api/integrations/profile/audiences", headers=headers, json=payload).status_code == 422


def test_product_sync_is_atomic_on_invalid_batch(competition):
    client, headers, _, _ = competition
    before = client.get("/api/product-packages", headers=headers).json()
    payload = {"source_id": "invalid_batch", "records": [{"external_id": "P1", "name": "有效产品"}, {"external_id": "P2", "name": "无效日期", "valid_from": "2026-10-10T00:00:00Z", "valid_to": "2026-10-09T00:00:00Z"}]}
    assert client.post("/api/integrations/products/packages", headers=headers, json=payload).status_code == 422
    assert client.get("/api/product-packages", headers=headers).json() == before
    payload["records"] = payload["records"][:1]
    assert client.post("/api/integrations/products/packages", headers=headers, json=payload).json()["created"] == 1
    assert client.post("/api/integrations/products/packages", headers=headers, json=payload).json()["unchanged"] == 1
