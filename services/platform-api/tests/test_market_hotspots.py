import json
from fastapi.testclient import TestClient
from app.main import app


def login(client):
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'Admin@12345'})
    assert response.status_code == 200
    payload = response.json()
    return {'Authorization': f"Bearer {payload['access_token']}"}, payload['tenants']


def headers(auth, tenant_id):
    return {**auth, 'X-Tenant-ID': str(tenant_id)}


def test_hotspot_ingest_deduplicates_and_requires_review():
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item['code'] == 'CEA-HQ')
        request_headers = headers(auth, hq['id'])
        payload = {
            'records': [{
                'source_name': '测试市场来源',
                'source_type': 'api',
                'source_url': 'https://example.test/feed',
                'title': '国庆上海至三亚航线搜索热度上升',
                'content': '三亚旅游热度与上海至三亚航线搜索、预订需求持续上升，适合评估机票、卡券和辅营产品机会。',
                'url': 'https://example.test/news/holiday?utm_source=test',
                'region': '国内',
            }],
            'process_with_agent': True,
        }
        created = client.post('/api/market-hotspots/ingest', headers=request_headers, json=payload)
        assert created.status_code == 202
        body = created.json()
        assert body['created'] == 1
        hotspot = body['hotspots'][0]
        assert hotspot['ontology_status'] == 'awaiting_confirmation'
        assert any(item['event'] == 'hotspot/classified' for item in hotspot['trace'])
        duplicate = client.post('/api/market-hotspots/ingest', headers=request_headers, json=payload)
        assert duplicate.status_code == 202
        assert duplicate.json()['duplicates'] == 1
        blocked = client.post(f"/api/market-hotspots/{hotspot['id']}/opportunity", headers=request_headers, json={})
        assert blocked.status_code == 409


def test_hotspot_reject_stays_out_of_ontology_and_tenant_isolation():
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item['code'] == 'CEA-HQ')
        request_headers = headers(auth, hq['id'])
        created = client.post('/api/market-hotspots/ingest', headers=request_headers, json={'records': [{
            'source_name': '测试市场来源2', 'source_type': 'manual', 'title': '上海机场中转服务需求增加',
            'content': '浦东机场国际中转和空铁联运关注度上升。', 'url': 'https://example.test/news/2'
        }]})
        assert created.status_code == 202
        hotspot = created.json()['hotspots'][0]
        rejected = client.post(f"/api/market-hotspots/{hotspot['id']}/review", headers=request_headers, json={'decision': 'reject', 'note': '仅作为市场证据保留'})
        assert rejected.status_code == 200
        assert rejected.json()['ontology_status'] == 'rejected'
        assert client.get(f"/api/market-hotspots/{hotspot['id']}", headers=headers(auth, 999999)).status_code in {401, 403, 404}


def test_atom_feed_parser():
    from app.market_hotspots import parse_feed
    xml = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>航线热度提升</title><link href="https://example.test/a"/><summary>上海至北京商务出行。</summary><published>2026-08-28T08:00:00Z</published></entry></feed>'.encode('utf-8')
    rows = parse_feed(xml, 'Atom测试', 'https://example.test/feed', 'atom')
    assert len(rows) == 1
    assert rows[0]['canonical_url'] == 'https://example.test/a'
