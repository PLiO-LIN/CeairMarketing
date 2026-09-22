from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.db_models import TenantMembershipRecord, TenantRecord, UserRecord


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert login.status_code == 200
    body = login.json()
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "X-Tenant-ID": str(body["tenants"][0]["id"]),
    }


def test_business_objects_support_full_field_updates() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        campaigns = client.get("/api/campaigns", headers=headers).json()
        campaign_id = campaigns[0]["id"]

        product = client.post(
            "/api/product-packages",
            headers=headers,
            json={
                "name": "编辑测试产品包",
                "product_type": "辅营组合",
                "description": "机票 + 预付费行李",
                "eligibility": "SHA-SYX，经济舱可售",
                "version": "V1",
                "status": "草稿",
                "valid_from": None,
                "valid_to": None,
            },
        )
        assert product.status_code == 201
        product_id = product.json()["id"]
        updated_product = client.put(
            f"/api/product-packages/{product_id}",
            headers=headers,
            json={
                "name": "编辑测试产品包 V2",
                "product_type": "卡券权益",
                "description": "机票 + 行李 + 优选座位券",
                "eligibility": "国庆期间指定航线和渠道可用",
                "version": "V2",
                "status": "可用",
                "valid_from": None,
                "valid_to": None,
            },
        )
        assert updated_product.status_code == 200
        assert updated_product.json()["description"] == "机票 + 行李 + 优选座位券"

        content = client.post(
            "/api/content-assets",
            headers=headers,
            json={
                "campaign_id": campaign_id,
                "name": "编辑测试内容",
                "channel": "App",
                "version": "V1",
                "title": "出行权益",
                "body": "原始内容",
                "status": "草稿",
                "generated_by": "manual",
            },
        )
        assert content.status_code == 201
        content_id = content.json()["id"]
        updated_content = client.put(
            f"/api/content-assets/{content_id}",
            headers=headers,
            json={
                "campaign_id": campaign_id,
                "name": "编辑测试内容 V2",
                "channel": "微信",
                "version": "V2",
                "title": "三亚亲子出行权益包",
                "body": "完整的多渠道营销正文、权益说明和使用限制。",
                "status": "待审核",
                "generated_by": "content-generation",
            },
        )
        assert updated_content.status_code == 200
        assert updated_content.json()["body"].startswith("完整的多渠道")
        assert updated_content.json()["channel"] == "微信"

        opportunity = client.post(
            "/api/opportunities",
            headers=headers,
            json={"name": "编辑测试机会", "market_scope": "国内", "route": "SHA-SYX"},
        )
        assert opportunity.status_code == 201
        opportunity_id = opportunity.json()["id"]
        updated_opportunity = client.put(
            f"/api/opportunities/{opportunity_id}",
            headers=headers,
            json={
                "name": "编辑测试机会 V2",
                "market_scope": "会员经营",
                "route": "SHA-SYX",
                "signal_summary": "客座率下降、搜索热度上升、辅营购买空间明显",
                "status": "已确认",
                "score": 88,
                "estimated_audience": 12000,
                "estimated_revenue_yuan": 680000,
                "owner": "营销运营",
            },
        )
        assert updated_opportunity.status_code == 200
        assert updated_opportunity.json()["score"] == 88
        assert updated_opportunity.json()["estimated_revenue_yuan"] == 680000

        tag = client.post(
            "/api/audience-tags",
            headers=headers,
            json={
                "code": "EDIT-TEST-TAG",
                "name": "编辑测试标签",
                "category": "出行行为",
                "source": "画像接口",
                "description": "原始说明",
                "enabled": True,
            },
        )
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        updated_tag = client.put(
            f"/api/audience-tags/{tag_id}",
            headers=headers,
            json={
                "code": "EDIT-TEST-TAG-V2",
                "name": "编辑测试标签 V2",
                "category": "会员价值",
                "source": "用户画像数据空间",
                "description": "可用于高意向未购客群组合",
                "enabled": False,
            },
        )
        assert updated_tag.status_code == 200
        assert updated_tag.json()["description"] == "可用于高意向未购客群组合"
        assert updated_tag.json()["enabled"] is False
        reenabled_tag = client.put(f"/api/audience-tags/{tag_id}", headers=headers, json={**updated_tag.json(), "enabled": True})
        assert reenabled_tag.status_code == 200

        audience = client.post(
            "/api/audience-packages",
            headers=headers,
            json={
                "name": "编辑测试客群包",
                "selection_mode": "tag-combination",
                "tag_ids": [tag_id],
                "expression": {},
                "estimated_size": 2000,
                "status": "草稿",
            },
        )
        assert audience.status_code == 201
        audience_id = audience.json()["id"]
        updated_audience = client.put(
            f"/api/audience-packages/{audience_id}",
            headers=headers,
            json={
                "name": "编辑测试客群包 V2",
                "selection_mode": "ai-selection",
                "tag_ids": [],
                "expression": {"route": "SHA-SYX", "travel_intent": "high"},
                "estimated_size": 2600,
                "status": "可用",
            },
        )
        assert updated_audience.status_code == 200
        assert updated_audience.json()["expression"]["travel_intent"] == "high"
        assert updated_audience.json()["estimated_size"] == 2600


