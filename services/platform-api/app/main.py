import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager
from contextlib import contextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents import AgentRuntime, MarketingCopilot
from .auth import TenantContext, create_token, get_current_user, get_tenant_context, hash_password, require_admin, require_platform_admin, require_write, verify_password
from .config import get_settings
from .data import AGENT_DOMAINS
from .database import Base, SessionLocal, engine, get_session
from .db_models import AgentRunRecord, ApprovalTaskRecord, AudiencePackageRecord, AudienceSnapshotRecord, AudienceTagRecord, CampaignRecord, CampaignVersionRecord, ChannelTaskRecord, ContentAssetRecord, DataPipelineJobRecord, DataSourceConfigRecord, ExecutionBatchRecord, ImportJobRecord, IntegrationConfigRecord, KnowledgeChunkRecord, KnowledgeDocumentRecord, MarketHotspotRecord, ModelProviderRecord, ModelUsageRecord, OntologyEntityRecord, OntologyRelationRecord, OpportunityRecord, ProductPackageRecord, TenantMembershipRecord, TenantRecord, UserRecord
from .data_pipeline import DataProcessingAgent, get_mineru_config, integration_view
from .ndc_mock import air_shopping_payload, best_pricing_payload, order_list_payload
from .market_hotspots import collect_source, confirm_hotspot_ontology, create_opportunity_from_hotspot, delete_hotspot, hotspot_view, ingest_hotspots, process_hotspot, synthetic_hotspot_rows
from .imports import import_file
from .llm import LLMClient, LLMConfig
from .migrations import assign_legacy_records, enforce_postgres_tenant_constraints, migrate_legacy_schema, record_schema_version, CURRENT_SCHEMA_VERSION
from .models import (
    AgentRun,
    AudiencePackage,
    AudiencePackageBase,
    AudienceSnapshot,
    ApprovalDecision,
    ApprovalTask,
    ExecutionBatch,
    ChannelTask,
    AudienceTag,
    AudienceTagBase,
    AgentRunListItem,
    AgentRunRequest,
    AgentChatRequest,
    AgentChatResponse,
    Campaign,
    CampaignUpdate,
    CurrentUser,
    GraphStats,
    ImportJob,
    LoginRequest,
    LoginResponse,
    MarketingGraph,
    OntologySemanticStatus,
    Opportunity,
    OpportunityCreate,
    OpportunityUpdate,
    MarketHotspot,
    MarketHotspotIngestRequest,
    MarketHotspotReviewRequest,
    MarketHotspotCollectRequest,
    MarketHotspotOpportunityRequest,
    MarketHotspotBatchResult,
    MarketHotspotSource,
    ModelProvider,
    ModelProviderCreate,
    ModelProviderUpdate,
    ProviderModelsResult,
    ProviderTestResult,
    ProviderUsageResult,
    DataPipelineCreateResult,
    DataPipelineJob,
    DataPipelineReviewRequest,
    IntegrationConfig,
    IntegrationConfigUpdate,
    DataSourceConfig,
    DataSourceConfigBase,
    InterfacePipelineRequest,
    FlightProductPipelineRequest,
    NdcAirShoppingRequest,
    NdcOrderListRequest,
    KnowledgeDocument,
    KnowledgeDocumentUpdate,
    KnowledgeSearchResult,
    MembershipCreate,
    PlatformUserCreate,
    PlatformUserSummary,
    ProductPackage,
    ProductPackageBase,
    CampaignVersion,
    CampaignVersionBase,
    ContentAsset,
    ContentAssetBase,
    TenantCreate,
    TenantSummary,
)
from .ontology import build_campaign_graph, graph_stats, semantic_model, semantic_status
from .security import SecretCipher
from .seed import seed_database, seed_persona_catalog, seed_tenant_data

settings = get_settings()


@contextmanager
def database_initialization_lock():
    if engine.dialect.name != "postgresql":
        yield
        return

    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(2026082501)"))
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(2026082501)"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_production()
    with database_initialization_lock():
        Base.metadata.create_all(bind=engine)
        migrate_legacy_schema(engine)
        record_schema_version(engine)
        with SessionLocal() as session:
            tenant_id = seed_database(session)
        assign_legacy_records(engine, tenant_id)
        enforce_postgres_tenant_constraints(engine)
        with SessionLocal() as session:
            seed_tenant_data(session, tenant_id)
        with SessionLocal() as session:
            seed_persona_catalog(session, tenant_id)
    yield


app = FastAPI(title=settings.app_name, version="3.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
runtime = AgentRuntime()
copilot = MarketingCopilot()
cipher = SecretCipher()
llm_client = LLMClient()


def memberships_for(session: Session, user_id: int) -> list[TenantSummary]:
    records = session.scalars(
        select(TenantMembershipRecord).where(TenantMembershipRecord.user_id == user_id).order_by(TenantMembershipRecord.id)
    ).all()
    return [TenantSummary(id=item.tenant.id, code=item.tenant.code, name=item.tenant.name, role=item.role) for item in records]


def provider_view(record: ModelProviderRecord) -> ModelProvider:
    return ModelProvider.model_validate(record).model_copy(update={"api_key_configured": bool(record.encrypted_api_key)})


def import_view(record: ImportJobRecord) -> ImportJob:
    return ImportJob.model_validate(record).model_copy(update={"errors": json.loads(record.errors_json or "[]")})


def clear_default(session: Session, tenant_id: int, excluding_id: int | None = None) -> None:
    statement = update(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id).values(is_default=False)
    if excluding_id is not None:
        statement = statement.where(ModelProviderRecord.id != excluding_id)
    session.execute(statement)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "ceair-marketing-platform-api"}


@app.get("/health/ready")
def health_ready(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    version = session.execute(text("SELECT version FROM schema_versions ORDER BY applied_at DESC LIMIT 1")).scalar_one_or_none()
    if version != CURRENT_SCHEMA_VERSION:
        raise HTTPException(status_code=503, detail="数据库 schema 版本不匹配")
    return {"status": "ready", "database": "connected", "schema_version": version}


@app.get("/health")
def health() -> dict[str, str]:
    return health_live()


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    user = session.scalar(select(UserRecord).where(UserRecord.username == payload.username))
    if user is None or not user.enabled or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    tenants = memberships_for(session, user.id)
    if not tenants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户未加入任何租户")
    return LoginResponse(access_token=create_token(user.id), display_name=user.display_name, tenants=tenants, is_platform_admin=user.is_platform_admin)


@app.get("/api/auth/me", response_model=CurrentUser)
def me(
    context: TenantContext = Depends(get_tenant_context),
    user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CurrentUser:
    tenants = memberships_for(session, user.id)
    active = next(item for item in tenants if item.id == context.tenant_id)
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name, active_tenant=active, tenants=tenants, is_platform_admin=user.is_platform_admin)


@app.get("/api/platform/tenants", response_model=list[TenantSummary])
def platform_tenants(_admin: UserRecord = Depends(require_platform_admin), session: Session = Depends(get_session)):
    return [TenantSummary(id=item.id, code=item.code, name=item.name, role="platform") for item in session.scalars(select(TenantRecord).order_by(TenantRecord.id))]


@app.post("/api/platform/tenants", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, admin: UserRecord = Depends(require_platform_admin), session: Session = Depends(get_session)):
    tenant = TenantRecord(code=payload.code, name=payload.name)
    session.add(tenant)
    try:
        session.flush()
        session.add(TenantMembershipRecord(tenant_id=tenant.id, user_id=admin.id, role="admin"))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="租户编码已存在") from exc
    return TenantSummary(id=tenant.id, code=tenant.code, name=tenant.name, role="admin")


def user_summary(session: Session, user: UserRecord) -> PlatformUserSummary:
    return PlatformUserSummary(id=user.id, username=user.username, display_name=user.display_name, enabled=user.enabled, is_platform_admin=user.is_platform_admin, memberships=memberships_for(session, user.id))


@app.get("/api/platform/users", response_model=list[PlatformUserSummary])
def platform_users(_admin: UserRecord = Depends(require_platform_admin), session: Session = Depends(get_session)):
    return [user_summary(session, item) for item in session.scalars(select(UserRecord).order_by(UserRecord.id))]


