"""Controlled bridge to existing platform APIs. Mutations are reviewable tasks."""
from __future__ import annotations

import json
import re
from collections import Counter
from uuid import uuid4
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from .auth import create_token
from .db_models import AssistantTaskRecord, CampaignRecord, OpportunityRecord, AudiencePackageRecord, ProductPackageRecord, ContentAssetRecord, ExecutionBatchRecord, ChannelTaskRecord
from .assistant_store import task_view, remember
from .agents.agentscope_runtime import make_tool, text_tool_result

# Concrete paths are matched against the platform's registered operations.
BUSINESS_PREFIXES = (
    "/api/campaigns", "/api/approvals", "/api/execution-batches", "/api/channel-tasks",
    "/api/product-packages", "/api/product-catalog", "/api/content-assets", "/api/opportunities",
    "/api/opportunity-insight", "/api/persona-", "/api/audience-", "/api/market-hotspots",
    "/api/agent-runs", "/api/agent-domains", "/api/ontology", "/api/graph", "/api/knowledge",
    "/api/data-pipelines", "/api/data-sources", "/api/integrations/profile", "/api/integrations/products",
    "/api/model-providers", "/api/ndc/sync-flight-products",
    "/api/platform/tenants", "/api/platform/users", "/api/imports",
    "/api/audit-logs", "/api/agent-evaluations",
    "/api/mock/flight-operations", "/api/mock/profile-summary", "/api/mock/market-signals",
    "/api/assistant/tasks", "/api/assistant/conversations", "/api/assistant/memories",
)


def operation(method, path):
    from .main import app
    if "?" in path or ".." in path or not any(path.startswith(p) for p in BUSINESS_PREFIXES):
        raise ValueError("此接口不在东东授权业务范围")
    # Model credentials and configuration stay in their dedicated settings UI.
    if method != "GET" and path.startswith(("/api/model-providers", "/api/imports", "/api/assistant")):
        raise ValueError("模型密钥及文件上传请在对应工作台完成")
    for route in app.routes:
        if method in (getattr(route, "methods", None) or []) and hasattr(route, "path_regex") and route.path_regex.fullmatch(path):
            return route
    raise ValueError("平台没有注册此业务接口")


def catalog():
    from .main import app
    schemas = app.openapi()
    operations = []
    for path, methods in schemas["paths"].items():
        if not any(path.startswith(p) for p in BUSINESS_PREFIXES):
            continue
        for method, spec in methods.items():
            if method.upper() not in {"GET", "POST", "PUT", "DELETE"} or method != "get" and path.startswith(("/api/model-providers", "/api/imports", "/api/assistant")):
                continue
            body = spec.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            ref = body.get("$ref", "").split("/")[-1]
            schema = schemas["components"]["schemas"].get(ref, body)
            operations.append({"method": method.upper(), "path": path, "name": spec.get("summary"), "parameters": [p for p in spec.get("parameters", []) if p.get("in") != "header"], "body": schema, "requires_confirmation": method != "get"})
    return operations


