"""Business-rule text catalog used by the distillation probe.

The simulator's DGP is frozen once training starts, so this catalog is kept
separate: it supplies the natural-language rule text that a production
``BusinessRule`` record carries, and the oracle for the probe is a
text-derivable property (does the rule state a hard blocking condition?).
"""

from __future__ import annotations

from dataclasses import dataclass

EVIDENCE_CONDITIONS = ("fresh", "stale", "absent")


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    text: str
    hard_block: bool


RULES: tuple[RuleSpec, ...] = (
    RuleSpec("R01", "中转时间 MCT 不足 45 分钟的联程票，不得挂接行李直挂产品包。", True),
    RuleSpec("R02", "国际航线产品包须取得目的地地面服务确认后方可上架。", True),
    RuleSpec("R03", "金卡以上客群可优先享受升舱券组合，无需额外审批。", False),
    RuleSpec("R04", "同一客户在 7 日内通过全渠道接收的营销触达不得超过 3 次。", True),
    RuleSpec("R05", "已退票或改期至非目标航班的客户，应从本次客群快照中剔除。", True),
    RuleSpec("R06", "暑运期间家庭出行客群对儿童餐与前排座位组合的偏好显著上升。", False),
    RuleSpec("R07", "运价舱位为折扣 R/N 舱的客票，不参与里程加倍活动。", True),
    RuleSpec("R08", "近 90 日无乘机记录的客户，短信渠道单次预算上限为 0.6 元。", False),
    RuleSpec("R09", "贵宾室产品须与可订舱位同版本发布，版本不一致时禁止推荐。", True),
    RuleSpec("R10", "企业客户协议价航线可叠加地面接送服务，需客户经理确认。", False),
    RuleSpec("R11", "投诉工单未关闭的客户，暂停推送促销类内容。", True),
    RuleSpec("R12", "航班取消或延误超过 60 分钟时，优先推送改签与辅营补偿方案。", False),
    RuleSpec("R13", "保险类产品仅可向已购买含托运行李的客票客户展示。", True),
    RuleSpec("R14", "会员积分余额充足的客户，可用积分抵扣部分辅营费用。", False),
    RuleSpec("R15", "涉及未成年人单独乘机的订单，须人工核验后再触达。", True),
    RuleSpec("R16", "目的地执行入境限制的航线，相关套餐在下架前不得新增曝光。", True),
)


def oracle_agreement(rule: RuleSpec, condition: str) -> float:
    """Text-derivable reference used only to score the distilled judge."""

    if condition == "absent":
        return 0.2 if rule.hard_block else 0.45
    if condition == "stale":
        return 0.35 if rule.hard_block else 0.7
    return 0.55 if rule.hard_block else 0.9
