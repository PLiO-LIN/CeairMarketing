"""A2UI 0.9.1 surfaces, validated against upstream wire schemas.

The agent chooses business tools; trusted tool observations generate declarative
UI. The client only supports the advertised platform catalog, never remote code.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Callable

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

VERSION = "v0.9.1"
CATALOG_ID = "ceair-marketing:assistant-v1"
SPECS = Path(__file__).with_name("a2ui_specs")


def platform_catalog():
    basic = json.loads((SPECS / "basic_catalog.json").read_text(encoding="utf-8"))
    catalog = copy.deepcopy(basic)
    catalog["$id"] = "https://a2ui.org/specification/v0_9/catalog.json"
    catalog["catalogId"] = CATALOG_ID
    catalog["components"] = {k: basic["components"][k] for k in ("Text", "Column", "Row", "Card", "Button", "Divider")}
    catalog["functions"] = {}
    for name, field in (("Chart", "data"), ("DataTable", "data"), ("TaskCard", "task")):
        catalog["components"][name] = {
            "type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "component": {"const": name}, field: {"type": "object", "required": ["path"], "properties": {"path": {"type": "string", "pattern": "^/"}}, "additionalProperties": False}},
            "required": ["id", "component", field],
        }
    catalog["$defs"]["anyComponent"] = {"oneOf": [{"$ref": "#/components/" + k} for k in catalog["components"]]}
    catalog["$defs"]["anyFunction"] = False
    return catalog


CATALOG = platform_catalog()
_schemas = [json.loads((SPECS / n).read_text(encoding="utf-8")) for n in ("server_to_client.json", "common_types.json", "client_to_server.json")]
_schemas[2]["$id"] = "https://a2ui.org/specification/v0_9/client_to_server.json"
_schemas[2]["$schema"] = "https://json-schema.org/draft/2020-12/schema"
_registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in [*_schemas, CATALOG]])
VALIDATOR = Draft202012Validator(_schemas[0], registry=_registry)
ACTION_VALIDATOR = Draft202012Validator(_schemas[2], registry=_registry)


class ReplySurfaces:
    def __init__(self, run_id: str, sink: Callable | None = None):
        self.run_id, self.sink = run_id, sink
        self.messages: list[dict] = []
        self.keys: set[str] = set()

    def add(self, data: dict, kind: str):
        data = json.loads(json.dumps(data, ensure_ascii=False, default=str))
        key = kind + ":" + str(data.get("id") or data.get("metric") or data.get("path") or data.get("page") or len(self.keys))
        if key in self.keys:
            return
        self.keys.add(key)
        sid = self.run_id + "-" + str(len(self.keys))
        components = [{"id": "root", "component": "Column", "children": ["content"]}]
        if kind == "navigation":
            components += [{"id": "content", "component": "Button", "child": "label", "action": {"event": {"name": "open_page", "context": {"page": data["page"]}}}}, {"id": "label", "component": "Text", "text": "打开" + data["title"]}]
        else:
            name = {"bar": "Chart", "table": "DataTable", "task": "TaskCard"}[kind]
            components.append({"id": "content", "component": name, "task" if kind == "task" else "data": {"path": "/content"}})
        batch = [
            {"version": VERSION, "createSurface": {"surfaceId": sid, "catalogId": CATALOG_ID, "theme": {"primaryColor": "#245B9E", "agentDisplayName": "东东"}}},
            {"version": VERSION, "updateDataModel": {"surfaceId": sid, "path": "/", "value": {"content": data}}},
            {"version": VERSION, "updateComponents": {"surfaceId": sid, "components": components}},
        ]
        for message in batch:
            VALIDATOR.validate(message)
            self.messages.append(message)
            if self.sink:
                self.sink(message)
