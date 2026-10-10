"""生产阻断与业务完整性的回归覆盖。

对应审查报告 P0-03 / P0-04 / P1-01 / P1-02 / P2-06，逐条锁住"改坏了也能被发现"的行为：
归档活动的审计链、洞察来源的 SSRF 入口校验、执行批次状态机、渠道回执单调约束，
以及多租户用户必须显式选择租户。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from fixtures_business import complete_campaign
from app.main import app


def login(client: TestClient) -> tuple[dict[str, str], list[dict]]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["tenants"]


def headers(auth: dict[str, str], tenant_id: int) -> dict[str, str]:
    return {**auth, "X-Tenant-ID": str(tenant_id)}


def approved_batch(client: TestClient, request_headers: dict[str, str]) -> tuple[int, int, int, str]:
    """按仓库既有的合法业务夹具造一个可审批的活动，返回 (批次 id, 渠道任务 id, 版本 id, 活动 id)。

    复用 fixtures_business.complete_campaign，避免在本文件里重抄"产品已审批 +
    内容已审核 + 逐渠道覆盖"这套就绪规则。
    """
    channels = ["东航App", "短信"]
    created = client.post(
        "/api/campaigns",
        headers=request_headers,
        json={"name": f"生产阻断回归 {uuid4().hex[:8]}", "audience_size": 1000, "budget_yuan": 50000, "channels": channels},
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    complete_campaign(client, request_headers, campaign_id, tuple(channels))

    version = client.get(f"/api/campaigns/{campaign_id}/versions", headers=request_headers).json()[0]
    approval = client.post(f"/api/campaigns/{campaign_id}/versions/{version['id']}/approval", headers=request_headers)
    assert approval.status_code == 201, approval.text
    decision = client.post(f"/api/approvals/{approval.json()['id']}/decision", headers=request_headers, json={"decision": "approve", "comment": "回归通过"})
    assert decision.status_code == 200, decision.text

    batch = next(item for item in client.get("/api/execution-batches", headers=request_headers).json() if item["campaign_id"] == campaign_id)
    tasks = [item for item in client.get("/api/channel-tasks", headers=request_headers).json() if item["batch_id"] == batch["id"]]
    return batch["id"], tasks[0]["id"], version["id"], campaign_id


def test_insight_source_rejects_internal_addresses() -> None:
    """SSRF 的入口校验：内网、元数据地址、非 HTTP 协议都必须在创建来源时被拒。"""
    restricted = [
        "http://127.0.0.1/feed",
        "http://localhost:6379/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.8/rss",
        "http://192.168.1.1/upnp",
        "http://[::1]/feed",
        "file:///etc/passwd",
    ]
    with TestClient(app) as client:
        auth, tenants = login(client)
        request_headers = headers(auth, tenants[0]["id"])
        for index, url in enumerate(restricted):
            response = client.post(
                "/api/opportunity-insight/sources",
                headers=request_headers,
                json={"name": f"越权来源 {index}", "source_url": url, "source_type": "web", "schedule": "manual", "focus": "测试"},
            )
            assert response.status_code == 422, (url, response.text)
            assert "受限网络" in response.text or "http 或 https" in response.text, (url, response.text)


def test_batch_status_machine_rejects_illegal_transitions() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        request_headers = headers(auth, tenants[0]["id"])
        batch_id, _task_id, _version_id, _campaign_id = approved_batch(client, request_headers)

        # 待执行 → 已完成 不允许跳过执行期
        skip = client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "已完成"})
        assert skip.status_code == 409, skip.text

        assert client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "执行中"}).status_code == 200
        assert client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "已完成"}).status_code == 200

        # 终态不可逆
        reopen = client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "待执行"})
        assert reopen.status_code == 409, reopen.text
        assert client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "未知状态"}).status_code == 422


def test_channel_receipts_are_monotonic() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        request_headers = headers(auth, tenants[0]["id"])
        _batch_id, task_id, _version_id, _campaign_id = approved_batch(client, request_headers)

        # 点击不得大于送达
        bad = client.post(f"/api/channel-tasks/{task_id}/feedback", headers=request_headers, json={"sent_count": 10, "delivered_count": 5, "clicked_count": 8, "converted_count": 1, "failed_count": 0})
        assert bad.status_code == 422, bad.text
        # 转化不得大于点击
        bad2 = client.post(f"/api/channel-tasks/{task_id}/feedback", headers=request_headers, json={"sent_count": 10, "delivered_count": 5, "clicked_count": 3, "converted_count": 4, "failed_count": 0})
        assert bad2.status_code == 422, bad2.text
        # 失败 + 送达不得超过发送数
        bad3 = client.post(f"/api/channel-tasks/{task_id}/feedback", headers=request_headers, json={"sent_count": 10, "delivered_count": 6, "clicked_count": 2, "converted_count": 1, "failed_count": 5})
        assert bad3.status_code == 422, bad3.text
        # 负数
        assert client.post(f"/api/channel-tasks/{task_id}/feedback", headers=request_headers, json={"sent_count": -1}).status_code == 422
        # 合法回执
        ok = client.post(f"/api/channel-tasks/{task_id}/feedback", headers=request_headers, json={"sent_count": 10, "delivered_count": 6, "clicked_count": 2, "converted_count": 1, "failed_count": 4})
        assert ok.status_code == 200, ok.text
        assert ok.json()["delivered_count"] == 6


def test_archived_campaign_keeps_its_audit_chain() -> None:
    """已归档活动的审批链与执行留痕必须保留，物理删除要挡下来。"""
    with TestClient(app) as client:
        auth, tenants = login(client)
        request_headers = headers(auth, tenants[0]["id"])
        batch_id, _task_id, version_id, campaign_id = approved_batch(client, request_headers)
        assert client.post(f"/api/execution-batches/{batch_id}/status", headers=request_headers, json={"status": "执行中"}).status_code == 200

        archived = client.post(f"/api/campaigns/{campaign_id}/archive", headers=request_headers)
        assert archived.status_code == 200, archived.text
        blocked = client.delete(f"/api/campaigns/{campaign_id}", headers=request_headers)
        assert blocked.status_code == 409, blocked.text

        approvals = client.get("/api/approvals", headers=request_headers).json()
        assert version_id in {item["campaign_version_id"] for item in approvals}
        batches = client.get("/api/execution-batches", headers=request_headers).json()
        assert any(item["id"] == batch_id for item in batches)


def test_multi_tenant_user_must_name_a_tenant() -> None:
    """多租户用户不给 X-Tenant-ID 就不能默认落到第一个租户。"""
    with TestClient(app) as client:
        auth, tenants = login(client)
        if len(tenants) < 2:
            pytest.skip("登录用户只有一个租户")
        ambiguous = client.get("/api/campaigns", headers=auth)
        assert ambiguous.status_code == 400, ambiguous.text
        explicit = client.get("/api/campaigns", headers={**auth, "X-Tenant-ID": str(tenants[0]["id"])})
        assert explicit.status_code == 200, explicit.text
