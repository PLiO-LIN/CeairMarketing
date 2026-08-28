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
from .flight_product_pipeline import normalize_flight_product_payload
from .security import SecretCipher

MINERU_INTEGRATION_ID = "mineru"
MINERU_DEFAULT_URL = "https://mineru.net"
DOCUMENT_SUFFIXES = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "html"}


def normalize_ontology_decision(payload: Any) -> dict[str, Any]:
    """Normalize an agent admission decision without allowing implicit ontology writes."""
    raw = payload if isinstance(payload, dict) else {}
    decision = raw.get("ontology_gate") if isinstance(raw.get("ontology_gate"), dict) else raw.get("ontology_decision")
    decision = decision if isinstance(decision, dict) else {}
    entities = raw.get("entities") if isinstance(raw.get("entities"), list) else []
    allowed = object_type_ids()
    business_types = {str(item.get("entity_type")) for item in entities if isinstance(item, dict) and str(item.get("entity_type") or "") in allowed and str(item.get("entity_type")) not in {"Evidence", "KnowledgeDocument", "KnowledgeChunk"}}
    requested = decision.get("eligible") is True or str(decision.get("decision") or "").lower() in {"update", "eligible", "admit"}
    eligible = bool(requested and business_types)
    return {
        "eligible": eligible,
        "decision": "update" if eligible else "knowledge_only",
        "reason": str(decision.get("reason") or ("发现可映射且有来源证据的航空营销业务对象" if eligible else "内容未识别出可稳定映射的航空营销业务对象")),
        "matched_entity_types": sorted(business_types) if eligible else [],
        "confidence": max(0.0, min(1.0, float(decision.get("confidence", 0.75 if eligible else 0.88) or 0.0))),
        "review_required": eligible,
    }

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

    def process_structured(self, payload: dict[str, Any], source_name: str) -> list[dict[str, Any]]:
        self._stage("received", "Structured flight/product snapshot received", "completed", source_name=source_name)
        self._stage("normalizing", "Normalize flight, segment, cabin, fare, product and ancillary objects", "running")
        raw_candidates = normalize_flight_product_payload(payload, source_name)
        self._stage("normalized", "Stable ids generated and duplicate business objects merged", "completed", entities=len(raw_candidates.get("entities", [])), relations=len(raw_candidates.get("relations", [])), output_preview=raw_candidates)
        self._stage("semantic-validation", "Validate ontology types, relation direction, evidence and confidence", "running")
        candidates = apply_ontology_admission(raw_candidates)
        decision = candidates["ontology_gate"]
        entities = candidates.get("entities", [])
        relations = candidates.get("relations", [])
        self.job.total_entities = len(entities)
        self.job.total_relations = len(relations)
        self.job.rejected_items = len(candidates.get("rejected_items", []))
        self.result = {"source_name": source_name, "source_format": "ceair-flight-product-snapshot", "candidates": candidates, "ontology_gate": decision}
        self._stage("semantic-validated", "Ontology candidates validated and awaiting human admission", "completed", entities=len(entities), relations=len(relations), rejected=self.job.rejected_items, output_preview=decision)
        if not decision["eligible"]:
            self.job.status = "completed"
            self.job.completed_at = datetime.now(timezone.utc)
            self._stage("knowledge-only", "No eligible ontology candidates; retain processing result only", "completed", ontology_updated=False)
        else:
            self.job.status = "awaiting_confirmation"
            self.job.completed_at = datetime.now(timezone.utc)
            self._stage("awaiting-confirmation", "Flight/product ontology candidates await human confirmation", "needs_review", entities=len(entities), relations=len(relations))
        self._checkpoint()
        return self.events
    def process(self, filename: str, content: bytes) -> list[dict[str, Any]]:
        self._stage("received", "文件接收与安全检查", "completed", file_name=filename, bytes=len(content))
        self._stage("extracting", "文档解析与结构识别", "running")
        text = self._extract_text(filename, content)
        self._stage("extracted", "解析完成并保留来源定位", "completed", text_length=len(text), mineru_task_id=self.job.mineru_task_id, output_preview=text[:500])
        self._stage("knowledge-persisting", "清洗切分并写入营销知识中心", "running")
        document_id = self._persist_knowledge(filename, text)
        self._stage("knowledge-ready", "营销知识文档已入库", "completed", document_id=document_id)
        self._stage("agent-processing", "数据处理智能体正在抽取业务对象与关系", "running")
        candidates = apply_ontology_admission(self._extract_candidates(text, filename))
        decision = candidates["ontology_gate"]
        entities = candidates["entities"]
        relations = candidates["relations"]
        entity_count = len(entities)
        relation_count = len(relations)
        eligible_entity_count = decision["accepted_entity_count"]
        eligible_relation_count = decision["accepted_relation_count"]
        self.job.total_entities = entity_count
        self.job.total_relations = relation_count
        self._stage("agent-output", "数据处理智能体已输出候选对象、关系与准入结论", "completed", entities=entity_count, relations=relation_count, ontology_gate=decision, output_preview={"ontology_gate": decision, "entities": entities[:5], "relations": relations[:5]})
        self._stage("semantic-validation", "对象类型、关系方向、证据、置信度与本体准入校验", "completed", entities=eligible_entity_count, relations=eligible_relation_count, rejected=len(candidates["rejected_items"]), output_preview=decision)
        self.result.update({"text_length": len(text), "document_id": document_id, "candidates": candidates, "ontology_gate": decision})
        if not decision["eligible"]:
            self.job.status = "completed"
            self.job.accepted_entities = 0
            self.job.accepted_relations = 0
            self.job.rejected_items = len(candidates["rejected_items"])
            self.job.completed_at = datetime.now(timezone.utc)
            self._stage("knowledge-only", "智能体判断本次仅保存知识，不更新本体", "completed", reason=decision["reason"], matched_entity_types=decision["matched_entity_types"], ontology_updated=False)
            return self.events
        self.job.status = "awaiting_confirmation"
        self.job.completed_at = datetime.now(timezone.utc)
        self._stage("awaiting-confirmation", "候选本体更新等待人工二次确认", "needs_review", reason=decision["reason"], matched_entity_types=decision["matched_entity_types"], entities=eligible_entity_count, relations=eligible_relation_count)
        return self.events
    def confirm(self, decision: str, note: str, reviewer: str) -> dict[str, Any]:
        saved = json.loads(self.job.result_json or "{}")
        self.events = list(saved.get("events") or [])
        self.result = saved
        review = {"decision": decision, "note": note, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat()}
        self.result["review"] = review
        if decision == "reject":
            self.job.status = "rejected"
            self.job.completed_at = datetime.now(timezone.utc)
            self._stage("rejected", "人工已驳回本体更新，知识文档继续保留", "completed", reviewer=reviewer, note=note)
            return {"accepted_entities": 0, "accepted_relations": 0, "rejected_items": self.job.total_entities + self.job.total_relations}
        candidates = saved.get("candidates") or {}
        gate = candidates.get("ontology_gate") or saved.get("ontology_gate") or {}
        if gate.get("eligible") is not True:
            raise ValueError("该任务没有通过本体准入门禁，不能执行本体更新")
        self._stage("ontology-persisting", "人工确认通过，正在更新本体并记录证据血缘", "running", reviewer=reviewer)
        document_id = str(saved.get("document_id") or "")
        if document_id:
            self._persist_knowledge_ontology(document_id, self.job.file_name)
        result = self._persist_candidates(candidates, self.job.file_name, pipeline_status="confirmed")
        self.job.status = "completed"
        self.job.completed_at = datetime.now(timezone.utc)
        self._stage("ontology-updated", "本体更新完成并保留审核与来源记录", "completed", reviewer=reviewer, **result)
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
                self.harness.set_usage_recorder(lambda result: self.session.add(ModelUsageRecord(tenant_id=self.tenant.tenant_id, provider_id=provider.id, run_id=self.job.id, agent_id="data-processing", request_type="data-pipeline", model_name=result.model_name or provider.model_name, prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens, total_tokens=result.total_tokens)))
                system_prompt = (
                    "你是东航营销数据处理智能体。先判断内容是否适合更新本体，再抽取对象与关系。只输出合法JSON。"
                    "所有内容都可以进入知识中心，只有能映射到稳定航空营销对象、关系明确且来源和时间可追溯的内容才允许更新本体。"
                    "泛化宣传文案、无明确对象的制度说明、无法确认来源或时间的推测、重复内容或无法映射的内容，必须返回ontology_decision.eligible=false、decision=knowledge_only，并将entities和relations设为空数组。"
                    "适合入本体时返回ontology_decision：eligible、decision、reason、matched_entity_types、confidence、needs_human_confirmation；本体更新必须人工二次确认。"
                    "抽取范围包括市场信号、航线、航班、机场、MCT、经营指标、聚合客群、客户需求、机票运价、联运、辅营、卡券、会员权益、营销机会、策略、内容、活动、审批、渠道、触达反馈和归因。"
                    "每个实体必须包含entity_type、external_id、label、attributes、confidence、evidence、valid_time、status；每个关系必须包含source_external_id、target_external_id、relation_type、evidence、confidence。"
                    "只允许使用allowed_types和已注册关系，不得把推断写成事实，不得输出旅客个人信息。"
                )
                data = self.harness.generate_json(LLMConfig(provider.provider_type, provider.base_url, provider.model_name, SecretCipher().decrypt(provider.encrypted_api_key), provider.timeout_seconds, provider.temperature, min(provider.max_tokens, 4096)), system_prompt, json.dumps({"file": filename, "text": text[:50000], "allowed_types": sorted(object_type_ids())}, ensure_ascii=False))
                if isinstance(data, dict) and isinstance(data.get("entities"), list):
                    return data
            except Exception as exc:
                self.harness.emit("harness/model-fallback", reason=type(exc).__name__)
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
            if item.get("ontology_eligible") is not True or not source or not target or not relation or validate_relation_endpoints(relation, source.entity_type, target.entity_type):
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



