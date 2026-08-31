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
