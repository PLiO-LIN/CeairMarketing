"""Market hotspot ingestion, agent processing, ontology gating and opportunity discovery."""
from __future__ import annotations
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urldefrag, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from sqlalchemy import select
from sqlalchemy.orm import Session
from .agents.harness import HarnessContext, UnifiedHarness
from .auth import TenantContext
from .db_models import MarketHotspotRecord, ModelProviderRecord, OntologyEntityRecord, OntologyRelationRecord, OpportunityRecord
from .llm import LLMConfig
from .ontology import agent_contract, object_type_ids, relation_type_ids, validate_relation_endpoints
from .security import SecretCipher

AVIATION_KEYWORDS = {
    "\u822a\u7ebf", "\u822a\u73ed", "\u673a\u7968", "\u5ba2\u5ea7\u7387", "\u673a\u573a", "\u4e2d\u8f6c", "\u7a7a\u94c1", "\u822a\u7a7a", "\u51fa\u884c", "\u65c5\u6e38", "\u5546\u52a1\u5dee\u65c5", "\u4f01\u4e1a\u5dee\u65c5", "\u4eb2\u5b50", "\u63a2\u4eb2", "\u5047\u671f", "\u9152\u5e97", "\u9ad8\u94c1", "\u4f1a\u5458", "\u91cc\u7a0b", "\u5361\u5238", "\u8f85\u8425", "\u4e0a\u6d77", "\u5317\u4eac", "\u5e7f\u5dde", "\u6df1\u5733", "\u6210\u90fd", "\u6606\u660e", "\u4e09\u4e9a", "\u897f\u5b89", "\u4e1c\u4eac", "\u65b0\u52a0\u5761"
}
TOPIC_RULES = {
    "\u8282\u5047\u65e5\u51fa\u884c": {"\u56fd\u5e86", "\u6625\u8282", "\u6691\u671f", "\u4e94\u4e00", "\u4e2d\u79cb", "\u7aef\u5348", "\u5047\u671f", "\u8fd4\u4e61"},
    "\u65c5\u6e38\u76ee\u7684\u5730": {"\u65c5\u6e38", "\u666f\u533a", "\u6587\u65c5", "\u9152\u5e97", "\u5ea6\u5047", "\u4eb2\u5b50", "\u6ed1\u96ea", "\u7814\u5b66"},
    "\u5546\u52a1\u5dee\u65c5": {"\u5546\u52a1", "\u4f1a\u8bae", "\u5c55\u4f1a", "\u51fa\u5dee", "\u5dee\u65c5", "\u4f01\u4e1a\u5dee\u65c5"},
    "\u822a\u73ed\u7ecf\u8425": {"\u822a\u73ed", "\u5ba2\u5ea7\u7387", "\u822a\u7ebf", "\u673a\u573a", "\u5ef6\u8bef", "\u53d6\u6d88", "\u4e2d\u8f6c", "\u8fd0\u4ef7"},
    "\u4ef7\u683c\u4fc3\u9500": {"\u673a\u7968", "\u7968\u4ef7", "\u4ef7\u683c", "\u6298\u6263", "\u4fc3\u9500", "\u4f18\u60e0", "\u5361\u5238", "\u8865\u8d34"},
    "\u4f1a\u5458\u4e0e\u8f85\u8425": {"\u4f1a\u5458", "\u91cc\u7a0b", "\u5347\u8231", "\u884c\u674e", "\u8d35\u5bbe\u5ba4", "\u9009\u5ea7", "\u8f85\u8425"},
}

def utc_now(): return datetime.now(timezone.utc)
def clean_text(value: Any) -> str: return html.unescape(re.sub(r"\s+", " ", str(value or ""))).strip()[:12000]
def parse_date(value: Any):
    if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw: return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00")); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            d = parsedate_to_datetime(raw); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError): return None

def canonicalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw: return ""
    raw, _ = urldefrag(raw); p = urlsplit(raw)
    query = "&".join(x for x in p.query.split("&") if x and not x.lower().startswith(("utm_", "spm=", "from=")))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))

def content_hash(title, content): return hashlib.sha256((clean_text(title).lower()+"\n"+clean_text(content).lower()).encode()).hexdigest()
def dedupe_key(item):
    basis = canonicalize_url(item.get("canonical_url") or item.get("url") or "") or (clean_text(item.get("source_name"))+"|"+clean_text(item.get("title")).lower())
    return hashlib.sha256(basis.encode()).hexdigest()