def apply_ontology_admission(candidates: dict[str, Any]) -> dict[str, Any]:
    """Validate ontology candidates and keep rejected content in the knowledge layer only."""
    data = dict(candidates) if isinstance(candidates, dict) else {}
    gate = normalize_ontology_decision(data)
    raw_entities = data.get("entities") if isinstance(data.get("entities"), list) else []
    raw_relations = data.get("relations") if isinstance(data.get("relations"), list) else []
    allowed_types = object_type_ids()
    entities: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = list(data.get("rejected_items") or []) if isinstance(data.get("rejected_items"), list) else []
    accepted_ids: set[str] = set()
    accepted_types: set[str] = set()
    accepted_type_by_id: dict[str, str] = {}
    for raw_item in raw_entities:
        if not isinstance(raw_item, dict):
            rejected.append({"kind": "entity", "reason": "候选对象格式无效"})
            continue
        item = dict(raw_item)
        entity_type = str(item.get("entity_type") or "")
        external_id = str(item.get("external_id") or "")
        confidence = float(item.get("confidence", 0) or 0)
        has_evidence = bool(item.get("source_refs") or item.get("evidence"))
        eligible = item.get("ontology_eligible") is not False and entity_type in allowed_types and entity_type not in {"KnowledgeDocument", "KnowledgeChunk"} and bool(external_id) and bool(item.get("label")) and has_evidence and confidence >= 0.65
        item["ontology_eligible"] = eligible
        if eligible:
            accepted_ids.add(external_id)
            accepted_types.add(entity_type)
            accepted_type_by_id[external_id] = entity_type
        else:
            item["eligibility_reason"] = item.get("eligibility_reason") or "缺少合法对象类型、稳定标识、来源证据或最低置信度"
            rejected.append({"kind": "entity", "label": item.get("label", ""), "reason": item["eligibility_reason"]})
        entities.append(item)
    relations: list[dict[str, Any]] = []
    accepted_relation_count = 0
    for raw_item in raw_relations:
        if not isinstance(raw_item, dict):
            rejected.append({"kind": "relation", "reason": "候选关系格式无效"})
            continue
        item = dict(raw_item)
        confidence = float(item.get("confidence", 0) or 0)
        source_id = str(item.get("source_external_id") or "")
        target_id = str(item.get("target_external_id") or "")
        relation_type = str(item.get("relation_type") or "")
        endpoint_error = validate_relation_endpoints(relation_type, accepted_type_by_id.get(source_id, ""), accepted_type_by_id.get(target_id, "")) if source_id in accepted_type_by_id and target_id in accepted_type_by_id else "关系两端对象未通过准入"
        eligible = item.get("ontology_eligible") is not False and source_id in accepted_ids and target_id in accepted_ids and bool(relation_type) and bool(item.get("evidence")) and confidence >= 0.65 and endpoint_error is None
        item["ontology_eligible"] = eligible
        if eligible:
            accepted_relation_count += 1
        else:
            item["eligibility_reason"] = item.get("eligibility_reason") or "关系两端未通过准入，或关系缺少证据与最低置信度"
            rejected.append({"kind": "relation", "reason": item["eligibility_reason"]})
        relations.append(item)
    eligible = bool(gate["eligible"] and accepted_ids)
    data["entities"] = entities
    data["relations"] = relations
    data["rejected_items"] = rejected
    data["ontology_gate"] = {
        **gate,
        "eligible": eligible,
        "decision": "update" if eligible else "knowledge_only",
        "review_required": eligible,
        "matched_entity_types": sorted(accepted_types) if eligible else [],
        "accepted_entity_count": len(accepted_ids) if eligible else 0,
        "accepted_relation_count": accepted_relation_count if eligible else 0,
    }
    return data

