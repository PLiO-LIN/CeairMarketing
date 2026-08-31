from fastapi.testclient import TestClient
from app.main import app

def test_persona_catalog_is_available_to_current_tenant():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"}).json()
        headers = {"Authorization": "Bearer " + login["access_token"], "X-Tenant-ID": str(login["tenants"][0]["id"])}
        dimensions = client.get("/api/persona-dimensions", headers=headers)
        segments = client.get("/api/persona-segments", headers=headers)
        assert dimensions.status_code == 200
        assert segments.status_code == 200
        assert len(dimensions.json()) >= 96
        assert len(segments.json()) >= 17
        assert all("field_code" in item for item in dimensions.json())
        assert all("rules" in item for item in segments.json())
