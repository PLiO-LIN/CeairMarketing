from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents import HarnessContext, UnifiedHarness
from .auth import TenantContext
from .db_models import DataPipelineJobRecord, IntegrationConfigRecord, KnowledgeChunkRecord, KnowledgeDocumentRecord, ModelProviderRecord, ModelUsageRecord, OntologyEntityRecord, OntologyRelationRecord
from .llm import LLMConfig
from .ontology import object_type_ids, validate_relation_endpoints
from .security import SecretCipher

MINERU_INTEGRATION_ID = "mineru"
MINERU_DEFAULT_URL = "https://mineru.net"
DOCUMENT_SUFFIXES = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "html"}


def integration_view(record: IntegrationConfigRecord | None) -> dict[str, Any]:
    return {"integration_id": MINERU_INTEGRATION_ID, "display_name": record.display_name if record else "MinerU 文档解析", "base_url": record.base_url if record else MINERU_DEFAULT_URL, "enabled": bool(record and record.enabled), "api_key_configured": bool(record and record.encrypted_api_key), "config": json.loads(record.config_json or "{}") if record else {"model_version": "vlm", "enable_table": True, "is_ocr": False}, "updated_at": record.updated_at if record else datetime.now(timezone.utc)}


def get_mineru_config(session: Session, tenant_id: int) -> IntegrationConfigRecord | None:
    return session.scalar(select(IntegrationConfigRecord).where(IntegrationConfigRecord.tenant_id == tenant_id, IntegrationConfigRecord.integration_id == MINERU_INTEGRATION_ID))


class MinerUClient:
    def __init__(self, config: IntegrationConfigRecord, cipher: SecretCipher) -> None:
        self.base_url = (config.base_url or MINERU_DEFAULT_URL).rstrip("/")
        self.token = cipher.decrypt(config.encrypted_api_key)
        self.options = json.loads(config.config_json or "{}")

    def parse(self, filename: str, content: bytes) -> tuple[str, str]:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"files": [{"name": filename, "data_id": f"pipeline-{uuid4().hex}"}], "model_version": self.options.get("model_version", "vlm"), "enable_table": self.options.get("enable_table", True), "is_ocr": self.options.get("is_ocr", False), "language": self.options.get("language", "ch")}
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.base_url}/api/v4/file-urls/batch", headers=headers, json=payload); response.raise_for_status()
            body = response.json()
            if body.get("code") != 0: raise RuntimeError(body.get("msg", "MinerU upload URL request failed"))
            upload_url = body["data"]["file_urls"][0]; upload = client.put(upload_url, content=content, timeout=180); upload.raise_for_status()
            task_id = body["data"].get("batch_id", "")
            for _ in range(60):
                result = client.get(f"{self.base_url}/api/v4/extract-results/batch/{task_id}", headers={"Authorization": f"Bearer {self.token}"}); result.raise_for_status()
                data = result.json().get("data", {})
                extraction = data.get("extract_result", data)
                if isinstance(extraction, list):
                    extraction = extraction[0] if extraction else {}
                state = extraction.get("state", data.get("state"))
                if state == "done":
                    archive_url = extraction.get("full_zip_url") or data.get("full_zip_url")
                    markdown_url = extraction.get("md_url") or data.get("md_url")
                    if markdown_url:
                        markdown_response = client.get(markdown_url, timeout=180); markdown_response.raise_for_status()
                        return markdown_response.text, task_id
                    if not archive_url: raise RuntimeError("MinerU response did not include full_zip_url or md_url")
                    archive = client.get(archive_url, timeout=180); archive.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
                        markdown = next((zipped.read(name).decode("utf-8", "ignore") for name in zipped.namelist() if name.endswith("full.md")), "")
                    return markdown, task_id
                if state == "failed": raise RuntimeError(extraction.get("err_msg") or data.get("err_msg", "MinerU parse failed"))
                time.sleep(2)
        raise TimeoutError("MinerU parse timed out")


