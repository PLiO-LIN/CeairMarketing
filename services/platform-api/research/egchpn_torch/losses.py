"""Five-term training objective for Marsh-Echo (EG-CHPN v2).

L = L_factual + lb*L_balance + lc*L_counterfactual + le*L_evidence + lp*L_policy

L_counterfactual may touch true individual treatment effects only on the
randomized holdout; L_evidence is supervised on the observable ontology rule
status and never on the hidden product-fit quantity; L_policy carries the
budget and frequency-group constraints with projected dual ascent.
"""

from __future__ import annotations

import numpy as np
import torch


def factual_loss(out: dict[str, torch.Tensor], outcome: torch.Tensor, treatment: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    pred = torch.where(treatment > 0, out["y1"], out["y0"])
    return torch.mean((pred[mask] - outcome[mask]) ** 2)


def balance_loss(out: dict[str, torch.Tensor], treatment: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    treated = mask & (treatment > 0)
    control = mask & (treatment == 0)
    if not treated.any() or not control.any():
        return torch.zeros((), device=treatment.device)
    diff = out["h1"][treated].mean(dim=0) - out["h0"][control].mean(dim=0)
    return torch.sum(diff * diff)


def counterfactual_loss(out: dict[str, torch.Tensor], ite: torch.Tensor, holdout: torch.Tensor) -> torch.Tensor:
    if not holdout.any():
        return torch.zeros((), device=ite.device)
    return torch.mean((out["tau"][holdout] - ite[holdout]) ** 2)


def evidence_loss(g_raw: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return torch.nn.functional.binary_cross_entropy(g_raw.clamp(1e-6, 1 - 1e-6), target)


def policy_terms(
    out: dict[str, torch.Tensor],
    tau: torch.Tensor,
    quality: torch.Tensor,
    margin: torch.Tensor,
    cost: torch.Tensor,
    group_ids: torch.Tensor,
    budget: float,
    group_cap: int,
    mask: torch.Tensor,
) -> tuple[torch.Tensor, dict[str, float]]:
    z = out["z"] * mask.float()
    # Value is expressed in uplift units (cost divided by the margin): with a
    # margin of 100 the raw yuan-scale reward outweighs every other loss term
    # by three orders of magnitude and saturates tau at its clamp.
    value = quality * torch.clamp(tau, min=0.0, max=2.0) - cost / margin.clamp(min=1e-6)
    reward = -torch.mean(z * value)
    spend = torch.sum(z * cost)
    budget_violation = torch.clamp(spend - budget, min=0.0)
    groups = torch.unique(group_ids[mask])
    group_violation = torch.zeros((), device=z.device)
    for group in groups:
        count = torch.sum(z * (group_ids == group).float())
        group_violation = group_violation + torch.clamp(count - group_cap, min=0.0)
    violations = {"budget": float(budget_violation.detach()), "group": float(group_violation.detach()), "spend": float(spend.detach())}
    return reward, violations


def admissibility_loss(tau: torch.Tensor, admissible: torch.Tensor) -> torch.Tensor:
    """Penalise claimed uplift on paths the ontology gate refuses.

    A masked path carries no message signal, so without this term the network
    keeps predicting positive uplift from customer features alone and ranks
    inexecutable actions first.  The target is the observable rule status only;
    the hidden product-fit quantity is never used here.
    """

    blocked = 1.0 - admissible
    if not bool((blocked > 0).any()):
        return torch.zeros((), device=tau.device)
    return torch.mean(torch.clamp(tau, min=0.0) * blocked)


def dr_pseudo_outcome(x: np.ndarray, outcome: np.ndarray, treatment: np.ndarray, propensity: np.ndarray, fit_index: np.ndarray, ridge: float = 0.2) -> np.ndarray:
    """AIPW pseudo-outcome for the CATE, built only from observed data.

    ``mu0`` / ``mu1`` are ridge fits on the control / treated arms of the fit
    split and the propensity is clipped, so the target is doubly robust and
    never consults the simulated potential outcomes.
    """

    ones = np.ones((x.shape[0], 1), dtype=np.float64)
    design = np.column_stack([ones, x])
    penalty = ridge * np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    mu = {}
    for arm in (0, 1):
        rows = fit_index[treatment[fit_index] == arm]
        if len(rows) < design.shape[1] + 1:
            rows = fit_index
        a = design[rows]
        beta = np.linalg.solve(a.T @ a + penalty, a.T @ outcome[rows])
        mu[arm] = design @ beta
    e = np.clip(propensity, 0.05, 0.95)
    return mu[1] - mu[0] + treatment * (outcome - mu[1]) / e - (1.0 - treatment) * (outcome - mu[0]) / (1.0 - e)


def dr_loss(tau: torch.Tensor, pseudo: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    if not bool(mask.any()):
        return torch.zeros((), device=tau.device)
    return torch.mean((tau[mask] - pseudo[mask]) ** 2)


def policy_supervision(score: torch.Tensor, plan: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Imitate the exact constrained projection (the deployed selector).

    The soft Lagrangian relaxation alone cannot teach the head to respect the
    budget: once the relaxation saturates, gradients vanish.  The projection
    label is detached, so the deployed plan is feasible by construction.
    """

    if not bool(mask.any()):
        return torch.zeros((), device=score.device)
    return torch.nn.functional.binary_cross_entropy_with_logits(score[mask], plan[mask])


def total_loss(
    out: dict[str, torch.Tensor],
    outcome: torch.Tensor,
    treatment: torch.Tensor,
    ite: torch.Tensor,
    holdout: torch.Tensor,
    rule_target: torch.Tensor,
    mask: torch.Tensor,
    quality: torch.Tensor,
    margin: torch.Tensor,
    cost: torch.Tensor,
    group_ids: torch.Tensor,
    budget: float,
    group_cap: int,
    multipliers: dict[str, float],
    lambdas: dict[str, torch.Tensor],
    ablations: set[str],
    plan: torch.Tensor | None = None,
    admissible: torch.Tensor | None = None,
    gate_consistency: float = 0.0,
    lagrangian: bool = True,
) -> tuple[torch.Tensor, dict[str, float]]:
    loss = factual_loss(out, outcome, treatment, mask)
    parts = {"factual": float(loss.detach())}
    if "no_balance" not in ablations:
        lb = balance_loss(out, treatment, mask)
        loss = loss + multipliers["balance"] * lb
        parts["balance"] = float(lb.detach())
    if "no_counterfactual" not in ablations:
        lc = counterfactual_loss(out, ite, holdout & mask)
        loss = loss + multipliers["counterfactual"] * lc
        parts["counterfactual"] = float(lc.detach())
    if "no_evidence_loss" not in ablations:
        le = evidence_loss(out["g_node"], rule_target)
        loss = loss + multipliers["evidence"] * le
        parts["evidence"] = float(le.detach())
    if gate_consistency and admissible is not None:
        term = admissibility_loss(out["tau"] * mask.float(), admissible * mask.float())
        loss = loss + gate_consistency * term
        parts["admissibility"] = float(term.detach())
    if "no_policy_head" not in ablations and plan is not None:
        sup = policy_supervision(out["score"], plan, mask)
        loss = loss + multipliers["policy"] * sup
        parts["policy_supervision"] = float(sup.detach())
    if lagrangian and "no_lagrangian" not in ablations:
        reward, violations = policy_terms(out, out["tau"], quality, margin, cost, group_ids, budget, group_cap, mask)
        penalty = lambdas["budget"] * violations["budget"] + lambdas["group"] * violations["group"]
        loss = loss + 0.25 * multipliers["policy"] * (reward + penalty)
        parts["policy"] = float(reward.detach())
        parts["budget_violation"] = violations["budget"]
        parts["group_violation"] = violations["group"]
    return loss, parts
