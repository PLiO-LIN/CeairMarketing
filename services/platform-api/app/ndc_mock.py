
"""Deterministic, fictional NDC 24.1 responses for local integration testing.

The payload shape mirrors the documented envelope and keeps the business data
synthetic. It is intentionally independent of any production endpoint,
credential, or customer information.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from typing import Any


def _date(value: str | None) -> str:
    if value:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return (date.today() + timedelta(days=14)).isoformat()


def _envelope(data: dict[str, Any], sales_channel: str, *, message_type: str) -> dict[str, Any]:
    trx_id = f"MOCK-{uuid4().hex[:20].upper()}"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "versionNumber": "24.1",
        "messageType": message_type,
        "trxID": trx_id,
        "echoTokenText": trx_id,
        "timestamp": now,
        "retransmissionInd": False,
        "salesChannel": sales_channel,
        "distributionChain": [{"ordinal": 1, "orgRole": "Seller", "orgID": "MU"}],
        "data": data,
    }


def _flight_items(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    names = {"SHA": "上海虹桥", "PVG": "上海浦东", "SYX": "三亚凤凰", "CAN": "广州白云", "PEK": "北京首都"}
    origin_name = names.get(origin, origin)
    destination_name = names.get(destination, destination)
    rows = [
        ("MU781", "08:20", "11:45", "MU781-1", 680, 24),
        ("MU789", "14:10", "17:35", "MU789-1", 820, 16),
    ]
    flight_items: list[dict[str, Any]] = []
    for flight_no, dep, arr, flight_id, economy_price, inventory in rows:
        segments = [{
            "flightInfoId": flight_id,
            "flightNo": flight_no,
            "airlineCode": "MU",
            "orgCode": origin,
            "destCode": destination,
            "orgName": origin_name,
            "destName": destination_name,
            "departureDate": departure_date,
            "departureTime": dep,
            "arrivalDate": departure_date,
            "arrivalTime": arr,
            "equipment": "C919" if flight_no == "MU781" else "A321",
            "duration": "03:25",
        }]
        flight_items.append({
            "flightInfos": [{"flightInfoId": flight_id, "flightSegments": segments, "tripLabelIds": ["label-early-bird"]}],
            "cabinInfoDescs": [
                {"ccode": "Y", "ctype": "Economy", "cabinLevelName": "经济舱", "availability": inventory,
                 "fareInfoDescList": [
                     {"productCode": "MU-EARLY-Y", "paxType": "ADT", "totalPrice": economy_price, "taxPrice": 50, "lprice": economy_price - 50, "rescheduleTotalPrice": 120, "priceSource": "NDC_MOCK", "brandLevel": "早鸟经济舱", "xProductIds": ["XB20"]},
                     {"productCode": "MU-FLEX-Y", "paxType": "ADT", "totalPrice": economy_price + 160, "taxPrice": 50, "lprice": economy_price + 110, "rescheduleTotalPrice": 0, "priceSource": "NDC_MOCK", "brandLevel": "灵活经济舱", "xProductIds": ["XB20", "SEAT-PREF"]},
                 ]},
                {"ccode": "C", "ctype": "Business", "cabinLevelName": "公务舱", "availability": 6,
                 "fareInfoDescList": [{"productCode": "MU-BIZ-C", "paxType": "ADT", "totalPrice": economy_price + 2180, "taxPrice": 50, "lprice": economy_price + 2130, "rescheduleTotalPrice": 0, "priceSource": "NDC_MOCK", "brandLevel": "公务舱", "xProductIds": ["LOUNGE"]}]},
            ],
        })
    return {
        "shoppingResponseId": f"SHOP-{uuid4().hex[:12].upper()}",
        "query": {"origin": origin, "destination": destination, "departureDate": departure_date, "passengers": [{"paxType": "ADT", "quantity": 1}]},
        "productLabelInfoList": [{"id": "label-early-bird", "labelName": "早鸟优惠", "labelNotice": "模拟营销标签", "labelDescriptionii": "提前预订优惠产品"}, {"id": "label-flex", "labelName": "灵活出行", "labelNotice": "可退改", "labelDescriptionii": "适合行程不确定旅客"}],
        "productGroupInfoList": [{"id": "group-air-ticket", "groupName": "机票基础产品包", "productCode": "MU-EARLY-Y MU-FLEX-Y MU-BIZ-C", "process": "出票前选择"}],
        "productInfos": [
            {"productCode": "MU-EARLY-Y", "promotionCode": "EARLY-MU", "beneficiary": "成人旅客", "buyTicketMember": "ALL", "takeType": "ticket", "cabinLabelInfo": [{"labelName": "早鸟优惠"}]},
            {"productCode": "MU-FLEX-Y", "promotionCode": "FLEX-MU", "beneficiary": "成人旅客", "buyTicketMember": "ALL", "takeType": "ticket", "cabinLabelInfo": [{"labelName": "灵活出行"}]},
            {"productCode": "MU-BIZ-C", "promotionCode": "BIZ-MU", "beneficiary": "成人旅客", "buyTicketMember": "东方万里行会员", "takeType": "ticket", "cabinLabelInfo": []},
        ],
        "xProductMap": {
            "XB20": {"productCode": "XB20", "productName": "预付费行李20KG", "resourceCode": "BAG20", "accountPrice": 180, "salePrice": 180, "productValue": "20KG", "xProductType": "BAGGAGE"},
            "SEAT-PREF": {"productCode": "SEAT-PREF", "productName": "优选座位", "resourceCode": "SEAT", "accountPrice": 60, "salePrice": 60, "productValue": "优选座位", "xProductType": "SEAT"},
            "LOUNGE": {"productCode": "LOUNGE", "productName": "机场贵宾室", "resourceCode": "LOUNGE", "accountPrice": 320, "salePrice": 320, "productValue": "贵宾室服务", "xProductType": "LOUNGE"},
        },
        "flightItems": flight_items,
    }


def air_shopping_payload(origin: str = "SHA", destination: str = "SYX", departure_date: str | None = None, sales_channel: str = "10000") -> dict[str, Any]:
    """Return a fictional AirShopping-style NDC 24.1 response."""
    return _envelope(_flight_items(origin.upper(), destination.upper(), _date(departure_date)), sales_channel, message_type="AirShoppingRS")


def best_pricing_payload(origin: str = "SHA", destination: str = "SYX", departure_date: str | None = None, sales_channel: str = "10000") -> dict[str, Any]:
    data = _flight_items(origin.upper(), destination.upper(), _date(departure_date))
    data["bestOffer"] = {"flightNo": "MU781", "productCode": "MU-EARLY-Y", "totalPrice": 680, "currency": "CNY", "reason": "模拟最低含税价且库存充足"}
    return _envelope(data, sales_channel, message_type="AirShoppingBestPricingRS")


def order_list_payload(sales_channel: str = "10000") -> dict[str, Any]:
    orders = [
        {"orderId": "8533377", "orderStatus": "COMPLETED", "ticketingStatus": "ISSUED", "totalPrice": 860, "currency": "CNY", "segments": [{"flightNo": "MU781", "origin": "SHA", "destination": "SYX", "departureDate": _date(None)}]},
        {"orderId": "8533388", "orderStatus": "COMPLETED", "ticketingStatus": "ISSUED", "totalPrice": 1000, "currency": "CNY", "segments": [{"flightNo": "MU789", "origin": "SHA", "destination": "SYX", "departureDate": _date(None)}]},
    ]
    return _envelope({"orders": orders, "total": len(orders), "page": 1, "pageSize": 50}, sales_channel, message_type="OrderListRS")
