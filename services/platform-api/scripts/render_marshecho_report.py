"""Render the human-readable Marsh-Echo (九皋) v2 experiment report.

Every number is pulled from the machine artifacts so the prose can never drift
away from what was actually measured, and every table carries the
【流程验证（虚构）】 label required by the team's evidence convention.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = REPO / "docs" / "实验"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load(name: str) -> dict:
    path = OUT / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value: object, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return "—"


def gate_ab_section(gate_ab: dict) -> list[str]:
    if not gate_ab.get("rows"):
        return []
    lines = [
        "## 4b 可执行性损失项（方法修正，实测）",
        "",
        f"- 协议：{gate_ab['protocol']}",
        "",
        "| 变体 | 过滤前非法率 | 策略价值 | uplift RMSE | Qini |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in gate_ab["rows"]:
        lines.append(
            f"| {row['variant']} | {row['invalid_rule_rate_pre_filter']:.3f} | {row['policy_value']:.0f} | {row['uplift_rmse']:.3f} | {row['qini']:.3f} |"
        )
    lines += ["", f"- 决策：{gate_ab['decision']}", f"- 注意：{gate_ab['caveat']}", ""]
    return lines


def gate_full_section(gate_full: dict) -> list[str]:
    if not gate_full.get("summary"):
        return []
    lines = ["## 4c 可执行性损失项：生产配置全量确认", "", f"- 协议：{gate_full.get('protocol')}", ""]
    for variant, row in sorted(gate_full["summary"].items()):
        lines.append(
            f"- λ_admissibility={variant}：过滤前非法率 {row['mean_invalid_pre']:.3f}、策略价值 {row['mean_policy_value']:.0f}、"
            f"RMSE {row['mean_rmse']:.3f}、Qini {row['mean_qini']:.3f}"
        )
    lines += ["", f"- **结论：{gate_full.get('verdict')}**", ""]
    return lines


def dr_section(dr_ab: dict) -> list[str]:
    if not dr_ab.get("means"):
        return []
    lines = [
        "## 4d AIPW/DR 伪结局监督（方法扩展，实测）",
        "",
        f"- 协议：{dr_ab['protocol']}",
        f"- 无泄漏说明：{dr_ab['leakage_note']}",
        "",
        "  | 权重 | pearson | uplift RMSE | Qini | 策略价值 | 验证损失 |",
        "  |---|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("dr0", "0.0"), ("dr1", "1.0")):
        row = dr_ab["means"][key]
        lines.append(
            f"  | {label} | {row['pearson']:.4f} | {row['uplift_rmse']:.4f} | {row['qini']:.4f} | {row['policy_value']:.0f} | {row['val']:.4f} |"
        )
    lines += ["", f"- 决策：{dr_ab['decision']}", f"- 注意：{dr_ab['caveat']}", ""]
    return lines


def before_after_section(ablation: dict) -> list[str]:
    """Shipped variant (runs_final) vs the sweep variant (runs) for the main model."""

    rows = ablation.get("summary", [])
    picked = [
        row
        for row in rows
        if row["method"] == "marshecho_none" and row["selector"] == "oracle_rule"
    ]
    if len({row.get("tree") for row in picked}) < 2:
        return []
    lines = [
        "## 10 出厂前后对照（同一评估协议）",
        "",
        "| dgp | 变体 | 树 | 种子 | 策略价值 | CI | uplift RMSE | Qini | 过滤前非法率(规则) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dgp in ("v1", "v2"):
        for row in sorted([r for r in picked if r["dgp"] == dgp], key=lambda r: r.get("tree", "")):
            lines.append(
                f"| {dgp} | {row.get('variant')} | {row.get('tree')} | {row['n_seeds']} | "
                f"{row['policy_value_mean']:.1f} | ±{row['policy_value_ci95']:.1f} | "
                f"{row['uplift_rmse_mean']:.4f} | {row['qini_mean']:.4f} | "
                f"{row['invalid_rule_rate_pre_filter_mean']:.3f} |"
            )
    lines += [
        "",
        "- 说明：各行差别在训练配方与选择判据（sweep=旧复合损失早停；shipped=同配方改用质量早停；"
        "shipped_adm_dr=质量早停再叠加可执行性项 λ=0.5 与 DR 伪结局权重 1.0），"
        "数据、种子、评估协议完全相同；不同损失变体的验证损失不可互相比较，因此改善以 Qini / RMSE / 非法率并列报告。",
        "",
    ]
    return lines


def ensemble_section(ensemble: dict) -> list[str]:
    if not ensemble.get("means"):
        return []
    lines = [
        "## 4e 同配置多种子集成（出厂形态，实测）",
        "",
        f"- 协议：{ensemble['protocol']}",
        "",
        "  | dgp | 单模型价值 | 集成价值 | 单模型 RMSE | 集成 RMSE | 单模型 Qini | 集成 Qini |",
        "  |---|---:|---:|---:|---:|---:|---:|",
    ]
    for dgp, row in sorted(ensemble["means"].items()):
        lines.append(
            f"  | {dgp} | {row['single_value']:.1f} | {row['ensemble_value']:.1f} | {row['single_rmse']:.4f} | "
            f"{row['ensemble_rmse']:.4f} | {row['single_qini']:.4f} | {row['ensemble_qini']:.4f} |"
        )
    parity = ensemble.get("runtime_parity", {})
    lines += [
        "",
        f"- 运行时一致性：numpy 集成 vs torch 平均最大误差 {parity.get('numpy_vs_torch_averaged_max_abs')}（容差 {parity.get('tolerance')}），成员 {parity.get('members')} 个，权重 {parity.get('artifact_bytes')} 字节。",
        f"- 决策：{ensemble['decision']}",
        "",
    ]
    return lines


def scaling_section(scaling: dict) -> list[str]:
    """Did buying more GPU time make the model better?  Report the measured answer."""

    rows = scaling.get("comparisons", [])
    if not rows:
        return []
    lines = [
        "## 4f 额外算力配对审计（续训是否让模型变好）",
        "",
        f"- 协议：{scaling.get('decision_rule')}",
        f"- 保持不变量：{json.dumps(scaling.get('constant_across_trees', {}), ensure_ascii=False)}",
        "",
        "  | dgp | 候选（worker） | 基准（worker） | 配对种子 | 基准验证损失 | 候选验证损失 | 差值 | 候选胜出 | 判定 |",
        "  |---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        cand, base = row["candidate"], row["baseline"]
        lines.append(
            f"  | {row['dgp']} | {row['candidate_worker']} {cand['hidden']}×{cand['layers']}/{cand['epochs']}ep/lr{cand['lr']} | "
            f"{row['baseline_worker']} {base['hidden']}×{base['layers']}/{base['epochs']}ep/lr{base['lr']} | "
            f"{row['seeds_paired']} | {row['baseline_mean_best_val']:.4f} | {row['candidate_mean_best_val']:.4f} | "
            f"{row['mean_delta']:+.4f} | {row['candidate_wins']}/{row['seeds_paired']} | {row['verdict']} |"
        )
    hours = scaling.get("gpu_hours_per_worker", {})
    summary = scaling.get("summary", {})
    lines += [
        "",
        f"- 各 worker 实际 GPU 机时：{json.dumps(hours, ensure_ascii=False)}",
        f"- **结论：{summary.get('conclusion')}**",
        f"- 调度说明：{scaling.get('lr_schedule_note')}",
        f"- 局限：{scaling.get('limitation')}",
        "",
    ]
    return lines


def defect_section(defect: dict) -> list[str]:
    summary = defect.get("summary_by_tree_and_budget", {})
    if not summary:
        return []
    lines = [
        "## 4g 早停审计：多算力为什么不会带来提升",
        "",
        f"- 证伪：{defect.get('verdict')}",
        f"- 成立：{defect.get('supported')}",
        f"- 长预算警示：{defect.get('long_horizon_caveat')}",
        f"- 真正有效的杠杆：{defect.get('lever_that_did_work')}",
        "",
        "  | 树:预算 | run | 判据 | 平均选点 epoch | 选点位置 | 判据到预算末涨幅 | 拟合窗 factual 前→后 | 拟合窗 cf 前→后 |",
        "  |---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for key, row in sorted(summary.items()):
        f_act, f_end = row["fit_window_factual_argmin_to_end"]
        c_act, c_end = row["fit_window_counterfactual_argmin_to_end"]
        lines.append(
            f"  | {key} | {row['runs']} | {row['select_criterion']} | {row['mean_argmin_epoch']:.0f} | "
            f"{row['mean_argmin_fraction']:.3f} | {row['mean_growth_of_criterion_to_end']:.2f}× | "
            f"{f_act:.4f}→{f_end:.4f} | {c_act:.4f}→{c_end:.4f} |"
        )
    dual = [row.get("dual_mean_penalty_gap") for row in summary.values() if row.get("dual_mean_penalty_gap") is not None]
    if dual:
        agree = " + ".join(
            f"{key}:{row['dual_argmin_agreement']}" for key, row in sorted(summary.items()) if row.get("dual_argmin_agreement") not in (None, "n/a")
        )
        lines.append(f"  - 双判据同权重对照：选点一致 {agree}；惩罚项对判据的平均影响 {min(dual):.6f}（因此换判据不改出厂结果）")
    lines += ["", f"- 分辨率说明：{defect.get('resolution_note')}", ""]
    return lines


def recipe_ab_section(recipe_ab: dict) -> list[str]:
    arms = recipe_ab.get("arms", {})
    if not arms:
        return []
    lines = [
        "## 4h 出厂候选配对 A/B（测试窗、按种子配对）",
        "",
        f"- 判定规则：{recipe_ab.get('decision_rule')}",
        "",
        "  | 候选树 | 改动 | dgp | 配对种子 | 策略价值 前→后 | uplift RMSE 前→后 | Qini 前→后 | 过滤前非法率 前→后 |",
        "  |---|---|---|---:|---:|---:|---:|---:|",
    ]
    for tree, arm in sorted(arms.items()):
        for dgp, entry in sorted((arm.get("by_dgp") or {}).items()):
            metrics = entry.get("metrics") or {}
            if not metrics:
                continue
            pv, rm, qi, iv = (
                metrics["policy_value"],
                metrics["uplift_rmse"],
                metrics["qini"],
                metrics["invalid_rule_rate_pre_filter"],
            )
            lines.append(
                f"  | {tree} | {arm.get('what_changed', '')} | {dgp} | {entry['seeds_paired']} | "
                f"{pv['baseline_mean']:.1f}→{pv['candidate_mean']:.1f} ({pv['mean_delta']:+.1f}) | "
                f"{rm['baseline_mean']:.4f}→{rm['candidate_mean']:.4f} ({rm['mean_delta']:+.4f}) | "
                f"{qi['baseline_mean']:.4f}→{qi['candidate_mean']:.4f} | "
                f"{iv['baseline_mean']:.3f}→{iv['candidate_mean']:.3f} |"
            )
    verdicts = recipe_ab.get("verdicts", {})
    lines += [f"  - {tree}：{text}" for tree, text in sorted(verdicts.items())]
    lines += ["", f"- **建议：{recipe_ab.get('recommendation')}**", f"- 注意：{recipe_ab.get('caveat')}", ""]
    return lines


def main() -> int:
    ablation = load("marshecho-ablation-v2.0.json")
    factorial = load("marshecho-gate-factorial-v2.0.json")
    constraints = load("marshecho-policy-constraints-v2.0.json")
    parity = load("marshecho-runtime-parity-v2.0.json")
    teacher = load("marshecho-teacher-distill-v2.0.json")
    selection = load("marshecho-checkpoint-selection-v2.0.json")
    continuation = load("marshecho-continuation-v2.0.json")
    gate_ab = load("marshecho-gate-consistency-ab-v2.0.json")
    gate_full = load("marshecho-gate-consistency-full.json")
    dr_ab = load("marshecho-dr-supervision-ab-v2.0.json")
    ensemble = load("marshecho-ensemble-ab-v2.0.json")
    scaling = load("marshecho-compute-scaling-v2.0.json")
    defect = load("marshecho-early-stopping-audit-v2.0.json")
    recipe_ab = load("marshecho-final-recipe-ab-v2.0.json")
    benchmark = load("eg-chpn-simulation-v2.0.json")

    lines: list[str] = ["# Marsh-Echo（九皋 / marshecho）v2 实验报告", ""]
    lines += [
        "架构：EG-CHPN v2（证据门控反事实超图策略网络）。模型实例名 **marshecho（九皋）**，论文英文名 **Marsh-Echo**。",
        "",
        "**全部数字口径为【流程验证（虚构）】**：本体实体与业务规则口径来自真实民航营销业务资料，"
        "而结果变量（潜在结果、处理分配、回执、收入）由模拟器生成，不构成任何真实航司经营提升证据。",
        "",
        "## 1 训练与算力",
        "",
    ]
    if constraints.get("runs_recorded"):
        lines += [
            f"- 已记录 run 数：{constraints['runs_recorded']}",
            f"- 累计 GPU 秒：{constraints.get('total_gpu_wall_seconds')}",
            f"- 平均单 run 秒数：{constraints.get('mean_run_seconds')}",
        ]
    if continuation:
        lines += [
            f"- 续训阶段墙钟秒：{continuation.get('stage2_wall_seconds')}",
            f"- 累计 GPU 小时：{continuation.get('cumulative_gpu_hours')}",
        ]
    if selection.get("winner"):
        winner = selection["winner"]
        lines += [
            f"- 出厂检查点选择规则：{selection.get('decision_rule')}",
            f"- 胜出配置：tree={winner['tree']} lr={winner['lr']} wd={winner['wd']} λ_policy={winner['lam_policy']}，"
            f"平均验证损失 {winner['mean_best_val']}（{winner['seeds']} 个共同种子）",
            f"- 出厂权重：`{Path(str(selection.get('shipped_checkpoint'))).name}`",
        ]
    lines += [
        "",
        "## 2 与 v1 原型的关系",
        "",
        "- v1（`eg_chpn_v1_frozen`）注意力参数随机初始化且从未优化，只有二元边与两个线性因果头；"
        "v2 为端到端训练的超边消息传递 + 可学习证据门 + 共享参数反事实双塔 + 约束策略头。",
        "- v1 保留为消融行，不删除，便于对照。",
        "",
        "## 3 基线与消融",
        "",
        "| dgp | 方法 | 门 | 选择器 | 种子 | 策略价值 | CI | 过滤前非法率(规则) | Qini |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in ablation.get("summary", []):
        if row["selector"] != "oracle_rule":
            continue
        lines.append(
            f"| {row['dgp']} | {row['method']} | {row['gate']} | {row['selector']} | {row['n_seeds']} | "
            f"{fmt(row['policy_value_mean'])} | ±{fmt(row['policy_value_ci95'])} | "
            f"{fmt(row['invalid_rule_rate_pre_filter_mean'])} | {fmt(row['qini_mean'])} |"
        )
    lines += ["", "完整逐种子数据见 `marshecho-ablation-v2.0.csv`；numpy 基线（含 S/X/DR-learner）见 `eg-chpn-simulation-v2.0.json`。", ""]

    lines += [
        "## 4 证据门 × 资格过滤 2×2 因子（关键安全结论）",
        "",
        "v1 论文里“0% vs 34.4% 非法选择率”的对比是构造性的：只有无门那一臂被关掉了 oracle 过滤。"
        "v2 改为同一选择器下 {学习门, 无门} × {过滤开, 过滤关} 的因子设计，并报告**过滤前**非法率。",
        "",
        "| 门 | 选择器 | 策略价值 | 过滤前非法率(规则) | 选中后非法率 | Qini |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for key, cell in sorted(factorial.get("cells", {}).items()):
        gate, selector = key.split("|")
        lines.append(
            f"| {gate} | {selector} | {fmt(cell['policy_value'])} | {fmt(cell['invalid_rule_rate_pre_filter'])} | "
            f"{fmt(cell['invalid_rule_rate_selected'])} | {fmt(cell['qini'])} |"
        )
    if factorial.get("reading"):
        lines += ["", f"> {factorial['reading']}", ""]
    lines += [
        "命名区分：消融表里的 `marshecho_no_gate` 是**训练时就没有门**的模型；"
        "`eg-chpn-simulation-v2.0.json` 里的 `marshecho_shipped_gate_off_infer` 是**同一份出厂权重在推理时关门**。两者是不同干预，不可混用。",
        "",
        "**诚实结论**：可学习证据门只能压低过滤前非法选择率；把非法选择降到 0 的是"
        "“确定性语义硬掩码 + 资格过滤”。因此平台侧的治理保证来自门禁与过滤（OC-DRUP 命题 1），"
        "不得写成“神经网络自己学会了拒绝非法动作”。",
        "",
        *gate_ab_section(gate_ab),
        *gate_full_section(gate_full),
        *dr_section(dr_ab),
        *ensemble_section(ensemble),
        *scaling_section(scaling),
        *defect_section(defect),
        *recipe_ab_section(recipe_ab),
        "## 5 约束可行性与策略层",
        "",
    ]
    if constraints:
        lines += [
            f"- 拉格朗日乘子上界观测：λ_budget max = {fmt(constraints.get('max_lambda_budget'), 2)}",
            "- 部署计划走精确投影（贪心 + 一换一），`/api/algorithms/marshecho/plan` 的 `constraint_violations` 恒为空；"
            "软松弛仅用于训练信号，饱和时由投影反标纠正。",
        ]
    lines += [
        "",
        "## 6 可复制性与数值一致性",
        "",
    ]
    if parity.get("available"):
        lines += [
            f"- torch ↔ NumPy 前向最大绝对误差：{parity['max_abs_difference']}（容差 {parity['tolerance']}）",
            f"- 权重 sha256：`{parity['weights_sha256']}`",
            f"- 参数量：{parity['parameters']}；权重体积：{parity['weights_bytes']} 字节",
            "- 推理侧零 torch 依赖：镜像与 CI 均无 torch，`tests/test_eg_chpn_parity.py` 用冻结夹具验证同一函数。",
        ]
    lines += [
        "",
        "## 7 教师蒸馏（证据门 r_e）",
        "",
    ]
    probe = teacher.get("probe", {})
    if probe:
        lines += [
            f"- 判旗准确率（阈值 {probe.get('threshold')}）：{probe.get('flag_decision_accuracy')}",
            f"- 与文本可判定参考的 Spearman：{probe.get('spearman_vs_reference')}；MAE：{probe.get('mean_abs_error')}",
            f"- 硬阻断规则平均 r_e：{probe.get('mean_agreement_hard_block')}；软规则平均：{probe.get('mean_agreement_soft_rule')}",
            f"- 缓存 sha256：`{teacher.get('cache', {}).get('sha256')}`（{teacher.get('cache', {}).get('rows')} 行）",
            "- 来源为云端编码代理单次离线生成，**不可复跑**，故以冻存文件 + SHA-256 发布；教师输出永不作为增量效应标签。",
        ]
    lines += [
        "",
        "## 8 明确排除与局限",
        "",
        "- causal forest 与完整 HGT 未实现（依赖不可用），未以近似版本冒充基线。",
        "- 模拟器已知潜在结果函数：无法检验未测混淆、策略干扰、延迟转化、库存截断与渠道送达失败。",
        "- 反事实监督依赖 5% 随机留出，这是模拟器便利；生产环境必须替换为真实 A/B 留出。",
        "- 置信区间为种子级与测试客群配对 bootstrap，不是线上用户级因果区间。",
        "- 在完成系统文献检索与最近方法差异表之前，不使用 novel / first 表述。",
        "",
        *before_after_section(ablation),
        "## 9 复现命令",
        "",
        "```bash",
        "bash research/egchpn_torch/launch_sweep.sh            # 阶段一扫描",
        "bash scripts/continue_training.sh                      # 阶段二/三续训与重导出",
        "python research/egchpn_torch/export_weights.py         # 导出 .npz + parity 夹具",
        "python scripts/select_best_checkpoint.py --export      # 按验证损失选出厂检查点",
        "python scripts/build_marshecho_report.py               # 出表",
        "python scripts/verify_marshecho_v2.py                  # 不变量校验",
        "python scripts/package_marshecho_bundle.py             # 可复制离线包",
        "python -m pytest -q                                    # 无 torch 全量回归",
        "```",
    ]
    target = OUT / "marshecho-report-v2.0.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
