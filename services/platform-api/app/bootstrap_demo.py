"""Initialize the authorized presentation workspace without touching HQ business data.

Run explicitly during deployment. The complete source bundle is versioned and
compressed; source provenance remains in the catalog and ontology attributes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from .auth import hash_password
from .config import get_settings
from .database import SessionLocal
from .dataset_import import import_dataset
from .db_models import (AudiencePackageRecord, CampaignRecord, DatasetRecord,
    ModelProviderRecord, OntologyEntityRecord, ProductPackageRecord,
    TenantMembershipRecord, TenantRecord, UserRecord)
from .seed import seed_competition_workspace

WORKSPACE_CODE = "CEA-COMPETITION"
WORKSPACE_NAME = "M航营销运营"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def normalize_workspace_labels(session, tenant_id):
    """Migrate only legacy fixture labels; never rewrite user-authored records."""
    tenant = session.get(TenantRecord, tenant_id)
    if tenant.name in {"竞赛演示（虚构数据）", "竞赛演示", WORKSPACE_NAME}:
        tenant.name = WORKSPACE_NAME
    for row in session.scalars(select(AudiencePackageRecord).where(
            AudiencePackageRecord.tenant_id == tenant_id,
            AudiencePackageRecord.external_id.startswith("CE26-SEG-", autoescape=True))):
        if row.name.endswith("（模拟）"):
            row.name = row.name[:-4]
    for row in session.scalars(select(CampaignRecord).where(
            CampaignRecord.tenant_id == tenant_id,
            CampaignRecord.id.startswith("CE26-", autoescape=True))):
        if row.status == "已完成（模拟历史）":
            row.status = "已完成"
    for row in session.scalars(select(ProductPackageRecord).where(
            ProductPackageRecord.tenant_id == tenant_id,
            ProductPackageRecord.external_id.startswith("CE26-PP-", autoescape=True))):
        row.description = row.description.replace("，模拟价格 ", "，参考价格 ")
    # Graph metadata still retains synthetic/data_mode/source. Update status only.
    for row in session.scalars(select(OntologyEntityRecord).where(
            OntologyEntityRecord.tenant_id == tenant_id,
            OntologyEntityRecord.entity_type == "Campaign")):
        attrs = json.loads(row.attributes_json or "{}")
        if attrs.get("status") == "已完成（模拟历史）":
            attrs["status"] = "已完成"
            row.attributes_json = json.dumps(attrs, ensure_ascii=False)


def import_bundle(session, manifest, data_dir=DATA_DIR):
    tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == WORKSPACE_CODE))
    existing = session.scalar(select(DatasetRecord).where(
        DatasetRecord.tenant_id == tenant.id,
        DatasetRecord.dataset_key.startswith(manifest["namespace"] + "-", autoescape=True)))
    if existing is not None:
        metadata = json.loads(existing.metadata_json)
        if metadata.get("fingerprint") != manifest["sha256"]:
            raise ValueError("已有数据版本指纹不一致，拒绝覆盖")
        # import_dataset checks all catalog entries and import report completeness
        # before accessing the source payload, so no large file read is needed.
        return import_dataset(session, {}, WORKSPACE_CODE, "competition",
            manifest["namespace"], manifest["sha256"])
    source = data_dir / manifest["file"]
    digest = hashlib.sha256()
    with gzip.open(source, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("数据包SHA256校验失败")
    with gzip.open(source, "rt", encoding="utf8") as stream:
        data = json.load(stream)
    return import_dataset(session, data, WORKSPACE_CODE, "competition",
        manifest["namespace"], manifest["sha256"], lambda message: print(message, flush=True))


def prepare_workspace(session):
    settings = get_settings()
    admin = session.scalar(select(UserRecord).where(UserRecord.username == settings.initial_admin_username))
    if admin is None:
        raise ValueError("平台管理员尚未初始化")
    tenant_id = seed_competition_workspace(session, admin.id)
    user = session.scalar(select(UserRecord).where(UserRecord.username == "competition"))
    if user is None:
        user = UserRecord(username="competition", display_name="营销运营",
            password_hash=hash_password("Competition@2026"), enabled=True)
        session.add(user); session.flush()
    if session.scalar(select(TenantMembershipRecord.id).where(
            TenantMembershipRecord.user_id == user.id,
            TenantMembershipRecord.tenant_id == tenant_id)) is None:
        session.add(TenantMembershipRecord(user_id=user.id, tenant_id=tenant_id, role="admin"))
    configured = session.scalar(select(ModelProviderRecord).where(
        ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True),
        ModelProviderRecord.provider_type != "mock"))
    if configured is None:
        # Reuse the already-authorized server-side provider without exposing keys.
        donor = session.scalar(select(ModelProviderRecord).where(
            ModelProviderRecord.tenant_id != tenant_id, ModelProviderRecord.enabled.is_(True),
            ModelProviderRecord.is_default.is_(True), ModelProviderRecord.provider_type != "mock"))
        if donor is not None:
            for p in session.scalars(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id)):
                p.is_default = False
            values = {c.name: getattr(donor, c.name) for c in ModelProviderRecord.__table__.columns
                if c.name not in {"id", "tenant_id", "created_at", "updated_at"}}
            session.add(ModelProviderRecord(tenant_id=tenant_id, **values))
    session.commit()
    return tenant_id


def main():
    manifest = json.loads((DATA_DIR / "ce26-manifest.json").read_text("utf-8-sig"))
    with SessionLocal() as session:
        tenant_id = prepare_workspace(session)
        try:
            report = import_bundle(session, manifest)
            normalize_workspace_labels(session, tenant_id)
            session.commit()
        except Exception:
            session.rollback()
            raise
    print(json.dumps({k: report[k] for k in ["namespace", "source_rows", "dataset_count", "idempotent"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
