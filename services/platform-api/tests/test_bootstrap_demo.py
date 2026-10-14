import json

import pytest

from sqlalchemy import select

from app.bootstrap_demo import normalize_workspace_labels, import_bundle
from app.db_models import AudiencePackageRecord, OntologyEntityRecord, TenantRecord, UserRecord
from test_dataset_import import imported_fixture
from app.dataset_import import import_dataset


@pytest.mark.parametrize("old_name, expected_name", [
    ("竞赛演示（虚构数据）", "东航营销运营"),
    ("M航营销运营", "东航营销运营"),
    ("华东营销团队", "华东营销团队"),
])
def test_fixture_labels_are_normalized_without_losing_provenance(imported_fixture, old_name, expected_name):
    session, data, tid, other = imported_fixture
    tenant = session.get(TenantRecord, tid)
    tenant.code = "CEA-COMPETITION"
    tenant.name = old_name
    user = session.scalar(select(UserRecord).where(UserRecord.username == "test-importer"))
    user.username = "competition"
    session.commit()
    import_dataset(session, data, "CEA-COMPETITION", "competition", "CE26", "hash")
    session.commit()
    audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tid))
    audience.name += "（模拟）"
    legacy_channel = OntologyEntityRecord(tenant_id=tid, external_id="channel-ceair-app",
        entity_type="Channel", label="M航App", source="本体初始化", attributes_json='{"synthetic": true}')
    custom_channel = OntologyEntityRecord(tenant_id=tid, external_id="user-channel",
        entity_type="Channel", label="M航App历史案例", source="用户导入")
    other_channel = OntologyEntityRecord(tenant_id=other, external_id="channel-ceair-app",
        entity_type="Channel", label="M航App", source="本体初始化")
    session.add_all([legacy_channel, custom_channel, other_channel])
    session.flush()
    normalize_workspace_labels(session, tid)
    session.commit()
    assert tenant.name == expected_name
    assert audience.name == "商务高频"
    assert json.loads(audience.expression_json)["synthetic"] is True
    assert legacy_channel.label == "东航App"
    assert json.loads(legacy_channel.attributes_json)["synthetic"] is True
    assert custom_channel.label == "M航App历史案例"
    assert other_channel.label == "M航App"
    report = import_bundle(session, {"namespace": "CE26", "sha256": "hash", "file": "does-not-exist.gz"})
    assert report["idempotent"] is True
    assert session.get(TenantRecord, other).name == "B"