def test_campaign_editor_saves_and_clears_all_associations() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        product = client.post("/api/product-packages", headers=headers, json={"name": "编辑关联产品"}).json()
        audience = client.post("/api/audience-packages", headers=headers, json={
            "name": "编辑关联客群", "expression": {"route": "SHA-SYX"}, "estimated_size": 450,
        }).json()
        snapshot = client.post(f"/api/audience-packages/{audience['id']}/snapshots", headers=headers).json()
        content = client.post("/api/content-assets", headers=headers, json={"name": "编辑关联文案", "body": "完整正文"}).json()
        campaign = client.post("/api/campaigns", headers=headers, json={"name": "编辑关联活动"}).json()
        url = f"/api/campaigns/{campaign['id']}"
        response = client.put(url, headers=headers, json={
            "name": campaign["name"], "audience_snapshot_id": snapshot["id"],
            "product_package_id": product["id"], "content_asset_ids": [content["id"]],
            "channels": ["微信", "短信"], "budget_yuan": 30000, "roi_target": 4.5,
        })
        assert response.status_code == 200
        assert response.json()["audience_size"] == 450
        assert response.json()["product_package"] == product["name"]
        version = client.get(url + "/versions", headers=headers).json()[0]
        assert version["content_asset_ids"] == [content["id"]]
        assert version["audience_snapshot_id"] == snapshot["id"]
        assert version["product_package_id"] == product["id"]
        assert version["channels"] == ["微信", "短信"]
        assert version["budget_yuan"] == 30000
        cleared = client.put(url, headers=headers, json={
            "name": campaign["name"], "audience_snapshot_id": None, "product_package_id": None,
            "content_asset_ids": [], "channels": [], "audience_size": 0,
        })
        assert cleared.status_code == 200
        assert cleared.json()["product_package"] == ""
        version = client.get(url + "/versions", headers=headers).json()[0]
        assert version["audience_snapshot_id"] is None
        assert version["product_package_id"] is None
        assert version["content_asset_ids"] == []
        assert version["channels"] == []


def test_product_date_errors_do_not_overwrite_saved_values() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        product = client.post("/api/product-packages", headers=headers, json={
            "name": "有效期测试产品", "valid_from": "2026-10-01T00:00:00+08:00", "valid_to": "2026-10-08T00:00:00+08:00",
        }).json()
        invalid = {**product, "description": "不应该保存", "valid_to": "2026-09-01T00:00:00+08:00"}
        response = client.put(f"/api/product-packages/{product['id']}", headers=headers, json=invalid)
        assert response.status_code == 422
        saved = next(item for item in client.get("/api/product-packages", headers=headers).json() if item["id"] == product["id"])
        assert saved["description"] == product["description"]
        assert saved["valid_to"] == product["valid_to"]
        assert client.post("/api/product-packages", headers=headers, json=invalid).status_code == 422


