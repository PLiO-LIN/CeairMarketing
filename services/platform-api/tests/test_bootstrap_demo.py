import json

from sqlalchemy import select

from app.bootstrap_demo import normalize_workspace_labels, import_bundle
from app.db_models import AudiencePackageRecord, TenantRecord, UserRecord
from test_dataset_import import imported_fixture
from app.dataset_import import import_dataset


def test_fixture_labels_are_normalized_without_losing_provenance(imported_fixture):
    session, data, tid, other = imported_fixture
    tenant = session.get(TenantRecord, tid)
    tenant.code = "CEA-COMPETITION"
    tenant.name = "竞赛演示（虚构数据）"
    user = session.scalar(select(UserRecord).where(UserRecord.username == "test-importer"))
    user.username = "competition"
    session.commit()
    import_dataset(session, data, "CEA-COMPETITION", "competition", "CE26", "hash")
    session.commit()
    audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tid))
    audience.name += "（模拟）"
    normalize_workspace_labels(session, tid)
    session.commit()
    assert tenant.name == "M航营销运营"
    assert audience.name == "商务高频"
    assert json.loads(audience.expression_json)["synthetic"] is True
    report = import_bundle(session, {"namespace": "CE26", "sha256": "hash", "file": "does-not-exist.gz"})
    assert report["idempotent"] is True
    assert session.get(TenantRecord, other).name == "B"
