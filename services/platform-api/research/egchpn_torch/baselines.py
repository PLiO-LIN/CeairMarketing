"""Torch baselines for the Marsh-Echo sweep.

tarnet / dragonnet are customer-only representation learners (the honest
"is the graph needed at all?" control); gat_trained is the same relation-aware
attention stack trained on the pairwise clique expansion (the fair upgrade of
the v1 prototype).  A full HGT and causal forests are deliberately excluded:
neither admits a faithful dependency-light implementation, and both exclusions
are stated in the experiment report instead of being approximated.
"""

from __future__ import annotations

import torch
from torch import nn

from research.egchpn_torch.model import EGCHPNv2


class _TabularBase(nn.Module):
    def __init__(self, input_dim: int, hidden: int, propensity: bool = False) -> None:
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(input_dim, hidden), nn.GELU(), nn.Linear(hidden, hidden), nn.GELU())
        self.head1 = nn.Linear(hidden, 1)
        self.head0 = nn.Linear(hidden, 1)
        self.prop = nn.Linear(hidden, 1) if propensity else None

    def forward(self, batch, temperature: float = 0.2) -> dict[str, torch.Tensor]:
        h = self.trunk(batch.x)
        y1 = self.head1(h).squeeze(-1)
        y0 = self.head0(h).squeeze(-1)
        tau = y1 - y0
        z = torch.sigmoid(tau / max(temperature, 1e-3))
        g_raw = batch.hard_mask.clone()
        out = {"g_raw": g_raw, "g": g_raw, "h1": h, "h0": h, "tau": tau, "y1": y1, "y0": y0, "score": tau, "z": z}
        if self.prop is not None:
            out["propensity"] = torch.sigmoid(self.prop(h).squeeze(-1))
        return out


def build(name: str, input_dim: int, n_relations: int, n_types: int, hidden: int, layers: int) -> nn.Module:
    if name == "tarnet":
        return _TabularBase(input_dim, hidden, propensity=False)
    if name == "dragonnet":
        return _TabularBase(input_dim, hidden, propensity=True)
    if name == "gat_trained":
        return EGCHPNv2(
            input_dim=input_dim,
            hidden_dim=hidden,
            n_layers=layers,
            n_relations=max(n_relations, 1),
            n_types=max(n_types, 1),
            temporal=True,
            gate=True,
            dual_tower=True,
            policy_head=True,
        )
    raise ValueError(f"unknown baseline {name}")
