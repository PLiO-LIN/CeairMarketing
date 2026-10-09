import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .db_models import (
    IntegrationConfigRecord,
    ApprovalTaskRecord,
    AudiencePackageRecord,
    AudienceSnapshotRecord,
    CampaignRecord,
    CampaignVersionRecord,
    ContentAssetRecord,
    ModelProviderRecord,
    OpportunityRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
    OntologyEntityRecord,
    OntologyRelationRecord,
    PersonaDimensionDefinitionRecord,
    PersonaSegmentRecord,
    PersonaSegmentRuleRecord,
    ProductPackageRecord,
    OpportunityInsightSourceRecord,
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


def seed_demo_business_data(session: Session, tenant_id: int, user_id: int) -> None:
    """Create one complete, idempotent competition walkthrough case.

    This is deliberately opt-in through ``SEED_DEMO_BUSINESS_DATA`` so a
    production database is never populated with fictional marketing metrics.
    Each record uses stable external IDs and is safe to run on every restart.
    """
    campaign_id = "ACT-2026-0921"
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.tenant_id == tenant_id, CampaignRecord.id == campaign_id))
    if campaign is None:
        campaign = CampaignRecord(
            tenant_id=tenant_id, id=campaign_id, name="上海—三亚国庆早鸟",
            stage="审批", status="审批中", version="V3", owner="竞赛运营",
            audience_size=36420, product_package="三亚国庆早鸟产品包",
            budget_yuan=320000, roi_target=4.0,
        )
        session.add(campaign)

    opportunity = session.scalar(select(OpportunityRecord).where(OpportunityRecord.tenant_id == tenant_id, OpportunityRecord.id == "OPP-2026-0921"))
    if opportunity is None:
        session.add(OpportunityRecord(
            tenant_id=tenant_id, id="OPP-2026-0921", name="上海—三亚国庆早鸟",
            market_scope="国内旅游", route="SHA-SYX", signal_summary="目的地搜索热度上升32%，提前预订窗口收窄，航班供给充足。",
            status="待处理", score=92, estimated_audience=36420, estimated_revenue_yuan=0, owner="竞赛运营",
        ))

    package = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tenant_id, AudiencePackageRecord.external_id == "AUD-DEMO-SANYA"))
    if package is None:
        package = AudiencePackageRecord(
            tenant_id=tenant_id, external_id="AUD-DEMO-SANYA", name="三亚高意向未购客群",
            selection_mode="ai-selection", tag_ids_json="[]",
            expression_json=json.dumps({"route": "SHA-SYX", "journey_stage": "搜索未购", "price_sensitivity": "中高", "contact_permission": True}, ensure_ascii=False),
            estimated_size=36420, status="可用", created_by=user_id,
        )
        session.add(package)
        session.flush()
    snapshot = session.scalar(select(AudienceSnapshotRecord).where(AudienceSnapshotRecord.tenant_id == tenant_id, AudienceSnapshotRecord.external_id == "AUD-SNAP-DEMO-SANYA-V4"))
    if snapshot is None:
        snapshot = AudienceSnapshotRecord(
            tenant_id=tenant_id, package_id=package.id, external_id="AUD-SNAP-DEMO-SANYA-V4", version="V4",
            estimated_size=36420, tag_ids_json=package.tag_ids_json, expression_json=package.expression_json,
            source="竞赛虚构聚合客群", status="已冻结", created_by=user_id,
        )
        session.add(snapshot)
        session.flush()

    product = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.external_id == "PKG-DEMO-SANYA"))
    if product is None:
        product = ProductPackageRecord(
            tenant_id=tenant_id, external_id="PKG-DEMO-SANYA", name="三亚国庆早鸟产品包",
            product_type="机票 + 辅营组合", description="上海—三亚早鸟客票、预付费行李和优选座位组合权益。",
            eligibility="适用于SHA-SYX航线，搜索未购且已授权触达客群。", version="V2", status="已审批",
            created_by=user_id,
        )
        session.add(product)
        session.flush()
    content = session.scalar(select(ContentAssetRecord).where(ContentAssetRecord.tenant_id == tenant_id, ContentAssetRecord.external_id == "CNT-DEMO-SANYA-APP-V3"))
    if content is None:
        content = ContentAssetRecord(
            tenant_id=tenant_id, external_id="CNT-DEMO-SANYA-APP-V3", campaign_id=campaign_id,
            audience_package_id=package.id, product_package_id=product.id, generation_objective="提升早鸟出票转化",
            generation_context_json=json.dumps({"route": "上海—三亚", "audience": "家庭高意向未购", "evidence": ["目的地热度", "搜索行为"]}, ensure_ascii=False),
            name="东航App家庭出游内容V3", channel="App", version="V3", title="国庆去三亚，提前规划出行",
            body="上海—三亚早鸟方案搭配行李与优选座位。适用航班和权益以最终产品规则为准。", status="待审核", generated_by="manual", created_by=user_id,
        )
        session.add(content)
        session.flush()

    version = session.scalar(select(CampaignVersionRecord).where(CampaignVersionRecord.tenant_id == tenant_id, CampaignVersionRecord.external_id == "ACT-2026-0921-V3"))
    if version is None:
        version = CampaignVersionRecord(
            tenant_id=tenant_id, campaign_id=campaign_id, external_id="ACT-2026-0921-V3", version="V3",
            audience_snapshot_id=snapshot.id, product_package_id=product.id,
            content_asset_ids_json=json.dumps([content.id]), budget_yuan=320000,
            channels_json=json.dumps(["App", "微信"], ensure_ascii=False), status="待审批", created_by=user_id,
        )
        session.add(version)
        session.flush()
    approval = session.scalar(select(ApprovalTaskRecord).where(ApprovalTaskRecord.tenant_id == tenant_id, ApprovalTaskRecord.external_id == "APR-ACT-2026-0921-V3"))
    if approval is None:
        session.add(ApprovalTaskRecord(
            tenant_id=tenant_id, campaign_id=campaign_id, campaign_version_id=version.id,
            external_id="APR-ACT-2026-0921-V3", approver_role="合规复核", status="待审批",
        ))
    seed_demo_knowledge(session, tenant_id, campaign, snapshot, product)
    session.commit()


