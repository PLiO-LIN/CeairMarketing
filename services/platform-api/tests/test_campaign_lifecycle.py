from fastapi.testclient import TestClient
from app.main import app

def auth_headers(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    body = login.json()
    return {"Authorization": "Bearer " + body["access_token"], "X-Tenant-ID": str(body["tenants"][0]["id"])}

def test_campaign_creation_creates_version_and_mock_execution_closes_loop():
    with TestClient(app) as client:
        headers = auth_headers(client)
        created = client.post("/api/campaigns", headers=headers, json={"name": "Mock lifecycle campaign", "audience_size": 1000, "budget_yuan": 50000, "channels": ["App", "SMS"]})
        assert created.status_code == 201
        campaign_id = created.json()["id"]
        versions = client.get(f"/api/campaigns/{campaign_id}/versions", headers=headers)
        assert versions.status_code == 200
        version = versions.json()[0]
        approval = client.post(f"/api/campaigns/{campaign_id}/versions/{version['id']}/approval", headers=headers)
        assert approval.status_code == 201
        decision = client.post(f"/api/approvals/{approval.json()['id']}/decision", headers=headers, json={"decision": "approve", "comment": "Mock lifecycle campaign"})
        assert decision.status_code == 200
        batches = client.get("/api/execution-batches", headers=headers).json()
        batch = next(item for item in batches if item["campaign_id"] == campaign_id)
        run = client.post(f"/api/execution-batches/{batch['id']}/run", headers=headers)
        assert run.status_code == 200
        assert run.json()["status"] == "已完成"
        summary = client.get(f"/api/campaigns/{campaign_id}/effect-summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["delivered_count"] > 0
        assert summary.json()["converted_count"] >= 0


def test_campaign_version_and_approval_boundaries_are_enforced():
    with TestClient(app) as client:
        headers = auth_headers(client)
        created = client.post("/api/campaigns", headers=headers, json={"name": "Boundary campaign", "audience_size": 100, "channels": ["东航App"]})
        assert created.status_code == 201
        campaign_id = created.json()["id"]
        versions = client.get(f"/api/campaigns/{campaign_id}/versions", headers=headers).json()
        version_id = versions[0]["id"]

        first_approval = client.post(f"/api/campaigns/{campaign_id}/versions/{version_id}/approval", headers=headers)
        assert first_approval.status_code == 201
        duplicate_approval = client.post(f"/api/campaigns/{campaign_id}/versions/{version_id}/approval", headers=headers)
        assert duplicate_approval.status_code == 409

        decision = client.post(f"/api/approvals/{first_approval.json()['id']}/decision", headers=headers, json={"decision": "reject", "comment": "需要补充内容"})
        assert decision.status_code == 200

        resubmitted = client.post(f"/api/campaigns/{campaign_id}/versions/{version_id}/approval", headers=headers)
        assert resubmitted.status_code == 201
        assert resubmitted.json()["external_id"].endswith("-R2")

        archived = client.post(f"/api/campaigns/{campaign_id}/archive", headers=headers)
        assert archived.status_code == 200
        new_version = client.post(f"/api/campaigns/{campaign_id}/versions", headers=headers, json={"status": "草稿"})
        assert new_version.status_code == 409


def test_campaign_update_persists_editable_version_configuration():
    with TestClient(app) as client:
        headers = auth_headers(client)
        created = client.post("/api/campaigns", headers=headers, json={"name": "Configuration campaign", "audience_size": 100, "channels": ["短信"]})
        assert created.status_code == 201
        campaign_id = created.json()["id"]
        updated = client.put(f"/api/campaigns/{campaign_id}", headers=headers, json={"name": "Configuration campaign updated", "stage": "创建", "audience_size": 888, "budget_yuan": 12000, "channels": ["东航App", "微信"]})
        assert updated.status_code == 200
        version = client.get(f"/api/campaigns/{campaign_id}/versions", headers=headers).json()[0]
        assert version["budget_yuan"] == 12000
        assert version["channels"] == ["东航App", "微信"]
