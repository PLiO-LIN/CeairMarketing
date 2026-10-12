import copy
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.dataset_import import import_dataset
from app.datasets import scoped_dataset, imported_product_catalog
from app.db_models import (DatasetRecord, DatasetRowRecord, OntologyEntityRecord,
    OntologyRelationRecord, TenantRecord, TenantMembershipRecord, UserRecord)
from app.ontology.service import build_campaign_graph, graph_stats
from app.main import audience_package_view
from app.db_models import AudiencePackageRecord


def sheet(name, pk, rows, fks=None):
    return dict(name=name, pk=pk, fields=[dict(code=k, label=k, type="text") for k in rows[0]],
        rows=rows, fks=fks or {}, description="测试数据", grain="源记录", source="SIM-TEST", use="导入测试")


@pytest.fixture
def imported_fixture():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        a, b = TenantRecord(code="TEST-A", name="A"), TenantRecord(code="TEST-B", name="B")
        user = UserRecord(username="test-importer", display_name="Importer", password_hash="unused")
        session.add_all([a, b, user]); session.flush()
        session.add(TenantMembershipRecord(tenant_id=a.id, user_id=user.id, role="admin")); session.commit()
        data = dict(metadata=dict(total_data_rows=4, as_of="2026-09-30"), statistics={}, sheets=[
            sheet("客户画像", "customer_id", [dict(customer_id="C1", business_segment="商务高频", data_mode="模拟")]),
            sheet("产品目录", "product_id", [dict(product_id="P1", product_name="行李", category="行李", price_yuan=80,
                unit="次", eligibility="经济舱", valid_from="2025-10-01", valid_to="2026-10-31", source_id="SIM-TEST", data_mode="模拟")]),
            sheet("客票订单", "order_id", [dict(order_id="O1", customer_id="C1", paid_yuan=100, refund_yuan=30, net_yuan=70,
                data_mode="模拟")], {"customer_id": "客户画像.customer_id"}),
            sheet("本体实体", "external_id", [dict(external_id="E1", entity_type="Evidence", label="证据", attributes_json='{"captured_at":null}', source_id="SIM-TEST", data_mode="模拟")])])
        yield session, data, a.id, b.id
    engine.dispose()


def test_import_retains_rows_and_is_idempotent(imported_fixture):
    session, data, tid, other = imported_fixture
    first = import_dataset(session, data, "TEST-A", "test-importer", "TEST26", "hash")
    session.commit()
    counts = lambda model: session.scalar(select(func.count()).select_from(model))
    before = (counts(DatasetRowRecord), counts(OntologyEntityRecord), counts(OntologyRelationRecord))
    second = import_dataset(session, data, "TEST-A", "test-importer", "TEST26", "hash")
    session.commit()
    assert second["idempotent"] and first["source_rows"] == 4
    assert before == (counts(DatasetRowRecord), counts(OntologyEntityRecord), counts(OntologyRelationRecord))
    row = session.scalar(select(DatasetRowRecord).where(DatasetRowRecord.record_key == "O1"))
    assert json.loads(row.payload_json) == data["sheets"][2]["rows"][0]
    with pytest.raises(HTTPException) as exc:
        scoped_dataset(session, other, "TEST26-orders")
    assert exc.value.status_code == 404
    assert imported_product_catalog(session, other) is None
    assert imported_product_catalog(session, tid)["products"][0]["status"] == "待上游核验"
    audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tid))
    assert audience_package_view(audience).selection_mode == "expression"
    assert audience_package_view(audience).estimated_size == 1
    assert len(build_campaign_graph(session, tid, limit=2).nodes) == 2
    assert graph_stats(session, tid).entity_count == before[1]
    with pytest.raises(ValueError, match="同版本"):
        import_dataset(session, data, "TEST-A", "test-importer", "TEST26", "changed")


def test_invalid_input_rolls_back_whole_bundle(imported_fixture):
    session, data, tid, other = imported_fixture
    bad = copy.deepcopy(data)
    # Semantic failure occurs after source and business inserts; all must roll back.
    bad["sheets"].append(sheet("本体关系", "relation_id", [dict(relation_id="R1", source_external_id="E1",
        target_external_id="E1", relation_type="has_fare", evidence="invalid")]))
    bad["metadata"]["total_data_rows"] += 1
    with pytest.raises(ValueError, match="requires source type"):
        import_dataset(session, bad, "TEST-A", "test-importer", "TEST26", "hash")
    session.rollback()
    assert session.scalar(select(func.count()).select_from(DatasetRecord)) == 0
    assert session.scalar(select(func.count()).select_from(OntologyEntityRecord)) == 0
    bad = copy.deepcopy(data); bad["sheets"][2]["rows"][0]["net_yuan"] = 100
    with pytest.raises(ValueError, match="不平衡"):
        import_dataset(session, bad, "TEST-A", "test-importer", "TEST26", "hash")
    bad = copy.deepcopy(data); bad["sheets"][2]["rows"][0]["customer_id"] = "missing"
    with pytest.raises(ValueError, match="无效外键"):
        import_dataset(session, bad, "TEST-A", "test-importer", "TEST26", "hash")
    with pytest.raises(ValueError, match="权限"):
        import_dataset(session, data, "TEST-B", "test-importer", "TEST26", "hash")
