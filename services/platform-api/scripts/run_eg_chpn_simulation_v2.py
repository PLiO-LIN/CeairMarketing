"""EG-CHPN v2 synthetic temporal benchmark (numpy only).

Extends the v1 benchmark with a real eligibility hypergraph, two separate
eligibility notions (observable rule status vs hidden product fit), a
randomized holdout that is the only place true individual treatment effects
are visible to training, and a 2x2 factorial {learned gate, no gate} x
{oracle rule filter on, off} so the safety contribution of the evidence gate
is measured instead of assumed.  Invalid-selection rates are reported
*before* any selector mask is applied.

This script must run without torch: trained-model rows are loaded from the
exported ``marshecho_v2_0.npz`` through the numpy runtime and are skipped
gracefully when the artifact is absent.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.algorithms.hypergraph_spec import (  # noqa: E402
    ELIGIBILITY_HOPS,
    FEATURE_DIM,
    Hyperedge,
    HypergraphSpec,
    STATUS_ELIGIBLE,
    STATUS_INELIGIBLE,
    STATUS_PENDING,
    clique_expansion,
)
from app.algorithms.oth_gct import CausalSample  # noqa: E402

_V1_PATH = ROOT / "scripts" / "run_eg_chpn_simulation.py"
_spec = importlib.util.spec_from_file_location("eg_chpn_v1", _V1_PATH)
_v1 = importlib.util.module_from_spec(_spec)
sys.modules["eg_chpn_v1"] = _v1
assert _spec.loader is not None
_spec.loader.exec_module(_v1)
ridge_fit = _v1.ridge_fit
predict = _v1.predict

SEEDS = [13, 29, 41, 53, 67, 83, 97, 101, 113, 127]
TRAIN_DAYS, TEST_DAYS = 63, 90
HOLDOUT_FRACTION = 0.05


@dataclass
class SimV2:
    spec: HypergraphSpec
    customer_nodes: np.ndarray
    days: np.ndarray
    treatment: np.ndarray
    outcome: np.ndarray
    y0: np.ndarray
    y1: np.ndarray
    eligible_rule: np.ndarray
    eligible_latent: np.ndarray
    in_holdout: np.ndarray
    propensity: np.ndarray
    context: dict[str, np.ndarray]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def simulate(seed: int, n_customers: int = 1800, dgp: str = "v1") -> SimV2:
    if dgp not in ("v1", "v2"):
        raise ValueError("dgp must be v1 or v2")
    rng = np.random.default_rng(seed)
    counts = {"Route": 36, "Flight": 24, "Cabin": 12, "Fare": 20, "Product": 24, "ProductPackage": 24, "BusinessRule": 16, "Evidence": 18}
    route_signal = rng.uniform(0.15, 0.95, counts["Route"])
    flight_route = rng.integers(0, counts["Route"], counts["Flight"])
    cabin_flight = rng.integers(0, counts["Flight"], counts["Cabin"])
    fare_cabin = rng.integers(0, counts["Cabin"], counts["Fare"])
    product_fit = rng.uniform(0.15, 0.95, counts["Product"])
    fare_product = rng.integers(0, counts["Product"], counts["Fare"])
    package_product = rng.integers(0, counts["Product"], counts["ProductPackage"])
    rule_blocked = rng.random(counts["BusinessRule"]) < 0.15
    evidence_quality = rng.uniform(0.45, 0.99, counts["Evidence"])

    node_types: list[str] = []
    rows: list[list[float]] = []
    offsets: dict[str, int] = {}
    for name, count in counts.items():
        offsets[name] = len(node_types)
        for _ in range(count):
            node_types.append(name)
            rows.append([0.0] * FEATURE_DIM)
    for i, value in enumerate(route_signal):
        rows[offsets["Route"] + i][0] = value
    for i, value in enumerate(product_fit):
        rows[offsets["Product"] + i][1] = value
    for i, value in enumerate(evidence_quality):
        rows[offsets["Evidence"] + i][2] = value
    for i in range(counts["BusinessRule"]):
        rows[offsets["BusinessRule"] + i][5] = 0.9 if rule_blocked[i] else 0.2

    customer_features = rng.uniform(0.0, 1.0, (n_customers, FEATURE_DIM))
    customer_start = len(node_types)
    for i in range(n_customers):
        node_types.append("AudienceSnapshot")
        rows.append(list(customer_features[i]))

    route_ids = rng.integers(0, counts["Route"], n_customers)
    package_ids = rng.integers(0, counts["ProductPackage"], n_customers)
    product_ids = package_product[package_ids]
    flight_ids = np.array([int(rng.choice(np.flatnonzero(flight_route == r))) if (flight_route == r).any() else 0 for r in route_ids])
    cabin_ids = np.array([int(rng.choice(np.flatnonzero(cabin_flight == f))) if (cabin_flight == f).any() else 0 for f in flight_ids])
    fare_ids = np.empty(n_customers, dtype=int)
    for i in range(n_customers):
        candidates = np.flatnonzero((fare_cabin == cabin_ids[i]) & (fare_product == product_ids[i]))
        if candidates.size == 0:
            candidates = np.flatnonzero(fare_cabin == cabin_ids[i])
        if candidates.size == 0:
            candidates = np.flatnonzero(fare_product == product_ids[i])
        fare_ids[i] = int(rng.choice(candidates)) if candidates.size else int(rng.integers(0, counts["Fare"]))
    evidence_ids = rng.integers(0, counts["Evidence"], n_customers)
    rule_ids = rng.integers(0, counts["BusinessRule"], n_customers)

    hyperedges: list[Hyperedge] = []
    for i in range(n_customers):
        members = {
            "ProductPackage": offsets["ProductPackage"] + int(package_ids[i]),
            "AudienceSnapshot": customer_start + i,
            "Product": offsets["Product"] + int(product_ids[i]),
            "Fare": offsets["Fare"] + int(fare_ids[i]),
            "Cabin": offsets["Cabin"] + int(cabin_ids[i]),
            "Flight": offsets["Flight"] + int(flight_ids[i]),
            "Route": offsets["Route"] + int(route_ids[i]),
            "Evidence": offsets["Evidence"] + int(evidence_ids[i]),
            "BusinessRule": offsets["BusinessRule"] + int(rule_ids[i]),
        }
        quality = float(evidence_quality[evidence_ids[i]])
        blocked = bool(rule_blocked[rule_ids[i]])
        status = STATUS_INELIGIBLE if blocked else (STATUS_ELIGIBLE if quality >= 0.65 else STATUS_PENDING)
        member_types = tuple(node_types[index] for index in members.values())
        hyperedges.append(
            Hyperedge(
                member_nodes=tuple(members.values()),
                member_types=member_types,
                hops=ELIGIBILITY_HOPS,
                status=status,
                confidence=max(quality, 1e-3),
                freshness_days=float((i * 7 + seed) % 45),
                rule_agreement=0.1 if blocked else 0.9,
                source_stability=max(quality, 1e-3),
                delta_days=float((i * 7 + seed) % 45),
            )
        )

    features = np.asarray(rows, dtype=float)
    spec = HypergraphSpec(features, tuple(node_types), tuple(hyperedges))

    x = customer_features
    r = route_signal[route_ids]
    p = product_fit[product_ids]
    e = evidence_quality[evidence_ids]
    baseline = 0.25 + 0.45 * x[:, 0] - 0.18 * x[:, 1] + 0.12 * x[:, 3] + 0.25 * r
    if dgp == "v1":
        uplift = 0.18 + 0.34 * x[:, 0] - 0.16 * x[:, 1] + 0.42 * p + 0.30 * e + 0.35 * r * p
    else:
        uplift = 0.18 + 0.34 * x[:, 0] - 0.16 * x[:, 1] + 0.42 * p + 0.30 * e + 0.45 * np.tanh(2.0 * (e * p - 0.25))
    y0 = baseline + rng.normal(0, 0.10, n_customers)
    y1 = baseline + uplift + rng.normal(0, 0.10, n_customers)
    propensity_base = _sigmoid(-0.55 + 0.8 * x[:, 0] + 0.25 * x[:, 1] + 0.15 * r)
    in_holdout = rng.random(n_customers) < HOLDOUT_FRACTION
    propensity = np.where(in_holdout, 0.5, propensity_base)
    treatment = (rng.random(n_customers) < propensity).astype(int)
    outcome = np.where(treatment == 1, y1, y0)
    days = np.arange(n_customers) % TEST_DAYS
    eligible_rule = (e >= 0.65) & ~rule_blocked[rule_ids]
    eligible_latent = p >= 0.25
    context = {
        "route_signal": r,
        "product_fit": p,
        "evidence_quality": e,
        "rule_blocked": rule_blocked[rule_ids],
    }
    return SimV2(spec, np.arange(customer_start, customer_start + n_customers), days, treatment, outcome, y0, y1, eligible_rule, eligible_latent, in_holdout, propensity, context)


def _uplift_scores_numpy(sim: SimV2, train: np.ndarray, test: np.ndarray, method: str) -> np.ndarray:
    x = sim.spec.node_features[sim.customer_nodes]
    t = sim.treatment
    y = sim.outcome
    if method == "random_feasible":
        return np.random.default_rng(int(train[0]) + 100).normal(size=len(test))
    if method == "response_only":
        c1 = train[t[train] == 1]
        return predict(ridge_fit(x[c1], y[c1], 0.2), x[test])
    if method == "tabular_t_learner":
        c0 = train[t[train] == 0]
        c1 = train[t[train] == 1]
        return predict(ridge_fit(x[c1], y[c1], 0.2), x[test]) - predict(ridge_fit(x[c0], y[c0], 0.2), x[test])
    if method == "s_learner":
        stacked = np.column_stack([x, t.astype(float)])
        beta = ridge_fit(stacked[train], y[train], 0.2)
        ones = np.ones(len(test))
        return predict(beta, np.column_stack([x[test], ones])) - predict(beta, np.column_stack([x[test], 0.0 * ones]) )
    if method == "x_learner":
        c0 = train[t[train] == 0]
        c1 = train[t[train] == 1]
        mu0 = ridge_fit(x[c0], y[c0], 0.2)
        mu1 = ridge_fit(x[c1], y[c1], 0.2)
        d1 = y[c1] - predict(mu0, x[c1])
        d0 = predict(mu1, x[c0]) - y[c0]
        tau1 = ridge_fit(x[c1], d1, 0.2)
        tau0 = ridge_fit(x[c0], d0, 0.2)
        e = np.clip(sim.propensity[test], 0.05, 0.95)
        return e * predict(tau0, x[test]) + (1.0 - e) * predict(tau1, x[test])
    if method == "dr_learner":
        c0 = train[t[train] == 0]
        c1 = train[t[train] == 1]
        mu0 = ridge_fit(x[c0], y[c0], 0.2)
        mu1 = ridge_fit(x[c1], y[c1], 0.2)
        e = np.clip(sim.propensity[train], 0.05, 0.95)
        pseudo = predict(mu1, x[train]) - predict(mu0, x[train]) + t[train] * (y[train] - predict(mu1, x[train])) / e - (1 - t[train]) * (y[train] - predict(mu0, x[train])) / (1 - e)
        return predict(ridge_fit(x[train], pseudo, 0.2), x[test])
    raise ValueError(f"unknown numpy method {method}")


def _qini_auuc(score: np.ndarray, true_uplift: np.ndarray) -> tuple[float, float]:
    order = np.argsort(-score)
    gains = np.cumsum(true_uplift[order])
    n = len(order)
    curve = gains / np.arange(1, n + 1) * np.arange(1, n + 1)
    auuc = float(np.trapezoid(np.concatenate([[0.0], gains]), dx=1.0) / n)
    random_auuc = float(gains[-1] / 2.0 / n)
    oracle_order = np.argsort(-true_uplift)
    oracle_gains = np.cumsum(true_uplift[oracle_order])
    oracle_auuc = float(np.trapezoid(np.concatenate([[0.0], oracle_gains]), dx=1.0) / n)
    denom = oracle_auuc - random_auuc
    qini = (auuc - random_auuc) / denom if abs(denom) > 1e-9 else 0.0
    return qini, auuc


def _brier_ece(pred_logit: np.ndarray | None, outcome: np.ndarray) -> tuple[float, float]:
    if pred_logit is None:
        return float("nan"), float("nan")
    p = _sigmoid(pred_logit)
    y = (outcome > np.median(outcome)).astype(float)
    brier = float(np.mean((p - y) ** 2))
    bins = np.linspace(0.0, 1.0, 11)
    idx = np.clip(np.digitize(p, bins[1:-1]), 0, 9)
    ece = 0.0
    for b in range(10):
        mask = idx == b
        if mask.any():
            ece += float(mask.mean() * abs(p[mask].mean() - y[mask].mean()))
    return brier, float(ece)


def policy_metrics_v2(
    sim: SimV2,
    test: np.ndarray,
    score: np.ndarray,
    *,
    selector: str = "oracle_rule",
    top_fraction: float = 0.20,
    factual_logit: np.ndarray | None = None,
) -> dict[str, float]:
    if selector not in ("none", "oracle_rule", "oracle_both"):
        raise ValueError("selector must be none, oracle_rule or oracle_both")
    rule_ok = sim.eligible_rule[test]
    both_ok = rule_ok & sim.eligible_latent[test]
    ranked_raw = np.argsort(-score)
    k = max(1, int(len(test) * top_fraction))
    raw_top = ranked_raw[:k]
    invalid_rule_pre = float(np.mean(~rule_ok[raw_top]))
    invalid_latent_pre = float(np.mean(~sim.eligible_latent[test][raw_top]))
    masked = score.copy()
    if selector == "oracle_rule":
        masked = np.where(rule_ok, masked, -np.inf)
    elif selector == "oracle_both":
        masked = np.where(both_ok, masked, -np.inf)
    selected = np.argsort(-masked)[:k]
    selected_global = test[selected]
    true_uplift = sim.y1 - sim.y0
    realized = np.where(sim.eligible_rule[selected_global] & sim.eligible_latent[selected_global], true_uplift[selected_global] * 100.0 - 1.0, -50.0)
    policy_value = float(np.sum(realized))
    qini, auuc = _qini_auuc(score, true_uplift[test])
    brier, ece = _brier_ece(factual_logit[selected] if factual_logit is not None else None, sim.outcome[selected_global])
    return {
        "policy_value": policy_value,
        "uplift_rmse": float(np.sqrt(np.mean((score - true_uplift[test]) ** 2))),
        "topk_true_uplift": float(np.mean(true_uplift[selected_global])),
        "invalid_rule_rate_pre_filter": invalid_rule_pre,
        "invalid_latent_rate_pre_filter": invalid_latent_pre,
        "invalid_rule_rate_selected": float(np.mean(~sim.eligible_rule[selected_global])),
        "qini": qini,
        "auuc": auuc,
        "brier": brier,
        "ece": ece,
        "selected_count": float(k),
    }


def bootstrap_policy_ci(sim: SimV2, test: np.ndarray, score: np.ndarray, selector: str, draws: int = 200, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        idx = rng.integers(0, len(test), len(test))
        if len(np.unique(idx)) < 2:
            continue
        values.append(policy_metrics_v2(sim, test[idx], score[idx], selector=selector)["policy_value"])
    arr = np.asarray(values, dtype=float)
    return float(1.96 * arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else 0.0


def _v1_frozen_scores(sim: SimV2, train: np.ndarray, test: np.ndarray, seed: int) -> np.ndarray:
    """The shipped v1 prototype (untrained attention + ridge causal heads).

    Evaluated on the identical v2 population so "is the new model better?" is
    answered on the same data instead of across two different simulators.
    """

    from app.algorithms.eg_chpn import EGCHPN
    from app.algorithms.hypergraph_spec import clique_expansion

    edges = clique_expansion(sim.spec)
    samples = [CausalSample(int(sim.customer_nodes[i]), int(sim.treatment[i]), float(sim.outcome[i])) for i in train]
    model = EGCHPN(input_dim=sim.spec.node_features.shape[1], hidden_dim=24, confidence_floor=0.65, seed=seed + 200)
    model.fit(sim.spec.node_features, edges, samples, ridge=0.03)
    uplift = model.predict_uplift(sim.spec.node_features, edges)
    return uplift[sim.customer_nodes[test]]


def _marshecho_rows(sim: SimV2, test: np.ndarray) -> list[tuple[str, np.ndarray, np.ndarray | None]]:
    try:
        from app.algorithms.eg_chpn_runtime import load_default_runtime
    except Exception:
        return []
    try:
        runtime = load_default_runtime()
    except Exception:
        return []
    rows: list[tuple[str, np.ndarray, np.ndarray | None]] = []
    # These two rows switch the gate off at inference time on the SAME shipped
    # weights; they are not the trained ``marshecho_no_gate`` ablation that the
    # sweep report evaluates.  Keep the names distinct so the two interventions
    # cannot be conflated in the artifacts.
    for label, use_gate in (("marshecho_shipped_gate_on", True), ("marshecho_shipped_gate_off_infer", False)):
        uplift, factual, _ = runtime.predict_from_spec(sim.spec, use_gate=use_gate, with_factual=True)
        rows.append((label, uplift[sim.customer_nodes[test]], factual[sim.customer_nodes[test]]))
    return rows


def run_seed(seed: int, dgp: str) -> list[dict[str, float | int | str]]:
    sim = simulate(seed, dgp=dgp)
    train = np.flatnonzero(sim.days < TRAIN_DAYS)
    test = np.flatnonzero(sim.days >= TRAIN_DAYS)
    rows: list[dict[str, float | int | str]] = []
    methods = ["random_feasible", "response_only", "tabular_t_learner", "s_learner", "x_learner", "dr_learner"]
    for method in methods:
        score = _uplift_scores_numpy(sim, train, test, method)
        for selector in ("none", "oracle_rule", "oracle_both"):
            metrics = policy_metrics_v2(sim, test, score, selector=selector)
            metrics["policy_value_ci95_boot"] = bootstrap_policy_ci(sim, test, score, selector, seed=seed)
            rows.append({"seed": seed, "dgp": dgp, "method": method, "gate": "na", "selector": selector, "train_n": len(train), "test_n": len(test), **metrics})
    try:
        v1_scores = _v1_frozen_scores(sim, train, test, seed)
        for selector in ("none", "oracle_rule", "oracle_both"):
            metrics = policy_metrics_v2(sim, test, v1_scores, selector=selector)
            metrics["policy_value_ci95_boot"] = bootstrap_policy_ci(sim, test, v1_scores, selector, seed=seed)
            rows.append({"seed": seed, "dgp": dgp, "method": "eg_chpn_v1_frozen", "gate": "learned", "selector": selector, "train_n": len(train), "test_n": len(test), **metrics})
    except Exception as exc:  # pragma: no cover - the v1 row is a convenience comparison
        print(f"v1 frozen comparison row skipped: {exc}")
    for label, score, factual in _marshecho_rows(sim, test):
        gate = "none" if label.endswith("gate_off_infer") else "learned"
        for selector in ("none", "oracle_rule", "oracle_both"):
            metrics = policy_metrics_v2(sim, test, score, selector=selector, factual_logit=factual)
            metrics["policy_value_ci95_boot"] = bootstrap_policy_ci(sim, test, score, selector, seed=seed)
            rows.append({"seed": seed, "dgp": dgp, "method": label, "gate": gate, "selector": selector, "train_n": len(train), "test_n": len(test), **metrics})
    return rows


def summarize(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    keys = sorted({(str(r["method"]), str(r["gate"]), str(r["selector"]), str(r["dgp"])) for r in rows})
    out = []
    for method, gate, selector, dgp in keys:
        subset = [r for r in rows if (str(r["method"]), str(r["gate"]), str(r["selector"]), str(r["dgp"])) == (method, gate, selector, dgp)]
        item: dict[str, float | int | str] = {"method": method, "gate": gate, "selector": selector, "dgp": dgp, "n_seeds": len(subset)}
        for metric in ["policy_value", "uplift_rmse", "topk_true_uplift", "invalid_rule_rate_pre_filter", "invalid_latent_rate_pre_filter", "invalid_rule_rate_selected", "qini", "auuc"]:
            values = np.asarray([float(r[metric]) for r in subset], dtype=float)
            item[f"{metric}_mean"] = float(values.mean())
            item[f"{metric}_ci95"] = float(1.96 * values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
        out.append(item)
    return out


def main() -> None:
    """Evaluate both pre-registered data-generating processes.

    The second DGP exists to detect architecture-overfit-to-one-generator; it
    has to actually be run, otherwise the guard is decorative.
    """

    OUT_DIR = REPO / "docs" / "实验"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for index, dgp in enumerate(("v1", "v2")):
        suffix = "" if index == 0 else ".dgp2"
        rows = [row for seed in SEEDS for row in run_seed(seed, dgp)]
        summary = summarize(rows)
        raw_path = OUT_DIR / f"eg-chpn-simulation-v2.0{suffix}.csv"
        summary_path = OUT_DIR / f"eg-chpn-simulation-v2.0{suffix}.json"
        table_path = OUT_DIR / f"eg-chpn-simulation-table-v2.0{suffix}.md"
        with raw_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        payload = {
            "experiment": "EG-CHPN v2 synthetic temporal benchmark (marshecho / 九皋)",
            "synthetic": True,
            "label": "流程验证（虚构）",
            "seeds": SEEDS,
            "dgp": dgp,
            "n_rows": len(rows),
            "design": {
                "factorial": "gate {learned, none} x selector {none, oracle_rule, oracle_both}",
                "invalid_rates": "reported pre-filter on the raw top-k",
                "holdout": f"{HOLDOUT_FRACTION} randomized holdout, propensity 0.5",
                "eligibility": "eligible_rule observable; eligible_latent hidden, feature-only",
                "runtime_rows": "marshecho_shipped_* switch the gate at inference time on the shipped weights; the trained no-gate model is evaluated in marshecho-ablation-v2.0.json",
            },
            "summary": summary,
        }
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["| method | gate | selector | policy value | CI | invalid rule (pre) | invalid latent (pre) | qini |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for item in summary:
            if item["selector"] != "oracle_rule":
                continue
            lines.append(
                f"| {item['method']} | {item['gate']} | {item['selector']} | {float(item['policy_value_mean']):.3f} | ±{float(item['policy_value_ci95']):.3f} | {float(item['invalid_rule_rate_pre_filter_mean']):.3f} | {float(item['invalid_latent_rate_pre_filter_mean']):.3f} | {float(item['qini_mean']):.3f} |"
            )
        table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(str(summary_path))
    print(json.dumps({"dgps": ["v1", "v2"], "artifacts": written}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
