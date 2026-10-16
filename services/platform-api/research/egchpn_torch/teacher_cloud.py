"""Frozen cloud-teacher judgements for evidence-gate rule agreement.

Source C of the teacher design: the judgements below were produced by the
cloud coding agent in a single offline pass (no seed, no re-runnable API), so
they are committed as a frozen cache with a sha256 and a provenance header.
Training, CI and the verify scripts only ever read this file; nothing calls a
cloud model at run time.

What is distilled: ``BusinessRule`` free text -> a scalar rule-agreement in
(0, 1] plus a short rationale, i.e. the quantity the evidence gate consumes as
``r_e`` in a production deployment.  It is never a treatment-effect label.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np

from research.egchpn_torch.rule_catalog import EVIDENCE_CONDITIONS, RULES, oracle_agreement

DISCLOSURE = {
    "teacher_source": "cloud-agent",
    "teacher_note": "云端编码代理单次离线生成，无固定随机种子、模型版本随时间变化，故以冻存缓存形式发布",
    "generated_on": "2026-10-16",
    "license": "CC-BY-4.0",
    "used_for": "证据门 rule_agreement 先验与解释文案，不作为增量效应标签",
}

# (rule_id, condition) -> (agreement, rationale)
JUDGEMENTS: dict[str, tuple[float, str]] = {
    "R01|fresh": (0.55, "MCT 阈值明确，需核到具体联程票时长才可放行"),
    "R01|stale": (0.32, "时刻数据过期，MCT 判定不可信"),
    "R01|absent": (0.15, "无 MCT 证据，按硬性阻断处理"),
    "R02|fresh": (0.58, "地面确认存在，仍缺目的地版本核对"),
    "R02|stale": (0.3, "确认记录过期，上架资格存疑"),
    "R02|absent": (0.12, "无地面服务确认，禁止上架"),
    "R03|fresh": (0.9, "会员等级证据充分，无需审批"),
    "R03|stale": (0.68, "等级快照略旧但方向一致"),
    "R03|absent": (0.38, "缺等级证据，只能降级为候选"),
    "R04|fresh": (0.52, "频控为硬约束，需按窗口计数核验"),
    "R04|stale": (0.28, "触达记录过期，无法确认未超限"),
    "R04|absent": (0.14, "无触达历史，按可能超限处理"),
    "R05|fresh": (0.57, "退改状态可查，剔除逻辑清晰"),
    "R05|stale": (0.33, "退改事实可能已变化"),
    "R05|absent": (0.18, "无退改证据，快照含无效客户风险"),
    "R06|fresh": (0.88, "偏好信号为软先验，不构成阻断"),
    "R06|stale": (0.66, "季节信号衰减但仍正向"),
    "R06|absent": (0.4, "缺偏好证据，仅可作弱先验"),
    "R07|fresh": (0.54, "舱位可核，折扣舱排除规则为硬性"),
    "R07|stale": (0.31, "舱位版本过期，排除判定不稳"),
    "R07|absent": (0.16, "无舱位证据，默认排除"),
    "R08|fresh": (0.86, "预算上限为参数约束，不阻断资格"),
    "R08|stale": (0.63, "乘机记录时间窗略旧"),
    "R08|absent": (0.36, "无乘机记录，只能给保守上限"),
    "R09|fresh": (0.56, "版本一致性可校验，属硬性前置"),
    "R09|stale": (0.29, "版本对账数据过期"),
    "R09|absent": (0.13, "无版本证据，禁止推荐"),
    "R10|fresh": (0.84, "协议航线可叠加，仅需客户经理确认"),
    "R10|stale": (0.61, "确认时间较久，需回看"),
    "R10|absent": (0.34, "无确认记录，暂缓叠加"),
    "R11|fresh": (0.5, "投诉状态可查，未关闭即暂停"),
    "R11|stale": (0.27, "工单状态可能已更新"),
    "R11|absent": (0.12, "无工单证据，按保守暂停处理"),
    "R12|fresh": (0.87, "运行事件实时性足够，属正向触发"),
    "R12|stale": (0.62, "航班状态已过期"),
    "R12|absent": (0.33, "无运行证据，不能触发补偿"),
    "R13|fresh": (0.53, "行李购买记录可核，前置为硬性"),
    "R13|stale": (0.3, "订单记录过期"),
    "R13|absent": (0.15, "无行李购买证据，禁止展示"),
    "R14|fresh": (0.89, "积分余额可查，抵扣为权益类"),
    "R14|stale": (0.67, "余额快照略旧"),
    "R14|absent": (0.37, "无余额证据，只能给保守值"),
    "R15|fresh": (0.48, "涉未成年人，必须人工核验后放行"),
    "R15|stale": (0.26, "核验材料时效不明"),
    "R15|absent": (0.1, "无核验记录，禁止触达"),
    "R16|fresh": (0.51, "入境限制为外部硬性条件"),
    "R16|stale": (0.25, "限制通告可能已更新"),
    "R16|absent": (0.11, "无官方限制证据，按禁止处理"),
}


def build_cache(path: Path) -> dict:
    rows = []
    for rule in RULES:
        for condition in EVIDENCE_CONDITIONS:
            key = f"{rule.rule_id}|{condition}"
            agreement, rationale = JUDGEMENTS[key]
            rows.append(
                {
                    "rule_id": rule.rule_id,
                    "condition": condition,
                    "rule_text": rule.text,
                    "rule_agreement": agreement,
                    "rationale": rationale,
                    "oracle_hard_block": rule.hard_block,
                    "source": "cloud-agent",
                }
            )
    payload = {"disclosure": DISCLOSURE, "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": digest, "rows": len(rows)}


def probe(threshold: float = 0.65) -> dict:
    """Score the distilled judge against the text-derivable reference.

    The governance question is binary: below the evidence-gate threshold the
    action is held for human review, above it the path may proceed.  So the
    judge is scored on that decision (flagged == hard block), plus rank
    correlation and MAE against the graded reference.
    """

    judged, reference = [], []
    flagged_correct = 0
    hard_mean, soft_mean = [], []
    total = 0
    for rule in RULES:
        for condition in EVIDENCE_CONDITIONS:
            agreement, _ = JUDGEMENTS[f"{rule.rule_id}|{condition}"]
            judged.append(agreement)
            reference.append(oracle_agreement(rule, condition))
            flagged = agreement < threshold
            flagged_correct += int(flagged == rule.hard_block)
            (hard_mean if rule.hard_block else soft_mean).append(agreement)
            total += 1
    rank_j = _ranks(judged)
    rank_r = _ranks(reference)
    spearman = float(np.corrcoef(rank_j, rank_r)[0, 1]) if total > 2 else 0.0
    mae = sum(abs(a - b) for a, b in zip(judged, reference)) / total
    return {
        "rows": total,
        "threshold": threshold,
        "flag_decision_accuracy": flagged_correct / total,
        "spearman_vs_reference": round(spearman, 4),
        "mean_abs_error": round(mae, 4),
        "mean_agreement_hard_block": round(sum(hard_mean) / len(hard_mean), 4),
        "mean_agreement_soft_rule": round(sum(soft_mean) / len(soft_mean), 4),
    }


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = float(position)
    return ranks


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "cache" / "teacher_cloud_frozen.json"
    meta = build_cache(out)
    result = {"experiment": "Marsh-Echo 证据门 rule_agreement 蒸馏探针", "synthetic": True, "label": "流程验证（虚构）", "cache": meta, "probe": probe()}
    artifact = Path(__file__).resolve().parents[4] / "docs" / "实验" / "marshecho-teacher-distill-v2.0.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"artifact={artifact}")
