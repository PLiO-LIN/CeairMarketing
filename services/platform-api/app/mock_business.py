"""Deterministic airline business mock services used for local and staging integration."""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any

MOCK_SOURCE = "ceair-mock-business-v1"

def _now():
    return datetime.now(timezone.utc).isoformat()

def flight_operations(origin: str = "SHA", destination: str = "SYX") -> dict[str, Any]:
    return {"source": MOCK_SOURCE, "generated_at": _now(), "route": {"origin": origin.upper(), "destination": destination.upper()}, "flights": [
        {"flight_no": "MU5387", "departure": "06:45", "arrival": "09:55", "aircraft": "C919", "cabin_inventory": {"Y": 42, "W": 8, "C": 4}, "load_factor": 0.78, "on_time_rate_7d": 0.94, "fare_yuan": 760, "wifi": True},
        {"flight_no": "MU5393", "departure": "10:20", "arrival": "13:35", "aircraft": "A321", "cabin_inventory": {"Y": 86, "W": 12, "C": 6}, "load_factor": 0.61, "on_time_rate_7d": 0.89, "fare_yuan": 620, "wifi": False},
        {"flight_no": "MU5411", "departure": "16:10", "arrival": "19:25", "aircraft": "A350", "cabin_inventory": {"Y": 54, "W": 6, "C": 3}, "load_factor": 0.83, "on_time_rate_7d": 0.91, "fare_yuan": 910, "wifi": True},
    ]}

def profile_summary() -> dict[str, Any]:
    return {"source": MOCK_SOURCE, "generated_at": _now(), "total_members": 6000000, "segments": [
        {"code": "A1", "name": "京沪快线商务型", "size": 48200, "preferred_route": "SHA-PVG/PEK", "member_tier": "金卡以上", "top_products": ["贵宾室优享", "Wi-Fi优享"]},
        {"code": "B2", "name": "亲子周末出游型", "size": 93600, "preferred_route": "SHA-SYX/HKT", "member_tier": "普通会员", "top_products": ["行李优享", "安心优享"]},
        {"code": "C3", "name": "低碳体验偏好型", "size": 26700, "preferred_route": "国内航线", "member_tier": "会员", "top_products": ["低碳优享", "C919优享"]},
        {"code": "D4", "name": "国际多人出行型", "size": 18900, "preferred_route": "SHA-NRT/SIN", "member_tier": "会员", "top_products": ["国际2-9人小团", "Wi-Fi优享"]},
    ], "available_dimensions": 96}

def market_signals() -> dict[str, Any]:
    return {"source": MOCK_SOURCE, "generated_at": _now(), "signals": [
        {"id": "MOCK-HOT-001", "type": "holiday", "title": "国庆前往三亚的搜索和提前预订意向上升", "topic": "国内旅游", "route": "SHA-SYX", "trend_score": 0.91, "evidence": ["模拟搜索指数周环比 +28%", "模拟提前预订天数 15 天"]},
        {"id": "MOCK-HOT-002", "type": "operations", "title": "晚间航班客座率低于近四周均值", "topic": "航线经营", "route": "SHA-SYX", "trend_score": 0.84, "evidence": ["模拟客座率 61%", "模拟近四周均值 74%"]},
        {"id": "MOCK-HOT-003", "type": "ancillary", "title": "亲子客群对行李和优选座位组合需求增强", "topic": "辅营服务", "route": "国内航线", "trend_score": 0.79, "evidence": ["模拟组合购买率 +16%", "模拟会员标签命中 9.36 万"]},
    ]}

def product_catalog() -> dict[str, Any]:
    return {"source": MOCK_SOURCE, "generated_at": _now(), "products": [
        {"code": "MOCK-WIFI", "name": "Wi-Fi优享", "category": "机上服务", "eligibility": "东方万里行会员；航班需支持机上互联", "benefits": ["标准全航程空中上网抵用券"], "status": "active"},
        {"code": "MOCK-MILE", "name": "里程优享", "category": "会员权益", "eligibility": "乘机前完成会员注册", "benefits": ["额外赠送 300-2400 里程积分"], "status": "active"},
        {"code": "MOCK-BAG", "name": "行李优享", "category": "辅营服务", "eligibility": "符合客票和航线适用条件", "benefits": ["额外行李额度"], "status": "active"},
        {"code": "MOCK-LOWCARBON", "name": "低碳优享", "category": "绿色出行", "eligibility": "国内航班；乘机后发放权益", "benefits": ["前排选座、升舱券、里程或SAF电子勋章"], "status": "active"},
        {"code": "MOCK-C919", "name": "C919优享", "category": "客舱体验", "eligibility": "C919执飞航班", "benefits": ["C919限定礼品"], "status": "active"},
    ]}

def channel_delivery(channel: str, audience_size: int, campaign_id: str = "MOCK-CAMPAIGN") -> dict[str, Any]:
    size = max(0, int(audience_size))
    delivered = round(size * 0.982)
    return {"source": MOCK_SOURCE, "generated_at": _now(), "channel": channel, "campaign_id": campaign_id, "task_id": f"MOCK-TASK-{datetime.now(timezone.utc):%Y%m%d%H%M%S}", "status": "accepted", "metrics": {"target": size, "delivered": delivered, "failed": size - delivered, "estimated_clicks": round(delivered * 0.114), "estimated_conversions": round(delivered * 0.028)}}
