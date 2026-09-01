from __future__ import annotations

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./ceair-marketing-test.db"
os.environ["INITIAL_ADMIN_USERNAME"] = "admin"
os.environ["INITIAL_ADMIN_PASSWORD"] = "Admin@12345"
os.environ["TOKEN_SECRET"] = "test-only-token-secret"

from app.data import CAMPAIGNS
from app.database import Base, SessionLocal, engine
from app.db_models import CampaignRecord, TenantRecord
from app.ontology.bootstrap import seed_marketing_lifecycle
from app.seed import seed_database, seed_tenant_data


@pytest.fixture(scope="session", autouse=True)
def seed_test_business_data():
    """Tests own their fixtures; production startup remains free of demo business data."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        tenant_id = seed_database(session)
        seed_tenant_data(session, tenant_id)
        tenant = session.query(TenantRecord).filter(TenantRecord.code == "CEA-HQ").one()
        if session.get(CampaignRecord, (tenant.id, "ACT-2026-0921")) is None:
            session.add_all([CampaignRecord(tenant_id=tenant.id, **campaign.model_dump()) for campaign in CAMPAIGNS])
            session.commit()
        seed_marketing_lifecycle(session, tenant.id)
    yield
    Base.metadata.drop_all(bind=engine)
