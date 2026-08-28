from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantSummary(BaseModel):
    id: int
    code: str
    name: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    display_name: str
    tenants: list[TenantSummary]
    is_platform_admin: bool = False


class CurrentUser(BaseModel):
    id: int
    username: str
    display_name: str
    active_tenant: TenantSummary
    tenants: list[TenantSummary]
    is_platform_admin: bool = False


class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)


class PlatformUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    tenant_id: int
    role: Literal["admin", "manager", "analyst", "viewer"] = "viewer"


class PlatformUserSummary(BaseModel):
    id: int
    username: str
    display_name: str
    enabled: bool
    is_platform_admin: bool
    memberships: list[TenantSummary]


class MembershipCreate(BaseModel):
    tenant_id: int
    role: Literal["admin", "manager", "analyst", "viewer"]


class Campaign(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    stage: str
    status: str
    version: str
    owner: str
    audience_size: int
    product_package: str
    budget_yuan: int
    roi_target: float


class CampaignUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class OpportunityBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    market_scope: str = Field(default="\u8349\u7a3f", max_length=40)
    route: str = Field(default="", max_length=120)
    signal_summary: str = Field(default="", max_length=2000)
    status: str = Field(default="\u5f85\u8bc4\u4f30", max_length=32)
    score: int = Field(default=0, ge=0, le=100)
    estimated_audience: int = Field(default=0, ge=0)
    estimated_revenue_yuan: int = Field(default=0, ge=0)
    owner: str = Field(default="", max_length=64)


class OpportunityCreate(OpportunityBase):
    id: str = Field(default="", max_length=32)


class OpportunityUpdate(OpportunityBase):
    pass


class Opportunity(OpportunityBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class MarketHotspotInput(BaseModel):
    source_name: str = Field(min_length=2, max_length=160)
    source_type: Literal["rss", "atom", "opml", "api", "web", "social", "manual"] = "api"
    source_url: str = Field(default="", max_length=500)
    external_id: str = Field(default="", max_length=240)
    canonical_url: str = Field(default="", max_length=500)
    title: str = Field(min_length=2, max_length=500)
    content: str = Field(default="", max_length=50000)
    published_at: datetime | None = None
    language: str = Field(default="zh", max_length=16)
    region: str = Field(default="", max_length=120)


class MarketHotspotIngestRequest(BaseModel):
    records: list[MarketHotspotInput] = Field(min_length=1, max_length=500)
    process_with_agent: bool = True


class MarketHotspotSource(BaseModel):
    source_name: str = Field(min_length=2, max_length=160)
    source_url: str = Field(min_length=8, max_length=500)
    source_type: Literal["rss", "atom"] = "rss"
    max_items: int = Field(default=30, ge=1, le=200)


class MarketHotspotSourceInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    url: str = Field(min_length=8, max_length=500)
    source_type: Literal["rss", "atom", "opml"] = "rss"
    max_items: int = Field(default=30, ge=1, le=100)


class MarketHotspotCollectRequest(BaseModel):
    sources: list[MarketHotspotSourceInput] = Field(min_length=1, max_length=30)
    process_with_agent: bool = True


class MarketHotspotReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class MarketHotspotOpportunityRequest(BaseModel):
    owner: str = Field(default="", max_length=64)
    estimated_audience: int = Field(default=0, ge=0)
    estimated_revenue_yuan: int = Field(default=0, ge=0)


class MarketHotspot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_name: str
    source_type: str
    source_url: str
    external_id: str
    canonical_url: str
    title: str
    content: str
    summary: str
    published_at: datetime | None
    collected_at: datetime
    language: str
    region: str
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    decision: dict[str, Any] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    relevance_score: float
    trend_score: float
    sentiment: str
    status: str
    ontology_status: str
    agent_run_id: str
    created_at: datetime
    updated_at: datetime


class MarketHotspotBatchResult(BaseModel):
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    hotspots: list[MarketHotspot] = Field(default_factory=list)
    source_health: list[dict[str, Any]] = Field(default_factory=list)


class AudienceTagBase(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="\u57fa\u7840\u5c5e\u6027", max_length=80)
    source: str = Field(default="\u7528\u6237\u753b\u50cf\u5e73\u53f0", max_length=120)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True


class AudienceTag(AudienceTagBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class AudiencePackageBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    selection_mode: Literal["tag-combination", "ai-selection"] = "tag-combination"
    tag_ids: list[int] = Field(default_factory=list)
    expression: dict[str, Any] = Field(default_factory=dict)
    estimated_size: int = Field(default=0, ge=0)
    status: str = Field(default="\u8349\u7a3f", max_length=32)


class AudiencePackage(AudiencePackageBase):
    id: int
    external_id: str
    created_at: datetime
    updated_at: datetime


class KnowledgeDocument(BaseModel):
    id: int
    external_id: str
    title: str
    source_type: str
    source_name: str
    classification: str
    status: str
    version: int
    chunk_count: int = 0
    entity_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    classification: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=32)


class InterfacePipelineRequest(BaseModel):
    source_type: Literal["flight", "customer", "market", "operation", "hotspot"]
    source_name: str = Field(min_length=2, max_length=120)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=5000)


class FlightProductPipelineRequest(BaseModel):
    source_name: str = Field(default="China Eastern flight and product scraper", min_length=2, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    require_confirmation: bool = True

class AgentDomain(BaseModel):
    id: str
    name: str
    module: str
    responsibility: str
    input_types: list[str]
    output_types: list[str]
    status: Literal["ready", "running", "blocked"] = "ready"


class AgentRunRequest(BaseModel):
    campaign_id: str
    domain_id: str
    operator: str = ""
    provider_id: int | None = None


class RuntimeEvent(BaseModel):
    id: str
    run_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentRun(BaseModel):
    id: str
    campaign_id: str
    domain_id: str
    status: Literal["completed", "needs_approval", "failed"]
    summary: str
    events: list[RuntimeEvent]


class AgentRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    campaign_id: str
    domain_id: str
    operator: str
    status: str
    summary: str
    created_at: datetime


class ModelProviderCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    provider_type: Literal["openai-compatible", "mock"] = "openai-compatible"
    base_url: str = ""
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str = ""
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=128, le=32768)
    enabled: bool = True
    is_default: bool = False


class ModelProviderUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    provider_type: Literal["openai-compatible", "mock"] | None = None
    base_url: str | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=128, le=32768)
    enabled: bool | None = None
    is_default: bool | None = None


