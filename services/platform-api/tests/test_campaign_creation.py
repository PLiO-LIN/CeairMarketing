from fastapi.testclient import TestClient
from app.main import app

def test_campaign_creation_persists_tenant_scoped_draft():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
        assert login.status_code == 200
        body = login.json()
        headers = {"Authorization": "Bearer " + body["access_token"], "X-Tenant-ID": str(body["tenants"][0]["id"])}
        created = client.post("/api/campaigns", headers=headers, json={"name": "Mock航线辅营组合活动", "stage": "机会", "audience_size": 12000, "product_package": "行李优享", "budget_yuan": 80000, "roi_target": 3.5})
        assert created.status_code == 201
        item = created.json()
        assert item["id"].startswith("ACT-")
        assert item["status"] == "草稿"
        assert item["owner"] == "平台管理员"
        listed = client.get("/api/campaigns", headers=headers)
        assert any(value["id"] == item["id"] for value in listed.json())
