from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantRecord(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TenantMembershipRecord(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    tenant: Mapped[TenantRecord] = relationship()
    user: Mapped[UserRecord] = relationship()


class CampaignRecord(Base):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_campaign_tenant_business_id"),)

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(16))
    owner: Mapped[str] = mapped_column(String(64))
    audience_size: Mapped[int] = mapped_column(Integer)
    product_package: Mapped[str] = mapped_column(String(160))
    budget_yuan: Mapped[int] = mapped_column(Integer)
    roi_target: Mapped[float] = mapped_column(Float)


class ModelProviderRecord(Base):
    __tablename__ = "model_providers"
    __table_args__ = (UniqueConstraint("tenant_id", "display_name", name="uq_model_provider_tenant_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    provider_type: Mapped[str] = mapped_column(String(40), default="openai-compatible")
    base_url: Mapped[str] = mapped_column(String(300), default="")
    model_name: Mapped[str] = mapped_column(String(120))
    encrypted_api_key: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(String(32), index=True)
    domain_id: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(64))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("model_providers.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    events: Mapped[list["RuntimeEventRecord"]] = relationship(cascade="all, delete-orphan", back_populates="run")


class RuntimeEventRecord(Base):
    __tablename__ = "runtime_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[AgentRunRecord] = relationship(back_populates="events")


class ImportJobRecord(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    dataset_type: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(200))
    file_format: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OntologyEntityRecord(Base):
    __tablename__ = "ontology_entities"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_ontology_entity_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(200))
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    import_job_id: Mapped[str | None] = mapped_column(ForeignKey("import_jobs.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class OntologyRelationRecord(Base):
    __tablename__ = "ontology_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("ontology_entities.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(80), index=True)
    target_entity_id: Mapped[int] = mapped_column(ForeignKey("ontology_entities.id", ondelete="CASCADE"), index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(160), default="import")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    import_job_id: Mapped[str | None] = mapped_column(ForeignKey("import_jobs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PersonaDimensionDefinitionRecord(Base):
    __tablename__ = "persona_dimension_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "field_code", name="uq_persona_dimension_tenant_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    module_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    field_name: Mapped[str] = mapped_column(String(120))
    field_code: Mapped[str] = mapped_column(String(120), index=True)
    data_type: Mapped[str] = mapped_column(String(32))
    source_data_type: Mapped[str] = mapped_column(String(40))
    collection_method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    required_mode: Mapped[str] = mapped_column(String(32))
    allowed_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    applicable_personas_json: Mapped[str] = mapped_column(Text, default="[]")
    is_supplemental: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str] = mapped_column(String(200))
    source_version: Mapped[str] = mapped_column(String(32))
    source_row: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PersonaSegmentRecord(Base):
    __tablename__ = "persona_segments"
    __table_args__ = (UniqueConstraint("tenant_id", "segment_code", name="uq_persona_segment_tenant_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    segment_code: Mapped[str] = mapped_column(String(24), index=True)
    primary_persona_code: Mapped[str] = mapped_column(String(8), index=True)
    primary_persona_name: Mapped[str] = mapped_column(String(80))
    segment_name: Mapped[str] = mapped_column(String(120))
    belongs_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    within_persona_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_products: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_channels: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str] = mapped_column(String(200))
    source_version: Mapped[str] = mapped_column(String(32))
    source_row: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rules: Mapped[list["PersonaSegmentRuleRecord"]] = relationship(cascade="all, delete-orphan", back_populates="segment")


class PersonaSegmentRuleRecord(Base):
    __tablename__ = "persona_segment_rules"
    __table_args__ = (UniqueConstraint("segment_id", "source_row", name="uq_persona_segment_rule_source_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("persona_segments.id", ondelete="CASCADE"), index=True)
    dimension_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    field_code: Mapped[str] = mapped_column(String(120), index=True)
    field_variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    condition_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_operator: Mapped[str | None] = mapped_column(String(24), nullable=True)
    condition_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    field_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_order: Mapped[int] = mapped_column(Integer)
    source_row: Mapped[int] = mapped_column(Integer)
    segment: Mapped[PersonaSegmentRecord] = relationship(back_populates="rules")
