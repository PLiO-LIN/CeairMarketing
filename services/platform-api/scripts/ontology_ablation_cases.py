"""Perturbation fixture for the ontology ablation experiment.

This module holds cases only. Every accept/reject verdict in the experiment comes
from the production gate functions, never from rules re-implemented here.
``view`` names the observable read off the gate output that counts as blocked.
"""
from __future__ import annotations

from typing import Any

ROUTES = [
    {"org": "SHA", "org_name": "上海虹桥", "dest": "SYX", "dest_name": "三亚", "flight_no": "MU5101"},
    {"org": "SHA", "org_name": "上海浦东", "dest": "CKG", "dest_name": "重庆", "flight_no": "MU5303"},
    {"org": "PKX", "org_name": "北京大兴", "dest": "SHA", "dest_name": "上海虹桥", "flight_no": "MU5202"},
    {"org": "CAN", "org_name": "广州白云", "dest": "SYX", "dest_name": "三亚", "flight_no": "MU5721"},
]

FAMILIES = {
    "A": "关系方向与端点类型合法性",
    "P1": "删除必要关系",
    "P2": "产品有效期与审批门禁",
    "P3": "关系方向反转",
    "P4": "缺失来源证据",
    "P5": "置信度阈值边界",
    "P6": "未注册类型与非法端点",
}


def build_snapshot() -> dict[str, Any]:
    """Scraper-shaped payload covering four MU routes with a full fare path."""
    product_group = {"id": "G1", "groupName": "家庭出行运价包", "productCode": "P1,P2", "process": "1"}
    labels = [
        {"id": "L1", "labelName": "早鸟优惠", "labelNotice": "提前7天购买", "labelDescriptionii": "行前锁定价格", "subLabel1": "价格", "subLabel2": "", "subLabel3": ""},
        {"id": "L2", "labelName": "行李权益", "labelNotice": "20kg 免费托运", "labelDescriptionii": "家庭出行", "subLabel1": "服务", "subLabel2": "", "subLabel3": ""},
    ]
    products = [
        {"productCode": "P1", "promotionCode": "早鸟家庭价", "beneficiary": "实名旅客", "buyTicketMember": "1", "takeType": "电子", "cabinLabelInfo": [{"labelName": "早鸟优惠"}]},
        {"productCode": "P2", "promotionCode": "标准价", "beneficiary": "实名旅客", "buyTicketMember": "0", "takeType": "电子", "cabinLabelInfo": [{"labelName": "行李权益"}]},
    ]
    x_products = {
        "X1": {"productName": "额外20kg行李", "productCode": "XB1", "xProductType": "baggage", "resourceCode": "R-XB1", "accountPrice": 60, "salePrice": 80, "productValue": "20kg"},
        "X2": {"productName": "前排优选座位", "productCode": "SE1", "xProductType": "seat", "resourceCode": "R-SE1", "accountPrice": 40, "salePrice": 60, "productValue": "前三排"},
    }
    flight_items = []
    for index, route in enumerate(ROUTES):
        flight_items.append({
            "cabinInfoDescs": [
                {"ccode": "Y", "cabinLevelName": "经济舱", "ctype": "E", "muCabinLevel": "1",
                 "fareInfoDescList": [
                     {"productCode": "P1", "paxType": "ADT", "totalPrice": 680 + index * 40, "lprice": 580, "taxPrice": 100, "rescheduleTotalPrice": 120, "priceSource": "engine", "brandLevel": "ECONOMY", "xProductIds": ["X1"]},
                     {"productCode": "P2", "paxType": "ADT", "totalPrice": 840 + index * 40, "lprice": 740, "taxPrice": 100, "rescheduleTotalPrice": 160, "priceSource": "engine", "brandLevel": "ECONOMY", "xProductIds": ["X1", "X2"]},
                 ]},
                {"ccode": "C", "cabinLevelName": "公务舱", "ctype": "B", "muCabinLevel": "2",
                 "fareInfoDescList": [{"productCode": "P2", "paxType": "ADT", "totalPrice": 2260 + index * 60, "lprice": 2100, "taxPrice": 160, "rescheduleTotalPrice": 300, "priceSource": "engine", "brandLevel": "BUSINESS", "xProductIds": ["X2"]}]},
            ],
            "flightInfos": [{
                "flightSegments": [{"flightInfoId": f"FI{index}", "flightNo": route["flight_no"], "orgCode": route["org"], "orgName": route["org_name"], "destCode": route["dest"], "destName": route["dest_name"], "airlineCode": "MU"}],
                "tripLabelIds": ["L1", "L2"],
            }],
        })
    return {"data": {"productLabelInfoList": labels, "productGroupInfoList": [product_group], "productInfos": products, "xProductMap": x_products, "flightItems": flight_items}}


