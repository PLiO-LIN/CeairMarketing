"""Turn Marsh-Echo uplift estimates into a governed, feasible contact plan.

The optimisation itself is reused verbatim from :mod:`ontology_uplift_policy`
(greedy primal solution plus one-for-one exchange, with the feasibility
checker used as an assertion), so the platform has exactly one implementation
of the budget / channel / frequency contract.  Uplift comes from the model;
eligibility and constraints never do.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ontology_uplift_policy import Action, ScoredAction, _feasible, _select


@dataclass(frozen=True)
class UpliftItem:
    action_id: str
    customer_id: str
    channel: str
    product_id: str
    uplift: float
    evidence_confidence: float
    status: str
    margin_yuan: float = 120.0
    contact_cost_yuan: float = 1.0
    frequency_group: str = "default"


def plan_from_uplift(
    items: list[UpliftItem],
    *,
    budget: float,
    channel_caps: dict[str, int],
    max_per_group: int,
    confidence_floor: float = 0.65,
) -> dict[str, object]:
    """Score model output and select a plan that satisfies every hard cap."""

    scored: list[ScoredAction] = []
    rejected: list[tuple[str, str]] = []
    for item in items:
        if item.status != "eligible":
            rejected.append((item.action_id, f"ontology_gate:{item.status}"))
            continue
        if item.evidence_confidence < confidence_floor:
            rejected.append((item.action_id, "evidence_below_floor"))
            continue
        action = Action(
            action_id=item.action_id,
            customer_id=item.customer_id,
            channel=item.channel,
            product_id=item.product_id,
            margin_yuan=item.margin_yuan,
            contact_cost_yuan=item.contact_cost_yuan,
            evidence_confidence=item.evidence_confidence,
            eligibility=item.status,
            frequency_group=item.frequency_group,
        )
        value = item.evidence_confidence * max(0.0, item.uplift) * item.margin_yuan - item.contact_cost_yuan
        scored.append(ScoredAction(action, item.uplift, item.uplift, item.uplift, value, "uplift×margin×evidence−cost"))
    selected = _select(scored, budget, channel_caps, max_per_group)
    violations: list[str] = []
    if selected and not _feasible(selected, budget, channel_caps, max_per_group):
        violations.append("projection_infeasible")
    return {
        "selected": selected,
        "rejected": rejected,
        "objective_value": sum(item.value for item in selected),
        "budget_used": round(sum(item.action.contact_cost_yuan for item in selected), 6),
        "constraint_violations": violations,
        "candidate_count": len(items),
        "eligible_count": len(scored),
    }