@app.post("/api/platform/users", response_model=PlatformUserSummary, status_code=status.HTTP_201_CREATED)
def create_platform_user(payload: PlatformUserCreate, _admin: UserRecord = Depends(require_platform_admin), session: Session = Depends(get_session)):
    if session.get(TenantRecord, payload.tenant_id) is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    user = UserRecord(username=payload.username, display_name=payload.display_name, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        session.flush()
        session.add(TenantMembershipRecord(tenant_id=payload.tenant_id, user_id=user.id, role=payload.role))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    return user_summary(session, user)


@app.post("/api/platform/users/{user_id}/memberships", response_model=PlatformUserSummary)
def add_membership(user_id: int, payload: MembershipCreate, _admin: UserRecord = Depends(require_platform_admin), session: Session = Depends(get_session)):
    user = session.get(UserRecord, user_id)
    if user is None or session.get(TenantRecord, payload.tenant_id) is None:
        raise HTTPException(status_code=404, detail="用户或租户不存在")
    membership = session.scalar(select(TenantMembershipRecord).where(TenantMembershipRecord.user_id == user_id, TenantMembershipRecord.tenant_id == payload.tenant_id))
    if membership is None:
        membership = TenantMembershipRecord(user_id=user_id, tenant_id=payload.tenant_id, role=payload.role)
        session.add(membership)
    else:
        membership.role = payload.role
    session.commit()
    return user_summary(session, user)


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return list(session.scalars(select(CampaignRecord).where(CampaignRecord.tenant_id == context.tenant_id).order_by(CampaignRecord.id.desc())))


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    return campaign


@app.put("/api/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: str, payload: CampaignUpdate, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    campaign.name = payload.name
    campaign.version = campaign.version or "V1"
    session.commit()
    return campaign


@app.delete("/api/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    version_count = session.scalar(select(func.count()).select_from(CampaignVersionRecord).where(CampaignVersionRecord.tenant_id == context.tenant_id, CampaignVersionRecord.campaign_id == campaign_id))
    if version_count:
        raise HTTPException(status_code=409, detail=f"活动已有 {version_count} 个版本，请先归档后删除")
    session.delete(campaign)
    session.commit()


def campaign_version_view(record: CampaignVersionRecord) -> CampaignVersion:
    return CampaignVersion(
        id=record.id,
        campaign_id=record.campaign_id,
        external_id=record.external_id,
        version=record.version,
        audience_snapshot_id=record.audience_snapshot_id,
        product_package_id=record.product_package_id,
        content_asset_ids=json.loads(record.content_asset_ids_json or "[]"),
        budget_yuan=record.budget_yuan,
        channels=json.loads(record.channels_json or "[]"),
        status=record.status,
        created_at=record.created_at,
    )


@app.get("/api/campaigns/{campaign_id}/versions", response_model=list[CampaignVersion])
def list_campaign_versions(campaign_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    if session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id)) is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    records = session.scalars(select(CampaignVersionRecord).where(CampaignVersionRecord.campaign_id == campaign_id, CampaignVersionRecord.tenant_id == context.tenant_id).order_by(CampaignVersionRecord.id.desc())).all()
    return [campaign_version_view(record) for record in records]


@app.post("/api/campaigns/{campaign_id}/versions", response_model=CampaignVersion, status_code=status.HTTP_201_CREATED)
def create_campaign_version(campaign_id: str, payload: CampaignVersionBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    if payload.audience_snapshot_id and session.scalar(select(AudienceSnapshotRecord).where(AudienceSnapshotRecord.id == payload.audience_snapshot_id, AudienceSnapshotRecord.tenant_id == context.tenant_id)) is None:
        raise HTTPException(status_code=404, detail="客群快照不存在")
    if payload.product_package_id and session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.id == payload.product_package_id, ProductPackageRecord.tenant_id == context.tenant_id)) is None:
        raise HTTPException(status_code=404, detail="产品包不存在")
    if payload.content_asset_ids:
        count = session.scalar(select(func.count()).select_from(ContentAssetRecord).where(ContentAssetRecord.tenant_id == context.tenant_id, ContentAssetRecord.id.in_(payload.content_asset_ids)))
        if count != len(set(payload.content_asset_ids)):
            raise HTTPException(status_code=404, detail="内容资产不存在或不属于当前租户")
    latest = session.scalar(select(CampaignVersionRecord).where(CampaignVersionRecord.campaign_id == campaign_id, CampaignVersionRecord.tenant_id == context.tenant_id).order_by(CampaignVersionRecord.id.desc()))
    version = f"V{(int(latest.version[1:]) + 1) if latest and latest.version[1:].isdigit() else 1}"
    record = CampaignVersionRecord(tenant_id=context.tenant_id, campaign_id=campaign_id, external_id=f"{campaign_id}-{version}", version=version, audience_snapshot_id=payload.audience_snapshot_id, product_package_id=payload.product_package_id, content_asset_ids_json=json.dumps(payload.content_asset_ids), budget_yuan=payload.budget_yuan, channels_json=json.dumps(payload.channels, ensure_ascii=False), status=payload.status, created_by=context.user_id)
    session.add(record)
    session.commit()
    session.refresh(record)
    return campaign_version_view(record)


def approval_view(record: ApprovalTaskRecord) -> ApprovalTask:
    return ApprovalTask.model_validate(record)


@app.get("/api/approvals", response_model=list[ApprovalTask])
def list_approval_tasks(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return session.scalars(select(ApprovalTaskRecord).where(ApprovalTaskRecord.tenant_id == context.tenant_id).order_by(ApprovalTaskRecord.created_at.desc())).all()


@app.post("/api/campaigns/{campaign_id}/versions/{version_id}/approval", response_model=ApprovalTask, status_code=status.HTTP_201_CREATED)
def create_approval_task(campaign_id: str, version_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    version = session.scalar(select(CampaignVersionRecord).where(CampaignVersionRecord.id == version_id, CampaignVersionRecord.campaign_id == campaign_id, CampaignVersionRecord.tenant_id == context.tenant_id))
    if version is None:
        raise HTTPException(status_code=404, detail="活动版本不存在")
    record = ApprovalTaskRecord(tenant_id=context.tenant_id, campaign_id=campaign_id, campaign_version_id=version.id, external_id=f"APR-{campaign_id}-{version.version}", approver_role="营销经理")
    session.add(record)
    version.status = "待审批"
    session.commit()
    session.refresh(record)
    return approval_view(record)


@app.post("/api/approvals/{approval_id}/decision", response_model=ApprovalTask)
def decide_approval(approval_id: int, payload: ApprovalDecision, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(ApprovalTaskRecord).where(ApprovalTaskRecord.id == approval_id, ApprovalTaskRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="审批任务不存在")
    if record.status != "待审批":
        raise HTTPException(status_code=409, detail="审批任务已处理")
    record.status = "已通过" if payload.decision == "approve" else "已退回"
    record.comment = payload.comment
    record.decided_by = context.user_id
    record.decided_at = datetime.now(timezone.utc)
    version = session.get(CampaignVersionRecord, record.campaign_version_id)
    if version:
        version.status = "已通过" if payload.decision == "approve" else "已退回"
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == record.campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign:
        campaign.stage = "执行" if payload.decision == "approve" else "内容"
        campaign.status = "待执行" if payload.decision == "approve" else "待修改"
    if payload.decision == "approve" and version:
        existing = session.scalar(select(ExecutionBatchRecord).where(ExecutionBatchRecord.tenant_id == context.tenant_id, ExecutionBatchRecord.campaign_version_id == version.id))
        if existing is None:
            snapshot_size = session.scalar(select(AudienceSnapshotRecord.estimated_size).where(AudienceSnapshotRecord.id == version.audience_snapshot_id, AudienceSnapshotRecord.tenant_id == context.tenant_id)) or 0
            batch = ExecutionBatchRecord(tenant_id=context.tenant_id, campaign_id=record.campaign_id, campaign_version_id=version.id, external_id=f"BATCH-{record.campaign_id}-{version.version}", channels_json=version.channels_json, target_size=snapshot_size, status="待执行", created_by=context.user_id)
            session.add(batch)
            session.flush()
            channels = json.loads(version.channels_json or "[]") or ["App"]
            share = snapshot_size // len(channels) if channels else snapshot_size
            for index, channel in enumerate(channels):
                target = share + (snapshot_size - share * len(channels) if index == 0 else 0)
                session.add(ChannelTaskRecord(tenant_id=context.tenant_id, batch_id=batch.id, campaign_id=record.campaign_id, channel=channel, external_id=f"TASK-{record.campaign_id}-{version.version}-{index + 1}", target_count=target, status="待执行"))
    session.commit()
    session.refresh(record)
    return approval_view(record)


def execution_batch_view(record: ExecutionBatchRecord) -> ExecutionBatch:
    return ExecutionBatch(
        id=record.id,
        campaign_id=record.campaign_id,
        campaign_version_id=record.campaign_version_id,
        external_id=record.external_id,
        channels=json.loads(record.channels_json or "[]"),
        target_size=record.target_size,
        delivered_count=record.delivered_count,
        feedback_count=record.feedback_count,
        failed_count=record.failed_count,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/api/execution-batches", response_model=list[ExecutionBatch])
def list_execution_batches(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(ExecutionBatchRecord).where(ExecutionBatchRecord.tenant_id == context.tenant_id).order_by(ExecutionBatchRecord.created_at.desc())).all()
    return [execution_batch_view(record) for record in records]


@app.post("/api/execution-batches/{batch_id}/status", response_model=ExecutionBatch)
def update_execution_batch_status(batch_id: int, payload: dict[str, str], context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(ExecutionBatchRecord).where(ExecutionBatchRecord.id == batch_id, ExecutionBatchRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="执行批次不存在")
    next_status = payload.get("status", "")
    if next_status not in {"待执行", "执行中", "已暂停", "已完成", "失败"}:
        raise HTTPException(status_code=422, detail="不支持的执行状态")
    record.status = next_status
    tasks = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.batch_id == record.id, ChannelTaskRecord.tenant_id == context.tenant_id)).all()
    for task in tasks:
        task.status = next_status
    if next_status == "执行中":
        record.delivered_count = max(record.delivered_count, min(record.target_size, max(1, int(record.target_size * 0.35))))
    if next_status == "已完成":
        record.delivered_count = record.target_size
        record.feedback_count = max(record.feedback_count, record.delivered_count)
    session.commit()
    session.refresh(record)
    return execution_batch_view(record)


@app.get("/api/channel-tasks", response_model=list[ChannelTask])
def list_channel_tasks(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.tenant_id == context.tenant_id).order_by(ChannelTaskRecord.created_at.desc())).all()
    return records


@app.post("/api/channel-tasks/{task_id}/feedback", response_model=ChannelTask)
def update_channel_feedback(task_id: int, payload: dict[str, int | str], context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    task = session.scalar(select(ChannelTaskRecord).where(ChannelTaskRecord.id == task_id, ChannelTaskRecord.tenant_id == context.tenant_id))
    if task is None:
        raise HTTPException(status_code=404, detail="渠道任务不存在")
    for field in ("sent_count", "delivered_count", "clicked_count", "converted_count", "failed_count"):
        if field in payload:
            value = int(payload[field])
            if value < 0 or value > task.target_count:
                raise HTTPException(status_code=422, detail=f"{field} 超出渠道任务范围")
            setattr(task, field, value)
    next_status = str(payload.get("status", task.status))
    if next_status not in {"待执行", "执行中", "已暂停", "已完成", "失败"}:
        raise HTTPException(status_code=422, detail="不支持的渠道任务状态")
    task.last_feedback_at = datetime.now(timezone.utc)
    task.status = next_status
    batch = session.scalar(select(ExecutionBatchRecord).where(ExecutionBatchRecord.id == task.batch_id, ExecutionBatchRecord.tenant_id == context.tenant_id))
    if batch:
        siblings = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.batch_id == batch.id, ChannelTaskRecord.tenant_id == context.tenant_id)).all()
        batch.delivered_count = sum(item.delivered_count for item in siblings)
        batch.feedback_count = sum(item.clicked_count + item.converted_count for item in siblings)
        batch.failed_count = sum(item.failed_count for item in siblings)
    session.commit()
    session.refresh(task)
    return task


@app.get("/api/campaigns/{campaign_id}/effect-summary")
def campaign_effect_summary(campaign_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.id == campaign_id, CampaignRecord.tenant_id == context.tenant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    batches = session.scalars(select(ExecutionBatchRecord).where(ExecutionBatchRecord.campaign_id == campaign_id, ExecutionBatchRecord.tenant_id == context.tenant_id).order_by(ExecutionBatchRecord.created_at.desc())).all()
    batch_ids = [batches[0].id] if batches else []
    tasks = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.campaign_id == campaign_id, ChannelTaskRecord.tenant_id == context.tenant_id, ChannelTaskRecord.batch_id.in_(batch_ids))).all() if batch_ids else []
    target = sum(item.target_count for item in tasks)
    sent = sum(item.sent_count for item in tasks)
    delivered = sum(item.delivered_count for item in tasks)
    clicked = sum(item.clicked_count for item in tasks)
    converted = sum(item.converted_count for item in tasks)
    failed = sum(item.failed_count for item in tasks)
    return {
        "campaign_id": campaign_id,
        "batch_count": len(batches),
        "target_count": target,
        "sent_count": sent,
        "delivered_count": delivered,
        "clicked_count": clicked,
        "converted_count": converted,
        "failed_count": failed,
        "delivery_rate": round(delivered / target * 100, 2) if target else 0,
        "click_rate": round(clicked / delivered * 100, 2) if delivered else 0,
        "conversion_rate": round(converted / clicked * 100, 2) if clicked else 0,
        "channels": [{
            "channel": item.channel,
            "target_count": item.target_count,
            "sent_count": item.sent_count,
            "delivered_count": item.delivered_count,
            "clicked_count": item.clicked_count,
            "converted_count": item.converted_count,
            "failed_count": item.failed_count,
            "status": item.status,
            "last_feedback_at": item.last_feedback_at,
        } for item in tasks],
        "learning_inputs": ["渠道回执", "点击行为", "转化结果", "失败原因"],
    }

@app.get("/api/product-packages", response_model=list[ProductPackage])
def list_product_packages(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return session.scalars(
        select(ProductPackageRecord)
        .where(ProductPackageRecord.tenant_id == context.tenant_id)
        .order_by(ProductPackageRecord.updated_at.desc())
    ).all()


@app.post("/api/product-packages", response_model=ProductPackage, status_code=status.HTTP_201_CREATED)
def create_product_package(payload: ProductPackageBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = ProductPackageRecord(
        tenant_id=context.tenant_id,
        external_id=f"PKG-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}",
        created_by=context.user_id,
        **payload.model_dump(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@app.put("/api/product-packages/{package_id}", response_model=ProductPackage)
def update_product_package(package_id: int, payload: ProductPackageBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(
        select(ProductPackageRecord).where(
            ProductPackageRecord.id == package_id,
            ProductPackageRecord.tenant_id == context.tenant_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="产品包不存在")
    previous_name = record.name
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    if previous_name != payload.name:
        session.execute(
            update(CampaignRecord)
            .where(
                CampaignRecord.tenant_id == context.tenant_id,
                CampaignRecord.product_package == previous_name,
            )
            .values(product_package=payload.name)
        )
    session.commit()
    session.refresh(record)
    return record


@app.delete("/api/product-packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_package(package_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(
        select(ProductPackageRecord).where(
            ProductPackageRecord.id == package_id,
            ProductPackageRecord.tenant_id == context.tenant_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="产品包不存在")
    referenced = session.scalar(
        select(func.count())
        .select_from(CampaignRecord)
        .where(
            CampaignRecord.tenant_id == context.tenant_id,
            CampaignRecord.product_package == record.name,
        )
    )
    if referenced:
        raise HTTPException(status_code=409, detail=f"产品包已被 {referenced} 个活动引用，请先解除引用")
    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/content-assets", response_model=list[ContentAsset])
def list_content_assets(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return session.scalars(
        select(ContentAssetRecord)
        .where(ContentAssetRecord.tenant_id == context.tenant_id)
        .order_by(ContentAssetRecord.updated_at.desc())
    ).all()


@app.post("/api/content-assets", response_model=ContentAsset, status_code=status.HTTP_201_CREATED)
def create_content_asset(payload: ContentAssetBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    if payload.campaign_id and session.scalar(select(CampaignRecord).where(CampaignRecord.id == payload.campaign_id, CampaignRecord.tenant_id == context.tenant_id)) is None:
        raise HTTPException(status_code=404, detail="关联活动不存在")
    record = ContentAssetRecord(
        tenant_id=context.tenant_id,
        external_id=f"CNT-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}",
        created_by=context.user_id,
        **payload.model_dump(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@app.put("/api/content-assets/{asset_id}", response_model=ContentAsset)
def update_content_asset(asset_id: int, payload: ContentAssetBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(ContentAssetRecord).where(ContentAssetRecord.id == asset_id, ContentAssetRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="内容资产不存在")
    if payload.campaign_id and session.scalar(select(CampaignRecord).where(CampaignRecord.id == payload.campaign_id, CampaignRecord.tenant_id == context.tenant_id)) is None:
        raise HTTPException(status_code=404, detail="关联活动不存在")
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    session.commit()
    session.refresh(record)
    return record


@app.delete("/api/content-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content_asset(asset_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(ContentAssetRecord).where(ContentAssetRecord.id == asset_id, ContentAssetRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="内容资产不存在")
    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def audience_package_view(record: AudiencePackageRecord) -> AudiencePackage:
    return AudiencePackage(
        id=record.id,
        external_id=record.external_id,
        name=record.name,
        selection_mode=record.selection_mode,
        tag_ids=json.loads(record.tag_ids_json or "[]"),
        expression=json.loads(record.expression_json or "{}"),
        estimated_size=record.estimated_size,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/api/opportunities", response_model=list[Opportunity])
def list_opportunities(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return session.scalars(select(OpportunityRecord).where(OpportunityRecord.tenant_id == context.tenant_id).order_by(OpportunityRecord.score.desc(), OpportunityRecord.updated_at.desc())).all()


@app.post("/api/opportunities", response_model=Opportunity, status_code=status.HTTP_201_CREATED)
def create_opportunity(payload: OpportunityCreate, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    opportunity_id = payload.id.strip() or f"OPP-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"
    if session.get(OpportunityRecord, (context.tenant_id, opportunity_id)) is not None:
        raise HTTPException(status_code=409, detail="Request failed")
    record = OpportunityRecord(tenant_id=context.tenant_id, id=opportunity_id, **payload.model_dump(exclude={"id"}))
    session.add(record); session.commit(); session.refresh(record)
    return record


@app.put("/api/opportunities/{opportunity_id}", response_model=Opportunity)
def update_opportunity(opportunity_id: str, payload: OpportunityUpdate, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.get(OpportunityRecord, (context.tenant_id, opportunity_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Request failed")
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    session.commit(); session.refresh(record)
    return record


@app.delete("/api/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(opportunity_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.get(OpportunityRecord, (context.tenant_id, opportunity_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Request failed")
    session.delete(record); session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/audience-tags", response_model=list[AudienceTag])
def list_audience_tags(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return session.scalars(select(AudienceTagRecord).where(AudienceTagRecord.tenant_id == context.tenant_id).order_by(AudienceTagRecord.category, AudienceTagRecord.name)).all()


@app.post("/api/audience-tags", response_model=AudienceTag, status_code=status.HTTP_201_CREATED)
def create_audience_tag(payload: AudienceTagBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = AudienceTagRecord(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(record)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback(); raise HTTPException(status_code=409, detail="Request failed") from exc
    session.refresh(record); return record


@app.put("/api/audience-tags/{tag_id}", response_model=AudienceTag)
def update_audience_tag(tag_id: int, payload: AudienceTagBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(AudienceTagRecord).where(AudienceTagRecord.id == tag_id, AudienceTagRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Request failed")
    for key, value in payload.model_dump().items(): setattr(record, key, value)
    session.commit(); session.refresh(record); return record


def market_hotspot_view(record: MarketHotspotRecord) -> MarketHotspot:
    return MarketHotspot.model_validate(hotspot_view(record))


@app.get("/api/market-hotspots", response_model=list[MarketHotspot])
def list_market_hotspots(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(MarketHotspotRecord).where(MarketHotspotRecord.tenant_id == context.tenant_id).order_by(MarketHotspotRecord.trend_score.desc(), MarketHotspotRecord.created_at.desc()).limit(200)).all()
    return [market_hotspot_view(record) for record in records]


@app.get("/api/market-hotspots/{hotspot_id}", response_model=MarketHotspot)
def get_market_hotspot(hotspot_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    record = session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.id == hotspot_id, MarketHotspotRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="市场热点不存在")
    return market_hotspot_view(record)


@app.post("/api/market-hotspots/ingest", response_model=MarketHotspotBatchResult, status_code=status.HTTP_202_ACCEPTED)
def ingest_market_hotspots(payload: MarketHotspotIngestRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    return ingest_hotspots(session, context, [item.model_dump() for item in payload.records], payload.process_with_agent)


@app.post("/api/market-hotspots/collect", response_model=MarketHotspotBatchResult, status_code=status.HTTP_202_ACCEPTED)
def collect_market_hotspots(payload: MarketHotspotCollectRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    rows = []
    health = []
    processing_stages = [{"stage": "collecting", "label": "开始采集国内热点源", "status": "running", "timestamp": datetime.now(timezone.utc).isoformat()}]
    for source in payload.sources:
        try:
            items, source_health = collect_source(source.name, source.url, source.source_type, source.max_items)
            rows.extend(items)
            health.extend(source_health)
        except Exception as exc:
            health.append({"name": source.name, "url": source.url, "status": "failed", "error": type(exc).__name__})
    if not rows:
        rows = synthetic_hotspot_rows()
        health.append({"name": "系统降级演示信号", "url": "", "status": "fallback", "item_count": len(rows), "checked_at": datetime.now(timezone.utc), "message": "外部热点源未返回可解析内容，已生成明确标记的演示信号"})
    processing_stages[0]["status"] = "completed"
    processing_stages.extend([
        {"stage": "parsed", "label": "RSS 内容解析与来源归一化", "status": "completed", "item_count": len(rows), "timestamp": datetime.now(timezone.utc).isoformat()},
        {"stage": "agent-processing", "label": "机会洞察智能体分析热点、主题和航空业务关联", "status": "running", "timestamp": datetime.now(timezone.utc).isoformat()},
    ])
    result = ingest_hotspots(session, context, rows, payload.process_with_agent)
    processing_stages[-1]["status"] = "completed" if payload.process_with_agent else "skipped"
    processing_stages.append({"stage": "trace-ready", "label": "处理轨迹和本体准入结果已生成", "status": "completed", "hotspot_count": result.get("created", 0), "timestamp": datetime.now(timezone.utc).isoformat()})
    result["processing_stages"] = processing_stages
    result["source_health"] = health
    return result


@app.post("/api/market-hotspots/{hotspot_id}/process", response_model=MarketHotspot)
def reprocess_market_hotspot(hotspot_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.id == hotspot_id, MarketHotspotRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="市场热点不存在")
    process_hotspot(session, context, record)
    return market_hotspot_view(record)


@app.post("/api/market-hotspots/{hotspot_id}/review", response_model=MarketHotspot)
def review_market_hotspot(hotspot_id: str, payload: MarketHotspotReviewRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.id == hotspot_id, MarketHotspotRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="市场热点不存在")
    reviewer = session.get(UserRecord, context.user_id)
    try:
        confirm_hotspot_ontology(session, context, record, reviewer.display_name if reviewer else str(context.user_id), payload.decision, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return market_hotspot_view(record)


@app.post("/api/market-hotspots/{hotspot_id}/opportunity", response_model=Opportunity, status_code=status.HTTP_201_CREATED)
def hotspot_to_opportunity(hotspot_id: str, payload: MarketHotspotOpportunityRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.id == hotspot_id, MarketHotspotRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="市场热点不存在")
    try:
        return create_opportunity_from_hotspot(session, context, record, payload.owner, payload.estimated_audience, payload.estimated_revenue_yuan)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/market-hotspots/{hotspot_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_market_hotspot(hotspot_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.id == hotspot_id, MarketHotspotRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="市场热点不存在")
    delete_hotspot(session, context, record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/audience-tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audience_tag(tag_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(AudienceTagRecord).where(AudienceTagRecord.id == tag_id, AudienceTagRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Request failed")
    session.delete(record); session.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/audience-packages", response_model=list[AudiencePackage])
def list_audience_packages(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == context.tenant_id).order_by(AudiencePackageRecord.updated_at.desc())).all()
    return [audience_package_view(record) for record in records]


@app.post("/api/audience-packages", response_model=AudiencePackage, status_code=status.HTTP_201_CREATED)
def create_audience_package(payload: AudiencePackageBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = AudiencePackageRecord(tenant_id=context.tenant_id, external_id=f"AUD-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}", name=payload.name, selection_mode=payload.selection_mode, tag_ids_json=json.dumps(payload.tag_ids), expression_json=json.dumps(payload.expression, ensure_ascii=False), estimated_size=payload.estimated_size, status=payload.status, created_by=context.user_id)
    session.add(record); session.commit(); session.refresh(record); return audience_package_view(record)


@app.put("/api/audience-packages/{package_id}", response_model=AudiencePackage)
def update_audience_package(package_id: int, payload: AudiencePackageBase, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.id == package_id, AudiencePackageRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Request failed")
    record.name=payload.name; record.selection_mode=payload.selection_mode; record.tag_ids_json=json.dumps(payload.tag_ids); record.expression_json=json.dumps(payload.expression, ensure_ascii=False); record.estimated_size=payload.estimated_size; record.status=payload.status
    session.commit(); session.refresh(record); return audience_package_view(record)


@app.delete("/api/audience-packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audience_package(package_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.id == package_id, AudiencePackageRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Request failed")
    session.delete(record); session.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)


def audience_snapshot_view(record: AudienceSnapshotRecord) -> AudienceSnapshot:
    return AudienceSnapshot(
        id=record.id,
        package_id=record.package_id,
        external_id=record.external_id,
        version=record.version,
        estimated_size=record.estimated_size,
        tag_ids=json.loads(record.tag_ids_json or "[]"),
        expression=json.loads(record.expression_json or "{}"),
        source=record.source,
        status=record.status,
        created_at=record.created_at,
    )


@app.get("/api/audience-snapshots", response_model=list[AudienceSnapshot])
def list_audience_snapshots(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(AudienceSnapshotRecord).where(AudienceSnapshotRecord.tenant_id == context.tenant_id).order_by(AudienceSnapshotRecord.created_at.desc())).all()
    return [audience_snapshot_view(record) for record in records]


@app.post("/api/audience-packages/{package_id}/snapshots", response_model=AudienceSnapshot, status_code=status.HTTP_201_CREATED)
def create_audience_snapshot(package_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    package = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.id == package_id, AudiencePackageRecord.tenant_id == context.tenant_id))
    if package is None:
        raise HTTPException(status_code=404, detail="客群包不存在")
    latest = session.scalar(select(AudienceSnapshotRecord).where(AudienceSnapshotRecord.package_id == package.id, AudienceSnapshotRecord.tenant_id == context.tenant_id).order_by(AudienceSnapshotRecord.id.desc()))
    version = f"V{(int(latest.version[1:]) + 1) if latest and latest.version[1:].isdigit() else 1}"
    record = AudienceSnapshotRecord(
        tenant_id=context.tenant_id,
        package_id=package.id,
        external_id=f"AUD-SNAP-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}",
        version=version,
        estimated_size=package.estimated_size,
        tag_ids_json=package.tag_ids_json,
        expression_json=package.expression_json,
        source="用户画像平台 + 客群规则",
        created_by=context.user_id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return audience_snapshot_view(record)


@app.get("/api/agent-domains")
def list_agent_domains(_context: TenantContext = Depends(get_tenant_context)):
    return AGENT_DOMAINS


@app.post("/api/agent-runs", response_model=AgentRun)
def run_agent(request: AgentRunRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    return runtime.run(session, context, request)


@app.post("/api/agent-chat/stream")
def run_agent_chat_stream(payload: AgentChatRequest, context: TenantContext = Depends(require_write)):
    """SSE chat channel: harness events arrive before answer tokens."""
    events: queue.Queue[dict[str, object]] = queue.Queue()

    def worker() -> None:
        try:
            with SessionLocal() as worker_session:
                result = copilot.run(
                    worker_session,
                    context,
                    payload,
                    event_sink=lambda item: events.put({"type": "trace", "item": item}),
                    token_sink=lambda token: events.put({"type": "token", "text": token}),
                )
                events.put({"type": "result", "result": result.model_dump(mode="json")})
        except Exception as exc:
            events.put({"type": "error", "message": f"智能体运行失败：{exc}"})
        finally:
            events.put({"type": "done"})

    threading.Thread(target=worker, name="ceair-agent-chat", daemon=True).start()

    def encode(event: str, data: object) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def stream():
        yield ": ceair-agent-stream\n\n"
        while True:
            item = events.get()
            kind = item.get("type")
            if kind == "trace":
                yield encode("trace", item["item"])
            elif kind == "token":
                yield encode("token", {"text": item["text"]})
            elif kind == "result":
                result = item["result"]
                yield encode("complete", result)
            elif kind == "error":
                yield encode("error", {"message": item["message"]})
            elif kind == "done":
                yield encode("done", {})
                break

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

@app.get("/api/agent-runs/{run_id}", response_model=AgentRun)
def get_agent_run(run_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    record = session.scalar(select(AgentRunRecord).where(AgentRunRecord.id == run_id, AgentRunRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Agent run record not found")
    events = []
    for event in sorted(record.events, key=lambda item: item.timestamp):
        events.append({"id": event.id, "event_type": event.event_type, "timestamp": event.timestamp, "payload": json.loads(event.payload_json or "{}")})
    return AgentRun(id=record.id, campaign_id=record.campaign_id, domain_id=record.domain_id, status=record.status, summary=record.summary, events=events)


@app.get("/api/agent-runs", response_model=list[AgentRunListItem])
def list_agent_runs(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return list(session.scalars(select(AgentRunRecord).where(AgentRunRecord.tenant_id == context.tenant_id).order_by(AgentRunRecord.created_at.desc()).limit(100)))


@app.post("/api/agent-chat", response_model=AgentChatResponse)
def run_agent_chat(payload: AgentChatRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    try:
        return copilot.run(session, context, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"智能体运行失败：{exc}") from exc


@app.get("/api/ontology/semantic-model")
def ontology_semantic_model(_context: TenantContext = Depends(get_tenant_context)):
    return semantic_model()


@app.get("/api/agent-evaluations/summary")
def agent_evaluation_summary(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    runs = session.scalars(select(AgentRunRecord).where(AgentRunRecord.tenant_id == context.tenant_id)).all()
    usage = session.scalars(select(ModelUsageRecord).where(ModelUsageRecord.tenant_id == context.tenant_id)).all()
    by_domain: dict[str, dict[str, int | float]] = {}
    for run in runs:
        item = by_domain.setdefault(run.domain_id, {"run_count": 0, "completed": 0, "needs_confirmation": 0, "failed": 0, "success_rate": 0.0})
        item["run_count"] += 1
        if run.status in {"completed", "needs_approval"}:
            item["completed"] += 1
        if run.status in {"needs_approval", "needs_confirmation"}:
            item["needs_confirmation"] += 1
        if run.status == "failed":
            item["failed"] += 1
    for item in by_domain.values():
        item["success_rate"] = round(item["completed"] / item["run_count"] * 100, 2) if item["run_count"] else 0
    return {"run_count": len(runs), "completed_count": sum(item.status in {"completed", "needs_approval"} for item in runs), "failed_count": sum(item.status == "failed" for item in runs), "human_confirmation_count": sum(item.status in {"needs_approval", "needs_confirmation"} for item in runs), "total_tokens": sum(item.total_tokens for item in usage), "by_domain": [{"domain_id": domain_id, **metrics} for domain_id, metrics in sorted(by_domain.items())], "quality_dimensions": ["任务完成率", "人工确认率", "工具调用成功率", "Token用量", "结果可追溯性"]}

@app.get("/api/ontology/governance-summary")
def ontology_governance_summary(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    pipelines = session.scalars(select(DataPipelineJobRecord).where(DataPipelineJobRecord.tenant_id == context.tenant_id)).all()
    documents = session.scalars(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == context.tenant_id)).all()
    entity_count = session.scalar(select(func.count(OntologyEntityRecord.id)).where(OntologyEntityRecord.tenant_id == context.tenant_id)) or 0
    relation_count = session.scalar(select(func.count(OntologyRelationRecord.id)).where(OntologyRelationRecord.tenant_id == context.tenant_id)) or 0
    return {"knowledge_documents": len(documents), "ontology_entities": entity_count, "ontology_relations": relation_count, "awaiting_confirmation": sum(item.status == "awaiting_confirmation" for item in pipelines), "failed_jobs": sum(item.status == "failed" for item in pipelines), "completed_jobs": sum(item.status == "completed" for item in pipelines), "governance_rules": ["知识与本体分流判断", "候选对象人工确认", "来源证据保留", "租户隔离", "删除来源同步清理"]}

@app.get("/api/ontology/status", response_model=OntologySemanticStatus)
def ontology_status(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return semantic_status(session, context.tenant_id)


@app.get("/api/graph", response_model=MarketingGraph)
def tenant_graph(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return build_campaign_graph(session, context.tenant_id)


@app.get("/api/graph/stats", response_model=GraphStats)
def tenant_graph_stats(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return graph_stats(session, context.tenant_id)


@app.get("/api/campaigns/{campaign_id}/graph", response_model=MarketingGraph)
def campaign_graph(campaign_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    get_campaign(campaign_id, context, session)
    return build_campaign_graph(session, context.tenant_id, campaign_id)


def knowledge_document_view(record: KnowledgeDocumentRecord, session: Session) -> KnowledgeDocument:
    chunk_count = session.scalar(select(func.count(KnowledgeChunkRecord.id)).where(KnowledgeChunkRecord.document_id == record.id)) or 0
    entity_count = session.scalar(select(func.count(OntologyEntityRecord.id)).where(OntologyEntityRecord.tenant_id == record.tenant_id, OntologyEntityRecord.external_id == record.external_id)) or 0
    return KnowledgeDocument(id=record.id, external_id=record.external_id, title=record.title, source_type=record.source_type, source_name=record.source_name, classification=record.classification, status=record.status, version=record.version, chunk_count=chunk_count, entity_count=entity_count, created_at=record.created_at, updated_at=record.updated_at)


def delete_knowledge_document_data(session: Session, context: TenantContext, document: KnowledgeDocumentRecord) -> None:
    chunk_ids = session.scalars(select(KnowledgeChunkRecord.external_id).where(KnowledgeChunkRecord.document_id == document.id)).all()
    entities = session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.external_id.in_([document.external_id, *chunk_ids]))).all()
    entity_ids = [item.id for item in entities]
    if entity_ids:
        session.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == context.tenant_id, or_(OntologyRelationRecord.source_entity_id.in_(entity_ids), OntologyRelationRecord.target_entity_id.in_(entity_ids))))
        session.execute(delete(OntologyEntityRecord).where(OntologyEntityRecord.id.in_(entity_ids)))
    session.execute(delete(KnowledgeChunkRecord).where(KnowledgeChunkRecord.document_id == document.id))
    session.delete(document)


@app.get("/api/knowledge/documents", response_model=list[KnowledgeDocument])
def list_knowledge_documents(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == context.tenant_id).order_by(KnowledgeDocumentRecord.updated_at.desc())).all()
    return [knowledge_document_view(record, session) for record in records]


@app.put("/api/knowledge/documents/{document_id}", response_model=KnowledgeDocument)
def update_knowledge_document(document_id: int, payload: KnowledgeDocumentUpdate, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.id == document_id, KnowledgeDocumentRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Resource not found")
    for key, value in payload.model_dump(exclude_none=True).items(): setattr(record, key, value)
    record.version += 1
    session.commit(); session.refresh(record); return knowledge_document_view(record, session)


@app.delete("/api/knowledge/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_document(document_id: int, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.id == document_id, KnowledgeDocumentRecord.tenant_id == context.tenant_id))
    if record is None: raise HTTPException(status_code=404, detail="Knowledge document not found")
    delete_knowledge_document_data(session, context, record)
    session.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/imports", response_model=list[ImportJob])
def list_imports(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(ImportJobRecord).where(ImportJobRecord.tenant_id == context.tenant_id).order_by(ImportJobRecord.created_at.desc()).limit(100)).all()
    return [import_view(record) for record in records]


@app.post("/api/imports", response_model=ImportJob, status_code=status.HTTP_201_CREATED)
def create_import(
    dataset_type: str = Form(...),
    file: UploadFile = File(...),
    context: TenantContext = Depends(require_write),
    session: Session = Depends(get_session),
):
    return import_view(import_file(session, context.tenant_id, context.user_id, dataset_type, file))


def pipeline_view_internal(record: DataPipelineJobRecord) -> DataPipelineJob:
    return DataPipelineJob.model_validate(record).model_copy(update={"result": json.loads(record.result_json or "{}")})


@app.get("/api/internal/integrations/mineru", response_model=IntegrationConfig, include_in_schema=False)
def get_mineru_integration_internal(context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    return integration_view(get_mineru_config(session, context.tenant_id))


@app.put("/api/internal/integrations/mineru", response_model=IntegrationConfig, include_in_schema=False)
def update_mineru_integration_internal(payload: IntegrationConfigUpdate, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = get_mineru_config(session, context.tenant_id)
    if record is None:
        record = IntegrationConfigRecord(tenant_id=context.tenant_id, integration_id="mineru", display_name=payload.display_name, base_url=payload.base_url)
        session.add(record)
    record.display_name = payload.display_name
    record.base_url = payload.base_url.rstrip("/")
    record.enabled = payload.enabled
    record.config_json = json.dumps(payload.config, ensure_ascii=False)
    if payload.api_key:
        record.encrypted_api_key = cipher.encrypt(payload.api_key)
    session.commit(); session.refresh(record)
    return integration_view(record)


@app.get("/api/internal/data-pipelines", response_model=list[DataPipelineJob], include_in_schema=False)
def list_data_pipelines_internal(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(DataPipelineJobRecord).where(DataPipelineJobRecord.tenant_id == context.tenant_id).order_by(DataPipelineJobRecord.created_at.desc()).limit(100)).all()
    return [pipeline_view(record) for record in records]


@app.post("/api/internal/data-pipelines", response_model=DataPipelineCreateResult, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_data_pipeline_internal(file: UploadFile = File(...), context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    filename = file.filename or "upload.bin"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    supported = {"txt", "md", "json", "csv", "pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "html"}
    if suffix not in supported:
        raise HTTPException(status_code=422, detail="不支持的数据文件类型")
    raw = file.file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="数据文件不能超过 20MB")
    job = DataPipelineJobRecord(id=f"DP-{uuid4().hex[:12].upper()}", tenant_id=context.tenant_id, created_by=context.user_id, file_name=filename, file_format=suffix, status="running", current_stage="queued")
    session.add(job); session.commit(); session.refresh(job)
    agent = DataProcessingAgent(session, context, job)
    try:
        job.started_at = datetime.now(timezone.utc)
        events = agent.process(filename, raw)
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:
        session.rollback()
        job = session.get(DataPipelineJobRecord, job.id)
        job.status = "failed"
        job.current_stage = "failed"
        job.error_message = str(exc)[:1000]
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(status_code=502, detail=f"数据处理失败：{exc}") from exc
    return DataPipelineCreateResult(job=pipeline_view(job), stages=events)


def pipeline_view(record: DataPipelineJobRecord) -> DataPipelineJob:
    return DataPipelineJob.model_validate(record).model_copy(update={"result": json.loads(record.result_json or "{}")})


def process_data_pipeline_job(job_id: str, context: TenantContext, filename: str, raw: bytes) -> None:
    with SessionLocal() as session:
        job = session.get(DataPipelineJobRecord, job_id)
        if job is None:
            return
        try:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            session.commit()
            DataProcessingAgent(session, context, job).process(filename, raw)
            session.commit()
        except Exception as exc:
            session.rollback()
            job = session.get(DataPipelineJobRecord, job_id)
            if job is not None:
                job.status = "failed"
                job.current_stage = "failed"
                job.error_message = str(exc)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                session.commit()


@app.get("/api/integrations/mineru", response_model=IntegrationConfig)
def get_mineru_integration(context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    return integration_view(get_mineru_config(session, context.tenant_id))


@app.put("/api/integrations/mineru", response_model=IntegrationConfig)
def update_mineru_integration(payload: IntegrationConfigUpdate, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = get_mineru_config(session, context.tenant_id)
    if record is None:
        record = IntegrationConfigRecord(tenant_id=context.tenant_id, integration_id="mineru", display_name=payload.display_name, base_url=payload.base_url)
        session.add(record)
    record.display_name = payload.display_name; record.base_url = payload.base_url.rstrip("/"); record.enabled = payload.enabled; record.config_json = json.dumps(payload.config, ensure_ascii=False)
    if payload.api_key:
        record.encrypted_api_key = cipher.encrypt(payload.api_key)
    session.commit(); session.refresh(record)
    return integration_view(record)


def data_source_view(record: DataSourceConfigRecord) -> DataSourceConfig:
    return DataSourceConfig(
        id=record.id,
        source_id=record.source_id,
        display_name=record.display_name,
        source_type=record.source_type,
        endpoint=record.endpoint,
        credential_ref=record.credential_ref,
        mapping=json.loads(record.mapping_json or "{}"),
        schedule=record.schedule,
        enabled=record.enabled,
        last_sync_at=record.last_sync_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/api/data-sources", response_model=list[DataSourceConfig])
def list_data_sources(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(DataSourceConfigRecord).where(DataSourceConfigRecord.tenant_id == context.tenant_id).order_by(DataSourceConfigRecord.updated_at.desc())).all()
    return [data_source_view(record) for record in records]


@app.post("/api/data-sources", response_model=DataSourceConfig, status_code=status.HTTP_201_CREATED)
def create_data_source(payload: DataSourceConfigBase, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    existing = session.scalar(select(DataSourceConfigRecord).where(DataSourceConfigRecord.tenant_id == context.tenant_id, DataSourceConfigRecord.source_id == payload.source_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="数据源编号已存在")
    record = DataSourceConfigRecord(tenant_id=context.tenant_id, source_id=payload.source_id, display_name=payload.display_name, source_type=payload.source_type, endpoint=payload.endpoint, credential_ref=payload.credential_ref, mapping_json=json.dumps(payload.mapping, ensure_ascii=False), schedule=payload.schedule, enabled=payload.enabled)
    session.add(record); session.commit(); session.refresh(record)
    return data_source_view(record)


@app.put("/api/data-sources/{source_id}", response_model=DataSourceConfig)
def update_data_source(source_id: str, payload: DataSourceConfigBase, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = session.scalar(select(DataSourceConfigRecord).where(DataSourceConfigRecord.tenant_id == context.tenant_id, DataSourceConfigRecord.source_id == source_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    record.display_name = payload.display_name; record.source_type = payload.source_type; record.endpoint = payload.endpoint; record.credential_ref = payload.credential_ref; record.mapping_json = json.dumps(payload.mapping, ensure_ascii=False); record.schedule = payload.schedule; record.enabled = payload.enabled
    session.commit(); session.refresh(record)
    return data_source_view(record)


@app.post("/api/data-sources/{source_id}/test")
def test_data_source(source_id: str, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = session.scalar(select(DataSourceConfigRecord).where(DataSourceConfigRecord.tenant_id == context.tenant_id, DataSourceConfigRecord.source_id == source_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if not record.endpoint and record.source_type not in {"file", "hotspot"}:
        raise HTTPException(status_code=422, detail="接口或数据库数据源必须配置连接地址")
    return {"source_id": record.source_id, "status": "ready", "message": "数据源配置校验通过，可进入同步任务", "checked_at": datetime.now(timezone.utc)}

@app.post("/api/ndc/mock/air-shopping")
def ndc_mock_air_shopping(payload: NdcAirShoppingRequest):
    return air_shopping_payload(payload.origin, payload.destination, payload.departure_date, payload.sales_channel)


@app.post("/api/ndc/mock/best-pricing")
def ndc_mock_best_pricing(payload: NdcAirShoppingRequest):
    return best_pricing_payload(payload.origin, payload.destination, payload.departure_date, payload.sales_channel)


@app.post("/api/ndc/mock/order-list")
def ndc_mock_order_list(payload: NdcOrderListRequest):
    return order_list_payload(payload.sales_channel)


@app.post("/api/ndc/mock/sync-flight-products", response_model=DataPipelineCreateResult, status_code=status.HTTP_202_ACCEPTED)
def sync_ndc_mock_flight_products(payload: NdcAirShoppingRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    source_id = "ndc24-flight-shopping-mock"
    source = session.scalar(select(DataSourceConfigRecord).where(DataSourceConfigRecord.tenant_id == context.tenant_id, DataSourceConfigRecord.source_id == source_id))
    if source is None:
        source = DataSourceConfigRecord(tenant_id=context.tenant_id, source_id=source_id, display_name="NDC24.1模拟航班产品接口", source_type="product", endpoint="/api/ndc/mock/air-shopping", mapping_json=json.dumps({"protocol": "NDC", "version": "24.1", "synthetic": True}, ensure_ascii=False), schedule="manual", enabled=True)
        session.add(source)
        session.flush()
    response = air_shopping_payload(payload.origin, payload.destination, payload.departure_date, payload.sales_channel)
    filename = f"NDC24.1-{payload.origin.upper()}-{payload.destination.upper()}-{response['data']['query']['departureDate']}.json"
    job = DataPipelineJobRecord(id=f"DP-{uuid4().hex[:12].upper()}", tenant_id=context.tenant_id, created_by=context.user_id, file_name=filename, file_format="json", source_type="product", status="running", current_stage="queued")
    session.add(job)
    session.commit()
    session.refresh(job)
    agent = DataProcessingAgent(session, context, job)
    try:
        job.started_at = datetime.now(timezone.utc)
        stages = agent.process_structured(response["data"], "NDC 24.1模拟航班产品接口")
        source.last_sync_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:
        session.rollback()
        job = session.get(DataPipelineJobRecord, job.id)
        job.status = "failed"
        job.current_stage = "failed"
        job.error_message = str(exc)[:1000]
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(status_code=502, detail=f"NDC模拟数据处理失败：{exc}") from exc
    return DataPipelineCreateResult(job=pipeline_view(job), stages=stages)

@app.post("/api/data-pipelines/interface", response_model=DataPipelineCreateResult, status_code=status.HTTP_202_ACCEPTED)
def create_interface_pipeline(payload: InterfacePipelineRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    raw = json.dumps(payload.records, ensure_ascii=False).encode("utf-8")
    filename = f"{payload.source_name}.json"
    job = DataPipelineJobRecord(id=f"DP-{uuid4().hex[:12].upper()}", tenant_id=context.tenant_id, created_by=context.user_id, file_name=filename, file_format="json", source_type=payload.source_type, status="running", current_stage="queued")
    session.add(job); session.commit(); session.refresh(job)
    agent = DataProcessingAgent(session, context, job)
    try:
        job.started_at = datetime.now(timezone.utc)
        stages = agent.process(filename, raw)
        job.status = "completed"; job.completed_at = datetime.now(timezone.utc); session.commit()
    except Exception as exc:
        session.rollback(); job = session.get(DataPipelineJobRecord, job.id); job.status="failed"; job.current_stage="failed"; job.error_message=str(exc)[:1000]; job.completed_at=datetime.now(timezone.utc); session.commit()
        raise HTTPException(status_code=502, detail=f"Interface data processing failed: {exc}") from exc
    return DataPipelineCreateResult(job=pipeline_view(job), stages=stages)


@app.post("/api/data-pipelines/flight-products", response_model=DataPipelineCreateResult, status_code=status.HTTP_202_ACCEPTED)
def create_flight_product_pipeline(payload: FlightProductPipelineRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    filename = f"{payload.source_name}.json"
    job = DataPipelineJobRecord(id=f"DP-{uuid4().hex[:12].upper()}", tenant_id=context.tenant_id, created_by=context.user_id, file_name=filename, file_format="json", source_type="scraper", status="running", current_stage="queued")
    session.add(job); session.commit(); session.refresh(job)
    agent = DataProcessingAgent(session, context, job)
    try:
        job.started_at = datetime.now(timezone.utc)
        stages = agent.process_structured(payload.payload, payload.source_name)
        if not payload.require_confirmation and job.status == "awaiting_confirmation":
            agent.confirm("approve", "Auto-confirmed by explicitly requested trusted pipeline mode", "system")
        session.commit()
    except Exception as exc:
        session.rollback(); job = session.get(DataPipelineJobRecord, job.id)
        job.status = "failed"; job.current_stage = "failed"; job.error_message = str(exc)[:1000]; job.completed_at = datetime.now(timezone.utc); session.commit()
        raise HTTPException(status_code=502, detail=f"Flight/product pipeline failed: {exc}") from exc
    return DataPipelineCreateResult(job=pipeline_view(job), stages=stages)

@app.get("/api/data-pipelines", response_model=list[DataPipelineJob])
def list_data_pipelines(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(DataPipelineJobRecord).where(DataPipelineJobRecord.tenant_id == context.tenant_id).order_by(DataPipelineJobRecord.created_at.desc()).limit(100)).all()
    return [pipeline_view(record) for record in records]


@app.get("/api/data-pipelines/{job_id}", response_model=DataPipelineJob)
def get_data_pipeline(job_id: str, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    record = session.scalar(select(DataPipelineJobRecord).where(DataPipelineJobRecord.id == job_id, DataPipelineJobRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据处理任务不存在")
    return pipeline_view(record)


@app.post("/api/data-pipelines/{job_id}/cancel", response_model=DataPipelineJob)
def cancel_data_pipeline(job_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(DataPipelineJobRecord).where(DataPipelineJobRecord.id == job_id, DataPipelineJobRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据处理任务不存在")
    if record.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="只有排队中或处理中的任务可以取消")
    record.status = "cancelled"
    record.current_stage = "cancelled"
    record.error_message = "由用户取消"
    record.completed_at = datetime.now(timezone.utc)
    session.commit(); session.refresh(record)
    return pipeline_view(record)


@app.delete("/api/data-pipelines/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_pipeline(job_id: str, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(DataPipelineJobRecord).where(DataPipelineJobRecord.id == job_id, DataPipelineJobRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据处理任务不存在")
    if record.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="任务正在处理，暂不能删除")
    result = json.loads(record.result_json or "{}")
    source_name = f"data-pipeline:{record.id}"
    entities = session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.source == source_name)).all()
    entity_ids = [item.id for item in entities]
    if entity_ids:
        session.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == context.tenant_id, or_(OntologyRelationRecord.source_entity_id.in_(entity_ids), OntologyRelationRecord.target_entity_id.in_(entity_ids))))
        session.execute(delete(OntologyEntityRecord).where(OntologyEntityRecord.id.in_(entity_ids)))
    document_external_id = str(result.get("document_id") or "")
    document = session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == context.tenant_id, KnowledgeDocumentRecord.external_id == document_external_id)) if document_external_id else None
    if document is not None:
        chunk_external_ids = session.scalars(select(KnowledgeChunkRecord.external_id).where(KnowledgeChunkRecord.tenant_id == context.tenant_id, KnowledgeChunkRecord.document_id == document.id)).all()
        graph_entities = session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.external_id.in_([document.external_id, *chunk_external_ids]))).all()
        graph_ids = [item.id for item in graph_entities]
        if graph_ids:
            session.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == context.tenant_id, or_(OntologyRelationRecord.source_entity_id.in_(graph_ids), OntologyRelationRecord.target_entity_id.in_(graph_ids))))
            session.execute(delete(OntologyEntityRecord).where(OntologyEntityRecord.id.in_(graph_ids)))
        session.execute(delete(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == context.tenant_id, KnowledgeChunkRecord.document_id == document.id))
        session.delete(document)
    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/data-pipelines", response_model=DataPipelineCreateResult, status_code=status.HTTP_202_ACCEPTED)
def create_data_pipeline(background_tasks: BackgroundTasks, file: UploadFile = File(...), context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    filename = file.filename or "upload.bin"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {"txt", "md", "json", "csv", "pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "html"}
    if suffix not in allowed:
        raise HTTPException(status_code=422, detail="不支持的数据文件类型")
    raw = file.file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="数据文件不能超过 20MB")
    job = DataPipelineJobRecord(id=f"DP-{uuid4().hex[:12].upper()}", tenant_id=context.tenant_id, created_by=context.user_id, file_name=filename, file_format=suffix, status="queued", current_stage="queued")
    session.add(job); session.commit(); session.refresh(job)
    background_tasks.add_task(process_data_pipeline_job, job.id, context, filename, raw)
    return DataPipelineCreateResult(job=pipeline_view(job), stages=[{"stage": "queued", "label": "文件已进入处理队列", "status": "pending", "timestamp": datetime.now(timezone.utc).isoformat()}])


@app.post("/api/data-pipelines/{job_id}/review", response_model=DataPipelineJob)
def review_data_pipeline(job_id: str, payload: DataPipelineReviewRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    record = session.scalar(select(DataPipelineJobRecord).where(DataPipelineJobRecord.id == job_id, DataPipelineJobRecord.tenant_id == context.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="数据处理任务不存在")
    if record.status != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail="该任务当前不处于待确认状态")
    reviewer = session.get(UserRecord, context.user_id)
    DataProcessingAgent(session, context, record).confirm(payload.decision, payload.note, reviewer.display_name if reviewer else str(context.user_id))
    session.refresh(record)
    return pipeline_view(record)



@app.get("/api/knowledge/search", response_model=list[KnowledgeSearchResult])
def search_knowledge(q: str = "", limit: int = 10, context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    query = q.strip().lower()
    chunks = session.scalars(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == context.tenant_id).order_by(KnowledgeChunkRecord.created_at.desc()).limit(500)).all()
    documents = {item.id: item for item in session.scalars(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == context.tenant_id)).all()}
    selected = [item for item in chunks if not query or query in item.content.lower()][:max(1, min(limit, 50))]
    if not selected:
        return []
    ontology_chunks = {
        item.external_id: item
        for item in session.scalars(
            select(OntologyEntityRecord).where(
                OntologyEntityRecord.tenant_id == context.tenant_id,
                OntologyEntityRecord.external_id.in_([item.external_id for item in selected]),
            )
        ).all()
    }
    relations = session.scalars(
        select(OntologyRelationRecord).where(
            OntologyRelationRecord.tenant_id == context.tenant_id,
            OntologyRelationRecord.source_entity_id.in_([item.id for item in ontology_chunks.values()]),
        )
    ).all()
    linked_ids = {item.target_entity_id for item in relations}
    linked = {item.id: item for item in session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.id.in_(linked_ids))).all()}
    by_chunk = {}
    for relation in relations:
        target = linked.get(relation.target_entity_id)
        if target:
            by_chunk.setdefault(relation.source_entity_id, []).append({"id": target.external_id, "type": target.entity_type, "label": target.label, "confidence": relation.confidence})
    return [KnowledgeSearchResult(chunk_id=item.external_id, document_id=documents[item.document_id].external_id, title=documents[item.document_id].title, content=item.content, metadata=json.loads(item.metadata_json or "{}"), linked_objects=by_chunk.get(ontology_chunks[item.external_id].id, []) if item.external_id in ontology_chunks else []) for item in selected if item.document_id in documents]


@app.get("/api/model-providers", response_model=list[ModelProvider])
def list_model_providers(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    records = session.scalars(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == context.tenant_id).order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id)).all()
    return [provider_view(record) for record in records]


@app.post("/api/model-providers", response_model=ModelProvider, status_code=status.HTTP_201_CREATED)
def create_model_provider(payload: ModelProviderCreate, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    if payload.provider_type != "mock" and not payload.base_url:
        raise HTTPException(status_code=422, detail="OpenAI 兼容模型必须配置服务地址")
    if payload.is_default:
        clear_default(session, context.tenant_id)
    record = ModelProviderRecord(tenant_id=context.tenant_id, **payload.model_dump(exclude={"api_key"}), encrypted_api_key=cipher.encrypt(payload.api_key))
    session.add(record)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="模型配置名称已存在") from exc
    session.refresh(record)
    return provider_view(record)


def scoped_provider(session: Session, tenant_id: int, provider_id: int) -> ModelProviderRecord:
    record = session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.id == provider_id, ModelProviderRecord.tenant_id == tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return record


@app.put("/api/model-providers/{provider_id}", response_model=ModelProvider)
def update_model_provider(provider_id: int, payload: ModelProviderUpdate, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    changes = payload.model_dump(exclude_unset=True)
    api_key = changes.pop("api_key", None)
    if api_key is not None:
        record.encrypted_api_key = cipher.encrypt(api_key)
    if changes.get("is_default"):
        clear_default(session, context.tenant_id, excluding_id=provider_id)
    for key, value in changes.items():
        setattr(record, key, value)
    session.commit(); session.refresh(record)
    return provider_view(record)


@app.post("/api/model-providers/{provider_id}/default", response_model=ModelProvider)
def set_default_provider(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    clear_default(session, context.tenant_id, excluding_id=provider_id)
    record.is_default = True; record.enabled = True
    session.commit(); session.refresh(record)
    return provider_view(record)


@app.post("/api/model-providers/{provider_id}/test", response_model=ProviderTestResult)
def test_model_provider(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    try:
        result = llm_client.generate_result(
            LLMConfig(record.provider_type, record.base_url, record.model_name, cipher.decrypt(record.encrypted_api_key), record.timeout_seconds, record.temperature, min(record.max_tokens, 256)),
            "你是东方航空智能营销平台的模型连通性检测助手。",
            "仅回复：模型连接正常。",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型连接失败：{exc}") from exc
    session.add(ModelUsageRecord(tenant_id=context.tenant_id, provider_id=record.id, request_type="connectivity-test", model_name=result.model_name or record.model_name, prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens, total_tokens=result.total_tokens))
    session.commit()
    return ProviderTestResult(ok=True, provider=record.display_name, model=result.model_name or record.model_name, message=result.content[:160])


@app.get("/api/model-providers/{provider_id}/models", response_model=ProviderModelsResult)
def discover_provider_models(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    try:
        models = llm_client.list_models(LLMConfig(
            record.provider_type,
            record.base_url,
            record.model_name,
            cipher.decrypt(record.encrypted_api_key),
            record.timeout_seconds,
            record.temperature,
            record.max_tokens,
        ))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取可用模型失败：{exc}") from exc
    return ProviderModelsResult(provider_id=provider_id, models=models)


@app.get("/api/model-providers/{provider_id}/usage", response_model=ProviderUsageResult)
def get_provider_usage(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    scoped_provider(session, context.tenant_id, provider_id)
    rows = session.execute(
        select(
            ModelUsageRecord.model_name,
            func.count(ModelUsageRecord.id),
            func.coalesce(func.sum(ModelUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0),
        )
        .where(ModelUsageRecord.tenant_id == context.tenant_id, ModelUsageRecord.provider_id == provider_id)
        .group_by(ModelUsageRecord.model_name)
        .order_by(func.sum(ModelUsageRecord.total_tokens).desc())
    ).all()
    by_model = [
        {"model_name": row[0], "request_count": row[1], "prompt_tokens": row[2], "completion_tokens": row[3], "total_tokens": row[4]}
        for row in rows
    ]
    return ProviderUsageResult(
        provider_id=provider_id,
        request_count=sum(item["request_count"] for item in by_model),
        prompt_tokens=sum(item["prompt_tokens"] for item in by_model),
        completion_tokens=sum(item["completion_tokens"] for item in by_model),
        total_tokens=sum(item["total_tokens"] for item in by_model),
        by_model=by_model,
    )


@app.delete("/api/model-providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_provider(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    if record.is_default:
        raise HTTPException(status_code=409, detail="默认模型不能删除，请先切换默认模型")
    session.delete(record); session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
