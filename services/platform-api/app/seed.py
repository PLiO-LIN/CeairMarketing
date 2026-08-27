import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .data import CAMPAIGNS
from .ontology.bootstrap import seed_marketing_lifecycle
from .db_models import (
    CampaignRecord,
    IntegrationConfigRecord,
    ModelProviderRecord,
    OntologyEntityRecord,
    OntologyRelationRecord,
    TenantMembershipRecord,
    TenantRecord,
    UserRecord,
)
from .security import SecretCipher


def seed_database(session: Session) -> int:
    settings = get_settings()
    headquarters = session.scalar(select(TenantRecord).where(TenantRecord.code == "CEA-HQ"))
    if headquarters is None:
        headquarters = TenantRecord(code="CEA-HQ", name="东航营销运营中心")
        session.add(headquarters)
        session.flush()
    ecommerce = session.scalar(select(TenantRecord).where(TenantRecord.code == "CEA-ECOM"))
    if ecommerce is None:
        ecommerce = TenantRecord(code="CEA-ECOM", name="东航电商运营中心")
        session.add(ecommerce)
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
    for tenant in (headquarters, ecommerce):
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
        bootstrap_provider = session.scalar(select(ModelProviderRecord).where(
            ModelProviderRecord.tenant_id == headquarters_id,
            ModelProviderRecord.display_name == settings.bootstrap_model_display_name,
        ))
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
        mineru = session.scalar(select(IntegrationConfigRecord).where(
            IntegrationConfigRecord.tenant_id == headquarters_id,
            IntegrationConfigRecord.integration_id == "mineru",
        ))
        if mineru is None:
            session.add(IntegrationConfigRecord(
                tenant_id=headquarters_id,
                integration_id="mineru",
                display_name="MinerU 文档解析",
                base_url=settings.bootstrap_mineru_base_url.rstrip("/"),
                encrypted_api_key=SecretCipher().encrypt(settings.bootstrap_mineru_api_key),
                enabled=True,
                config_json=json.dumps({"model_version": "vlm", "enable_table": True, "is_ocr": False}, ensure_ascii=False),
            ))
    session.commit()


def _seed_graph(session: Session, tenant_id: int) -> None:
    if session.scalar(select(OntologyEntityRecord.id).where(OntologyEntityRecord.tenant_id == tenant_id).limit(1)) is not None:
        return
    entities = [
        ("opp-sanya", "Opportunity", "三亚国庆早鸟机会", {"window": "国庆前45天", "score": 0.94}, "机会洞察智能域", 0.94),
        ("aud-sanya", "Audience", "三亚高意向未购客群", {"size": 36420, "journey_stage": "搜索未购"}, "用户画像平台", 0.96),
        ("pkg-sanya", "ProductPackage", "三亚国庆早鸟产品包", {"components": ["客票", "额外行李", "优选座位"]}, "产品管理平台", 1.0),
        ("ACT-2026-0921", "Campaign", "上海—三亚国庆早鸟", {"version": "V3", "budget": 320000}, "营销活动平台", 1.0),
        ("content-app", "Content", "App家庭出游版", {"channel": "App", "approval": "passed"}, "内容生成智能域", 0.98),
        ("channel-app", "Channel", "东航App", {"touchpoint": "B2C官方触点"}, "渠道平台", 1.0),
        ("result-ticket", "ConversionResult", "出票3,572人", {"tickets": 3572, "roi": 4.3}, "交易回传", 0.88),
    ]
    records: dict[str, OntologyEntityRecord] = {}
    for external_id, entity_type, label, attributes, source, confidence in entities:
        record = OntologyEntityRecord(
            tenant_id=tenant_id,
            external_id=external_id,
            entity_type=entity_type,
            label=label,
            attributes_json=json.dumps(attributes, ensure_ascii=False),
            source=source,
            confidence=confidence,
        )
        session.add(record)
        session.flush()
        records[external_id] = record
    relations = [
        ("opp-sanya", "targets", "aud-sanya", "14日搜索未出票", 0.94),
        ("aud-sanya", "matches", "pkg-sanya", "航线、价格与辅营偏好匹配", 0.916),
        ("pkg-sanya", "used_by", "ACT-2026-0921", "活动V3引用", 1.0),
        ("ACT-2026-0921", "uses_content", "content-app", "内容审核记录", 1.0),
        ("content-app", "delivered_via", "channel-app", "渠道任务记录", 1.0),
        ("channel-app", "produced", "result-ticket", "渠道交易归因", 0.88),
        ("result-ticket", "updates", "aud-sanya", "转化结果回流画像", 0.97),
    ]
    for source, relation, target, evidence, confidence in relations:
        session.add(
            OntologyRelationRecord(
                tenant_id=tenant_id,
                source_entity_id=records[source].id,
                relation_type=relation,
                target_entity_id=records[target].id,
                evidence=evidence,
                source="系统初始化",
                confidence=confidence,
            )
        )
    session.commit()
