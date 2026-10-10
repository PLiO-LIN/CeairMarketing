from fastapi.testclient import TestClient

from app.main import app
from tests.test_agent_api_robustness import login, tenant_headers


def test_stream_returns_real_tenant_context_and_complete_answer():
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item['code'] == 'CEA-HQ')
        response = client.post('/api/agent-chat/stream', headers=tenant_headers(auth, hq['id']), json={'message': '当前有哪些营销活动？', 'provider_id': 1})
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        assert 'event: trace' in response.text
        assert 'event: complete' in response.text
        assert '"answer":' in response.text
        assert '上海—三亚' in response.text
        assert 'event: error' not in response.text


def test_stream_reports_provider_errors_and_requires_tenant_authorization():
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item['code'] == 'CEA-HQ')
        response = client.post('/api/agent-chat/stream', headers=tenant_headers(auth, hq['id']), json={'message': '查询活动', 'provider_id': 999999})
        assert 'event: error' in response.text
        assert 'event: complete' not in response.text
        assert client.post('/api/agent-chat/stream', json={'message': '查询活动'}).status_code == 401
        assert client.post('/api/agent-chat/stream', headers=tenant_headers(auth, 999999), json={'message': '查询活动'}).status_code == 403


def test_stream_sanitizes_unexpected_provider_failures(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('Bearer secret-provider-key')

    monkeypatch.setattr('app.main.copilot.run', fail)
    with TestClient(app) as client:
        auth, tenants = login(client)
        response = client.post('/api/agent-chat/stream', headers=tenant_headers(auth, tenants[0]['id']), json={'message': '查询活动'})
        assert 'event: error' in response.text
        assert '参考编号' in response.text
        assert 'secret-provider-key' not in response.text


def test_chat_follows_saved_campaign_changes():
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item['code'] == 'CEA-HQ')
        headers = tenant_headers(auth, hq['id'])
        campaigns = client.get('/api/campaigns', headers=headers).json()
        original = next(item for item in campaigns if item['id'] == 'ACT-2026-0921')
        try:
            from app.database import SessionLocal
            from app.db_models import CampaignRecord
            with SessionLocal() as session:
                record = session.get(CampaignRecord, (hq['id'], original['id']))
                record.name = '后台联动验证活动'
                session.commit()
            response = client.post('/api/agent-chat/stream', headers=headers, json={'message': '查询活动 ACT-2026-0921', 'provider_id': 1})
            assert '后台联动验证活动' in response.text
        finally:
            with SessionLocal() as session:
                record = session.get(CampaignRecord, (hq['id'], original['id']))
                record.name = original['name']
                session.commit()