def default_provider(session: Session, tenant_id: int) -> ModelProviderRecord | None:
    return session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True)).order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))


def heuristic_candidates(text: str, filename: str) -> dict[str, Any]:
    """Conservative fallback when no model is configured or model output is invalid."""
    lower = text.lower()
    signals = ("route", "flight", "load factor", "fare", "price", "audience", "demand", "conversion", "campaign", "航线", "航班", "客座率", "价格", "客群", "活动", "营销")
    if not any(token in lower for token in signals):
        return {
            "ontology_gate": {
                "eligible": False,
                "decision": "knowledge_only",
                "reason": "未识别出可稳定映射到航空营销本体的业务对象",
                "matched_entity_types": [],
                "confidence": 0.9,
                "review_required": False,
            },
            "entities": [],
            "relations": [],
            "rejected_items": [],
        }
    entities: list[dict[str, Any]] = []
    route = re.search(r"([\u4e00-\u9fffA-Za-z]{1,12})\s*(?:—|-|至|to)\s*([\u4e00-\u9fffA-Za-z]{1,12})(?:航线|route)?", text, re.IGNORECASE)
    if route:
        route_id = f"route-{route.group(1).lower()}-{route.group(2).lower()}"
        entities.append({
            "external_id": route_id,
            "entity_type": "Route",
            "label": f"{route.group(1)}—{route.group(2)}航线",
            "attributes": {"extraction_mode": "fallback"},
            "confidence": 0.74,
            "evidence": text[:500],
            "source_refs": ["document:body"],
            "status": "candidate",
            "ontology_eligible": True,
        })
    metric_id = f"metric-{hashlib.sha256((filename + text[:500]).encode('utf-8')).hexdigest()[:12]}"
    entities.append({
        "external_id": metric_id,
        "entity_type": "MetricObservation",
        "label": f"{filename}经营指标观测",
        "attributes": {"excerpt": text[:500], "extraction_mode": "fallback"},
        "confidence": 0.72,
        "evidence": text[:500],
        "source_refs": ["document:body"],
        "status": "candidate",
        "ontology_eligible": True,
    })
    return {
        "ontology_gate": {
            "eligible": True,
            "decision": "update",
            "reason": "识别到航线、航班或经营指标等稳定业务对象，建议人工确认后更新本体",
            "matched_entity_types": sorted({item["entity_type"] for item in entities}),
            "confidence": 0.7,
            "review_required": True,
        },
        "entities": entities,
        "relations": [],
        "rejected_items": [],
    }