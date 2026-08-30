from app.data_pipeline import apply_ontology_admission
from app.flight_product_pipeline import normalize_flight_product_payload


def snapshot():
    return {
        "data": {
            "productLabelInfoList": [{"id": "L1", "labelName": "Early bird"}],
            "productGroupInfoList": [{"id": "G1", "groupName": "Fare bundle", "productCode": "P1"}],
            "productInfos": [{"productCode": "P1", "promotionCode": "Early fare", "cabinLabelInfo": [{"labelName": "Early bird"}]}],
            "xProductMap": {"X1": {"productName": "Extra baggage", "productCode": "XB1", "xProductType": "baggage"}},
            "flightItems": [{
                "cabinInfoDescs": [{"ccode": "Y", "cabinLevelName": "Economy", "fareInfoDescList": [{"productCode": "P1", "totalPrice": 680, "xProductIds": ["X1"]}]}],
                "flightInfos": [{
                    "flightSegments": [{"flightInfoId": "F1", "flightNo": "MU5101", "orgCode": "SHA", "orgName": "Shanghai", "destCode": "SZX", "destName": "Shenzhen", "airlineCode": "MU"}],
                    "tripLabelIds": ["L1"],
                }],
            }],
        }
    }


def test_normalizer_covers_flight_fare_product_and_ancillary_graph():
    result = normalize_flight_product_payload(snapshot(), "fixture")
    types = {item["entity_type"] for item in result["entities"]}
    assert {"Airport", "Route", "Flight", "FlightSegment", "Cabin", "Fare", "Product", "ProductGroup", "ProductLabel", "AncillaryProduct"} <= types
    relations = {(item["relation_type"], item["source_external_id"], item["target_external_id"]) for item in result["relations"]}
    assert any(item[0] == "includes_ancillary" and item[2] == "ancillary-XB1" for item in relations)
    assert any(item[0] == "uses_product" and item[2] == "product-P1" for item in relations)


def test_normalizer_is_deterministic_and_empty_input_is_safe():
    first = normalize_flight_product_payload(snapshot())
    second = normalize_flight_product_payload(snapshot())
    assert [(x["entity_type"], x["external_id"]) for x in first["entities"]] == [(x["entity_type"], x["external_id"]) for x in second["entities"]]
    empty = normalize_flight_product_payload({})
    assert empty["entities"] == []
    assert empty["relations"] == []
    assert empty["ontology_gate"]["decision"] == "knowledge_only"


def test_admission_rejects_wrong_relation_endpoints():
    result = apply_ontology_admission({
        "ontology_gate": {"eligible": True, "decision": "update"},
        "entities": [
            {"external_id": "flight-1", "entity_type": "Flight", "label": "MU5101", "evidence": "fixture", "confidence": 0.9},
            {"external_id": "product-1", "entity_type": "Product", "label": "Fare product", "evidence": "fixture", "confidence": 0.9},
        ],
        "relations": [{"source_external_id": "flight-1", "relation_type": "belongs_to_product_group", "target_external_id": "product-1", "evidence": "fixture", "confidence": 0.9}],
    })
    assert result["relations"][0]["ontology_eligible"] is False
    assert result["ontology_gate"]["accepted_relation_count"] == 0
