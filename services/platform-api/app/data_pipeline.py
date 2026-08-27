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
from .db_models import DataPipelineJobRecord, IntegrationConfigRecord, KnowledgeChunkRecord, KnowledgeDocumentRecord, ModelProviderRecord, OntologyEntityRecord, OntologyRelationRecord
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
        self.session = session; self.tenant = tenant; self.job = job; self.events: list[dict[str, Any]] = []
        self.harness = UnifiedHarness(lambda event, payload: self.events.append({"event": event, **payload}))

    def process(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        self._stage("received", "数据接收", "completed"); text = self._extract_text(filename, content); self._persist_knowledge(filename, text); self._stage("extracted", "文档结构化提取", "completed")
        self._persist_knowledge(filename, text)
        candidates = self._extract_candidates(text, filename); self._stage("classified", "对象与关系分级分类", "completed", entities=len(candidates.get("entities", [])), relations=len(candidates.get("relations", [])))
        result = self._persist_candidates(candidates, filename); self._stage("ontology-updated", "本体对象与关系更新", "completed", **result)
        self.job.result_json = json.dumps({"events": self.events, "text_length": len(text), "candidates": candidates}, ensure_ascii=False); self.session.commit(); return self.events

    def _persist_knowledge(self, filename: str, text: str) -> None:
        document_id = f"knowledge-doc-{self.job.id.lower()}"
        document = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == document_id))
        if document is None:
            document = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=document_id)
            self.session.add(document)
        document.entity_type = "KnowledgeDocument"; document.label = filename; document.attributes_json = json.dumps({"pipeline_job_id": self.job.id, "content_length": len(text), "status": "parsed"}, ensure_ascii=False); document.source = f"data-pipeline:{filename}"; document.confidence = 1.0; self.session.flush()
        for index, chunk_text in enumerate([text[i:i + 1800] for i in range(0, len(text), 1800)][:100]):
            chunk_id = f"{document_id}-chunk-{index + 1}"
            chunk = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == chunk_id))
            if chunk is None:
                chunk = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=chunk_id)
                self.session.add(chunk)
            chunk.entity_type = "KnowledgeChunk"; chunk.label = f"{filename} / 片段 {index + 1}"; chunk.attributes_json = json.dumps({"document_id": document_id, "sequence": index + 1, "text": chunk_text}, ensure_ascii=False); chunk.source = f"data-pipeline:{filename}"; chunk.confidence = 1.0; self.session.flush()
            exists = self.session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id == self.tenant.tenant_id, OntologyRelationRecord.source_entity_id == document.id, OntologyRelationRecord.relation_type == "contains_chunk", OntologyRelationRecord.target_entity_id == chunk.id))
            if exists is None: self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=document.id, relation_type="contains_chunk", target_entity_id=chunk.id, evidence="文档切分", source=f"data-pipeline:{filename}", confidence=1.0))
        self.session.commit()

    def _extract_text(self, filename: str, content: bytes) -> str:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""; config = get_mineru_config(self.session, self.tenant.tenant_id)
        if suffix in DOCUMENT_SUFFIXES:
            if not config or not config.enabled or not config.encrypted_api_key: raise RuntimeError("MinerU 尚未启用或未配置 API Key")
            text, task_id = self.harness.run_tool("mineru.parse", lambda: MinerUClient(config, SecretCipher()).parse(filename, content)); self.job.mineru_task_id = task_id; return text
        if suffix in {"txt", "md", "json"}: return content.decode("utf-8-sig", "ignore")
        if suffix == "csv": return json.dumps(list(csv.DictReader(io.StringIO(content.decode("utf-8-sig", "ignore")))), ensure_ascii=False)
        raise ValueError(f"不支持的数据文件类型: .{suffix}")

    def _extract_candidates(self, text: str, filename: str) -> dict[str, Any]:
        provider = default_provider(self.session, self.tenant.tenant_id); reads = ["MarketSignal", "MetricObservation", "Flight", "Route", "Product", "CustomerAggregate"]; writes = ["Evidence", "Opportunity", "ConfigurableAttribute", "BusinessRule"]; functions = ["detect_business_anomaly"]
        self.harness.load_context(HarnessContext(self.tenant.tenant_id, self.job.id, "data-processing", reads, writes, functions))
        if provider is not None:
            try:
                from .llm import LLMConfig
                data = self.harness.generate_json(LLMConfig(provider.provider_type, provider.base_url, provider.model_name, SecretCipher().decrypt(provider.encrypted_api_key), provider.timeout_seconds, provider.temperature, min(provider.max_tokens, 4096)), "你是东航营销数据处理智能体。只输出合法JSON。抽取航空营销业务对象、关系、证据和置信度，不要杜撰事实。", json.dumps({"file": filename, "text": text[:50000], "allowed_types": sorted(object_type_ids())}, ensure_ascii=False))
                if isinstance(data.get("entities"), list): return data
            except Exception as exc: self.harness.emit("harness/model-fallback", reason=type(exc).__name__)
        return heuristic_candidates(text, filename)

    def _persist_knowledge(self, filename: str, text: str) -> None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        external_id = f"doc-{digest[:24]}"
        document = self.session.scalar(select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.tenant_id == self.tenant.tenant_id, KnowledgeDocumentRecord.external_id == external_id))
        if document is None:
            document = KnowledgeDocumentRecord(tenant_id=self.tenant.tenant_id, external_id=external_id, title=filename, source_name=filename, content=text, content_hash=digest, classification="internal", status="active", version=1)
            self.session.add(document); self.session.flush()
        else:
            document.content = text; document.content_hash = digest; document.version += 1; self.session.flush()
        doc_entity = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == external_id))
        if doc_entity is None:
            doc_entity = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=external_id, entity_type="KnowledgeDocument", label=filename, attributes_json=json.dumps({"content_hash": digest, "classification": document.classification}, ensure_ascii=False), source=f"data-pipeline:{filename}", confidence=1.0); self.session.add(doc_entity); self.session.flush()
        for sequence, start in enumerate(range(0, len(text), 1200), start=1):
            chunk_text = text[start:start + 1200].strip()
            if not chunk_text: continue
            chunk_id = f"{external_id}-chunk-{sequence}"
            chunk = self.session.scalar(select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.tenant_id == self.tenant.tenant_id, KnowledgeChunkRecord.external_id == chunk_id))
            if chunk is None:
                chunk = KnowledgeChunkRecord(tenant_id=self.tenant.tenant_id, document_id=document.id, external_id=chunk_id, sequence=sequence, heading="", content=chunk_text, token_estimate=max(1, len(chunk_text) // 2), metadata_json=json.dumps({"source_name": filename, "char_start": start, "char_end": start + len(chunk_text)}, ensure_ascii=False)); self.session.add(chunk); self.session.flush()
            chunk_entity = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == chunk_id))
            if chunk_entity is None:
                chunk_entity = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=chunk_id, entity_type="KnowledgeChunk", label=f"{filename}#{sequence}", attributes_json=json.dumps({"document_id": external_id, "sequence": sequence}, ensure_ascii=False), source=f"data-pipeline:{filename}", confidence=1.0); self.session.add(chunk_entity); self.session.flush()
            exists = self.session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id == self.tenant.tenant_id, OntologyRelationRecord.source_entity_id == doc_entity.id, OntologyRelationRecord.relation_type == "contains_chunk", OntologyRelationRecord.target_entity_id == chunk_entity.id))
            if exists is None: self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=doc_entity.id, relation_type="contains_chunk", target_entity_id=chunk_entity.id, evidence="文档切分结果", source=f"data-pipeline:{filename}", confidence=1.0))
        self.session.commit()

    def _persist_candidates(self, candidates: dict[str, Any], filename: str) -> dict[str, int]:
        entities = candidates.get("entities", []) if isinstance(candidates.get("entities"), list) else []; relations = candidates.get("relations", []) if isinstance(candidates.get("relations"), list) else []; records: dict[str, OntologyEntityRecord] = {}; accepted_entities = rejected = 0
        for item in entities:
            if not isinstance(item, dict): rejected += 1; continue
            external_id = str(item.get("external_id") or f"ingest-{uuid4().hex[:12]}"); entity_type = str(item.get("entity_type") or "Evidence"); label = str(item.get("label") or "未命名候选对象")
            if entity_type not in object_type_ids(): rejected += 1; continue
            record = self.session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == self.tenant.tenant_id, OntologyEntityRecord.external_id == external_id))
            if record is None: record = OntologyEntityRecord(tenant_id=self.tenant.tenant_id, external_id=external_id); self.session.add(record)
            record.entity_type = entity_type; record.label = label; record.attributes_json = json.dumps({"pipeline_status": "candidate", **(item.get("attributes") or {})}, ensure_ascii=False); record.source = f"data-pipeline:{filename}"; record.confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5)))); self.session.flush(); records[external_id] = record; accepted_entities += 1
        accepted_relations = 0
        for item in relations:
            if not isinstance(item, dict): rejected += 1; continue
            source = records.get(str(item.get("source_external_id"))); target = records.get(str(item.get("target_external_id"))); relation = str(item.get("relation_type") or "")
            if not source or not target or not relation: rejected += 1; continue
            if validate_relation_endpoints(relation, source.entity_type, target.entity_type): rejected += 1; continue
            self.session.add(OntologyRelationRecord(tenant_id=self.tenant.tenant_id, source_entity_id=source.id, relation_type=relation, target_entity_id=target.id, evidence=str(item.get("evidence") or ""), source=f"data-pipeline:{filename}", confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))))); accepted_relations += 1
        self.session.commit(); self.job.accepted_entities = accepted_entities; self.job.accepted_relations = accepted_relations; self.job.rejected_items = rejected; self.job.total_entities = len(entities); self.job.total_relations = len(relations); return {"accepted_entities": accepted_entities, "accepted_relations": accepted_relations, "rejected_items": rejected}

    def _stage(self, stage: str, label: str, status: str, **payload: Any) -> None:
        self.job.current_stage = stage; self.events.append({"stage": stage, "label": label, "status": status, **payload}); self.session.commit()


def default_provider(session: Session, tenant_id: int) -> ModelProviderRecord | None:
    return session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True)).order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))


def heuristic_candidates(text: str, filename: str) -> dict[str, Any]:
    entities: list[dict[str, Any]] = [{"external_id": f"evidence-{uuid4().hex[:10]}", "entity_type": "Evidence", "label": filename, "attributes": {"excerpt": text[:500], "extraction_mode": "fallback"}, "confidence": 0.55}]
    route = re.search(r"([\u4e00-\u9fffA-Za-z]{1,8})[—\-至]([\u4e00-\u9fffA-Za-z]{1,8})航线", text)
    if route: entities.append({"external_id": f"route-{route.group(1)}-{route.group(2)}", "entity_type": "Route", "label": f"{route.group(1)}—{route.group(2)}航线", "attributes": {"extraction_mode": "fallback"}, "confidence": 0.62})
    return {"entities": entities, "relations": []}
