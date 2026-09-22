"""Read-oriented local MCP server used by AgentScope 2.0.8 agents.

The server is intentionally small and stateless at the database level. It
reads only the tenant supplied by the parent process and never exposes API
keys or write operations. Mutations remain in the FastAPI service where the
normal permission, approval and audit checks apply.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


DB_PATH = Path(os.environ.get("CEAIR_MARKETING_DB", "ceair-marketing.db")).resolve()
TENANT_ID = int(os.environ.get("CEAIR_TENANT_ID", "0"))
PROFILE = ""


def db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def envelope(items: list[dict[str, Any]], *, key: str) -> dict[str, Any]:
    return {"count": len(items), key: items, "tenant_id": TENANT_ID, "profile": PROFILE, "sources": []}


def add_source(payload: dict[str, Any], source_type: str, source_id: str, title: str, excerpt: str) -> None:
    payload["sources"].append({"type": source_type, "id": source_id, "title": title, "excerpt": excerpt[:220]})


server = FastMCP(
    name="ceair-marketing-" + (PROFILE or "agent"),
    instructions="东航智能营销平台只读业务查询 MCP。返回租户范围内的知识、本体、活动和处理任务事实。",
)


@server.tool()
def search_marketing_knowledge(query: str = "", limit: int = 8) -> dict[str, Any]:
    """Search tenant knowledge chunks by simple lexical matching."""
    terms = [part.lower() for part in query.replace("，", " ").replace("。", " ").split() if len(part) > 1]
    rows = db_rows(
        "SELECT id, external_id, document_id, content FROM knowledge_chunks "
        "WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 500",
        (TENANT_ID,),
    )
    matched = [row for row in rows if not terms or any(term in (row.get("content") or "").lower() for term in terms)][: max(1, min(limit, 20))]
    documents = {row["id"]: row for row in db_rows("SELECT id, title FROM knowledge_documents WHERE tenant_id = ?", (TENANT_ID,))}
    items = []
    result = envelope(items, key="items")
    for row in matched:
        title = documents.get(row.get("document_id"), {}).get("title") or row.get("external_id")
        excerpt = str(row.get("content") or "")[:420]
        item = {"id": row.get("external_id"), "title": title, "excerpt": excerpt}
        items.append(item)
        add_source(result, "knowledge", str(row.get("external_id")), str(title), excerpt)
    return result


@server.tool()
def query_marketing_ontology(query: str = "", limit: int = 12) -> dict[str, Any]:
    """Find tenant ontology entities and connected relation facts."""
    terms = [part.lower() for part in query.replace("，", " ").split() if len(part) > 1]
    entities = db_rows(
        "SELECT id, external_id, entity_type, label, confidence, attributes_json "
        "FROM ontology_entities WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 500",
        (TENANT_ID,),
    )
    matched = [row for row in entities if not terms or any(term in ((row.get("label") or "") + " " + (row.get("entity_type") or "")).lower() for term in terms)][: max(1, min(limit, 30))]
    ids = {row["id"] for row in matched}
    relations = db_rows(
        "SELECT source_entity_id, relation_type, target_entity_id, evidence, confidence "
        "FROM ontology_relations WHERE tenant_id = ?", (TENANT_ID,),
    )
    result = envelope([], key="entities")
    for row in matched:
        item = {"id": row["external_id"], "type": row["entity_type"], "label": row["label"], "confidence": row["confidence"]}
        result["entities"].append(item)
        add_source(result, "ontology", row["external_id"], row["label"], row["entity_type"])
    result["relations"] = [row for row in relations if row["source_entity_id"] in ids or row["target_entity_id"] in ids][:40]
    return result


@server.tool()
def list_available_products(query: str = "", limit: int = 12) -> dict[str, Any]:
    """List product-like ontology instances available to the tenant."""
    types = ("Product", "ProductPackage", "ProductGroup", "ProductLabel", "Fare", "AncillaryProduct", "Coupon", "MemberBenefit", "IntermodalProduct")
    marks = ",".join("?" for _ in types)
    terms = [part.lower() for part in query.replace("，", " ").split() if len(part) > 1]
    rows = db_rows(
        f"SELECT external_id, entity_type, label, confidence FROM ontology_entities WHERE tenant_id = ? AND entity_type IN ({marks}) ORDER BY updated_at DESC LIMIT 100",
        (TENANT_ID, *types),
    )
    matched = [row for row in rows if not terms or any(term in (row.get("label") or "").lower() for term in terms)][: max(1, min(limit, 30))]
    result = envelope([], key="items")
    for row in matched:
        item = {"id": row["external_id"], "type": row["entity_type"], "label": row["label"], "confidence": row["confidence"]}
        result["items"].append(item)
        add_source(result, "product", row["external_id"], row["label"], row["entity_type"])
    return result


@server.tool()
def inspect_campaign(campaign_id: str = "") -> dict[str, Any]:
    """Inspect one tenant campaign and its current lifecycle state."""
    sql = "SELECT id, name, stage, status, audience_size, product_package, budget_yuan, roi_target FROM campaigns WHERE tenant_id = ?"
    params: tuple[Any, ...] = (TENANT_ID,)
    if campaign_id:
        sql += " AND id = ?"
        params += (campaign_id,)
    sql += " ORDER BY id LIMIT 1"
    rows = db_rows(sql, params)
    result = envelope([], key="campaign")
    result["campaign"] = rows[0] if rows else None
    if rows:
        add_source(result, "campaign", rows[0]["id"], rows[0]["name"], f"{rows[0]['stage']} / {rows[0]['status']}")
    return result


@server.tool()
def inspect_data_pipeline(job_id: str = "") -> dict[str, Any]:
    """Inspect the most recent tenant data processing job."""
    sql = "SELECT id, file_name, status, current_stage, total_entities, total_relations, result_json FROM data_pipeline_jobs WHERE tenant_id = ?"
    params: tuple[Any, ...] = (TENANT_ID,)
    if job_id:
        sql += " AND id = ?"
        params += (job_id,)
    sql += " ORDER BY created_at DESC LIMIT 1"
    rows = db_rows(sql, params)
    result = envelope([], key="job")
    if not rows:
        result["job"] = None
        return result
    row = rows[0]
    raw = json.loads(row.get("result_json") or "{}")
    result["job"] = {key: row.get(key) for key in ("id", "file_name", "status", "current_stage", "total_entities", "total_relations")}
    result["job"]["events"] = (raw.get("events") or [])[-12:]
    add_source(result, "data-pipeline", row["id"], row["file_name"], f"{row['status']} / {row['current_stage']}")
    return result


@server.tool()
def get_ontology_schema(query: str = "") -> dict[str, Any]:
    """Return the registered semantic model summary for data processing."""
    from app.ontology.semantic_model import semantic_model

    model = semantic_model()
    terms = [part.lower() for part in query.split() if len(part) > 1]
    objects = [item for item in model["object_types"] if not terms or any(term in json.dumps(item, ensure_ascii=False).lower() for term in terms)]
    return {
        "version": model["version"],
        "object_types": objects[:50],
        "relation_types": model["relation_types"][:100],
        "principles": model["principles"],
        "sources": [{"type": "semantic-model", "id": model["version"], "title": "东航营销本体语义模型", "excerpt": "注册对象、关系和建模原则"}],
    }


def main() -> None:
    global PROFILE, server
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    PROFILE = args.profile
    server = FastMCP(
        name="ceair-marketing-" + PROFILE,
        instructions="东航智能营销平台只读业务查询 MCP。当前租户=" + str(TENANT_ID),
    )
    # Decorators register on the module-level server at import time. The
    # runtime server is rebuilt above, so re-register the functions.
    for function in (search_marketing_knowledge, query_marketing_ontology, list_available_products, inspect_campaign, inspect_data_pipeline, get_ontology_schema):
        server.add_tool(function)
    server.run("stdio")


if __name__ == "__main__":
    main()