def _clone(candidates: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(candidates)


def _drop_relation(candidates: dict[str, Any], relation_type: str) -> dict[str, Any]:
    data = _clone(candidates)
    data["relations"] = [item for item in data["relations"] if item["relation_type"] != relation_type]
    return data


def _drop_one_relation(candidates: dict[str, Any], relation_type: str) -> dict[str, Any]:
    data = _clone(candidates)
    for position, item in enumerate(data["relations"]):
        if item["relation_type"] == relation_type:
            del data["relations"][position]
            break
    return data


def _reverse_relation(candidates: dict[str, Any], relation_type: str) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["relations"]:
        if item["relation_type"] == relation_type:
            item["source_external_id"], item["target_external_id"] = item["target_external_id"], item["source_external_id"]
    return data


def _strip_relation_evidence(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["relations"]:
        item["evidence"] = ""
        item["source_refs"] = []
    return data


def _strip_entity_evidence(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["entities"]:
        item["evidence"] = ""
        item["source_refs"] = []
    return data


def _set_entity_confidence(candidates: dict[str, Any], value: float) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["entities"]:
        item["confidence"] = value
    return data


def _set_relation_confidence(candidates: dict[str, Any], value: float) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["relations"]:
        item["confidence"] = value
    return data


def _fake_entity_type(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["entities"]:
        if item["entity_type"] == "Fare":
            item["entity_type"] = "FakeFareClass"
    return data


def _knowledge_type(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["entities"]:
        if item["entity_type"] == "Fare":
            item["entity_type"] = "KnowledgeDocument"
    return data


def _illegal_relation_endpoint(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    for item in data["relations"]:
        if item["relation_type"] == "belongs_to_product_group":
            item["target_external_id"] = "route-not-a-group"
    return data


def _gate_refused(candidates: dict[str, Any]) -> dict[str, Any]:
    data = _clone(candidates)
    data["ontology_gate"] = {**data["ontology_gate"], "eligible": False, "decision": "knowledge_only"}
    return data


def cases(base: dict[str, Any]) -> list[dict[str, Any]]:
    """Tier B matrix. ``target`` is the production function whose output is read."""
    return [
        {"id": "B0", "family": "B0", "name": "完整语义图基线", "target": "apply_ontology_admission", "view": "gate", "payload": base, "must_block": False},
        {"id": "P1a", "family": "P1", "name": "删除全部舱位到运价关系", "target": "apply_ontology_admission", "view": "path", "payload": _drop_relation(base, "has_fare"), "must_block": True},
        {"id": "P1b", "family": "P1", "name": "删除全部运价到产品关系", "target": "apply_ontology_admission", "view": "path", "payload": _drop_relation(base, "uses_product"), "must_block": True},
        {"id": "P1c", "family": "P1", "name": "仅删除一条舱位到运价关系", "target": "apply_ontology_admission", "view": "gate", "payload": _drop_one_relation(base, "has_fare"), "must_block": False},
        {"id": "P3a", "family": "P3", "name": "航班到航线方向反转", "target": "validate_relation_endpoints", "view": "relation:operates_on", "payload": _reverse_relation(base, "operates_on"), "must_block": True},
        {"id": "P3b", "family": "P3", "name": "舱位到运价方向反转", "target": "validate_relation_endpoints", "view": "relation:has_fare", "payload": _reverse_relation(base, "has_fare"), "must_block": True},
        {"id": "P3c", "family": "P3", "name": "运价到产品方向反转", "target": "validate_relation_endpoints", "view": "relation:uses_product", "payload": _reverse_relation(base, "uses_product"), "must_block": True},
        {"id": "P3d", "family": "P3", "name": "产品到产品组方向反转", "target": "validate_relation_endpoints", "view": "relation:belongs_to_product_group", "payload": _reverse_relation(base, "belongs_to_product_group"), "must_block": True},
        {"id": "P4a", "family": "P4", "name": "关系全部缺失来源证据", "target": "apply_ontology_admission", "view": "relation_any", "payload": _strip_relation_evidence(base), "must_block": True},
        {"id": "P4b", "family": "P4", "name": "实体全部缺失来源证据", "target": "apply_ontology_admission", "view": "gate", "payload": _strip_entity_evidence(base), "must_block": True},
        {"id": "P5a", "family": "P5", "name": "实体置信度低于阈值 0.64", "target": "apply_ontology_admission", "view": "gate", "payload": _set_entity_confidence(base, 0.64), "must_block": True},
        {"id": "P5b", "family": "P5", "name": "实体置信度等于阈值 0.65", "target": "apply_ontology_admission", "view": "gate", "payload": _set_entity_confidence(base, 0.65), "must_block": False},
        {"id": "P5c", "family": "P5", "name": "关系置信度低于阈值 0.64", "target": "apply_ontology_admission", "view": "relation_any", "payload": _set_relation_confidence(base, 0.64), "must_block": True},
        {"id": "P5d", "family": "P5", "name": "关系置信度等于阈值 0.65", "target": "apply_ontology_admission", "view": "relation_any", "payload": _set_relation_confidence(base, 0.65), "must_block": False},
        {"id": "P6a", "family": "P6", "name": "未注册对象类型 FakeFareClass", "target": "object_type_ids", "view": "path", "payload": _fake_entity_type(base), "must_block": True},
        {"id": "P6b", "family": "P6", "name": "运价降级为知识文档类型", "target": "normalize_ontology_decision", "view": "path", "payload": _knowledge_type(base), "must_block": True},
        {"id": "P6c", "family": "P6", "name": "关系端点指向非法对象", "target": "validate_relation_endpoints", "view": "relation:belongs_to_product_group", "payload": _illegal_relation_endpoint(base), "must_block": True},
        {"id": "P6d", "family": "P6", "name": "模型门禁拒绝写入本体", "target": "normalize_ontology_decision", "view": "gate", "payload": _gate_refused(base), "must_block": True},
    ]


def registry_cases(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Tier A: every registered relation with declared endpoint types, forward and swapped.

    The expected verdict is read off the declared domain and range, so a relation whose
    endpoint types overlap is not wrongly counted as a caught violation.
    """
    out = []
    for definition in model["relation_types"]:
        from_types = [str(item) for item in definition.get("from_types") or []]
        to_types = [str(item) for item in definition.get("to_types") or []]
        if not from_types or not to_types:
            continue
        out.append({"id": f"A-{definition['id']}-ok", "family": "A", "name": f"{definition['id']} 正向合法", "relation": definition["id"], "source_type": from_types[0], "target_type": to_types[0], "must_block": False})
        swapped_illegal = to_types[0] not in from_types or from_types[0] not in to_types
        out.append({"id": f"A-{definition['id']}-rev", "family": "A", "name": f"{definition['id']} 反向越界", "relation": definition["id"], "source_type": to_types[0], "target_type": from_types[0], "must_block": swapped_illegal})
    return out


def readiness_cases() -> list[dict[str, Any]]:
    """Tier C cases run against campaign_readiness on a freshly built in-memory database."""
    return [
        {"id": "C0", "family": "C", "name": "五门禁全通过基线", "must_block": False, "check": None, "mutate": None},
        {"id": "P2a", "family": "P2", "name": "产品包有效期已过", "must_block": True, "check": "product", "mutate": "expire_product"},
        {"id": "P2b", "family": "P2", "name": "产品包未审批", "must_block": True, "check": "product", "mutate": "draft_product"},
        {"id": "P2c", "family": "P2", "name": "客群快照未冻结", "must_block": True, "check": "audience", "mutate": "unfrozen_snapshot"},
        {"id": "P2d", "family": "P2", "name": "渠道缺少已审核内容", "must_block": True, "check": "channels", "mutate": "missing_channel_content"},
        {"id": "P2e", "family": "P2", "name": "活动预算为零", "must_block": True, "check": "budget", "mutate": "zero_budget"},
        {"id": "P2f", "family": "P2", "name": "内容未审核", "must_block": True, "check": "content", "mutate": "draft_content"},
    ]