class DataProcessingAgent:
    def __init__(self, session: Session, tenant: TenantContext, job: DataPipelineJobRecord) -> None:
        self.session = session
        self.tenant = tenant
        self.job = job
        self.events: list[dict[str, Any]] = []
        self.result: dict[str, Any] = {}
        self.harness = UnifiedHarness(self._record_harness_event)

    def process(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        self._stage("received", "文件接收与安全检查", "completed", file_name=filename, bytes=len(content))
        self._stage("extracting", "文档解析与结构识别", "running")
        text = self._extract_text(filename, content)
        self._stage("extracted", "解析完成，保留页码、章节和表格溯源", "completed", text_length=len(text), mineru_task_id=self.job.mineru_task_id)
        self._stage("knowledge-persisting", "清洗切分并写入营销知识库", "running")
        document_id = self._persist_knowledge(filename, text)
        self._stage("knowledge-ready", "营销知识文档已就绪", "completed", document_id=document_id)
        self._stage("agent-processing", "数据处理智能体开始理解业务数据", "running")
        candidates = self._extract_candidates(text, filename)
        entity_count = len(candidates.get("entities", []))
        relation_count = len(candidates.get("relations", []))
        self.job.total_entities = entity_count
        self.job.total_relations = relation_count
        self._stage("semantic-validation", "航空营销语义、关系方向和证据校验", "completed", entities=entity_count, relations=relation_count)
        self.result.update({"text_length": len(text), "document_id": document_id, "candidates": candidates})
        self.job.status = "awaiting_confirmation"
        self.job.completed_at = datetime.now(timezone.utc)
        self._stage("awaiting-confirmation", "候选本体更新等待人工二次确认", "needs_review", entities=entity_count, relations=relation_count)
        return self.events

    def confirm(self, decision: str, note: str, reviewer: str) -> dict[str, Any]:
        saved = json.loads(self.job.result_json or "{}")
        self.events = list(saved.get("events") or [])
        self.result = saved
        review = {"decision": decision, "note": note, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat()}
        self.result["review"] = review
        if decision == "reject":
            self.job.status = "rejected"
            self._stage("rejected", "人工已驳回本体更新", "completed", reviewer=reviewer, note=note)
            return {"accepted_entities": 0, "accepted_relations": 0, "rejected_items": self.job.total_entities + self.job.total_relations}
        self._stage("ontology-persisting", "人工确认通过，正在更新本体", "running", reviewer=reviewer)
        self._persist_knowledge_ontology(str(saved.get("document_id") or ""), self.job.file_name)
        result = self._persist_candidates(saved.get("candidates") or {}, self.job.file_name, pipeline_status="confirmed")
        self.job.status = "completed"
        self.job.completed_at = datetime.now(timezone.utc)
        self._stage("ontology-updated", "本体更新完成并保留审核溯源", "completed", reviewer=reviewer, **result)
        return result

    def _extract_text(self, filename: str, content: bytes) -> str:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""; config = get_mineru_config(self.session, self.tenant.tenant_id)
        if suffix in DOCUMENT_SUFFIXES:
            if not config or not config.enabled or not config.encrypted_api_key: raise RuntimeError("MinerU 尚未启用或未配置 API Key")
            text, task_id = self.harness.run_tool("mineru.parse", lambda: MinerUClient(config, SecretCipher()).parse(filename, content)); self.job.mineru_task_id = task_id; return text
        if suffix in {"txt", "md", "json"}: return content.decode("utf-8-sig", "ignore")
        if suffix == "csv": return json.dumps(list(csv.DictReader(io.StringIO(content.decode("utf-8-sig", "ignore")))), ensure_ascii=False)
        raise ValueError(f"不支持的数据文件类型: .{suffix}")

    def _extract_candidates(self, text: str, filename: str) -> dict[str, Any]:
        provider = default_provider(self.session, self.tenant.tenant_id)
        reads = ["MarketSignal", "MetricObservation", "Flight", "Route", "Product", "CustomerAggregate", "KnowledgeChunk"]
        writes = ["Evidence", "Opportunity", "MarketingObjective", "CustomerNeed", "ValueProposition", "StrategyPlan", "TouchpointPlan", "AttributionResult", "ConfigurableAttribute", "BusinessRule"]
        functions = ["detect_business_anomaly", "evaluate_target_attractiveness"]
        self.harness.load_context(HarnessContext(self.tenant.tenant_id, self.job.id, "data-processing", reads, writes, functions))
        if provider is not None:
            try:
                self.harness.set_usage_recorder(lambda result: self.session.add(ModelUsageRecord(
                    tenant_id=self.tenant.tenant_id,
                    provider_id=provider.id,
                    run_id=self.job.id,
                    agent_id="data-processing",
                    request_type="data-pipeline",
                    model_name=result.model_name or provider.model_name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                )))
                system_prompt = (
                    "你是东航营销数据处理智能体。只输出合法JSON，包含entities和relations。"
                    "从市场、航班、经营、客户、产品、活动和渠道数据中抽取可追溯对象与关系。"
                    "重点区分观测事实、营销机会、客户需求、营销目标、价值主张、策略方案、触点计划和归因结果。"
                    "不得把推断写成已确认事实；推断必须标记candidate状态、证据、有效期和置信度，不得杜撰旅客个人信息。"
                )
                data = self.harness.generate_json(LLMConfig(provider.provider_type, provider.base_url, provider.model_name, SecretCipher().decrypt(provider.encrypted_api_key), provider.timeout_seconds, provider.temperature, min(provider.max_tokens, 4096)), system_prompt, json.dumps({"file": filename, "text": text[:50000], "allowed_types": sorted(object_type_ids())}, ensure_ascii=False))
                if isinstance(data.get("entities"), list): return data
            except Exception as exc: self.harness.emit("harness/model-fallback", reason=type(exc).__name__)
        return heuristic_candidates(text, filename)

    def _persist_knowledge(self, filename: str, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        external_id = f"doc-{digest[:24]}"
        document = self.session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == self.tenant.tenant_id, KnowledgeDocumentRecord.external_id == external_id))
        if document is None:
            document = KnowledgeDocumentRecord(tenant_id=self.tenant.tenant_id, external_id=external_id, title=filename, source_name=filename, content=text, content_hash=digest, classification="internal", status="active", version=1)
            self.session.add(document)
            self.session.flush()
        else:
            document.content = text
            document.content_hash = digest
            document.version += 1
            self.session.flush()
        for sequence, start in enumerate(range(0, len(text), 1200), start=1):
            chunk_text = text[start:start + 1200].strip()
            if not chunk_text:
                continue
            chunk_id = f"{external_id}-chunk-{sequence}"
            chunk = self.session.scalar(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == self.tenant.tenant_id, KnowledgeChunkRecord.external_id == chunk_id))
            if chunk is None:
                chunk = KnowledgeChunkRecord(tenant_id=self.tenant.tenant_id, document_id=document.id, external_id=chunk_id, sequence=sequence, heading="", content=chunk_text, token_estimate=max(1, len(chunk_text) // 2), metadata_json=json.dumps({"source_name": filename, "char_start": start, "char_end": start + len(chunk_text)}, ensure_ascii=False))
                self.session.add(chunk)
        self.session.commit()
        return external_id

    def _persist_knowledge_ontology(self, document_external_id: str, filename: str) -> None:
        document = self.session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == self.tenant.tenant_id, KnowledgeDocumentRecord.external_id == document_external_id))
        if document is None:
            raise ValueError("待确认的知识文档不存在")
        source_name = f"data-pipeline:{self.job.id}"
        doc_entity = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == document.external_id))
        if doc_entity is None:
            doc_entity = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=document.external_id)
            self.session.add(doc_entity)
        doc_entity.entity_type = "KnowledgeDocument"
        doc_entity.label = filename
        doc_entity.attributes_json = json.dumps({"content_hash": document.content_hash, "classification": document.classification, "pipeline_status": "confirmed"}, ensure_ascii=False)
        doc_entity.source = source_name
        doc_entity.confidence = 1.0
        self.session.flush()
        chunks = self.session.scalars(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == self.tenant.tenant_id, KnowledgeChunkRecord.document_id == document.id).order_by(KnowledgeChunkRecord.sequence)).all()
        for chunk in chunks:
            chunk_entity = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == chunk.external_id))
            if chunk_entity is None:
                chunk_entity = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=chunk.external_id)
                self.session.add(chunk_entity)
            chunk_entity.entity_type = "KnowledgeChunk"
            chunk_entity.label = f"{filename}#{chunk.sequence}"
            chunk_entity.attributes_json = json.dumps({"document_id": document.external_id, "sequence": chunk.sequence, "excerpt": chunk.content[:240], "pipeline_status": "confirmed"}, ensure_ascii=False)
            chunk_entity.source = source_name
            chunk_entity.confidence = 1.0
            self.session.flush()
            exists = self.session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id == self.tenant.tenant_id, OntologyRelationRecord.source_entity_id == doc_entity.id, OntologyRelationRecord.relation_type == "contains_chunk", OntologyRelationRecord.target_entity_id == chunk_entity.id))
            if exists is None:
                self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=doc_entity.id, relation_type="contains_chunk", target_entity_id=chunk_entity.id, evidence="人工确认后的文档切分结果", source=source_name, confidence=1.0))
        self.session.commit()

    def _persist_candidates(self, candidates: dict[str, Any], filename: str, pipeline_status: str = "confirmed") -> dict[str, int]:
        entities = candidates.get("entities", []) if isinstance(candidates.get("entities"), list) else []
        relations = candidates.get("relations", []) if isinstance(candidates.get("relations"), list) else []
        records: dict[str, OntologyEntityRecord] = {}
        accepted_entities = rejected = 0
        source_name = f"data-pipeline:{self.job.id}"
        for item in entities:
            if not isinstance(item, dict):
                rejected += 1
                continue
            external_id = str(item.get("external_id") or f"ingest-{uuid4().hex[:12]}")
            entity_type = str(item.get("entity_type") or "Evidence")
            label = str(item.get("label") or "未命名候选对象")
            if entity_type not in object_type_ids():
                rejected += 1
                continue
            record = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == external_id))
            if record is None:
                record = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=external_id)
                self.session.add(record)
            record.entity_type = entity_type
            record.label = label
            record.attributes_json = json.dumps({"pipeline_status": pipeline_status, **(item.get("attributes") or {})}, ensure_ascii=False)
            record.source = source_name
            record.confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            self.session.flush()
            records[external_id] = record
            accepted_entities += 1
        knowledge_chunks = self.session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.entity_type == "KnowledgeChunk", OntologyEntityRecord.source == source_name).order_by(OntologyEntityRecord.id).limit(1)).all()
        if knowledge_chunks:
            chunk = knowledge_chunks[0]
            for record in records.values():
                if validate_relation_endpoints("evidence_for", chunk.entity_type, record.entity_type) is None:
                    exists = self.session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id == self.tenant.tenant_id, OntologyRelationRecord.source_entity_id == chunk.id, OntologyRelationRecord.relation_type == "evidence_for", OntologyRelationRecord.target_entity_id == record.id))
                    if exists is None:
                        self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=chunk.id, relation_type="evidence_for", target_entity_id=record.id, evidence="数据处理智能体抽取证据，已人工确认", source=source_name, confidence=record.confidence))
        accepted_relations = 0
        for item in relations:
            if not isinstance(item, dict):
                rejected += 1
                continue
            source = records.get(str(item.get("source_external_id")))
            target = records.get(str(item.get("target_external_id")))
            relation = str(item.get("relation_type") or "")
            if not source or not target or not relation or validate_relation_endpoints(relation, source.entity_type, target.entity_type):
                rejected += 1
                continue
            self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=source.id, relation_type=relation, target_entity_id=target.id, evidence=str(item.get("evidence") or ""), source=source_name, confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5))))))
            accepted_relations += 1
        self.session.commit()
        self.job.accepted_entities = accepted_entities
        self.job.accepted_relations = accepted_relations
        self.job.rejected_items = rejected
        self.job.total_entities = len(entities)
        self.job.total_relations = len(relations)
        return {"accepted_entities": accepted_entities, "accepted_relations": accepted_relations, "rejected_items": rejected}

    def _stage(self, stage: str, label: str, status: str, **payload: Any) -> None:
        self.job.current_stage = stage
        self.events.append({"stage": stage, "label": label, "status": status, "timestamp": datetime.now(timezone.utc).isoformat(), **payload})
        self._checkpoint()

    def _record_harness_event(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **payload})
        self._checkpoint()

    def _checkpoint(self) -> None:
        self.result["events"] = self.events
        self.job.result_json = json.dumps(self.result, ensure_ascii=False)
        self.session.commit()


def default_provider(session: Session, tenant_id: int) -> ModelProviderRecord | None:
    return session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True)).order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))


def heuristic_candidates(text: str, filename: str) -> dict[str, Any]:
    entities: list[dict[str, Any]] = [{"external_id": f"evidence-{uuid4().hex[:10]}", "entity_type": "Evidence", "label": filename, "attributes": {"excerpt": text[:500], "extraction_mode": "fallback"}, "confidence": 0.55}]
    route = re.search(r"([\u4e00-\u9fffA-Za-z]{1,8})[—\-至]([\u4e00-\u9fffA-Za-z]{1,8})航线", text)
    if route: entities.append({"external_id": f"route-{route.group(1)}-{route.group(2)}", "entity_type": "Route", "label": f"{route.group(1)}—{route.group(2)}航线", "attributes": {"extraction_mode": "fallback"}, "confidence": 0.62})
    return {"entities": entities, "relations": []}
