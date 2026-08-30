import json
from contextlib import asynccontextmanager
from contextlib import contextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .agents import AgentRuntime
from .auth import TenantContext, create_token, get_current_user, get_tenant_context, hash_password, require_admin, require_platform_admin, require_write, verify_password
from .config import get_settings
from .data import AGENT_DOMAINS
from .database import Base, SessionLocal, engine, get_session
from .db_models import AgentRunRecord, CampaignRecord, ImportJobRecord, ModelProviderRecord, TenantMembershipRecord, TenantRecord, UserRecord
from .imports import import_file
from .llm import LLMClient, LLMConfig
from .migrations import assign_legacy_records, enforce_postgres_tenant_constraints, migrate_legacy_schema
from .models import (
    AgentRun,
    AgentRunListItem,
    AgentRunRequest,
    Campaign,
    CurrentUser,
    GraphStats,
    ImportJob,
    LoginRequest,
    LoginResponse,
    MarketingGraph,
    OntologySemanticStatus,
    ModelProvider,
    ModelProviderCreate,
    ModelProviderUpdate,
    ProviderTestResult,
    MembershipCreate,
    PlatformUserCreate,
    PlatformUserSummary,
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
    with database_initialization_lock():
        Base.metadata.create_all(bind=engine)
        migrate_legacy_schema(engine)
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
runtime = AgentRuntime()
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
    return {"status": "ready", "database": "connected"}


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


@app.get("/api/agent-domains")
def list_agent_domains(_context: TenantContext = Depends(get_tenant_context)):
    return AGENT_DOMAINS


@app.post("/api/agent-runs", response_model=AgentRun)
def run_agent(request: AgentRunRequest, context: TenantContext = Depends(require_write), session: Session = Depends(get_session)):
    return runtime.run(session, context, request)


@app.get("/api/agent-runs", response_model=list[AgentRunListItem])
def list_agent_runs(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return list(session.scalars(select(AgentRunRecord).where(AgentRunRecord.tenant_id == context.tenant_id).order_by(AgentRunRecord.created_at.desc()).limit(100)))


@app.get("/api/ontology/semantic-model")
def ontology_semantic_model(_context: TenantContext = Depends(get_tenant_context)):
    return semantic_model()


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
        result = llm_client.generate(
            LLMConfig(record.provider_type, record.base_url, record.model_name, cipher.decrypt(record.encrypted_api_key), record.timeout_seconds, record.temperature, min(record.max_tokens, 256)),
            "你是东方航空智能营销平台的模型连通性检测助手。",
            "仅回复：模型连接正常。",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型连接失败：{exc}") from exc
    return ProviderTestResult(ok=True, provider=record.display_name, model=record.model_name, message=result[:160])


@app.delete("/api/model-providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_provider(provider_id: int, context: TenantContext = Depends(require_admin), session: Session = Depends(get_session)):
    record = scoped_provider(session, context.tenant_id, provider_id)
    if record.is_default:
        raise HTTPException(status_code=409, detail="默认模型不能删除，请先切换默认模型")
    session.delete(record); session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
