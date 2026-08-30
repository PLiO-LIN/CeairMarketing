"""Adapter for the China Eastern flight and product search snapshot."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _id(prefix: str, *parts: Any) -> str:
    raw = "|".join(_text(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]
    return f"{prefix}-{digest}"


def _entity(entities: list[dict[str, Any]], entity_type: str, external_id: str, label: str, attributes: dict[str, Any], evidence: str) -> None:
    if not external_id or any(item.get("external_id") == external_id for item in entities):
        return
    entities.append({
        "external_id": external_id,
        "entity_type": entity_type,
        "label": label or external_id,
        "attributes": attributes,
        "confidence": 0.98,
        "evidence": evidence[:1000],
        "source_refs": ["scraper:briefInfo", "scraper:querySummaryPrice"],
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
        "ontology_eligible": True,
    })


def _relation(relations: list[dict[str, Any]], source: str, relation_type: str, target: str, evidence: str) -> None:
    if not source or not target or source == target:
        return
    key = (source, relation_type, target)
    if any((item.get("source_external_id"), item.get("relation_type"), item.get("target_external_id")) == key for item in relations):
        return
    relations.append({
        "source_external_id": source,
        "target_external_id": target,
        "relation_type": relation_type,
        "evidence": evidence[:1000],
        "confidence": 0.96,
        "ontology_eligible": True,
    })


def normalize_flight_product_payload(payload: dict[str, Any], source_name: str = "东航航班及产品数据") -> dict[str, Any]:
    """Convert the scraper's nested response into ontology candidates.

    Supports both the saved response shape ({data: {...}}) and a bare data object.
    The adapter is deliberately deterministic; the agent may enrich or reject the
    candidates later, but it should not invent flight or fare identifiers.
    """
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(root, dict):
        root = {}
    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    labels_by_id: dict[str, str] = {}
    products_by_code: dict[str, str] = {}
    evidence = f"source={source_name}"

    for label in root.get("productLabelInfoList") or []:
        if not isinstance(label, dict):
            continue
        label_id = _text(label.get("id"))
        if not label_id:
            continue
        label_name = _text(label.get("labelName")) or label_id
        labels_by_id[label_id] = label_name
        _entity(entities, "ProductLabel", f"product-label-{label_id}", label_name, {"source_id": label_id, "notice": label.get("labelNotice"), "description": label.get("labelDescriptionii"), "sub_labels": [label.get("subLabel1"), label.get("subLabel2"), label.get("subLabel3")]}, evidence)

    for group in root.get("productGroupInfoList") or []:
        if not isinstance(group, dict):
            continue
        group_id = _text(group.get("id"))
        if not group_id:
            continue
        _entity(entities, "ProductGroup", f"product-group-{group_id}", _text(group.get("groupName")) or group_id, {"source_id": group_id, "product_codes": group.get("productCode"), "process": group.get("process")}, evidence)

    product_group_codes: dict[str, list[str]] = {}
    for group in root.get("productGroupInfoList") or []:
        if isinstance(group, dict):
            for code in _text(group.get("productCode")).replace(",", " ").split():
                product_group_codes.setdefault(code, []).append(_text(group.get("id")))

    for product in root.get("productInfos") or []:
        if not isinstance(product, dict):
            continue
        code = _text(product.get("productCode"))
        if not code:
            continue
        product_id = f"product-{code}"
        products_by_code[code] = product_id
        _entity(entities, "Product", product_id, _text(product.get("promotionCode")) or code, {"product_code": code, "promotion_code": product.get("promotionCode"), "beneficiary": product.get("beneficiary"), "buy_ticket_member": product.get("buyTicketMember"), "take_type": product.get("takeType"), "raw": product}, evidence)

        for group_id in product_group_codes.get(code, []):
            _relation(relations, product_id, "belongs_to_product_group", f"product-group-{group_id}", evidence)
        for item in product.get("cabinLabelInfo") or []:
            if not isinstance(item, dict):
                continue
            name = _text(item.get("labelName"))
            label_id = next((key for key, value in labels_by_id.items() if value == name), "")
            if label_id:
                _relation(relations, product_id, "has_product_label", f"product-label-{label_id}", evidence)

    ancillary_ids_by_ref: dict[str, str] = {}
    for raw_id, ancillary in (root.get("xProductMap") or {}).items():
        if not isinstance(ancillary, dict):
            continue
        ancillary_code = _text(ancillary.get("productCode")) or _text(raw_id)
        if not ancillary_code:
            continue
        ancillary_id = f"ancillary-{ancillary_code}"
        # Some snapshots reference xProductMap by map key, others by productCode.
        ancillary_ids_by_ref[_text(raw_id)] = ancillary_id
        ancillary_ids_by_ref[ancillary_code] = ancillary_id
        _entity(entities, "AncillaryProduct", ancillary_id, _text(ancillary.get("productName")) or ancillary_code, {"product_code": ancillary_code, "resource_code": ancillary.get("resourceCode"), "account_price": ancillary.get("accountPrice"), "sale_price": ancillary.get("salePrice"), "product_value": ancillary.get("productValue"), "type": ancillary.get("xProductType"), "raw": ancillary}, evidence)

    for item_index, item in enumerate(root.get("flightItems") or []):
        if not isinstance(item, dict):
            continue
        cabins = item.get("cabinInfoDescs") or []
        for flight_info in item.get("flightInfos") or []:
            if not isinstance(flight_info, dict):
                continue
            segments = flight_info.get("flightSegments") or []
            if not segments:
                continue
            first = segments[0] if isinstance(segments[0], dict) else {}
            last = segments[-1] if isinstance(segments[-1], dict) else first
            org = _text(first.get("orgCode")); dest = _text(last.get("destCode"))
            org_name = _text(first.get("orgName")) or org; dest_name = _text(last.get("destName")) or dest
            route_id = _id("route", org, dest)
            flight_key = _text(first.get("flightInfoId")) or f"{item_index}-{_text(first.get('flightNo'))}-{org}-{dest}"
            flight_id = _id("flight", flight_key)
            _entity(entities, "Airport", f"airport-{org}", org_name, {"airport_code": org}, evidence)
            _entity(entities, "Airport", f"airport-{dest}", dest_name, {"airport_code": dest}, evidence)
            _entity(entities, "Route", route_id, f"{org_name}-{dest_name}", {"origin_code": org, "destination_code": dest}, evidence)
            _entity(entities, "Flight", flight_id, _text(first.get("flightNo")) or flight_id, {"flight_info_id": flight_key, "airline_code": first.get("airlineCode"), "origin_code": org, "destination_code": dest, "raw": flight_info}, evidence)
            _relation(relations, route_id, "departs_from", f"airport-{org}", evidence)
            _relation(relations, route_id, "arrives_at", f"airport-{dest}", evidence)
            _relation(relations, flight_id, "operates_on", route_id, evidence)
            for segment_index, segment in enumerate(segments):
                if not isinstance(segment, dict):
                    continue
                segment_key = _text(segment.get("flightInfoId")) or f"{flight_key}-{segment_index}"
                segment_id = _id("segment", segment_key, segment_index)
                seg_org = _text(segment.get("orgCode")) or org; seg_dest = _text(segment.get("destCode")) or dest
                _entity(entities, "FlightSegment", segment_id, _text(segment.get("flightNo")) or segment_id, {"flight_info_id": segment_key, "airline_code": segment.get("airlineCode"), "flight_no": segment.get("flightNo"), "origin_code": seg_org, "destination_code": seg_dest, "origin_name": segment.get("orgName"), "destination_name": segment.get("destName"), "raw": segment}, evidence)
                _relation(relations, flight_id, "has_segment", segment_id, evidence)
                if seg_org: _relation(relations, segment_id, "departs_from", f"airport-{seg_org}", evidence)
                if seg_dest: _relation(relations, segment_id, "arrives_at", f"airport-{seg_dest}", evidence)
            for cabin in cabins:
                if not isinstance(cabin, dict):
                    continue
                ccode = _text(cabin.get("ccode"))
                if not ccode: continue
                cabin_id = _id("cabin", flight_id, ccode)
                _entity(entities, "Cabin", cabin_id, _text(cabin.get("cabinLevelName")) or ccode, {"flight_id": flight_id, "code": ccode, "type": cabin.get("ctype"), "mu_level": cabin.get("muCabinLevel")}, evidence)
                _relation(relations, flight_id, "has_cabin", cabin_id, evidence)
                for fare in cabin.get("fareInfoDescList") or []:
                    if not isinstance(fare, dict): continue
                    fare_key = (_text(fare.get("productCode")) or "fare", _text(fare.get("paxType")), _text(fare.get("totalPrice")), _text(fare.get("brandLevel")))
                    fare_id = _id("fare", cabin_id, *fare_key)
                    _entity(entities, "Fare", fare_id, f"{ccode} {_text(fare.get('totalPrice'))}".strip(), {"cabin_id": cabin_id, "pax_type": fare.get("paxType"), "lprice": fare.get("lprice"), "tax_price": fare.get("taxPrice"), "total_price": fare.get("totalPrice"), "reschedule_total_price": fare.get("rescheduleTotalPrice"), "price_source": fare.get("priceSource"), "product_code": fare.get("productCode"), "brand_level": fare.get("brandLevel"), "x_product_ids": fare.get("xProductIds")}, evidence)
                    _relation(relations, cabin_id, "has_fare", fare_id, evidence)
                    code = _text(fare.get("productCode"))
                    if code and code in products_by_code: _relation(relations, fare_id, "uses_product", products_by_code[code], evidence)
                    for x_id in fare.get("xProductIds") or []:
                        ancillary_id = ancillary_ids_by_ref.get(_text(x_id), f"ancillary-{_text(x_id)}")
                        if any(item.get("external_id") == ancillary_id for item in entities): _relation(relations, fare_id, "includes_ancillary", ancillary_id, evidence)
            for label_id in flight_info.get("tripLabelIds") or []:
                if _text(label_id) in labels_by_id: _relation(relations, flight_id, "has_product_label", f"product-label-{_text(label_id)}", evidence)

    return {"source_name": source_name, "source_format": "ceair-flight-product-snapshot", "entities": entities, "relations": relations, "ontology_gate": {"eligible": bool(entities), "decision": "update" if entities else "knowledge_only", "reason": "航班与产品快照已标准化，需人工确认后更新本体。" if entities else "未识别到可入本体的航班或产品对象。", "matched_entity_types": sorted({item["entity_type"] for item in entities}), "confidence": 0.96, "review_required": bool(entities)}}