async def call_platform(context, method, path, body=None, params=None):
    from .main import app
    operation(method, path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://platform.internal") as client:
        response = await client.request(method, path, json=body, params=params, headers={"Authorization": "Bearer " + create_token(context.user_id), "X-Tenant-ID": str(context.tenant_id)})
    result = response.json() if response.content else {"ok": True}
    if not response.is_success:
        detail = result.get("detail", "业务接口执行失败") if isinstance(result, dict) else "业务接口执行失败"
        raise HTTPException(response.status_code, detail)
    return result


def statistics(session, context, metric):
    tables = {
        "campaigns": (CampaignRecord, "活动阶段分布", "stage"),
        "opportunities": (OpportunityRecord, "机会状态分布", "status"),
        "audiences": (AudiencePackageRecord, "客群包规模", "estimated_size"),
        "products": (ProductPackageRecord, "产品审批状态", "status"),
        "contents": (ContentAssetRecord, "内容渠道分布", "channel"),
        "execution": (ChannelTaskRecord, "渠道送达量", "delivered_count"),
    }
    if metric not in tables:
        raise ValueError("统计指标可选 campaigns/opportunities/audiences/products/contents/execution")
    model, title, field = tables[metric]
    rows = session.scalars(select(model).where(model.tenant_id == context.tenant_id)).all()
    if metric == "audiences":
        labels = [r.name for r in rows]; values = [r.estimated_size for r in rows]; unit = "人"; note = "客群包规模未去重，不能作为独立旅客总数"
    elif metric == "execution":
        counts = Counter()
        for r in rows: counts[r.channel] += r.delivered_count
        labels = list(counts); values = list(counts.values()); unit = "次"; note = "渠道回执送达计数"
    else:
        counts = Counter(getattr(r, field) for r in rows)
        labels = list(counts); values = list(counts.values()); unit = "条"; note = "当前工作区后台业务记录"
    return {"type": "bar", "title": title, "labels": labels, "values": values, "unit": unit, "source": note, "metric": metric, "total": len(rows)}


def build_tools(session, context, conversation_id, widgets, tasks, emit, ui_sink=None):
    def publish(item, kind=None):
        if ui_sink:
            ui_sink(item, kind or item["type"])
    async def platform_api_catalog(keyword: str = ""):
        """Get registered platform operations and body schemas; use before preparing a task."""
        found = [op for op in catalog() if not keyword or keyword.lower() in json.dumps(op, ensure_ascii=False).lower()]
        return text_tool_result({"operations": found[:35], "total": len(found)})

    async def query_platform(path: str, query_json: str = "{}"):
        """Read any authorized platform GET API by concrete path, including tasks, profiles and campaign results."""
        try:
            params = json.loads(query_json)
            if not isinstance(params, dict): raise ValueError("查询参数必须为对象")
            value = await call_platform(context, "GET", path, params=params)
            columns = {
                "/api/campaigns": ("活动记录", [("name", "活动"), ("stage", "阶段"), ("status", "状态")], "campaigns"),
                "/api/opportunities": ("营销机会", [("name", "机会"), ("status", "状态")], "opportunities"),
                "/api/content-assets": ("内容记录", [("name", "内容"), ("channel", "渠道"), ("status", "状态")], "contents"),
                "/api/agent-runs": ("历史智能任务", [("domain_id", "智能域"), ("status", "状态"), ("summary", "摘要")], "campaigns"),
                "/api/data-pipelines": ("数据处理任务", [("file_name", "文件"), ("status", "状态"), ("current_stage", "阶段")], "imports"),
            }
            if path in columns and isinstance(value, list) and not any(w.get("path") == path for w in widgets):
                title, fields, page = columns[path]
                card = {"type": "table", "title": title, "columns": [label for key, label in fields], "rows": [[row.get(key, "") for key, label in fields] for row in value[:8]], "total": len(value), "path": path, "page": page}
                widgets.append(card); publish(card)
            return text_tool_result({"path": path, "count": len(value) if isinstance(value, list) else 1, "data": value[:40] if isinstance(value, list) else value, "sources": [{"type": "platform", "id": path, "title": "平台业务记录", "excerpt": "按当前工作区与用户权限实时查询"}]})
        except (HTTPException, ValueError) as exc:
            return text_tool_result({"ok": False, "error": getattr(exc, "detail", str(exc))})

    async def query_statistics(metric: str = "campaigns"):
        """Calculate trusted BI charts from saved backend records. Metrics: campaigns, opportunities, audiences, products, contents, execution."""
        try:
            chart = statistics(session, context, metric)
            if not any(w.get("metric") == metric for w in widgets):
                widgets.append(chart); publish(chart)
            return text_tool_result(chart)
        except ValueError as exc: return text_tool_result({"ok": False, "error": str(exc)})

    async def prepare_platform_task(method: str, path: str, title: str, body_json: str = "{}"):
        """Prepare a task for explicit UI confirmation; does NOT execute the business operation. Use catalog schemas and concrete IDs."""
        try:
            method = method.upper()
            if method not in {"POST", "PUT", "DELETE"}: raise ValueError("只为业务变更生成确认任务")
            route = operation(method, path)
            if context.role not in {"admin", "manager", "analyst"}: raise ValueError("当前角色无业务写入权限")
            dependencies = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
            if "require_admin" in dependencies and context.role != "admin": raise ValueError("此操作需要租户管理员权限")
            if "require_approver" in dependencies and context.role not in {"admin", "manager"}: raise ValueError("此操作需要审批权限")
            payload = json.loads(body_json)
            if not isinstance(payload, dict): raise ValueError("任务参数必须为对象")
            if re.search(r"api.?key|password|encrypted|access_token", json.dumps(payload), re.I): raise ValueError("任务中不能包含密钥或密码")
            if route.body_field is not None:
                content_type = getattr(route.body_field.field_info, "media_type", "application/json")
                if content_type != "application/json": raise ValueError("上传文件请在数据接入工作台完成")
                _, errors = route.body_field.validate(payload, {}, loc=("body",))
                if errors: raise ValueError("任务参数未通过接口校验，请补充必填字段或修正取值")
            item = AssistantTaskRecord(id="TASK-" + uuid4().hex[:20], tenant_id=context.tenant_id, user_id=context.user_id, conversation_id=conversation_id, title=title[:160], method=method, path=path, payload_json=json.dumps(payload, ensure_ascii=False))
            session.add(item); session.commit(); result = task_view(item); tasks.append(result)
            publish(result, "task")
            emit("assistant/task-prepared", {"task_id": item.id, "title": item.title})
            return text_tool_result(result)
        except (ValueError, json.JSONDecodeError) as exc: return text_tool_result({"ok": False, "error": str(exc)})

    async def remember_preference(content: str):
        """Save a user preference only when the user explicitly asks to remember it. Never store credentials or guessed facts."""
        try:
            result = remember(session, context, content); session.commit()
            return text_tool_result({"remembered": result})
        except ValueError as exc: return text_tool_result({"ok": False, "error": str(exc)})

    async def open_platform_page(page: str):
        """Offer an interactive page card for uploads, credentials and manual forms. Pages: overview, campaigns, opportunities, audiences, products, contents, approvals, execution, feedback, graph, imports, models, tenants, permissions."""
        pages = {"overview": "营销总览", "campaigns": "活动中心", "opportunities": "机会洞察", "audiences": "客群画像", "products": "产品与权益", "contents": "内容工坊", "approvals": "审批与发布", "execution": "执行监控", "feedback": "效果复盘", "graph": "知识中心", "imports": "数据接入", "models": "模型配置", "tenants": "租户与用户", "permissions": "权限与审计"}
        if page not in pages: return text_tool_result({"ok": False, "error": "页面不存在"})
        card = {"type": "navigation", "title": pages[page], "page": page}
        widgets.append(card); publish(card); return text_tool_result(card)

    # These tools either read facts or prepare private tasks/preferences. Actual
    # business mutations only happen through the separately confirmed endpoint.
    return [make_tool(f, read_only=True) for f in (platform_api_catalog, query_platform, query_statistics, open_platform_page)] + [make_tool(f, read_only=False, allow_internal=True) for f in (prepare_platform_task, remember_preference)]
