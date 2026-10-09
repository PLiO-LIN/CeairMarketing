"""Approval gates shared by API and demo presentation."""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from .db_models import AudienceSnapshotRecord, ProductPackageRecord, ContentAssetRecord


def canonical_channel(value):
    return {"东航App": "App", "东航 App": "App", "app": "App", "SMS": "短信", "sms": "短信"}.get(value, value)


def campaign_readiness(session, tenant_id, version, business_date=None):
    if business_date is None:
        from .db_models import TenantRecord
        tenant = session.get(TenantRecord, tenant_id)
        if tenant and tenant.code == "CEA-COMPETITION":
            from .competition_demo import DEMO_DATE
            business_date = DEMO_DATE
    snapshot = session.scalar(select(AudienceSnapshotRecord).where(AudienceSnapshotRecord.tenant_id == tenant_id, AudienceSnapshotRecord.id == version.audience_snapshot_id))
    product = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.id == version.product_package_id))
    ids = json.loads(version.content_asset_ids_json or "[]")
    contents = list(session.scalars(select(ContentAssetRecord).where(ContentAssetRecord.tenant_id == tenant_id, ContentAssetRecord.id.in_(ids))))
    channels = [canonical_channel(c) for c in json.loads(version.channels_json or "[]")]
    now = business_date or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    def aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    current_product = bool(product and product.status in {"已审批", "已通过", "可用"})
    if product:
        current_product = current_product and all([
            not product.valid_from or aware(product.valid_from) <= now,
            not product.valid_to or aware(product.valid_to) > now,
        ])
    approved_contents = [c for c in contents if c.status in {"已审核", "已审批", "已通过", "可用"} and c.title.strip() and c.body.strip()]
    consistent = len(contents) == len(set(ids)) and bool(ids) and all(c.product_package_id == version.product_package_id and snapshot and c.audience_package_id == snapshot.package_id and c.campaign_id in {None, version.campaign_id} for c in contents)
    covered = {canonical_channel(c.channel) for c in approved_contents}
    missing = sorted(set(channels) - covered)
    checks = [
        {"key": "audience", "label": "冻结客群快照", "passed": bool(snapshot and snapshot.status == "已冻结" and snapshot.estimated_size > 0), "detail": "需要已冻结且规模大于零的客群快照"},
        {"key": "product", "label": "产品版本与有效期", "passed": current_product, "detail": "需要已审批且处于有效期的产品包；实际库存和价格仍需上游核验"},
        {"key": "content", "label": "内容审核与业务关联", "passed": consistent and len(approved_contents) == len(contents), "detail": "内容须已审核并与当前客群、产品一致"},
        {"key": "channels", "label": "逐渠道内容覆盖", "passed": bool(channels) and len(set(channels)) == len(channels) and not missing, "detail": "缺少已审核内容：" + "、".join(missing) if missing else "每个渠道需要对应的已审核内容"},
        {"key": "budget", "label": "活动预算", "passed": version.budget_yuan > 0, "detail": "预算必须大于零，审批人确认预算依据"},
    ]
    return {"ready": all(c["passed"] for c in checks), "checks": checks, "missing_channels": missing, "sellability_status": "待上游核验"}
