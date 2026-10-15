"""Reproducible benchmark for the ontology-constrained uplift policy.

Run from ``services/platform-api`` or the repository root:
``python -B scripts/run_ontology_uplift_experiment.py``.
The data are synthetic and are explicitly labelled as such; they validate the
algorithmic mechanism, not airline business performance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.algorithms.ontology_uplift_policy import (  # noqa: E402
    Action,
    Candidate,
    _fit_response_models,
    fit_and_optimize,
    synthetic_history,
)


def true_uplift(features: tuple[float, ...]) -> float:
    return 0.45 * features[0] + 0.8 * features[1] - 0.25 * features[2]


def feasible_value(selected: list[Action], feature_by_customer: dict[str, tuple[float, ...]]) -> float:
    return sum(true_uplift(feature_by_customer[a.customer_id]) * a.margin_yuan - a.contact_cost_yuan for a in selected)


def response_only_policy(history: list[Candidate], actions: list[Action], budget: float, caps: dict[str, int]) -> list[Action]:
    m0, m1 = _fit_response_models(history, len(history[0].features))
    features = {x.action.customer_id: x.features for x in history}
    ranked = sorted(
        actions,
        key=lambda a: m1.predict(features[a.customer_id]) * a.margin_yuan - a.contact_cost_yuan,
        reverse=True,
    )
    result: list[Action] = []
    spend = 0.0
    for action in ranked:
        if action.customer_id in {x.customer_id for x in result}:
            continue
        if sum(x.channel == action.channel for x in result) >= caps.get(action.channel, 0):
            continue
        if spend + action.contact_cost_yuan > budget:
            continue
        result.append(action)
        spend += action.contact_cost_yuan
    return result


def random_policy(actions: list[Action], budget: float, caps: dict[str, int], seed: int = 19) -> list[Action]:
    rng = Random(seed)
    shuffled = actions[:]
    rng.shuffle(shuffled)
    result: list[Action] = []
    spend = 0.0
    for action in shuffled:
        if action.customer_id in {x.customer_id for x in result}:
            continue
        if sum(x.channel == action.channel for x in result) >= caps.get(action.channel, 0):
            continue
        if spend + action.contact_cost_yuan > budget:
            continue
        result.append(action)
        spend += action.contact_cost_yuan
    return result


def main() -> None:
    history, actions = synthetic_history(seed=7, n=1200)
    # Add three candidates that violate the semantic contract.  They must be
    # rejected before uplift scores are allowed to influence the policy.
    actions += [
        Action("bad-pending", "c-0", "App", "PKG-BAG", 130.0, 0.8, 0.99, "pending"),
        Action("bad-low-evidence", "c-1", "App", "PKG-BAG", 130.0, 0.8, 0.40),
        Action("bad-direction", "c-2", "App", "PKG-BAG", 130.0, 0.8, 0.99, "ineligible"),
    ]
    budget = 42.0
    caps = {"App": 28, "SMS": 14, "WeChat": 14}
    features = {x.action.customer_id: x.features for x in history}
    result = fit_and_optimize(history, actions, budget=budget, channel_caps=caps, max_per_frequency_group=3)
    response = response_only_policy(history, actions[: len(actions) - 3], budget, caps)
    random = random_policy(actions[: len(actions) - 3], budget, caps)

    payload = {
        "algorithm": "Ontology-Constrained Doubly-Robust Uplift Policy (OC-DRUP)",
        "seed": 7,
        "synthetic": True,
        "data_generation": {"history_rows": len(history), "action_rows": len(actions), "true_uplift": "0.45*x1 + 0.80*x2 - 0.25*x3"},
        "constraints": {"budget_yuan": budget, "channel_caps": caps, "max_per_frequency_group": 3, "evidence_floor": 0.65},
        "oc_drup": {**result.diagnostics, "objective_value": round(result.objective_value, 6), "true_policy_value": round(feasible_value([x.action for x in result.selected], features), 6), "rejected": result.rejected},
        "response_only": {"selected_count": len(response), "true_policy_value": round(feasible_value(response, features), 6)},
        "random_feasible": {"selected_count": len(random), "true_policy_value": round(feasible_value(random, features), 6)},
    }
    out = REPO / "docs" / "实验" / "ontology-uplift-policy-v1.0.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