def normalize_item(item, source_name, source_type, source_url=""):
    title = clean_text(item.get("title") or item.get("name")); content = clean_text(item.get("content") or item.get("description") or item.get("summary")); canonical = canonicalize_url(item.get("canonical_url") or item.get("url") or item.get("link") or "")
    result = {"source_name":clean_text(item.get("source_name") or source_name)[:160], "source_type":clean_text(item.get("source_type") or source_type)[:40], "source_url":clean_text(item.get("source_url") or source_url)[:500], "external_id":clean_text(item.get("external_id") or item.get("id"))[:240], "canonical_url":canonical[:500], "title":title[:500], "content":content, "published_at":parse_date(item.get("published_at") or item.get("pubDate") or item.get("published")), "language":clean_text(item.get("language") or "zh")[:16], "region":clean_text(item.get("region"))[:120]}
    result["dedupe_key"] = dedupe_key(result); result["content_hash"] = content_hash(title, content); return result

def parse_feed(payload, source_name, source_url, source_type="rss"):
    root = ElementTree.fromstring(payload); rows=[]
    for element in root.iter():
        tag = element.tag.rsplit("}",1)[-1].lower()
        if tag not in {"item","entry"}: continue
        values={}
        for child in list(element):
            key=child.tag.rsplit("}",1)[-1].lower(); value=child.attrib.get("href","") or child.text or ""
            if value and key not in values: values[key]=value
        rows.append(normalize_item(values, source_name, source_type, source_url))
    return rows

def fetch_feed(source_name, source_url, source_type="rss", timeout=20):
    req=Request(source_url, headers={"User-Agent":"CeairMarketing/1.0 hotspot-ingestor"})
    with urlopen(req, timeout=timeout) as response: return parse_feed(response.read(), source_name, source_url, source_type)

def classify_hotspot(title, content):
    text=f"{title} {content}".lower(); topics=[t for t, words in TOPIC_RULES.items() if any(w.lower() in text for w in words)]; keywords=sorted([w for w in AVIATION_KEYWORDS if w.lower() in text], key=lambda x:(-len(x),x)); relevance=min(.98,.16+min(.56,len(keywords)*.08)+(.16 if topics else 0)); trend=min(.95,.30+len(topics)*.11+len(keywords)*.035); risk="high" if any(w in text for w in ("\u5ef6\u8bef","\u53d6\u6d88","\u4e8b\u6545","\u6295\u8bc9")) else "medium" if any(w in text for w in ("\u4ef7\u683c","\u7968\u4ef7","\u4fc3\u9500","\u589e\u957f","\u70ed\u70b9")) else "low"; relevant=relevance>=.52
    return {"is_relevant":relevant,"reason":"识别到航空出行、航线、产品或客群需求信号" if relevant else "未识别到稳定航空营销业务信号","relevance_score":round(relevance,3),"trend_score":round(trend,3),"risk_level":risk,"ontology_eligible":relevant,"opportunity_eligible":relevant and trend>=.55,"topics":topics[:6],"keywords":keywords[:16],"summary":clean_text(content or title)[:420],"sentiment":"negative" if risk=="high" else "neutral"}

def heuristic_candidates(item, decision):
    text=f"{item.get('title','')} {item.get('content','')}"; source=item.get("canonical_url") or item.get("source_url") or item.get("source_name"); cities=[c for c in ("上海","北京","广州","深圳","成都","昆明","三亚","西安","东京","新加坡") if c in text]; entities=[]
    if decision["is_relevant"]: entities.append({"external_id":f"market-signal-{item['id']}","entity_type":"MarketSignal","label":item["title"],"attributes":{"topics":decision["topics"],"trend_score":decision["trend_score"],"risk_level":decision["risk_level"]},"confidence":decision["relevance_score"],"evidence":decision["summary"] or item["title"],"source_refs":[source]})
    for city in cities: entities.append({"external_id":f"market-{city}","entity_type":"Market","label":f"{city}出行市场","attributes":{"city":city},"confidence":min(.94,decision["relevance_score"]+.1),"evidence":item["title"],"source_refs":[source]})
    relations=[]
    if entities and len(entities)>1:
        for target in entities[1:]: relations.append({"source_external_id":entities[0]["external_id"],"relation_type":"concerns_market","target_external_id":target["external_id"],"evidence":item["title"],"confidence":decision["relevance_score"]})
    opportunity=None
    if decision["opportunity_eligible"]: opportunity={"title":item["title"][:110]+"营销机会","market_scope":"国际及地区" if any(c in cities for c in ("东京","新加坡")) else "国内","route":"-".join(cities[:2]) if len(cities)>=2 else "","reason":decision["summary"][:220]+" 建议结合航线经营指标、聚合客群和可售产品包进行人工评估","score":round((decision["relevance_score"]*.6+decision["trend_score"]*.4)*100)}
    return {"entities":entities,"relations":relations,"opportunity_candidate":opportunity}