def test_audience_edit_validates_tenant_tags_and_keeps_existing_disabled_tags() -> None:
    with SessionLocal() as session:
        admin = session.query(UserRecord).filter(UserRecord.username == "admin").one()
        tenant = TenantRecord(name="编辑隔离租户", code="EDIT-ISOLATED")
        session.add(tenant)
        session.flush()
        foreign_id = tenant.id
        session.add(TenantMembershipRecord(tenant_id=foreign_id, user_id=admin.id, role="admin"))
        session.commit()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        foreign_headers = {**headers, "X-Tenant-ID": str(foreign_id)}
        foreign_tag = client.post("/api/audience-tags", headers=foreign_headers, json={"code": "FOREIGN-TAG", "name": "其他租户标签"}).json()
        tag = client.post("/api/audience-tags", headers=headers, json={"code": "DISABLE-EDIT", "name": "停用标签测试"}).json()
        package = client.post("/api/audience-packages", headers=headers, json={"name": "标签保留客群", "tag_ids": [tag["id"]], "status": "可用"}).json()
        assert client.put(f"/api/audience-tags/{tag['id']}", headers=headers, json={**tag, "enabled": False}).status_code == 200
        url = f"/api/audience-packages/{package['id']}"
        assert client.put(url, headers=headers, json={**package, "estimated_size": 80}).status_code == 200
        assert client.post("/api/audience-packages", headers=headers, json={**package, "name": "禁止新增停用标签"}).status_code == 422
        assert client.put(url, headers=headers, json={**package, "tag_ids": [foreign_tag["id"]]}).status_code == 400
        assert client.put(url, headers=headers, json={**package, "selection_mode": "ai-selection", "expression": {}}).status_code == 422
        saved = next(item for item in client.get("/api/audience-packages", headers=headers).json() if item["id"] == package["id"])
        assert saved["tag_ids"] == [tag["id"]]
        assert saved["estimated_size"] == 80


def test_model_edit_preserves_key_and_returns_validation_conflicts() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        provider = client.post("/api/model-providers", headers=headers, json={
            "display_name": "编辑模型测试", "provider_type": "mock", "model_name": "mock-model", "api_key": "test-key-not-real",
        }).json()
        url = f"/api/model-providers/{provider['id']}"
        response = client.put(url, headers=headers, json={"api_key": "", "timeout_seconds": 80, "max_tokens": 4096})
        assert response.status_code == 200
        assert response.json()["api_key_configured"] is True
        assert response.json()["max_tokens"] == 4096
        assert response.json()["timeout_seconds"] == 80
        assert "api_key" not in response.json()
        duplicate = client.post("/api/model-providers", headers=headers, json={"display_name": "重复模型测试", "provider_type": "mock", "model_name": "mock-model"}).json()
        assert client.put(url, headers=headers, json={"display_name": duplicate["display_name"]}).status_code == 409
        assert client.put(url, headers=headers, json={"provider_type": "openai-compatible", "base_url": ""}).status_code == 422
        assert client.put(url, headers=headers, json={"model_name": None}).status_code == 422


def test_content_edit_retains_provenance_and_requires_review_after_changes() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        asset = client.post("/api/content-assets", headers=headers, json={
            "name": "审核状态测试文案", "body": "审核前正文", "generated_by": "content-generation", "status": "已审核",
        }).json()
        url = f"/api/content-assets/{asset['id']}"
        updated = client.put(url, headers=headers, json={**asset, "body": "修订后的正文\n需要重新审核", "generated_by": "manual"})
        assert updated.status_code == 200
        assert updated.json()["body"] == "修订后的正文\n需要重新审核"
        assert updated.json()["generated_by"] == "content-generation"
        assert updated.json()["status"] == "草稿"
        assert client.put(url, headers=headers, json={**updated.json(), "status": "已发布"}).status_code == 422


def test_approval_references_protect_product_and_content_from_in_place_edits() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        product = client.post("/api/product-packages", headers=headers, json={"name": "审批保护产品"}).json()
        asset = client.post("/api/content-assets", headers=headers, json={"name": "审批保护内容", "body": "提交审核的正文"}).json()
        campaign = client.post("/api/campaigns", headers=headers, json={"name": "审批保护活动", "channels": ["App"]}).json()
        url = f"/api/campaigns/{campaign['id']}"
        response = client.put(url, headers=headers, json={"name": campaign["name"], "product_package_id": product["id"], "content_asset_ids": [asset["id"]]})
        assert response.status_code == 200
        version = client.get(url + "/versions", headers=headers).json()[0]
        assert client.post(url + f"/versions/{version['id']}/approval", headers=headers).status_code == 201
        assert client.put(f"/api/content-assets/{asset['id']}", headers=headers, json={**asset, "body": "不能绕过审批修改"}).status_code == 409
        assert client.put(f"/api/product-packages/{product['id']}", headers=headers, json={**product, "eligibility": "不能绕过审批修改"}).status_code == 409
