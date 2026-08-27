import json

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.db_models import ModelProviderRecord
from app.ontology import validate_relation_endpoints
from app.ontology.bootstrap import LIFECYCLE_ENTITIES, LIFECYCLE_RELATIONS


def login(client: TestClient) -> tuple[dict[str, str], list[dict]]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["tenants"]


def headers(auth: dict[str, str], tenant_id: int) -> dict[str, str]:
    return {**auth, "X-Tenant-ID": str(tenant_id)}


def test_tenant_isolation_and_agent_runtime() -> None:
    with TestClient(app) as client:
        assert client.get("/api/campaigns").status_code == 401
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        ecom = next(item for item in tenants if item["code"] == "CEA-ECOM")
        campaigns = client.get("/api/campaigns", headers=headers(auth, hq["id"]))
        assert any(item["id"] == "ACT-2026-0921" for item in campaigns.json())
        assert all(item["id"] != "ACT-2026-0921" for item in client.get("/api/campaigns", headers=headers(auth, ecom["id"])).json())
        response = client.post("/api/agent-runs", headers=headers(auth, hq["id"]), json={"campaign_id": "ACT-2026-0921", "domain_id": "product-match"})
        assert response.status_code == 200
        event_types = [event["event_type"] for event in response.json()["events"]]
        assert "model/provider-selected" in event_types
        assert "ontology/context-loaded" in event_types
        isolated = client.post("/api/agent-runs", headers=headers(auth, ecom["id"]), json={"campaign_id": "ACT-2026-0921", "domain_id": "product-match"})
        assert isolated.json()["status"] == "failed"


def test_import_builds_dynamic_graph() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        request_headers = headers(auth, hq["id"])
        entities = [
            {"external_id": "customer-import-001", "entity_type": "Customer", "label": "上海高频商务旅客", "attributes": {"tier": "Gold"}, "source": "用户画像平台", "confidence": 0.95},
            {"external_id": "product-import-001", "entity_type": "Product", "label": "京沪快线优享包", "attributes": {"route": "SHA-PEK"}, "source": "产品管理平台", "confidence": 1.0},
        ]
        imported = client.post("/api/imports", headers=request_headers, data={"dataset_type": "entities"}, files={"file": ("entities.json", json.dumps(entities, ensure_ascii=False).encode(), "application/json")})
        assert imported.status_code == 201
        assert imported.json()["accepted_rows"] == 2
        relations = [{"source_external_id": "customer-import-001", "relation_type": "prefers", "target_external_id": "product-import-001", "evidence": "近90日京沪往返6次", "confidence": 0.91}]
        linked = client.post("/api/imports", headers=request_headers, data={"dataset_type": "relations"}, files={"file": ("relations.json", json.dumps(relations, ensure_ascii=False).encode(), "application/json")})
        assert linked.status_code == 201
        graph = client.get("/api/graph", headers=request_headers).json()
        assert {"customer-import-001", "product-import-001"}.issubset({item["id"] for item in graph["nodes"]})
        assert any(item["relation"] == "prefers" for item in graph["edges"])


def test_model_providers_are_tenant_scoped() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        ecom = next(item for item in tenants if item["code"] == "CEA-ECOM")
        providers = client.get("/api/model-providers", headers=headers(auth, hq["id"])).json()
        assert providers
        assert all("api_key" not in provider and "encrypted_api_key" not in provider for provider in providers)
        provider = next(item for item in providers if item["provider_type"] == "mock")
        provider_id = provider["id"]
        discovered = client.get(f"/api/model-providers/{provider_id}/models", headers=headers(auth, hq["id"]))
        assert discovered.status_code == 200
        assert discovered.json()["models"][0]["id"] == provider["model_name"]
        tested = client.post(f"/api/model-providers/{provider_id}/test", headers=headers(auth, hq["id"]))
        assert tested.status_code == 200
        usage = client.get(f"/api/model-providers/{provider_id}/usage", headers=headers(auth, hq["id"]))
        assert usage.status_code == 200
        assert usage.json()["request_count"] >= 1
        assert usage.json()["total_tokens"] >= 1
        assert client.get("/api/model-providers", headers=headers(auth, ecom["id"])).json() == []
        assert client.get(f"/api/model-providers/{provider_id}/usage", headers=headers(auth, ecom["id"])).status_code == 404