def provider_config(session, tenant_id):
    provider=session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id==tenant_id,ModelProviderRecord.enabled.is_(True)).order_by(ModelProviderRecord.is_default.desc(),ModelProviderRecord.id))
    if provider is None: return None
    return provider, LLMConfig(provider_type=provider.provider_type,base_url=provider.base_url,model_name=provider.model_name,api_key=SecretCipher().decrypt(provider.encrypted_api_key),timeout_seconds=provider.timeout_seconds,temperature=provider.temperature,max_tokens=provider.max_tokens)

def bounded_score(value, fallback=0.0):
    try: return round(max(0,min(1,float(value))),3)
    except (TypeError,ValueError): return fallback

def sanitize_entities(items):
    result=[]; allowed=object_type_ids()
    for x in items:
        if not isinstance(x,dict) or str(x.get("entity_type")) not in allowed: continue
        result.append({"external_id":clean_text(x.get("external_id"))[:240],"entity_type":str(x["entity_type"]),"label":clean_text(x.get("label"))[:240],"attributes":x.get("attributes") if isinstance(x.get("attributes"),dict) else {},"confidence":bounded_score(x.get("confidence")),"evidence":clean_text(x.get("evidence"))[:1200],"source_refs":[clean_text(v)[:500] for v in x.get("source_refs",[]) if v][:8]})
    return result[:40]

def sanitize_relations(items):
    result=[]; allowed=relation_type_ids()
    for x in items:
        if not isinstance(x,dict) or str(x.get("relation_type")) not in allowed: continue
        result.append({"source_external_id":clean_text(x.get("source_external_id"))[:240],"relation_type":str(x["relation_type"]),"target_external_id":clean_text(x.get("target_external_id"))[:240],"evidence":clean_text(x.get("evidence"))[:1200],"confidence":bounded_score(x.get("confidence"))})
    return result[:80]

def process_hotspot(session, context, record):
    trace=[]; emit=lambda event,**payload: trace.append({"event":event,"payload":payload,"timestamp":utc_now().isoformat()}); harness=UnifiedHarness(emit=lambda event,payload: trace.append({"event":event,"payload":payload,"timestamp":utc_now().isoformat()})); contract=agent_contract("opportunity-insight"); harness.load_context(HarnessContext(context.tenant_id,f"HOT-{record.id}","market-hotspot-processing",contract["reads"],contract["writes"],contract["functions"])); item={"id":record.id,"title":record.title,"content":record.content,"summary":record.summary,"canonical_url":record.canonical_url,"source_url":record.source_url,"source_name":record.source_name}; harness.emit("hotspot/normalized",title=record.title,source=record.source_name); decision=classify_hotspot(record.title,record.content); harness.emit("hotspot/classified",relevance_score=decision["relevance_score"],trend_score=decision["trend_score"],topics=decision["topics"]); candidates=heuristic_candidates(item,decision); configured=provider_config(session,context.tenant_id)
    if configured and record.content:
        _, config=configured
        try:
            model=harness.generate_json(config,"你是东航市场热点处理智能体。只输出JSON；新闻是证据，不要把不能映射到航空业务对象的内容写入本体。",json.dumps({"hotspot":item,"heuristic":{"decision":decision,"candidates":candidates}},ensure_ascii=False)); md=model.get("hotspot_decision") if isinstance(model,dict) else None
            if isinstance(md,dict): decision.update({k:md[k] for k in ("is_relevant","reason","relevance_score","trend_score","risk_level","summary","topics","keywords") if k in md})
            if isinstance(model.get("entities"),list): candidates["entities"]=sanitize_entities(model["entities"])
            if isinstance(model.get("relations"),list): candidates["relations"]=sanitize_relations(model["relations"])
            if isinstance(model.get("opportunity_candidate"),dict): candidates["opportunity_candidate"]={k:model["opportunity_candidate"].get(k) for k in ("title","market_scope","route","reason","score")}
        except Exception as exc: harness.emit("hotspot/model-fallback",error_type=type(exc).__name__)
    decision["relevance_score"]=bounded_score(decision.get("relevance_score")); decision["trend_score"]=bounded_score(decision.get("trend_score")); decision["topics"]=[str(x)[:80] for x in decision.get("topics",[]) if x][:8]; decision["keywords"]=[str(x)[:80] for x in decision.get("keywords",[]) if x][:24]; decision["is_relevant"]=bool(decision.get("is_relevant")); gate=_admit_candidates(candidates,decision,record); result={"decision":decision,"candidates":candidates,"ontology_gate":gate}; record.agent_run_id=f"HOT-{record.id}"; record.summary=decision.get("summary",""); record.topics_json=json.dumps(decision.get("topics",[]),ensure_ascii=False); record.keywords_json=json.dumps(decision.get("keywords",[]),ensure_ascii=False); record.entities_json=json.dumps(candidates.get("entities",[]),ensure_ascii=False); record.decision_json=json.dumps(result,ensure_ascii=False); record.trace_json=json.dumps(trace,ensure_ascii=False); record.relevance_score=decision["relevance_score"]; record.trend_score=decision["trend_score"]; record.ontology_status="awaiting_confirmation" if gate["eligible"] else "knowledge_only"; record.status="processed"; return result

