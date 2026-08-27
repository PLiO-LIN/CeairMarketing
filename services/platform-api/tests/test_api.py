import json

from fastapi.testclient import TestClient

from app.main import app


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
        assert client.get("/api/model-providers", headers=headers(auth, hq["id"])).json()
        assert client.get("/api/model-providers", headers=headers(auth, ecom["id"])).json() == []


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
            "AudienceSnapshot",
            "ProductPackage",
            "ContentAsset",
            "Campaign",
            "ApprovalTask",
            "ExecutionBatch",
            "Feedback",
            "Review",
            "ConfigurableAttribute",
        }.issubset(object_types)
        assert model["agent_contracts"]["product-match"]["functions"]
        assert model["lifecycle"] == [
            "data",
            "opportunity",
            "audience",
            "product",
            "content",
            "campaign",
            "approval",
            "execution",
            "feedback",
            "review",
        ]

        entities = [
            {
                "external_id": "market-signal-test-001",
                "entity_type": "MarketSignal",
                "label": "??????",
                "attributes": {"signal_type": "trend", "valid_to": "2026-09-30"},
                "source": "??????",
                "confidence": 0.9,
            },
            {
                "external_id": "attribute-test-001",
                "entity_type": "ConfigurableAttribute",
                "label": "???????",
                "attributes": {"source_mode": "existing_profile_api"},
                "source": "??????",
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
        assert status["semantic_model_version"] == "ceair-marketing-ontology-v1.0"
        assert status["registered_instance_types"]["MarketSignal"] >= 1
        assert status["registered_instance_types"]["ConfigurableAttribute"] >= 1

        graph = client.get("/api/graph", headers=request_headers).json()
        graph_types = {node["type"] for node in graph["nodes"]}
        assert {"MarketingCase", "ApprovalTask", "ExecutionBatch", "Review"}.issubset(graph_types)
        graph_relations = {edge["relation"] for edge in graph["edges"]}
        assert {
            "has_campaign_version",
            "requires_approval",
            "produces_feedback",
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
        auth, tenants = login(client)
        hq = next(item for item in tenants if item["code"] == "CEA-HQ")
        request_headers = headers(auth, hq["id"])
        payload = "上海—三亚航线国庆客座率和目的地热度出现变化，建议关注高意向未购客群。"
        response = client.post(
            "/api/data-pipelines",
            headers=request_headers,
            files={"file": ("route-signal.txt", payload.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["job"]["status"] == "completed"
        assert result["job"]["accepted_entities"] >= 1
        assert {"received", "extracted", "classified", "ontology-updated"}.issubset({item["stage"] for item in result["stages"] if "stage" in item})

        knowledge = client.get("/api/knowledge/search", headers=request_headers, params={"q": "三亚航线"})
        assert knowledge.status_code == 200
        assert knowledge.json()
