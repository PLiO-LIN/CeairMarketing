"""Reusable legal configurations for lifecycle tests; use the actual review endpoint."""


def approved_materials(client, headers, campaign_id, audience_id, channels):
    product = client.post("/api/product-packages", headers=headers, json={"name": "测试已审批产品", "description": "行李权益", "status": "已审批"}).json()
    assets = []
    for channel in channels:
        asset = client.post("/api/content-assets", headers=headers, json={"name": "测试渠道内容", "campaign_id": campaign_id, "audience_package_id": audience_id, "product_package_id": product["id"], "channel": channel, "title": "出行推荐", "body": "适用条件以已审核规则为准", "status": "待审核"}).json()
        review = client.post(f"/api/content-assets/{asset['id']}/review", headers=headers, json={"decision": "approve", "comment": "测试事实、渠道格式均核验"})
        assert review.status_code == 200, review.text
        assets.append(asset["id"])
    return {"product_package_id": product["id"], "content_asset_ids": assets}


def complete_campaign(client, headers, campaign_id, channels=("App",)):
    audience = client.post("/api/audience-packages", headers=headers, json={"name": "测试聚合客群", "estimated_size": 1000, "status": "可用", "expression": {"destination": "三亚"}}).json()
    snapshot = client.post(f"/api/audience-packages/{audience['id']}/snapshots", headers=headers).json()
    materials = approved_materials(client, headers, campaign_id, audience["id"], channels)
    campaign = client.get(f"/api/campaigns/{campaign_id}", headers=headers).json()
    saved = client.put(f"/api/campaigns/{campaign_id}", headers=headers, json={"name": campaign["name"], "audience_snapshot_id": snapshot["id"], "budget_yuan": 50000, "channels": list(channels), **materials})
    assert saved.status_code == 200, saved.text
    return materials
