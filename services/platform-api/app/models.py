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


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    linked_objects: list[dict[str, Any]] = Field(default_factory=list)


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