def test_marketing_ontology_semantic_contract() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        request_headers = headers(auth, hq["id"])

        response = client.get("/api/ontology/semantic-model", headers=request_headers)
        assert response.status_code == 200
        model = response.json()
        object_types = {item["id"] for item in model["object_types"]}
        assert {
            "MarketingCase",
            "Opportunity",
            "MarketingObjective",
            "CustomerNeed",
            "AudienceSnapshot",
            "ProductPackage",
            "ValueProposition",
            "StrategyPlan",
            "TouchpointPlan",
            "ContentAsset",
            "Campaign",
            "ApprovalTask",
            "ExecutionBatch",
            "Feedback",
            "AttributionResult",
            "Review",
            "ConfigurableAttribute",
        }.issubset(object_types)
        assert model["agent_contracts"]["product-match"]["functions"]
        assert model["lifecycle"] == [
            "data",
            "opportunity",
            "objective",
            "audience",
            "value",
            "product",
            "strategy",
            "content",
            "approval",
            "execution",
            "feedback",
            "attribution",
            "review",
        ]

        lifecycle_types = {item[0]: item[1] for item in LIFECYCLE_ENTITIES}
        assert all(validate_relation_endpoints(relation, lifecycle_types[source], lifecycle_types[target]) is None for source, relation, target, _, _ in LIFECYCLE_RELATIONS)

        entities = [
            {
                "external_id": "market-signal-test-001",
                "entity_type": "MarketSignal",
                "label": "三亚目的地热度信号",
                "attributes": {"signal_type": "trend", "valid_to": "2026-09-30"},
                "source": "市场数据接入",
                "confidence": 0.9,
            },
            {
                "external_id": "attribute-test-001",
                "entity_type": "ConfigurableAttribute",
                "label": "会员出行偏好属性",
                "attributes": {"source_mode": "existing_profile_api"},
                "source": "市场数据接入",
                "confidence": 1.0,
            },
        ]
        imported = client.post(
            "/api/imports",
            headers=request_headers,
            data={"dataset_type": "entities"},
            files={
                "file": (
                    "semantic-entities.json",
                    json.dumps(entities, ensure_ascii=False).encode(),
                    "application/json",
                )
            },
        )
        assert imported.status_code == 201
        assert imported.json()["accepted_rows"] == 2

        status_response = client.get("/api/ontology/status", headers=request_headers)
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["semantic_model_version"] == "ceair-marketing-ontology-v1.1"
        assert status["registered_instance_types"]["MarketSignal"] >= 1
        assert status["registered_instance_types"]["ConfigurableAttribute"] >= 1

        graph = client.get("/api/graph", headers=request_headers).json()
        graph_types = {node["type"] for node in graph["nodes"]}
        assert {"MarketingCase", "MarketingObjective", "CustomerNeed", "ValueProposition", "StrategyPlan", "TouchpointPlan", "ApprovalTask", "ExecutionBatch", "AttributionResult", "Review"}.issubset(graph_types)
        graph_relations = {edge["relation"] for edge in graph["edges"]}
        assert {
            "has_campaign_version",
            "requires_approval",
            "produces_feedback",
            "has_strategy_plan",
            "uses_touchpoint_plan",
            "produces_attribution",
            "attributes_to",
            "generates_recommendation",
        }.issubset(graph_relations)

        invalid_relation = [{
            "source_external_id": "market-signal-test-001",
            "relation_type": "has_tag_attribute",
            "target_external_id": "attribute-test-001",
            "confidence": 1.0,
        }]
        rejected = client.post(
            "/api/imports",
            headers=request_headers,
            data={"dataset_type": "relations"},
            files={
                "file": (
                    "invalid-semantic-relation.json",
                    json.dumps(invalid_relation).encode(),
                    "application/json",
                )
            },
        )
        assert rejected.status_code == 201
        assert rejected.json()["accepted_rows"] == 0
        assert rejected.json()["rejected_rows"] == 1
        assert "has_tag_attribute" in rejected.json()["errors"][0]["message"]


def test_data_pipeline_builds_knowledge_and_ontology() -> None:
    with TestClient(app) as client:
        with SessionLocal() as session:
            session.query(ModelProviderRecord).filter(ModelProviderRecord.provider_type == "openai-compatible").update({"enabled": False, "is_default": False})
            session.query(ModelProviderRecord).filter(ModelProviderRecord.provider_type == "mock").update({"enabled": True, "is_default": True})
            session.commit()
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        request_headers = headers(auth, hq["id"])
        payload = "上海—三亚航线国庆客座率和目的地热度出现变化，建议关注高意向未购客群。"
        response = client.post(
            "/api/data-pipelines",
            headers=request_headers,
            files={"file": ("route-signal.txt", payload.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 202
        result = response.json()
        assert result["job"]["status"] == "queued"
        assert result["stages"][0]["stage"] == "queued"

        job_response = client.get(f"/api/data-pipelines/{result['job']['id']}", headers=request_headers)
        assert job_response.status_code == 200
        job = job_response.json()
        assert job["status"] == "awaiting_confirmation"
        assert job["accepted_entities"] == 0
        assert job["total_entities"] >= 1
        assert {"received", "extracting", "extracted", "knowledge-persisting", "knowledge-ready", "agent-processing", "semantic-validation", "awaiting-confirmation"}.issubset(
            {item["stage"] for item in job["result"]["events"] if "stage" in item}
        )

        knowledge = client.get("/api/knowledge/search", headers=request_headers, params={"q": "三亚航线"})
        assert knowledge.status_code == 200
        assert knowledge.json()
        review = client.post(
            f"/api/data-pipelines/{result['job']['id']}/review",
            headers=request_headers,
            json={"decision": "approve", "note": "测试确认候选本体更新"},
        )
        assert review.status_code == 200
        reviewed_job = review.json()
        assert reviewed_job["status"] == "completed"
        assert reviewed_job["accepted_entities"] >= 1
        assert reviewed_job["result"]["review"]["decision"] == "approve"
        assert "ontology-updated" in {item["stage"] for item in reviewed_job["result"]["events"] if "stage" in item}

        knowledge_after_review = client.get("/api/knowledge/search", headers=request_headers, params={"q": "三亚航线"})
        assert knowledge_after_review.json()[0]["linked_objects"]


def test_marketing_copilot_uses_tools_and_sources() -> None:
    with TestClient(app) as client:
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        response = client.post(
            "/api/agent-chat",
            headers=headers(auth, hq["id"]),
            json={"message": "查询上海三亚航线相关营销机会和产品", "provider_id": 1},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"]
        event_types = {item["event"] for item in payload["trace"]}
        assert "harness/context-loaded" in event_types
        assert "harness/tool-started" in event_types
        assert isinstance(payload["sources"], list)