def _admit_candidates(candidates, decision, record):
    accepted=[]; rejected=[]; allowed=object_type_ids()
    for x in candidates.get("entities",[]):
        if isinstance(x,dict) and x.get("entity_type") in allowed and x.get("entity_type") not in {"KnowledgeDocument","KnowledgeChunk"} and x.get("external_id") and x.get("label") and x.get("evidence") and bounded_score(x.get("confidence"))>=.65: accepted.append(x)
        else: rejected.append({"kind":"entity","label":x.get("label","") if isinstance(x,dict) else "","reason":"对象类型、标识、证据或置信度不满足准入条件"})
    ids={str(x["external_id"]) for x in accepted}; relations=[]
    for x in candidates.get("relations",[]):
        if not isinstance(x,dict) or str(x.get("source_external_id")) not in ids or str(x.get("target_external_id")) not in ids: rejected.append({"kind":"relation","reason":"关系端点未通过实体准入"}); continue
        error=validate_relation_endpoints(x.get("relation_type"),next(i["entity_type"] for i in accepted if i["external_id"]==x["source_external_id"]),next(i["entity_type"] for i in accepted if i["external_id"]==x["target_external_id"]))
        if error or not x.get("evidence") or bounded_score(x.get("confidence"))<.65: rejected.append({"kind":"relation","reason":error or "关系证据或置信度不足"})
        else: relations.append(x)
    eligible=bool(decision.get("is_relevant") and accepted); return {"eligible":eligible,"decision":"update" if eligible else "knowledge_only","reason":decision.get("reason",""),"matched_entity_types":sorted({x["entity_type"] for x in accepted}) if eligible else [],"confidence":decision.get("relevance_score",0),"review_required":eligible,"accepted_entity_count":len(accepted) if eligible else 0,"accepted_relation_count":len(relations) if eligible else 0,"rejected_items":rejected}

def confirm_hotspot_ontology(session,context,record,reviewer,decision,note=""):
    payload=json.loads(record.decision_json or "{}");
    if record.ontology_status!="awaiting_confirmation": raise ValueError("该热点当前不等待本体确认")
    if decision=="reject": record.ontology_status="rejected"; payload["human_review"]={"decision":decision,"reviewer":reviewer,"note":note}; record.decision_json=json.dumps(payload,ensure_ascii=False); session.commit(); return payload
    records={}; source=f"market-hotspot:{record.id}"
    for x in payload.get("candidates",{}).get("entities",[]):
        if x.get("entity_type") not in object_type_ids() or not x.get("external_id") or bounded_score(x.get("confidence"))<.65: continue
        entity=session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id==context.tenant_id,OntologyEntityRecord.external_id==x["external_id"])) or OntologyEntityRecord(tenant_id=context.tenant_id,external_id=x["external_id"]); session.add(entity) if entity.id is None else None; entity.entity_type=x["entity_type"]; entity.label=x["label"]; entity.attributes_json=json.dumps(x.get("attributes") or {},ensure_ascii=False); entity.source=source; entity.confidence=bounded_score(x.get("confidence")); session.flush(); records[x["external_id"]]=entity
    for x in payload.get("candidates",{}).get("relations",[]):
        left,right=records.get(x.get("source_external_id")),records.get(x.get("target_external_id"));
        if not left or not right: continue
        if not validate_relation_endpoints(x.get("relation_type"),left.entity_type,right.entity_type) and session.scalar(select(OntologyRelationRecord.id).where(OntologyRelationRecord.tenant_id==context.tenant_id,OntologyRelationRecord.source_entity_id==left.id,OntologyRelationRecord.relation_type==x["relation_type"],OntologyRelationRecord.target_entity_id==right.id)) is None: session.add(OntologyRelationRecord(tenant_id=context.tenant_id,source_entity_id=left.id,relation_type=x["relation_type"],target_entity_id=right.id,evidence=x.get("evidence",""),source=source,confidence=bounded_score(x.get("confidence"))))
    record.ontology_status="updated"; payload["human_review"]={"decision":decision,"reviewer":reviewer,"note":note,"updated_entity_count":len(records)}; record.decision_json=json.dumps(payload,ensure_ascii=False); session.commit(); return payload

