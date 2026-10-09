from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .db_models import (
    AudiencePackageRecord, CampaignVersionRecord, DataSourceConfigRecord,
    ImportJobRecord, OntologyEntityRecord, PersonaDimensionDefinitionRecord, ProductPackageRecord,
)


class ProfileCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_code: str = Field(min_length=1, max_length=120)
    operator: Literal["eq", "ne", "in", "gte", "lte"]
    value: str | int | float | bool | list[str] | list[int]


class AggregateAudienceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=160)
    estimated_size: int = Field(ge=0)
    conditions: list[ProfileCondition] = Field(min_length=1, max_length=40)


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=160)
    product_type: str = Field(default="组合产品", max_length=64)
    description: str = Field(default="", max_length=2000)
    eligibility: str = Field(default="", max_length=1000)
    version: str = Field(default="V1", max_length=16)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class AudienceSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    records: list[AggregateAudienceInput] = Field(min_length=1, max_length=200)


class ProductSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    records: list[ProductInput] = Field(min_length=1, max_length=200)


def sync_business(session, context, payload, kind):
    ids = [item.external_id for item in payload.records]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "同一批次包含重复 external_id")
    source_key = f"{kind}:{payload.source_id}"
    source = session.scalar(select(DataSourceConfigRecord).where(
        DataSourceConfigRecord.tenant_id == context.tenant_id, DataSourceConfigRecord.source_id == source_key,
    ).with_for_update())
    if source is not None and not source.enabled:
        raise HTTPException(409, "数据源已停用")
    if source is None:
        source = DataSourceConfigRecord(tenant_id=context.tenant_id, source_id=source_key, display_name=payload.source_id, source_type="profile" if kind == "audience" else "product", enabled=True)
        session.add(source)
        session.flush()
    hashes = json.loads(source.mapping_json or "{}")
    model = AudiencePackageRecord if kind == "audience" else ProductPackageRecord
    changed = {"created": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)
    for item in payload.records:
        external_id = "SYNC-" + sha256(json.dumps([kind, payload.source_id, item.external_id]).encode()).hexdigest()[:40]
        digest = sha256(item.model_dump_json().encode()).hexdigest()
        record = session.scalar(select(model).where(model.tenant_id == context.tenant_id, model.external_id == external_id))
        if record is not None and hashes.get(item.external_id) == digest:
            changed["unchanged"] += 1
            continue
        if kind == "audience":
            codes = {condition.field_code for condition in item.conditions}
            if codes & {"member_id", "full_name", "id_number", "mobile", "phone", "email"}:
                raise HTTPException(422, "聚合接口不接收旅客身份、姓名或联系方式条件")
            registered = set(session.scalars(select(PersonaDimensionDefinitionRecord.field_code).where(PersonaDimensionDefinitionRecord.tenant_id == context.tenant_id, PersonaDimensionDefinitionRecord.field_code.in_(codes))))
            if registered != codes:
                raise HTTPException(422, "未注册的画像字段：" + ", ".join(sorted(codes - registered)))
            if record is not None and record.status in {"已冻结", "已使用", "执行中", "已归档"}:
                raise HTTPException(409, "客群包已冻结，请使用新的 external_id")
            values = {"name": item.name, "selection_mode": "tag-combination", "estimated_size": item.estimated_size, "expression_json": json.dumps({"source_id": payload.source_id, "synced_at": now.isoformat(), "conditions": [c.model_dump() for c in item.conditions]}, ensure_ascii=False), "status": "可用"}
        else:
            if item.valid_from and item.valid_to and item.valid_to.replace(tzinfo=item.valid_to.tzinfo or timezone.utc) <= item.valid_from.replace(tzinfo=item.valid_from.tzinfo or timezone.utc):
                raise HTTPException(422, "产品有效期不正确")
            if record is not None and session.scalar(select(CampaignVersionRecord.id).where(CampaignVersionRecord.tenant_id == context.tenant_id, CampaignVersionRecord.product_package_id == record.id, CampaignVersionRecord.status.notin_(["草稿", "已退回"]))):
                raise HTTPException(409, "产品包被审批版本引用，请同步新的 external_id")
            values = item.model_dump(exclude={"external_id"})
            values["status"] = "草稿"
        if record is None:
            record = model(tenant_id=context.tenant_id, external_id=external_id, created_by=context.user_id, **values)
            session.add(record)
            changed["created"] += 1
        else:
            for key, value in values.items():
                setattr(record, key, value)
            changed["updated"] += 1
        entity = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == context.tenant_id, OntologyEntityRecord.external_id == external_id))
        attributes = {"source_id": payload.source_id, "observed_at": now.isoformat(), "status": values["status"], "input": item.model_dump(mode="json")}
        if entity is None:
            entity = OntologyEntityRecord(tenant_id=context.tenant_id, external_id=external_id, entity_type="CustomerAggregate" if kind == "audience" else "ProductPackage", label=item.name, source=source_key, confidence=1.0)
            session.add(entity)
        entity.label, entity.attributes_json = item.name, json.dumps(attributes, ensure_ascii=False)
        hashes[item.external_id] = digest
    source.mapping_json, source.last_sync_at = json.dumps(hashes), now
    batch_id = f"SYNC-{uuid4().hex[:12].upper()}"
    session.add(ImportJobRecord(id=batch_id, tenant_id=context.tenant_id, created_by=context.user_id, dataset_type=kind, file_name=source_key, file_format="json", status="completed", total_rows=len(ids), accepted_rows=len(ids), completed_at=now))
    session.commit()
    return {"batch_id": batch_id, "source_id": payload.source_id, "total": len(ids), **changed}
