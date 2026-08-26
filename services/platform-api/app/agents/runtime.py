from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import TenantContext
from ..data import AGENT_DOMAINS
from ..db_models import AgentRunRecord, CampaignRecord, ModelProviderRecord, RuntimeEventRecord
from ..llm import LLMClient, LLMConfig
from ..models import AgentRun, AgentRunRequest, RuntimeEvent
from ..ontology import agent_contract
from ..security import SecretCipher


class AgentRuntime:
    """Tenant-scoped governed runtime with replaceable model providers and append-only events."""

    def __init__(self) -> None:
        self._client = LLMClient()
        self._cipher = SecretCipher()

    def run(self, session: Session, context: TenantContext, request: AgentRunRequest) -> AgentRun:
        run_id = f"RUN-{uuid4().hex[:10].upper()}"
        events: list[RuntimeEvent] = []

        def emit(event_type: str, **payload: object) -> None:
            events.append(RuntimeEvent(id=f"EVT-{uuid4().hex[:10].upper()}", run_id=run_id, event_type=event_type, payload=payload))

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
        emit(
            "ontology/context-loaded",
            reads=contract["reads"],
            writes=contract["writes"],
            functions=contract["functions"],
        )


        provider = self._resolve_provider(session, context.tenant_id, request.provider_id)
        if provider is None:
            emit("model/provider-missing", requested_provider_id=request.provider_id)
            return self._persist(session, context, request, operator, run_id, "failed", "当前租户未配置可用的大模型。", None, events)
        emit("model/provider-selected", provider=provider.display_name, model=provider.model_name)
        emit("tool/pre-execute", inputs=domain.input_types)
        try:
            model_output = self._client.generate(
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
                f"租户 {context.tenant_name} 的活动 {campaign.name} 调用 {domain.name}，输入包括：{'、'.join(domain.input_types)}。",
            )
        except Exception as exc:
            emit("model/invocation-failed", error_type=type(exc).__name__)
            return self._persist(session, context, request, operator, run_id, "failed", f"模型调用失败：{exc}", provider.id, events)
        emit("tool/post-execute", outputs=domain.output_types, provenance=provider.display_name)
        needs_approval = request.domain_id in {"activity-orchestration", "content-generation"}
        status = "needs_approval" if needs_approval else "completed"
        emit("governance/human-review", required=needs_approval)
        emit("agent/run-finished", status=status)
        summary = f"{domain.name}已生成结果，等待人工审核。" if needs_approval else f"{domain.name}已完成。{model_output[:90]}"
        return self._persist(session, context, request, operator, run_id, status, summary, provider.id, events)

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
