from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import TenantContext
from ..db_models import CampaignRecord, DataPipelineJobRecord, KnowledgeChunkRecord, KnowledgeDocumentRecord, ModelProviderRecord, ModelUsageRecord, OntologyEntityRecord, OntologyRelationRecord
from ..llm import LLMConfig
from ..models import AgentChatRequest, AgentChatResponse, AgentRunRequest
from ..security import SecretCipher
from .harness import HarnessContext, UnifiedHarness
from .runtime import AgentRuntime


class MarketingCopilot:
    def __init__(self) -> None:
        self._cipher: SecretCipher | None = None
        self._runtime = AgentRuntime()

    def run(self, session: Session, context: TenantContext, request: AgentChatRequest) -> AgentChatResponse:
        trace: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []

        def emit(event: str, payload: dict[str, Any]) -> None:
            trace.append({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **payload})

        provider = self._resolve_provider(session, context.tenant_id, request.provider_id)
        if provider is None:
            raise ValueError("当前租户未配置可用的大模型")
        run_id = f"CHAT-{uuid4().hex[:12].upper()}"
        harness = UnifiedHarness(emit)
        harness.load_context(HarnessContext(
            tenant_id=context.tenant_id,
            run_id=run_id,
            agent_id=request.domain_id,
            reads=["KnowledgeDocument", "KnowledgeChunk", "Opportunity", "CustomerAggregate", "Product", "Campaign", "AttributionResult"],
            writes=["Recommendation"],
            functions=["search_marketing_knowledge", "query_marketing_ontology", "inspect_campaign", "list_available_products", "inspect_data_pipeline", "run_marketing_domain"],
        ))
        harness.set_usage_recorder(lambda result: session.add(ModelUsageRecord(
            tenant_id=context.tenant_id,
            provider_id=provider.id,
            run_id=run_id,
            agent_id=request.domain_id,
            request_type="agent-chat",
            model_name=result.model_name or provider.model_name,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )))
        if provider.provider_type != "mock" and provider.encrypted_api_key:
            try:
                self._cipher = self._cipher or SecretCipher()
                api_key = self._cipher.decrypt(provider.encrypted_api_key)
            except RuntimeError:
                fallback = session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == context.tenant_id, ModelProviderRecord.enabled.is_(True), ModelProviderRecord.provider_type == "mock").order_by(ModelProviderRecord.id))
                if fallback is None:
                    raise
                provider = fallback
                api_key = ""
                emit("model/provider-fallback", provider=provider.display_name, reason="credential-unavailable")
        else:
            api_key = ""
        config = LLMConfig(provider.provider_type, provider.base_url, provider.model_name, api_key, provider.timeout_seconds, provider.temperature, provider.max_tokens)
        tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "search_marketing_knowledge": lambda args: self._search_knowledge(session, context.tenant_id, str(args.get("query") or request.message), sources),
            "query_marketing_ontology": lambda args: self._query_ontology(session, context.tenant_id, str(args.get("query") or request.message), sources),
            "inspect_campaign": lambda args: self._inspect_campaign(session, context.tenant_id, str(args.get("campaign_id") or ""), sources),
            "list_available_products": lambda args: self._list_products(session, context.tenant_id, str(args.get("query") or request.message), sources),
            "inspect_data_pipeline": lambda args: self._inspect_pipeline(session, context.tenant_id, str(args.get("job_id") or ""), sources),
            "run_marketing_domain": lambda args: self._run_domain(session, context, args, sources),
        }
        if provider.provider_type == "mock":
            observations = self._mock_observations(harness, tools, request.message)
            answer = self._mock_answer(request.message, observations)
        else:
            answer = self._agent_loop(harness, config, request, tools)
        session.commit()
        return AgentChatResponse(
            conversation_id=request.conversation_id or f"CONV-{uuid4().hex[:10].upper()}",
            answer=answer,
            provider_id=provider.id,
            model_name=provider.model_name,
            trace=trace,
            sources=self._deduplicate_sources(sources),
        )

    def _agent_loop(self, harness: UnifiedHarness, config: LLMConfig, request: AgentChatRequest, tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]]) -> str:
        observations: list[dict[str, Any]] = []
        history = [{"role": item.role, "content": item.content} for item in request.history[-12:]]
        system_prompt = (
            "你是东方航空智能营销平台的营销协同智能体。你必须先基于工具读取租户内真实知识、本体或活动数据，再回答业务问题。"
            "可用工具为 search_marketing_knowledge、query_marketing_ontology、inspect_campaign、list_available_products、inspect_data_pipeline、run_marketing_domain。"
            "run_marketing_domain可调用六大智能域，domain_id只能是opportunity-insight、audience-insight、product-match、activity-orchestration、content-generation、effect-analysis，且必须提供campaign_id。"
            "每一步只输出JSON：需要工具时输出{\"action\":工具名,\"arguments\":{...},\"reason\":原因}；"
            "信息充分时输出{\"action\":\"final\",\"answer\":\"结论\"}。"
            "不得杜撰旅客个人信息、产品库存、价格和活动结果；建议必须说明证据不足之处，并保留人工审核。"
        )
        for step in range(4):
            planner_input = json.dumps({"question": request.message, "history": history, "observations": observations, "step": step + 1}, ensure_ascii=False)
            try:
                decision = harness.generate_json(config, system_prompt, planner_input)
            except Exception:
                if not observations:
                    observations.append({"tool": "search_marketing_knowledge", "result": harness.run_tool("search_marketing_knowledge", lambda: tools["search_marketing_knowledge"]({"query": request.message}))})
                break
            action = str(decision.get("action") or "")
            if action == "final" and decision.get("answer"):
                return str(decision["answer"])
            if action not in tools:
                observations.append({"tool": action or "unknown", "error": "工具不在授权列表中"})
                continue
            arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
            result = harness.run_tool(action, lambda action=action, arguments=arguments: tools[action](arguments))
            observations.append({"tool": action, "reason": decision.get("reason", ""), "result": result})
        synthesis_prompt = json.dumps({"question": request.message, "history": history, "tool_observations": observations}, ensure_ascii=False)
        return harness.generate_text(
            config,
            "你是东航营销业务助手。仅根据工具观测回答，给出可执行结论、引用的数据依据、风险和需要人工确认的事项，不得编造。",
            synthesis_prompt,
        )

    def _mock_observations(self, harness: UnifiedHarness, tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]], message: str) -> list[dict[str, Any]]:
        selected = ["search_marketing_knowledge", "query_marketing_ontology"]
        if "活动" in message or "ACT-" in message.upper():
            selected.append("inspect_campaign")
        if any(word in message for word in ("产品", "卡券", "运价", "行李", "选座", "升舱")):
            selected.append("list_available_products")
        if any(word in message for word in ("流水线", "处理任务", "上传进度", "数据处理")):
            selected.append("inspect_data_pipeline")
        return [{"tool": name, "result": harness.run_tool(name, lambda name=name: tools[name]({"query": message}))} for name in selected]

    @staticmethod
    def _mock_answer(message: str, observations: list[dict[str, Any]]) -> str:
        counts = {item["tool"]: item["result"].get("count", 0) for item in observations}
        return (
            f"已围绕“{message}”执行营销知识检索、本体关系查询和业务上下文核验。"
            f"当前命中知识片段 {counts.get('search_marketing_knowledge', 0)} 条、本体对象 {counts.get('query_marketing_ontology', 0)} 个、"
            f"可参考产品 {counts.get('list_available_products', 0)} 个。建议先打开右侧运行轨迹核对证据，再由业务人员确认客群、产品资格、预算和渠道合规后进入活动编排。"
        )

    @staticmethod
    def _search_knowledge(session: Session, tenant_id: int, query: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        terms = [item.lower() for item in query.replace("，", " ").replace("。", " ").split() if len(item) > 1]
        chunks = session.scalars(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == tenant_id).order_by(KnowledgeChunkRecord.created_at.desc()).limit(400)).all()
        documents = {item.id: item for item in session.scalars(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == tenant_id)).all()}
        matched = [item for item in chunks if not terms or any(term in item.content.lower() for term in terms)][:8]
        items = []
        for chunk in matched:
            document = documents.get(chunk.document_id)
            source = {"type": "knowledge", "id": chunk.external_id, "title": document.title if document else chunk.external_id, "excerpt": chunk.content[:220]}
            sources.append(source)
            items.append(source)
        return {"count": len(items), "items": items}

    @staticmethod
    def _query_ontology(session: Session, tenant_id: int, query: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        entities = session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id).order_by(OntologyEntityRecord.updated_at.desc()).limit(400)).all()
        terms = [item.lower() for item in query.replace("，", " ").split() if len(item) > 1]
        matched = [item for item in entities if not terms or any(term in item.label.lower() for term in terms)][:12]
        ids = {item.id for item in matched}
        relations = session.scalars(select(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id)).all()
        relation_items = [{"source_id": item.source_entity_id, "relation": item.relation_type, "target_id": item.target_entity_id, "evidence": item.evidence[:160]} for item in relations if item.source_entity_id in ids or item.target_entity_id in ids][:20]
        items = [{"id": item.external_id, "type": item.entity_type, "label": item.label, "confidence": item.confidence} for item in matched]
        sources.extend({"type": "ontology", "id": item["id"], "title": item["label"], "excerpt": item["type"]} for item in items)
        return {"count": len(items), "entities": items, "relations": relation_items}

    @staticmethod
    def _inspect_campaign(session: Session, tenant_id: int, campaign_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        query = select(CampaignRecord).where(CampaignRecord.tenant_id == tenant_id)
        campaign = session.scalar(query.where(CampaignRecord.id == campaign_id)) if campaign_id else session.scalar(query.order_by(CampaignRecord.id))
        if campaign is None:
            return {"count": 0, "campaign": None}
        item = {"id": campaign.id, "name": campaign.name, "stage": campaign.stage, "status": campaign.status, "audience_size": campaign.audience_size, "product_package": campaign.product_package, "budget_yuan": campaign.budget_yuan, "roi_target": campaign.roi_target}
        sources.append({"type": "campaign", "id": campaign.id, "title": campaign.name, "excerpt": f"{campaign.stage} / {campaign.status}"})
        return {"count": 1, "campaign": item}

    @staticmethod
    def _list_products(session: Session, tenant_id: int, query: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        product_types = {"Product", "ProductPackage", "FareProduct", "AncillaryProduct", "Coupon", "MemberBenefit", "IntermodalProduct"}
        entities = session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.entity_type.in_(product_types)).order_by(OntologyEntityRecord.updated_at.desc()).limit(100)).all()
        terms = [item.lower() for item in query.replace("，", " ").split() if len(item) > 1]
        matched = [item for item in entities if not terms or any(term in item.label.lower() for term in terms)][:12]
        items = [{"id": item.external_id, "type": item.entity_type, "label": item.label, "confidence": item.confidence} for item in matched]
        sources.extend({"type": "product", "id": item["id"], "title": item["label"], "excerpt": item["type"]} for item in items)
        return {"count": len(items), "items": items}

    @staticmethod
    def _inspect_pipeline(session: Session, tenant_id: int, job_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        query = select(DataPipelineJobRecord).where(DataPipelineJobRecord.tenant_id == tenant_id)
        record = session.scalar(query.where(DataPipelineJobRecord.id == job_id)) if job_id else session.scalar(query.order_by(DataPipelineJobRecord.created_at.desc()))
        if record is None:
            return {"count": 0, "job": None}
        result = json.loads(record.result_json or "{}")
        item = {"id": record.id, "file_name": record.file_name, "status": record.status, "current_stage": record.current_stage, "total_entities": record.total_entities, "total_relations": record.total_relations, "events": (result.get("events") or [])[-12:]}
        sources.append({"type": "data-pipeline", "id": record.id, "title": record.file_name, "excerpt": f"{record.status} / {record.current_stage}"})
        return {"count": 1, "job": item}

    def _run_domain(self, session: Session, context: TenantContext, args: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
        allowed = {"opportunity-insight", "audience-insight", "product-match", "activity-orchestration", "content-generation", "effect-analysis"}
        domain_id = str(args.get("domain_id") or "")
        campaign_id = str(args.get("campaign_id") or "")
        if domain_id not in allowed:
            return {"ok": False, "error": "智能域不在授权范围", "allowed_domains": sorted(allowed)}
        if not campaign_id:
            return {"ok": False, "error": "调用智能域前必须选择活动"}
        run = self._runtime.run(session, context, AgentRunRequest(campaign_id=campaign_id, domain_id=domain_id, operator="营销智能助手"))
        sources.append({"type": "agent-run", "id": run.id, "title": domain_id, "excerpt": run.summary})
        return {"ok": run.status != "failed", "run_id": run.id, "status": run.status, "summary": run.summary, "events": [event.model_dump(mode="json") for event in run.events]}

    @staticmethod
    def _deduplicate_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in sources:
            key = (str(item.get("type")), str(item.get("id")))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result[:20]

    @staticmethod
    def _resolve_provider(session: Session, tenant_id: int, provider_id: int | None) -> ModelProviderRecord | None:
        query = select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True))
        if provider_id is not None:
            return session.scalar(query.where(ModelProviderRecord.id == provider_id))
        return session.scalar(query.order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))
