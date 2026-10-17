"""Bounded, tenant-scoped queries over imported source records."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import TenantContext, get_tenant_context
from .database import get_session
from .db_models import DatasetRecord, DatasetRowRecord, OntologyEntityRecord, OntologyRelationRecord

router = APIRouter(tags=["数据目录"])


def imported_product_catalog(session, tenant_id):
    datasets = list(session.scalars(select(DatasetRecord).where(DatasetRecord.tenant_id == tenant_id,
        DatasetRecord.name.in_(["产品目录", "爬取票价产品目录"])).order_by(DatasetRecord.id)))
    if not datasets:
        return None
    products = []
    for dataset in datasets:
        records = session.scalars(select(DatasetRowRecord).where(DatasetRowRecord.tenant_id == tenant_id,
            DatasetRowRecord.dataset_id == dataset.id).order_by(DatasetRowRecord.id).limit(200))
        for record in records:
            row = json.loads(record.payload_json)
            crawled = "fare_product_id" in row
            products.append(dict(code=dataset.dataset_key + ":" + record.record_key,
                name=(row.get("source_product_label") or row.get("source_product_name")) if crawled else row["product_name"],
                category="票价产品" if crawled else row["category"],
                eligibility=row.get("source_product_description", "") if crawled else row["eligibility"],
                benefits=[row.get("source_product_description") or "权益待核验"] if crawled else [row["product_name"]],
                status="待上游核验", source=record.source_id, data_mode=record.data_mode,
                dataset_key=dataset.dataset_key, record_key=record.record_key,
                price_yuan=None if crawled else row["price_yuan"]))
    return {"source": "已导入数据目录", "products": products}


def dataset_view(r):
    metadata = json.loads(r.metadata_json)
    metadata.pop("import_report", None)
    return dict(id=r.id, dataset_key=r.dataset_key, name=r.name, row_count=r.row_count,
                grain=r.grain, source=r.source, data_mode=r.data_mode, description=r.description,
                usage=r.usage, fields=json.loads(r.schema_json), metadata=metadata,
                import_job_id=r.import_job_id, imported_at=r.imported_at)


def scoped_dataset(session, tenant_id, key):
    r = session.scalar(select(DatasetRecord).where(DatasetRecord.tenant_id == tenant_id, DatasetRecord.dataset_key == key))
    if r is None:
        raise HTTPException(404, "数据集不存在于当前工作区")
    return r


@router.get("/api/datasets")
def list_datasets(context: TenantContext = Depends(get_tenant_context), session: Session = Depends(get_session)):
    return [dataset_view(r) for r in session.scalars(select(DatasetRecord).where(DatasetRecord.tenant_id == context.tenant_id).order_by(DatasetRecord.id))]


@router.get("/api/datasets/{dataset_key}/rows")
def dataset_rows(dataset_key: str, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                 route_id: str | None = None, flight_id: str | None = None, customer_id: str | None = None,
                 record_key: str | None = None, context: TenantContext = Depends(get_tenant_context),
                 session: Session = Depends(get_session)):
    dataset = scoped_dataset(session, context.tenant_id, dataset_key)
    query = select(DatasetRowRecord).where(DatasetRowRecord.tenant_id == context.tenant_id, DatasetRowRecord.dataset_id == dataset.id)
    for field, value in [("route_id", route_id), ("flight_id", flight_id), ("customer_id", customer_id), ("record_key", record_key)]:
        if value is not None:
            query = query.where(getattr(DatasetRowRecord, field) == value)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(DatasetRowRecord.id).offset(offset).limit(limit))
    return {"dataset": dataset_view(dataset), "total": total, "offset": offset, "limit": limit,
            "rows": [json.loads(r.payload_json) for r in rows]}


@router.get("/api/datasets/{dataset_key}/summary")
def dataset_summary(dataset_key: str, group_by: str | None = None, context: TenantContext = Depends(get_tenant_context),
                    session: Session = Depends(get_session)):
    dataset = scoped_dataset(session, context.tenant_id, dataset_key)
    result = {"dataset": dataset.name, "count": dataset.row_count, "source": dataset.source,
              "data_mode": dataset.data_mode, "statistics": json.loads(dataset.metadata_json).get("statistics", {})}
    if group_by:
        if group_by not in {"source_id", "data_mode", "route_id"}:
            raise HTTPException(422, "group_by可选source_id、data_mode、route_id")
        field = getattr(DatasetRowRecord, group_by)
        result["groups"] = [{"label": label, "count": count} for label, count in session.execute(
            select(field, func.count()).where(DatasetRowRecord.tenant_id == context.tenant_id, DatasetRowRecord.dataset_id == dataset.id)
            .group_by(field).order_by(func.count().desc()).limit(100))]
        result["group_limit"] = 100
    return result


@router.get("/api/ontology/entities")
def ontology_entities(q: str = "", entity_type: str | None = None, offset: int = Query(0, ge=0),
                      limit: int = Query(20, ge=1, le=100), context: TenantContext = Depends(get_tenant_context),
                      session: Session = Depends(get_session)):
    query = select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id)
    if entity_type:
        query = query.where(OntologyEntityRecord.entity_type == entity_type)
    if q:
        query = query.where(OntologyEntityRecord.label.contains(q, autoescape=True) | OntologyEntityRecord.external_id.contains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(OntologyEntityRecord.id).offset(offset).limit(limit))
    return {"total": total, "rows": [{"external_id": r.external_id, "type": r.entity_type, "label": r.label,
            "attributes": json.loads(r.attributes_json), "source": r.source, "confidence": r.confidence} for r in rows]}


@router.get("/api/ontology/entities/{external_id}/neighbors")
def ontology_neighbors(external_id: str, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100), context: TenantContext = Depends(get_tenant_context),
                       session: Session = Depends(get_session)):
    entity = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.external_id == external_id))
    if entity is None:
        raise HTTPException(404, "当前工作区未找到本体对象")
    query = select(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == context.tenant_id,
            (OntologyRelationRecord.source_entity_id == entity.id) | (OntologyRelationRecord.target_entity_id == entity.id))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    relations = list(session.scalars(query.order_by(OntologyRelationRecord.id).offset(offset).limit(limit)))
    ids = {entity.id} | {r.source_entity_id for r in relations} | {r.target_entity_id for r in relations}
    nodes = {r.id: r for r in session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.id.in_(ids)))}
    return {"total_relations": total, "offset": offset, "limit": limit, "nodes": [{"external_id": r.external_id, "type": r.entity_type, "label": r.label,
            "attributes": json.loads(r.attributes_json), "source": r.source} for r in nodes.values()],
            "edges": [{"source": nodes[r.source_entity_id].external_id, "target": nodes[r.target_entity_id].external_id,
            "relation": r.relation_type, "evidence": r.evidence} for r in relations]}
