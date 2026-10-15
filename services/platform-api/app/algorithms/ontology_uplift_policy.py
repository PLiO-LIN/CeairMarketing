"""Ontology-constrained uplift policy optimisation.

The module deliberately has no ML dependency.  It is a small, deterministic
reference implementation intended to be wrapped by a governed platform tool.
It separates three decisions that are often mixed together in marketing
systems: eligibility (the ontology contract), incremental response (causal
estimation), and allocation (a constrained policy problem).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, sqrt
from random import Random
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Action:
    """A possible intervention for one aggregate customer and one channel."""

    action_id: str
    customer_id: str
    channel: str
    product_id: str
    margin_yuan: float
    contact_cost_yuan: float
    evidence_confidence: float
    eligibility: str = "eligible"  # eligible, pending, ineligible
    frequency_group: str = "default"


@dataclass(frozen=True)
class Candidate:
    """An observed historical action used for policy learning.

    ``treatment`` is one for a delivered intervention and zero for a control
    observation.  ``outcome`` is the net contribution observed in the window.
    ``features`` must be precomputed from the frozen audience snapshot and
    ontology paths; the algorithm never infers business meaning from text.
    """

    action: Action
    features: tuple[float, ...]
    treatment: int
    outcome: float
    propensity: float


@dataclass(frozen=True)
class ScoredAction:
    action: Action
    baseline: float
    treated: float
    uplift: float
    value: float
    reason: str


@dataclass
class PolicyResult:
    selected: list[ScoredAction]
    rejected: list[tuple[str, str]]
    objective_value: float
    diagnostics: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    policy_value: float
    standard_error: float
    effective_sample_size: float
    treated_rate: float


class _Ridge:
    """Tiny coordinate-descent ridge model for dependency-free reproducibility."""

    def __init__(self, dimension: int, alpha: float = 1.0) -> None:
        self.weights = [0.0] * (dimension + 1)
        self.alpha = alpha

    def fit(self, rows: Sequence[tuple[Sequence[float], float]], steps: int = 900) -> None:
        if not rows:
            return
        scale = max(1.0, max(sum(abs(x) for x in row[0]) for row in rows))
        rate = 0.035 / scale
        for _ in range(steps):
            gradients = [0.0] * len(self.weights)
            for x, y in rows:
                z = self.weights[0] + sum(w * v for w, v in zip(self.weights[1:], x))
                error = z - y
                gradients[0] += error
                for j, value in enumerate(x, 1):
                    gradients[j] += error * value
            n = float(len(rows))
            self.weights[0] -= rate * gradients[0] / n
            for j in range(1, len(self.weights)):
                self.weights[j] -= rate * (gradients[j] / n + self.alpha * self.weights[j])

    def predict(self, x: Sequence[float]) -> float:
        return self.weights[0] + sum(w * v for w, v in zip(self.weights[1:], x))


def _fit_response_models(history: Sequence[Candidate], dimension: int) -> tuple[_Ridge, _Ridge]:
    treated = [(item.features, item.outcome) for item in history if item.treatment == 1]
    control = [(item.features, item.outcome) for item in history if item.treatment == 0]
    if not treated or not control:
        raise ValueError("历史样本必须同时包含 treatment=1 和 treatment=0")
    m1, m0 = _Ridge(dimension, alpha=0.08), _Ridge(dimension, alpha=0.08)
    m1.fit(treated)
    m0.fit(control)
    return m0, m1


def _eligibility(action: Action) -> tuple[bool, str]:
    if action.eligibility != "eligible":
        return False, f"ontology_gate:{action.eligibility}"
    if not (0.0 <= action.evidence_confidence <= 1.0):
        return False, "invalid_evidence_confidence"
    return True, "eligible_path_verified"


def _select(actions: Sequence[ScoredAction], budget: float, channel_caps: dict[str, int], max_per_group: int) -> list[ScoredAction]:
    """Greedy primal solution followed by pairwise exchange improvement.

    The exchange step fixes the most common greedy failure: a low-cost action
    can block a higher-value action in a scarce channel.  For a production
    deployment the same objective can be handed to an integer solver; this
    implementation remains portable for local experiments and CI.
    """
    selected: list[ScoredAction] = []
    used_budget = 0.0
    by_customer: set[str] = set()
    by_group: dict[str, int] = {}
    remaining = sorted(actions, key=lambda x: (x.value / max(x.action.contact_cost_yuan, 0.01), x.value), reverse=True)
    for item in remaining:
        a = item.action
        if a.customer_id in by_customer or by_group.get(a.frequency_group, 0) >= max_per_group:
            continue
        if sum(s.action.channel == a.channel for s in selected) >= channel_caps.get(a.channel, 0):
            continue
        if used_budget + a.contact_cost_yuan > budget or item.value <= 0:
            continue
        selected.append(item)
        used_budget += a.contact_cost_yuan
        by_customer.add(a.customer_id)
        by_group[a.frequency_group] = by_group.get(a.frequency_group, 0) + 1

    # One-for-one exchange preserves all hard constraints and improves value.
    selected_ids = {x.action.action_id for x in selected}
    for incoming in sorted(actions, key=lambda x: x.value, reverse=True):
        if incoming.action.action_id in selected_ids:
            continue
        for idx, outgoing in enumerate(selected):
            if incoming.value <= outgoing.value:
                break
            trial = selected[:idx] + [incoming] + selected[idx + 1 :]
            if _feasible(trial, budget, channel_caps, max_per_group) and sum(x.value for x in trial) > sum(x.value for x in selected):
                selected = trial
                selected_ids = {x.action.action_id for x in selected}
                break
    return selected


def _feasible(items: Sequence[ScoredAction], budget: float, channel_caps: dict[str, int], max_per_group: int) -> bool:
    if sum(x.action.contact_cost_yuan for x in items) > budget + 1e-9:
        return False
    if len({x.action.customer_id for x in items}) != len(items):
        return False
    if any(sum(x.action.channel == channel for x in items) > cap for channel, cap in channel_caps.items()):
        return False
    groups: dict[str, int] = {}
    for x in items:
        groups[x.action.frequency_group] = groups.get(x.action.frequency_group, 0) + 1
    return max(groups.values(), default=0) <= max_per_group


def fit_and_optimize(
    history: Sequence[Candidate],
    actions: Sequence[Action],
    *,
    budget: float,
    channel_caps: dict[str, int],
    max_per_frequency_group: int = 1000000,
    confidence_floor: float = 0.65,
) -> PolicyResult:
    """Estimate uplift and return a governed, budget-feasible intervention set.

    The score is ``confidence × (m1-m0) × margin - contact_cost``.  Confidence
    attenuates uncertain evidence; it never turns an ineligible ontology path
    into an eligible one.  Customers are treated as aggregate IDs, so no
    individual passenger data is required by the algorithm.
    """
    if not history:
        raise ValueError("history cannot be empty")
    dimension = len(history[0].features)
    if any(len(x.features) != dimension for x in history):
        raise ValueError("历史样本特征维度不一致")
    m0, m1 = _fit_response_models(history, dimension)
    scored: list[ScoredAction] = []
    rejected: list[tuple[str, str]] = []
    for action in actions:
        ok, reason = _eligibility(action)
        if not ok:
            rejected.append((action.action_id, reason))
            continue
        if action.evidence_confidence < confidence_floor:
            rejected.append((action.action_id, "evidence_below_floor"))
            continue
        # The feature vector is supplied by the frozen audience/ontology view.
        # A deterministic fallback keeps the pure function usable in adapters.
        matching = next((x for x in history if x.action.customer_id == action.customer_id), None)
        if matching is None:
            rejected.append((action.action_id, "missing_frozen_snapshot_features"))
            continue
        baseline, treated = m0.predict(matching.features), m1.predict(matching.features)
        uplift = max(-1.0, treated - baseline)
        value = action.evidence_confidence * uplift * action.margin_yuan - action.contact_cost_yuan
        scored.append(ScoredAction(action, baseline, treated, uplift, value, "uplift×margin×evidence−cost"))
    selected = _select(scored, budget, channel_caps, max_per_frequency_group)
    return PolicyResult(
        selected=selected,
        rejected=rejected,
        objective_value=sum(x.value for x in selected),
        diagnostics={
            "candidate_count": len(actions),
            "eligible_count": len(scored),
            "selected_count": len(selected),
            "budget_used": round(sum(x.action.contact_cost_yuan for x in selected), 6),
            "mean_selected_uplift": round(sum(x.uplift for x in selected) / len(selected), 6) if selected else 0.0,
        },
    )


def doubly_robust_policy_value(history: Sequence[Candidate], selected_action_ids: set[str], *, clip: float = 0.05) -> EvaluationResult:
    """Off-policy evaluation using a self-normalised doubly robust score."""
    if not history:
        raise ValueError("history cannot be empty")
    dimension = len(history[0].features)
    m0, m1 = _fit_response_models(history, dimension)
    contributions: list[float] = []
    treated_rate = 0
    for item in history:
        p = min(1.0 - clip, max(clip, item.propensity))
        target = 1 if item.action.action_id in selected_action_ids else 0
        mu = m1.predict(item.features) if target else m0.predict(item.features)
        observed_mu = m1.predict(item.features) if item.treatment else m0.predict(item.features)
        correction = (item.treatment == target) * (item.outcome - observed_mu) / (p if item.treatment else 1.0 - p)
        contributions.append(mu + correction)
        treated_rate += target
    mean = sum(contributions) / len(contributions)
    variance = sum((x - mean) ** 2 for x in contributions) / max(1, len(contributions) - 1)
    weights = [1.0 / min(1.0 - clip, max(clip, item.propensity)) for item in history]
    ess = sum(weights) ** 2 / sum(x * x for x in weights)
    return EvaluationResult(mean, sqrt(variance / len(contributions)), ess, treated_rate / len(history))


def synthetic_history(seed: int = 7, n: int = 1200) -> tuple[list[Candidate], list[Action]]:
    """Create a reproducible benchmark with heterogeneous treatment effects."""
    rng = Random(seed)
    history: list[Candidate] = []
    actions: list[Action] = []
    for i in range(n):
        x = (rng.random(), rng.random(), rng.random())
        propensity = 0.25 + 0.5 * x[0]
        treatment = int(rng.random() < propensity)
        true_uplift = 0.45 * x[0] + 0.8 * x[1] - 0.25 * x[2]
        baseline = 0.15 + 0.45 * x[0] + 0.15 * x[2]
        outcome = baseline + treatment * true_uplift + rng.gauss(0, 0.18)
        a = Action(f"hist-{i}", f"c-{i}", "App" if i % 2 else "WeChat", "PKG-BAG", 100.0 + 30.0 * x[1], 0.8, 0.9, frequency_group=f"g-{i % 20}")
        history.append(Candidate(a, x, treatment, outcome, propensity))
        if i < n // 5:
            # Reuse the historical action id for off-policy evaluation.  A
            # real adapter would use the stable business intervention id.
            actions.append(Action(f"hist-{i}", f"c-{i}", "App" if i % 3 else "SMS", "PKG-BAG", 100.0 + 30.0 * x[1], 0.8, 0.75 + 0.2 * x[0], frequency_group=f"g-{i % 20}"))
    return history, actions