class ModelProvider(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str
    provider_type: str
    base_url: str
    model_name: str
    timeout_seconds: int
    temperature: float
    max_tokens: int
    enabled: bool
    is_default: bool
    api_key_configured: bool = False
    created_at: datetime
    updated_at: datetime


class ProviderTestResult(BaseModel):
    ok: bool
    provider: str
    model: str
    message: str


class ProviderModel(BaseModel):
    id: str
    owned_by: str = ""


class ProviderModelsResult(BaseModel):
    provider_id: int
    models: list[ProviderModel]


class ModelUsageItem(BaseModel):
    model_name: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ProviderUsageResult(BaseModel):
    provider_id: int
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    by_model: list[ModelUsageItem]


class IntegrationConfigUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    base_url: str = "https://mineru.net"
    api_key: str = ""
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    integration_id: str
    display_name: str
    base_url: str
    enabled: bool
    api_key_configured: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class DataPipelineJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    file_name: str
    file_format: str
    source_type: str
    status: str
    current_stage: str
    mineru_task_id: str
    provider_id: int | None
    total_entities: int
    total_relations: int
    accepted_entities: int
    accepted_relations: int
    rejected_items: int
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class DataPipelineCreateResult(BaseModel):
    job: DataPipelineJob
    stages: list[dict[str, Any]] = Field(default_factory=list)


class DataPipelineReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    linked_objects: list[dict[str, Any]] = Field(default_factory=list)


class AgentChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str = Field(default="", max_length=80)
    domain_id: str = Field(default="marketing-copilot", max_length=80)
    provider_id: int | None = None
    history: list[AgentChatMessage] = Field(default_factory=list, max_length=30)


class AgentChatResponse(BaseModel):
    conversation_id: str
    answer: str
    provider_id: int
    model_name: str
    trace: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class OntologyNode(BaseModel):
    id: str
    type: str
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str
    confidence: float = 1.0


class OntologyEdge(BaseModel):
    source: str
    relation: str
    target: str
    evidence: str
    confidence: float = Field(ge=0, le=1)


class MarketingGraph(BaseModel):
    campaign_id: str | None = None
    nodes: list[OntologyNode]
    edges: list[OntologyEdge]


class ImportJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_type: str
    file_name: str
    file_format: str
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None


class GraphStats(BaseModel):
    entity_count: int
    relation_count: int
    entity_types: dict[str, int]
    source_count: int


class OntologySemanticStatus(BaseModel):
    semantic_model_version: str
    registered_object_type_count: int
    registered_relation_type_count: int
    instance_entity_count: int
    instance_relation_count: int
    registered_instance_types: dict[str, int]
    legacy_or_extension_types: dict[str, int]
    registered_instance_relations: dict[str, int]
    legacy_or_extension_relations: dict[str, int]
