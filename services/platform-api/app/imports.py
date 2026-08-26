from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import ImportJobRecord, OntologyEntityRecord, OntologyRelationRecord


ENTITY_TYPES = {"Customer", "Audience", "Opportunity", "Flight", "Route", "Product", "ProductPackage", "Campaign", "Content", "Channel", "ConversionResult"}


def import_file(session: Session, tenant_id: int, user_id: int, dataset_type: str, upload: UploadFile) -> ImportJobRecord:
    suffix = upload.filename.rsplit(".", 1)[-1].lower() if upload.filename and "." in upload.filename else ""
    if suffix not in {"csv", "json"}:
        raise HTTPException(status_code=422, detail="仅支持 CSV 或 JSON 文件")
    if dataset_type not in {"entities", "relations"}:
        raise HTTPException(status_code=422, detail="dataset_type 必须为 entities 或 relations")
    raw = upload.file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="导入文件不能超过 10MB")
    try:
        rows = _parse_rows(raw, suffix, dataset_type)
    except (UnicodeDecodeError, csv.Error, json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"文件解析失败：{exc}") from exc

    job = ImportJobRecord(
        id=f"IMP-{uuid4().hex[:12].upper()}",
        tenant_id=tenant_id,
        created_by=user_id,
        dataset_type=dataset_type,
        file_name=upload.filename or f"import.{suffix}",
        file_format=suffix,
        status="processing",
        total_rows=len(rows),
    )
    session.add(job)
    session.flush()
    errors: list[dict[str, object]] = []
    accepted = 0
    for index, row in enumerate(rows, start=2 if suffix == "csv" else 1):
        try:
            if dataset_type == "entities":
                _upsert_entity(session, tenant_id, job.id, row)
            else:
                _insert_relation(session, tenant_id, job.id, row)
            accepted += 1
        except ValueError as exc:
            errors.append({"row": index, "message": str(exc), "data": row})
    job.accepted_rows = accepted
    job.rejected_rows = len(errors)
    job.errors_json = json.dumps(errors[:200], ensure_ascii=False)
    job.status = "completed" if not errors else "completed_with_errors" if accepted else "failed"
    job.completed_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(job)
    return job


def _parse_rows(raw: bytes, suffix: str, dataset_type: str) -> list[dict[str, object]]:
    text = raw.decode("utf-8-sig")
    if suffix == "csv":
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]
    value = json.loads(text)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        rows = value.get(dataset_type)
        if isinstance(rows, list):
            return rows
    raise TypeError(f"JSON 必须为数组，或包含 {dataset_type} 数组")


def _upsert_entity(session: Session, tenant_id: int, job_id: str, row: dict[str, object]) -> None:
    external_id = str(row.get("external_id") or row.get("id") or "").strip()
    entity_type = str(row.get("entity_type") or row.get("type") or "").strip()
    label = str(row.get("label") or "").strip()
    if not external_id or not entity_type or not label:
        raise ValueError("实体缺少 external_id、entity_type/type 或 label")
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"不支持的实体类型：{entity_type}")
    confidence = _confidence(row.get("confidence", 1.0))
    attributes = row.get("attributes", {})
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes) if attributes.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError("attributes 不是有效 JSON") from exc
    if not isinstance(attributes, dict):
        raise ValueError("attributes 必须是 JSON 对象")
    record = session.scalar(
        select(OntologyEntityRecord).where(
            OntologyEntityRecord.tenant_id == tenant_id,
            OntologyEntityRecord.external_id == external_id,
        )
    )
    if record is None:
        record = OntologyEntityRecord(tenant_id=tenant_id, external_id=external_id)
        session.add(record)
    record.entity_type = entity_type
    record.label = label
    record.attributes_json = json.dumps(attributes, ensure_ascii=False)
    record.source = str(row.get("source") or "文件导入")
    record.confidence = confidence
    record.import_job_id = job_id
    session.flush()


def _insert_relation(session: Session, tenant_id: int, job_id: str, row: dict[str, object]) -> None:
    source_external_id = str(row.get("source_external_id") or row.get("source") or "").strip()
    target_external_id = str(row.get("target_external_id") or row.get("target") or "").strip()
    relation_type = str(row.get("relation_type") or row.get("relation") or "").strip()
    if not source_external_id or not target_external_id or not relation_type:
        raise ValueError("关系缺少 source_external_id、target_external_id 或 relation_type")
    entities = list(
        session.scalars(
            select(OntologyEntityRecord).where(
                OntologyEntityRecord.tenant_id == tenant_id,
                OntologyEntityRecord.external_id.in_([source_external_id, target_external_id]),
            )
        )
    )
    by_external_id = {item.external_id: item for item in entities}
    if source_external_id not in by_external_id or target_external_id not in by_external_id:
        raise ValueError("关系端点不存在于当前租户，请先导入实体")
    session.add(
        OntologyRelationRecord(
            tenant_id=tenant_id,
            source_entity_id=by_external_id[source_external_id].id,
            relation_type=relation_type,
            target_entity_id=by_external_id[target_external_id].id,
            evidence=str(row.get("evidence") or ""),
            source=str(row.get("provenance") or row.get("data_source") or "文件导入"),
            confidence=_confidence(row.get("confidence", 1.0)),
            import_job_id=job_id,
        )
    )


def _confidence(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence 必须是 0 到 1 之间的数字") from exc
    if not 0 <= result <= 1:
        raise ValueError("confidence 必须是 0 到 1 之间的数字")
    return result
