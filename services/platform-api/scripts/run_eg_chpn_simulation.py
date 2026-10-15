"""Synthetic temporal benchmark for the EG-CHPN research prototype.

The simulator deliberately hides route/product/evidence signals in ontology
nodes.  This tests whether the graph model can recover a heterogeneous
counterfactual signal that a customer-only tabular baseline cannot observe.
The output is a mechanism experiment, not an airline performance claim.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.algorithms.eg_chpn import EGCHPN  # noqa: E402
from app.algorithms.oth_gct import CausalSample, GraphEdge, OTHGCT  # noqa: E402


@dataclass
class Simulated:
    node_features: np.ndarray
    edges: list[GraphEdge]
    customer_nodes: np.ndarray
    days: np.ndarray
    treatment: np.ndarray
    outcome: np.ndarray
    y0: np.ndarray
    y1: np.ndarray
    eligible: np.ndarray
    evidence: np.ndarray


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def simulate(seed: int, n_customers: int = 1800) -> Simulated:
    rng = np.random.default_rng(seed)
    route_count, product_count, evidence_count = 36, 24, 18
    d = 6
    context_count = route_count + product_count + evidence_count
    customer_start = context_count
    node_features = np.zeros((context_count + n_customers, d), dtype=float)
    route_signal = rng.uniform(0.15, 0.95, route_count)
    product_fit = rng.uniform(0.15, 0.95, product_count)
    evidence_quality = rng.uniform(0.45, 0.99, evidence_count)
    for i, value in enumerate(route_signal):
        node_features[i] = [value, 0.1, 0.0, 1.0, 0.0, 0.0]
    for i, value in enumerate(product_fit):
        node_features[route_count + i] = [0.0, value, 0.0, 0.0, 1.0, 0.0]
    for i, value in enumerate(evidence_quality):
        node_features[route_count + product_count + i] = [0.0, 0.0, value, 0.0, 0.0, 1.0]

    customer_features = rng.uniform(0.0, 1.0, (n_customers, d))
    node_features[customer_start:] = customer_features
    route_ids = rng.integers(0, route_count, n_customers)
    product_ids = rng.integers(0, product_count, n_customers)
    evidence_ids = rng.integers(0, evidence_count, n_customers)
    edges: list[GraphEdge] = []
    for i in range(n_customers):
        target = customer_start + i
        route = int(route_ids[i])
        product = int(product_ids[i])
        evidence = int(evidence_ids[i])
        day_delta = float((i * 7 + seed) % 45)
        q = float(evidence_quality[evidence])
        edges.extend([
            GraphEdge(route, target, "concerns_route", day_delta, q),
            GraphEdge(route_count + product, target, "supports_product", day_delta / 2.0, q),
            GraphEdge(route_count + product_count + evidence, target, "has_evidence", day_delta, q),
        ])

    x = customer_features
    r = route_signal[route_ids]
    p = product_fit[product_ids]
    e = evidence_quality[evidence_ids]
    # The graph-only terms r, p and e are deliberately absent from x.
    baseline = 0.25 + 0.45 * x[:, 0] - 0.18 * x[:, 1] + 0.12 * x[:, 3] + 0.25 * r
    uplift = 0.18 + 0.34 * x[:, 0] - 0.16 * x[:, 1] + 0.42 * p + 0.30 * e + 0.35 * r * p
    y0 = baseline + rng.normal(0, 0.10, n_customers)
    y1 = baseline + uplift + rng.normal(0, 0.10, n_customers)
    propensity = _sigmoid(-0.55 + 0.8 * x[:, 0] + 0.25 * x[:, 1] + 0.15 * r)
    treatment = (rng.random(n_customers) < propensity).astype(int)
    outcome = np.where(treatment == 1, y1, y0)
    days = np.arange(n_customers) % 90
    eligible = (e >= 0.65) & (p >= 0.25)
    return Simulated(node_features, edges, np.arange(customer_start, customer_start + n_customers), days, treatment, outcome, y0, y1, eligible, e)


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float = 0.15) -> np.ndarray:
    a = np.column_stack([np.ones(len(x)), x])
    penalty = alpha * np.eye(a.shape[1])
    penalty[0, 0] = 0.0
    return np.linalg.solve(a.T @ a + penalty, a.T @ y)


def predict(beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ beta


def fit_tabular_uplift(sim: Simulated, train: np.ndarray, test: np.ndarray) -> np.ndarray:
    x = sim.node_features[sim.customer_nodes]
    # Use only the matching arm, not masked outcomes with artificial zeros.
    c0 = train[sim.treatment[train] == 0]
    c1 = train[sim.treatment[train] == 1]
    b0 = ridge_fit(x[c0], sim.outcome[c0], 0.2)
    b1 = ridge_fit(x[c1], sim.outcome[c1], 0.2)
    return predict(b1, x[test]) - predict(b0, x[test])


def fit_response_only(sim: Simulated, train: np.ndarray, test: np.ndarray) -> np.ndarray:
    x = sim.node_features[sim.customer_nodes]
    c1 = train[sim.treatment[train] == 1]
    b1 = ridge_fit(x[c1], sim.outcome[c1], 0.2)
    return predict(b1, x[test])


def fit_graph_uplift(sim: Simulated, train: np.ndarray, test: np.ndarray, *, evidence_gate: bool, seed: int) -> np.ndarray:
    edges = sim.edges if evidence_gate else [GraphEdge(e.source, e.target, e.relation, e.delta_days, 1.0) for e in sim.edges]
    samples = [CausalSample(int(sim.customer_nodes[i]), int(sim.treatment[i]), float(sim.outcome[i])) for i in train]
    if evidence_gate:
        model = EGCHPN(input_dim=sim.node_features.shape[1], hidden_dim=24, confidence_floor=0.65, seed=seed).fit(sim.node_features, edges, samples, ridge=0.03)
        return model.predict_uplift(sim.node_features, edges)[sim.customer_nodes[test]]
    model = OTHGCT(input_dim=sim.node_features.shape[1], hidden_dim=24, seed=seed).fit(sim.node_features, edges, samples, ridge=0.03)
    return model.predict_uplift(sim.node_features, edges)[sim.customer_nodes[test]]


def policy_metrics(sim: Simulated, test: np.ndarray, score: np.ndarray, *, enforce_eligibility: bool, top_fraction: float = 0.20) -> dict[str, float]:
    eligible = sim.eligible[test]
    ranked = np.argsort(np.where(eligible, score, -np.inf) if enforce_eligibility else score)[::-1]
    k = max(1, int(len(test) * top_fraction))
    selected = ranked[:k]
    selected_global = test[selected]
    true_uplift = sim.y1 - sim.y0
    selected_value = float(np.sum(np.where(sim.eligible[selected_global], true_uplift[selected_global] * 100.0 - 1.0, -50.0)))
    all_value = float(np.sum(true_uplift[test[eligible]] * 100.0 - 1.0))
    random_value = all_value * k / max(1, int(eligible.sum()))
    invalid = float(np.mean(~sim.eligible[selected_global]))
    ranking = true_uplift[test]
    rmse = float(np.sqrt(np.mean((score - ranking) ** 2)))
    # A normalized top-k gain is more interpretable than a raw policy value.
    top_true = float(np.mean(np.sort(true_uplift[test[eligible]])[-min(k, int(eligible.sum())):])) if eligible.any() else 0.0
    selected_mean = float(np.mean(true_uplift[selected_global]))
    return {"policy_value": selected_value, "random_policy_value": random_value, "policy_lift_vs_random": selected_value - random_value, "uplift_rmse": rmse, "topk_true_uplift": selected_mean, "oracle_topk_uplift": top_true, "invalid_selection_rate": invalid, "selected_count": float(k)}


def run_seed(seed: int) -> list[dict[str, float | int | str]]:
    sim = simulate(seed)
    train = np.flatnonzero(sim.days < 63)
    test = np.flatnonzero(sim.days >= 63)
    methods: list[tuple[str, Callable[[], np.ndarray]]] = [
        ("random_feasible", lambda: np.random.default_rng(seed + 100).normal(size=len(test))),
        ("response_only", lambda: fit_response_only(sim, train, test)),
        ("tabular_t_learner", lambda: fit_tabular_uplift(sim, train, test)),
        ("oth_gct_no_evidence_gate", lambda: fit_graph_uplift(sim, train, test, evidence_gate=False, seed=seed + 200)),
        ("eg_chpn_graph_evidence_gate", lambda: fit_graph_uplift(sim, train, test, evidence_gate=True, seed=seed + 200)),
    ]
    rows = []
    for name, fn in methods:
        score = fn()
        metrics = policy_metrics(sim, test, score, enforce_eligibility=name != "oth_gct_no_evidence_gate")
        rows.append({"seed": seed, "method": name, "train_n": len(train), "test_n": len(test), **metrics})
    return rows


def summarize(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    methods = sorted({str(row["method"]) for row in rows})
    result = []
    for method in methods:
        subset = [row for row in rows if row["method"] == method]
        item: dict[str, float | int | str] = {"method": method, "n_seeds": len(subset)}
        for metric in ["policy_value", "policy_lift_vs_random", "uplift_rmse", "topk_true_uplift", "invalid_selection_rate"]:
            values = np.asarray([float(row[metric]) for row in subset])
            mean = float(values.mean())
            ci = float(1.96 * values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
            item[f"{metric}_mean"] = mean
            item[f"{metric}_ci95"] = ci
        result.append(item)
    return result


def main() -> None:
    seeds = [13, 29, 41, 53, 67]
    rows = [row for seed in seeds for row in run_seed(seed)]
    summary = summarize(rows)
    out_dir = REPO / "docs" / "实验"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "eg-chpn-simulation-v1.0.csv"
    summary_path = out_dir / "eg-chpn-simulation-v1.0.json"
    table_path = out_dir / "eg-chpn-simulation-table-v1.0.md"
    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {"experiment": "EG-CHPN synthetic temporal benchmark", "synthetic": True, "seeds": seeds, "n_rows": len(rows), "data_generation": {"customers_per_seed": 1800, "train_days": "0-62", "test_days": "63-89", "hidden_graph_terms": "route × product and evidence quality affect uplift but are absent from customer-only features"}, "summary": summary}
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["| method | policy value mean | 95% CI half-width | uplift RMSE | top-k true uplift | invalid selection |", "|---|---:|---:|---:|---:|---:|"]
    for item in summary:
        lines.append(f"| {item['method']} | {float(item['policy_value_mean']):.3f} | ±{float(item['policy_value_ci95']):.3f} | {float(item['uplift_rmse_mean']):.4f} | {float(item['topk_true_uplift_mean']):.4f} | {float(item['invalid_selection_rate_mean']):.3f} |")
    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"raw={raw_path}")
    print(f"summary={summary_path}")
    print(f"table={table_path}")


if __name__ == "__main__":
    main()
