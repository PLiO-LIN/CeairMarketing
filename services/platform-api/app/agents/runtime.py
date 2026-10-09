from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import TenantContext
from ..data import AGENT_DOMAINS
from ..db_models import AgentRunRecord, CampaignRecord, ModelProviderRecord, ModelUsageRecord, RuntimeEventRecord
from ..llm import LLMConfig
from ..models import AgentRun, AgentRunRequest, RuntimeEvent
from ..ontology import agent_contract
from ..security import SecretCipher
from .harness import HarnessContext, UnifiedHarness
from .business_results import business_context, structured_result


class AgentRuntime:
    """Tenant-scoped governed runtime with replaceable model providers and append-only events."""

    def __init__(self) -> None:
        self._cipher = SecretCipher()

    def run(self, session: Session, context: TenantContext, request: AgentRunRequest) -> AgentRun:
        run_id = f"RUN-{uuid4().hex[:10].upper()}"
        events: list[RuntimeEvent] = []

        def emit(event_type: str, **payload: object) -> None:
            events.append(RuntimeEvent(id=f"EVT-{uuid4().hex[:10].upper()}", run_id=run_id, event_type=event_type, payload=payload))

        harness = UnifiedHarness(lambda event_type, payload: emit(event_type, **payload))

        operator = request.operator or context.display_name
        emit("agent/run-started", operator=operator, tenant=context.tenant_code)
        campaign = session.scalar(
            select(CampaignRecord).where(
                CampaignRecord.id == request.campaign_id,
                CampaignRecord.tenant_id == context.tenant_id,
            )
        )
        emit("governance/guard-checked", guard="tenant_campaign_scope", accepted=campaign is not None)
        if campaign is None:
            return self._persist(session, context, request, operator, run_id, "failed", "活动不存在或不属于当前租户。", None, events)
        domain = next((item for item in AGENT_DOMAINS if item.id == request.domain_id), None)
        emit("governance/guard-checked", guard="agent_domain_registered", accepted=domain is not None)
        if domain is None:
            return self._persist(session, context, request, operator, run_id, "failed", "智能域未注册。", None, events)
        contract = agent_contract(request.domain_id)
        harness.load_context(HarnessContext(context.tenant_id, run_id, request.domain_id, contract["reads"], contract["writes"], contract["functions"]))
        emit(
            "ontology/context-loaded",
            reads=contract["reads"],
            writes=contract["writes"],
            functions=contract["functions"],
        )


        try:
            facts = business_context(session, context.tenant_id, campaign, request)
        except ValueError as exc:
            return self._persist(session, context, request, operator, run_id, "failed", str(exc), None, events)
        emit("business/context-loaded", context=facts)
        if request.domain_id == "product-match" and (not facts.get("product") or facts["product"]["status"] not in {"已审批", "已通过", "可用"}):
            emit("governance/guard-checked", accepted=False, detail="产品版本未审批，库存与资格待核验")
            return self._persist(session, context, request, operator, run_id, "failed", "产品未审批，无法形成可执行匹配；请补充产品资格与库存依据。", None, events)
        provider = self._resolve_provider(session, context.tenant_id, request.provider_id)
        if provider is None:
            emit("model/provider-missing", requested_provider_id=request.provider_id)
            return self._persist(session, context, request, operator, run_id, "failed", "当前租户未配置可用的大模型。", None, events)
        harness.set_usage_recorder(lambda result: session.add(ModelUsageRecord(
            tenant_id=context.tenant_id,
            provider_id=provider.id,
            run_id=run_id,
            agent_id=request.domain_id,
            request_type="agent",
            model_name=result.model_name or provider.model_name,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )))
        emit("model/provider-selected", provider=provider.display_name, model=provider.model_name)
        emit("tool/pre-execute", inputs=domain.input_types)
        try:
            model_output = harness.generate_text(
                LLMConfig(
                    provider_type=provider.provider_type,
                    base_url=provider.base_url,
                    model_name=provider.model_name,
                    api_key=self._cipher.decrypt(provider.encrypted_api_key),
                    timeout_seconds=provider.timeout_seconds,
                    temperature=provider.temperature,
                    max_tokens=provider.max_tokens,
                ),
                "你是航空公司营销智能域，必须遵守产品事实、客户授权、预算、频控、渠道合规和租户数据边界。",
                json.dumps({"domain": domain.name, "context": facts}, ensure_ascii=False) + (
                    "\n仅输出JSON对象，包含title和body；不得把补充要求当作最终文案，不得编造价格、库存和已通过校验结论。" if request.domain_id == "content-generation" else
                    '\n仅输出JSON对象，包含text和selection，selection包含conditions列表，每条使用field_code/operator/value。field_code只能来自available_fields，operator只能为eq/ne/in/gte/lte。不支持的需求请说明，人数等待上游计算。' if request.domain_id == "audience-insight" else ""
                ),
            )
            if request.domain_id == "content-generation":
                if provider.provider_type == "mock":
                    model_output = json.dumps({"title": campaign.name + " · 出行推荐", "body": f"关注{facts['product']['name']}。{facts['product']['description']} 适用条件：{facts['product']['eligibility']}。具体权益以审核后的产品规则为准。"}, ensure_ascii=False)
                output = UnifiedHarness._parse_json(model_output)
                if not isinstance(output.get("title"), str) or not isinstance(output.get("body"), str) or not output["title"].strip() or not output["body"].strip() or len(output["title"]) > 240 or len(output["body"]) > 12000:
                    raise ValueError("内容结果必须包含有效标题和正文")
            elif request.domain_id == "audience-insight":
                if provider.provider_type == "mock":
                    matches = "三亚" in request.instruction or (not request.instruction and "三亚" in campaign.name)
                    conditions = [{"field_code": "search_destination", "operator": "eq", "value": "三亚"}, {"field_code": "search_frequency_7d", "operator": "gte", "value": 2}] if matches else []
                    output = {"object_type": "CustomerAggregate", "text": "受控规则样例仅支持三亚搜索客群，家庭属性仍需人工补齐。" if matches else "受控模型不支持解析此要求，请使用真实模型或人工配置条件。", "selection": {"conditions": conditions, "instruction": request.instruction, "requires_calculation": True, "supported": matches}}
                else:
                    from ..business_sync import ProfileCondition
                    output = UnifiedHarness._parse_json(model_output)
                    conditions = (output.get("selection") or {}).get("conditions")
                    if not isinstance(conditions, list) or not 1 <= len(conditions) <= 40:
                        raise ValueError("圈选结果必须包含有效条件")
                    allowed = {item["code"] for item in facts["available_fields"]}
                    checked = [ProfileCondition.model_validate(item).model_dump() for item in conditions]
                    if any(item["field_code"] not in allowed for item in checked):
                        raise ValueError("圈选条件引用了未授权或不存在的画像字段")
                    output["selection"] = {"conditions": checked, "requires_calculation": True}
                    output["text"] = str(output.get("text") or "圈选条件已解析，等待计算人数")
            else:
                output = structured_result(request.domain_id, facts, model_output)
            if request.domain_id == "content-generation":
                output["visual"] = {"theme": "family", "headline": output["title"], "destination": (facts.get("audience") or {}).get("name", "出游推荐"), "benefit": (facts.get("product") or {}).get("description", ""), "mode": "可编辑模板，文字由当前模型生成"}
            output["object_type"] = {"content-generation": "ContentAsset", "audience-insight": "CustomerAggregate"}.get(request.domain_id, output.get("object_type", "Recommendation"))
            output["context"] = facts
            output["provider_type"] = provider.provider_type
            output["execution"] = "governed-mock" if provider.provider_type == "mock" else "model"
            emit("business/result-generated", output=output)
        except Exception as exc:
            emit("model/invocation-failed", error_type=type(exc).__name__)
            return self._persist(session, context, request, operator, run_id, "failed", f"模型调用失败：{exc}", provider.id, events)
        emit("tool/post-execute", outputs=domain.output_types, provenance=provider.display_name)
        needs_approval = True
        status = "needs_approval" if needs_approval else "completed"
        emit("governance/human-review", required=needs_approval)
        emit("agent/run-finished", status=status)
        summary = f"{domain.name}已生成结果，等待人工审核。" if needs_approval else f"{domain.name}已完成。{model_output[:90]}"
        result = self._persist(session, context, request, operator, run_id, status, summary, provider.id, events)
        return result.model_copy(update={"output": output})

    @staticmethod
    def _resolve_provider(session: Session, tenant_id: int, provider_id: int | None) -> ModelProviderRecord | None:
        query = select(ModelProviderRecord).where(
            ModelProviderRecord.tenant_id == tenant_id,
            ModelProviderRecord.enabled.is_(True),
        )
        if provider_id is not None:
            return session.scalar(query.where(ModelProviderRecord.id == provider_id))
        return session.scalar(query.order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))

    @staticmethod
    def _persist(
        session: Session,
        context: TenantContext,
        request: AgentRunRequest,
        operator: str,
        run_id: str,
        status: str,
        summary: str,
        provider_id: int | None,
        events: list[RuntimeEvent],
    ) -> AgentRun:
        record = AgentRunRecord(
            id=run_id,
            tenant_id=context.tenant_id,
            campaign_id=request.campaign_id,
            domain_id=request.domain_id,
            operator=operator,
            provider_id=provider_id,
            status=status,
            summary=summary,
        )
        record.events = [
            RuntimeEventRecord(
                id=event.id,
                run_id=run_id,
                event_type=event.event_type,
                payload_json=json.dumps(event.payload, ensure_ascii=False),
                timestamp=event.timestamp,
            )
            for event in events
        ]
        session.add(record)
        session.commit()
        return AgentRun(id=run_id, campaign_id=request.campaign_id, domain_id=request.domain_id, status=status, summary=summary, events=events)