def create_opportunity_from_hotspot(session,context,record,owner="",estimated_audience=0,estimated_revenue_yuan=0):
    payload=json.loads(record.decision_json or "{}"); candidate=payload.get("candidates",{}).get("opportunity_candidate")
    if record.ontology_status!="updated" or not candidate: raise ValueError("热点必须先通过本体确认，且存在机会候选")
    existing=session.scalar(select(OpportunityRecord).where(OpportunityRecord.tenant_id==context.tenant_id,OpportunityRecord.signal_summary==record.title));
    if existing: return existing
    opportunity=OpportunityRecord(tenant_id=context.tenant_id,id=f"OPP-HOT-{record.id[-12:]}",name=candidate.get("title") or record.title,market_scope=candidate.get("market_scope") or record.region or "国内",route=candidate.get("route") or "",signal_summary=record.title,status="待评估",score=int(candidate.get("score") or record.relevance_score*100),estimated_audience=estimated_audience,estimated_revenue_yuan=estimated_revenue_yuan,owner=owner); session.add(opportunity); session.commit(); return opportunity

def hotspot_view(record):
    payload=json.loads(record.decision_json or "{}"); return {"id":record.id,"source_name":record.source_name,"source_type":record.source_type,"source_url":record.source_url,"external_id":record.external_id,"canonical_url":record.canonical_url,"title":record.title,"content":record.content,"summary":record.summary,"published_at":record.published_at,"collected_at":record.collected_at,"language":record.language,"region":record.region,"topics":json.loads(record.topics_json or "[]"),"keywords":json.loads(record.keywords_json or "[]"),"entities":json.loads(record.entities_json or "[]"),"decision":payload,"trace":json.loads(record.trace_json or "[]"),"relevance_score":record.relevance_score,"trend_score":record.trend_score,"sentiment":record.sentiment,"status":record.status,"ontology_status":record.ontology_status,"agent_run_id":record.agent_run_id,"created_at":record.created_at,"updated_at":record.updated_at}

def collect_source(name,url,source_type,max_items=30):
    items=fetch_feed(name,url,source_type)[:max_items]; return items,[{"name":name,"url":url,"status":"healthy","item_count":len(items),"checked_at":utc_now().isoformat()}]

def ingest_hotspots(session,context,rows,process_with_agent=True):
    created=[]; duplicates=failed=0
    for row in rows:
        normalized=normalize_item(row,row.get("source_name","外部数据源"),row.get("source_type","api"),row.get("source_url",""))
        if not normalized["title"]: failed+=1; continue
        if session.scalar(select(MarketHotspotRecord).where(MarketHotspotRecord.tenant_id==context.tenant_id,MarketHotspotRecord.dedupe_key==normalized["dedupe_key"])): duplicates+=1; continue
        record=MarketHotspotRecord(id=f"HS-{hashlib.sha1((normalized['dedupe_key']+str(utc_now())).encode()).hexdigest()[:14].upper()}",tenant_id=context.tenant_id,**normalized); session.add(record); session.flush(); created.append(record)
    session.commit()
    if process_with_agent:
        for record in created: process_hotspot(session,context,record)
        session.commit()
    return {"created":len(created),"duplicates":duplicates,"failed":failed,"hotspots":[hotspot_view(x) for x in created],"source_health":[]}

def delete_hotspot(session,context,record):
    source=f"market-hotspot:{record.id}"; owned=list(session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id==context.tenant_id,OntologyEntityRecord.source==source))); ids=[x.id for x in owned]
    if ids: session.query(OntologyRelationRecord).filter(OntologyRelationRecord.tenant_id==context.tenant_id,(OntologyRelationRecord.source_entity_id.in_(ids))|(OntologyRelationRecord.target_entity_id.in_(ids))).delete(synchronize_session=False); [session.delete(x) for x in owned]
    session.delete(record); session.commit()
