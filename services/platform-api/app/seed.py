import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .db_models import (
    IntegrationConfigRecord,
    ModelProviderRecord,
    PersonaDimensionDefinitionRecord,
    PersonaSegmentRecord,
    PersonaSegmentRuleRecord,
    TenantMembershipRecord,
    TenantRecord,
    UserRecord,
)
from .security import SecretCipher


PERSONA_CATALOG_PATH = Path(__file__).with_name("persona_catalog_seed.json")


def seed_database(session: Session) -> int:
    settings = get_settings()
    # 租户模型只保留业务租户；清理早期版本遗留的演示电商租户。
    legacy_tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == "CEA-ECOM"))
    if legacy_tenant is not None:
        session.execute(delete(TenantMembershipRecord).where(TenantMembershipRecord.tenant_id == legacy_tenant.id))
        session.delete(legacy_tenant)
        session.flush()
    headquarters = session.scalar(select(TenantRecord).where(TenantRecord.code == "CEA-HQ"))
    if headquarters is None:
        headquarters = TenantRecord(code="CEA-HQ", name="东航营销运营中心")
        session.add(headquarters)
        session.flush()
    admin = session.scalar(select(UserRecord).where(UserRecord.username == settings.initial_admin_username))
    if admin is None:
        admin = UserRecord(
            username=settings.initial_admin_username,
            display_name="平台管理员",
            password_hash=hash_password(settings.initial_admin_password),
            is_platform_admin=True,
        )
        session.add(admin)
        session.flush()
    elif not admin.is_platform_admin:
        admin.is_platform_admin = True
    for tenant in (headquarters,):
        membership = session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == tenant.id,
                TenantMembershipRecord.user_id == admin.id,
            )
        )
        if membership is None:
            session.add(TenantMembershipRecord(tenant_id=tenant.id, user_id=admin.id, role="admin"))

    session.commit()
    return headquarters.id


def seed_tenant_data(session: Session, headquarters_id: int) -> None:
    settings = get_settings()
    if session.scalar(select(ModelProviderRecord.id).where(ModelProviderRecord.tenant_id == headquarters_id).limit(1)) is None:
        session.add(
            ModelProviderRecord(
                tenant_id=headquarters_id,
                display_name="内置测试模型",
                provider_type="mock",
                base_url="",
                model_name="ceair-governed-mock-v1",
                enabled=True,
                is_default=True,
            )
        )
    if settings.bootstrap_model_api_key and settings.bootstrap_model_base_url and settings.bootstrap_model_name:
        bootstrap_provider = session.scalar(
            select(ModelProviderRecord).where(
                ModelProviderRecord.tenant_id == headquarters_id,
                ModelProviderRecord.display_name == settings.bootstrap_model_display_name,
            )
        )
        if bootstrap_provider is None:
            session.query(ModelProviderRecord).filter(ModelProviderRecord.tenant_id == headquarters_id).update({"is_default": False})
            bootstrap_provider = ModelProviderRecord(
                tenant_id=headquarters_id,
                display_name=settings.bootstrap_model_display_name,
                provider_type="openai-compatible",
                base_url=settings.bootstrap_model_base_url.rstrip("/"),
                model_name=settings.bootstrap_model_name,
                encrypted_api_key=SecretCipher().encrypt(settings.bootstrap_model_api_key),
                timeout_seconds=180,
                max_tokens=512,
                enabled=True,
                is_default=True,
            )
            session.add(bootstrap_provider)
    if settings.bootstrap_mineru_api_key:
        mineru = session.scalar(
            select(IntegrationConfigRecord).where(
                IntegrationConfigRecord.tenant_id == headquarters_id,
                IntegrationConfigRecord.integration_id == "mineru",
            )
        )
        if mineru is None:
            session.add(
                IntegrationConfigRecord(
                    tenant_id=headquarters_id,
                    integration_id="mineru",
                    display_name="MinerU 文档解析",
                    base_url=settings.bootstrap_mineru_base_url.rstrip("/"),
                    encrypted_api_key=SecretCipher().encrypt(settings.bootstrap_mineru_api_key),
                    enabled=True,
                    config_json=json.dumps({"model_version": "vlm", "enable_table": True, "is_ocr": False}, ensure_ascii=False),
                )
            )
    session.commit()


def seed_persona_catalog(session: Session, tenant_id: int) -> None:
    if session.scalar(select(PersonaSegmentRecord.id).where(PersonaSegmentRecord.tenant_id == tenant_id).limit(1)) is not None:
        return
    catalog = json.loads(PERSONA_CATALOG_PATH.read_text(encoding="utf-8"))
    source_file = catalog["source_file"]
    source_version = catalog["catalog_version"]

    for item in catalog["dimensions"]:
        session.add(
            PersonaDimensionDefinitionRecord(
                tenant_id=tenant_id,
                module_key=item["module_key"],
                module_name=item["module_name"],
                field_name=item["field_name"],
                field_code=item["field_code"],
                data_type=item["data_type"],
                source_data_type=item["source_data_type"],
                collection_method=item["collection_method"],
                required_mode=item["required_mode"],
                allowed_values=item["allowed_values"],
                update_frequency=item["update_frequency"],
                applicable_personas_json=json.dumps(item["applicable_personas"], ensure_ascii=False),
                is_supplemental=bool(item.get("is_supplemental", False)),
                source_file=source_file,
                source_version=source_version,
                source_row=item["source_row"],
            )
        )
    session.flush()

    segments: dict[str, PersonaSegmentRecord] = {}
    for item in catalog["segments"]:
        record = PersonaSegmentRecord(
            tenant_id=tenant_id,
            segment_code=item["segment_code"],
            primary_persona_code=item["primary_persona_code"],
            primary_persona_name=item["primary_persona_name"],
            segment_name=item["segment_name"],
            belongs_to=item["belongs_to"],
            within_persona_share=item["within_persona_share"],
            recommended_products=item["recommended_products"],
            recommended_channels=item["recommended_channels"],
            source_file=source_file,
            source_version=source_version,
            source_row=item["source_row"],
        )
        session.add(record)
        session.flush()
        segments[item["segment_code"]] = record

    for item in catalog["rules"]:
        session.add(
            PersonaSegmentRuleRecord(
                segment_id=segments[item["segment_code"]].id,
                dimension_name=item["dimension_name"],
                field_code=item["field_code"],
                field_variant=item["field_variant"],
                condition_expression=item["condition_expression"],
                condition_operator=item["condition_operator"],
                condition_value=item["condition_value"],
                data_source=item["data_source"],
                field_registered=bool(item["field_registered"]),
                rule_order=item["rule_order"],
                source_row=item["source_row"],
            )
        )
    session.commit()
