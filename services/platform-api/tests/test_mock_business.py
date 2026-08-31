from fastapi.testclient import TestClient
from app.main import app

def login(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert response.status_code == 200
    body = response.json()
    tenant = body["tenants"][0]
    return {"Authorization": "Bearer " + body["access_token"], "X-Tenant-ID": str(tenant["id"])}

def test_mock_business_sources_are_authenticated_and_deterministic():
    with TestClient(app) as client:
        unauthorized = client.get("/api/mock/flight-operations")
        assert unauthorized.status_code == 401
        headers = login(client)
        for path in ["/api/mock/flight-operations", "/api/mock/profile-summary", "/api/mock/market-signals", "/api/mock/product-catalog"]:
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json()["source"] == "ceair-mock-business-v1"
        delivery = client.post("/api/mock/channels/sms/deliver?audience_size=1000&campaign_id=MOCK-001", headers=headers)
        assert delivery.status_code == 200
        assert delivery.json()["metrics"]["target"] == 1000
        assert delivery.json()["metrics"]["delivered"] == 982