def seed_demo_knowledge(session, tenant_id, campaign, snapshot, product):
    from hashlib import sha256
    content = "竞赛虚构案例：上海—三亚。聚合客群36420人，搜索未购且已授权触达。产品组合为客票、行李、优选座位。全部数值用于流程验证，不代表东航真实经营结果；没有实时价格、库存或收入证据。"
    document = session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == tenant_id, KnowledgeDocumentRecord.external_id == "DOC-DEMO-SANYA"))
    if document is None:
        document = KnowledgeDocumentRecord(tenant_id=tenant_id, external_id="DOC-DEMO-SANYA", title="三亚竞赛案例说明", source_type="competition", source_name="竞赛虚构案例", content=content, content_hash=sha256(content.encode()).hexdigest())
        session.add(document)
        session.flush()
    if session.scalar(select(KnowledgeChunkRecord.id).where(KnowledgeChunkRecord.tenant_id == tenant_id, KnowledgeChunkRecord.external_id == "CHUNK-DEMO-SANYA")) is None:
        session.add(KnowledgeChunkRecord(tenant_id=tenant_id, external_id="CHUNK-DEMO-SANYA", document_id=document.id, sequence=1, heading="案例口径", content=content, metadata_json=json.dumps({"synthetic": True})))
    objects = [
        (campaign.id, "Campaign", campaign.name, {"status": campaign.status}),
        ("OPP-2026-0921", "Opportunity", "三亚国庆早鸟机会", {"score": 92}),
        (snapshot.external_id, "AudienceSnapshot", "三亚高意向未购快照", {"size": snapshot.estimated_size}),
        (product.external_id, "ProductPackage", product.name, {"eligibility": product.eligibility}),
    ]
    graph = {}
    for external_id, entity_type, label, attributes in objects:
        entity = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == external_id))
        if entity is None:
            entity = OntologyEntityRecord(tenant_id=tenant_id, external_id=external_id, entity_type=entity_type, label=label, attributes_json=json.dumps({**attributes, "synthetic": True}, ensure_ascii=False), source="竞赛虚构案例", confidence=1.0)
            session.add(entity)
            session.flush()
        graph[external_id] = entity
    for relation, target in [("addresses_opportunity", "OPP-2026-0921"), ("targets_audience", snapshot.external_id), ("uses_product_package", product.external_id)]:
        if session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id == tenant_id, OntologyRelationRecord.source_entity_id == graph[campaign.id].id, OntologyRelationRecord.relation_type == relation, OntologyRelationRecord.target_entity_id == graph[target].id)) is None:
            session.add(OntologyRelationRecord(tenant_id=tenant_id, source_entity_id=graph[campaign.id].id, target_entity_id=graph[target].id, relation_type=relation, evidence="竞赛虚构案例", source="竞赛初始化"))


def seed_competition_workspace(session: Session, user_id: int) -> int:
    tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == "CEA-COMPETITION"))
    if tenant is None:
        tenant = TenantRecord(code="CEA-COMPETITION", name="竞赛演示（虚构数据）")
        session.add(tenant)
        session.flush()
    if session.scalar(select(TenantMembershipRecord.id).where(TenantMembershipRecord.tenant_id == tenant.id, TenantMembershipRecord.user_id == user_id)) is None:
        session.add(TenantMembershipRecord(tenant_id=tenant.id, user_id=user_id, role="admin"))
    if session.scalar(select(ModelProviderRecord.id).where(ModelProviderRecord.tenant_id == tenant.id)) is None:
        session.add(ModelProviderRecord(tenant_id=tenant.id, display_name="竞赛流程验证模型", provider_type="mock", model_name="ceair-governed-mock-v1", enabled=True, is_default=True))
    session.commit()
    seed_persona_catalog(session, tenant.id)
    seed_demo_business_data(session, tenant.id, user_id)
    return tenant.id


def seed_opportunity_insight_sources(session: Session, tenant_id: int) -> None:
    if session.scalar(select(OpportunityInsightSourceRecord.id).where(OpportunityInsightSourceRecord.tenant_id == tenant_id).limit(1)) is not None:
        return
    defaults = [
        {"name": "中国民航行业动态", "source_type": "web", "source_url": "https://www.caac.gov.cn/XWZX/HYDT/", "focus": "关注航线供需、航班运行、机场与民航政策变化", "schedule": "manual", "max_pages": 5},
        {"name": "东航官方动态", "source_type": "web", "source_url": "https://www.ceair.com/", "focus": "关注东航航线、会员权益、产品服务和营销活动变化", "schedule": "manual", "max_pages": 3},
        {"name": "文旅热点观察", "source_type": "web", "source_url": "https://www.gov.cn/lianbo/", "focus": "关注节假日、文旅目的地、消费趋势和区域客流信号", "schedule": "manual", "max_pages": 5},
    ]
    for item in defaults:
        session.add(OpportunityInsightSourceRecord(tenant_id=tenant_id, **item))
    session.commit()
