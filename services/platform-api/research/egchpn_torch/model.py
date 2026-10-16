"""Marsh-Echo (九皋 / marshecho): EG-CHPN v2 in PyTorch.

Evidence-gated counterfactual hypergraph policy network.  The encoder is
trained end-to-end (unlike the v1 prototype whose attention was frozen at
initialisation): hyperedge incidence message passing, a learned evidence
gate multiplied by a non-learnable semantic hard mask, shared-parameter
counterfactual towers and a constrained policy head.

Dense incidence matrices keep every aggregation a plain matmul, which makes
the forward pass bit-reproducible under ``use_deterministic_algorithms`` and
portable to the numpy runtime one operation at a time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import nn


@dataclass(frozen=True)
class Batch:
    x: torch.Tensor            # N x dx raw node features
    type_ids: torch.Tensor     # N
    H: torch.Tensor            # N x M incidence (0/1)
    H_norm: torch.Tensor       # N x M symmetric normalisation
    attrs: torch.Tensor        # M x 4 gate attributes
    hard_mask: torch.Tensor    # M
    delta: torch.Tensor        # M
    rel_ids: torch.Tensor      # M
    group_ids: torch.Tensor    # N (frequency/rule group per customer)
    cost: torch.Tensor         # N
    margin: torch.Tensor       # N


class EvidenceGate(nn.Module):
    """g = sigmoid(w . [c, f, r, s]) * hard_mask; the mask is not learnable."""

    def __init__(self) -> None:
        super().__init__()
        self.linear = nn.Linear(4, 1)

    def forward(self, attrs: torch.Tensor, hard_mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        raw = torch.sigmoid(self.linear(attrs)).squeeze(-1)
        return raw, raw * hard_mask


class HypergraphAttentionLayer(nn.Module):
    def __init__(self, dim: int, n_relations: int, temporal: bool = True) -> None:
        super().__init__()
        self.w_q = nn.Linear(dim, dim, bias=False)
        self.w_k = nn.Linear(dim, dim, bias=False)
        self.w_v = nn.Linear(dim, dim, bias=False)
        self.w_o = nn.Linear(dim, dim, bias=False)
        self.relation = nn.Embedding(n_relations, dim)
        self.temporal = nn.Linear(2, dim, bias=False)
        self.treat = nn.Embedding(2, dim)
        self.use_temporal = temporal

    def forward(
        self,
        h: torch.Tensor,
        batch: Batch,
        g: torch.Tensor,
        treat: torch.Tensor,
    ) -> torch.Tensor:
        q, k, v = self.w_q(h), self.w_k(h), self.w_v(h)
        degree = batch.H.sum(dim=0).clamp(min=1.0)
        key_e = (batch.H.T @ k) / degree[:, None]
        logits = (q @ key_e.T) / math.sqrt(h.shape[1]) + torch.log(g + 1e-6)
        logits = torch.where(batch.H > 0, logits, torch.full_like(logits, -1e9))
        alpha = torch.softmax(logits, dim=0) * batch.H
        if self.use_temporal:
            phase = torch.stack([torch.sin(batch.delta / 7.0), torch.cos(batch.delta / 7.0)], dim=1)
            temporal = self.temporal(phase)
        else:
            temporal = torch.zeros_like(k[: batch.H.shape[1]])
        messages = (alpha * batch.H).T @ v + self.relation(batch.rel_ids)
        messages = messages + (temporal + self.treat(treat.long())) * treat[:, None]
        messages = messages * g[:, None]
        return torch.tanh(h + self.w_o(batch.H_norm @ messages))


class EGCHPNv2(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 96,
        n_layers: int = 3,
        n_relations: int = 8,
        n_types: int = 16,
        temporal: bool = True,
        gate: bool = True,
        dual_tower: bool = True,
        policy_head: bool = True,
        semantic_mask: bool = True,
    ) -> None:
        super().__init__()
        self.cfg = {
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "n_layers": n_layers,
            "n_relations": n_relations,
            "n_types": n_types,
            "temporal": temporal,
            "gate": gate,
            "dual_tower": dual_tower,
            "policy_head": policy_head,
            "semantic_mask": semantic_mask,
        }
        self.type_emb = nn.Embedding(n_types, 8)
        self.w_in = nn.Linear(input_dim + 8, hidden_dim)
        self.gate_module = EvidenceGate()
        self.layers = nn.ModuleList([HypergraphAttentionLayer(hidden_dim, n_relations, temporal) for _ in range(n_layers)])
        self.head1 = nn.Linear(hidden_dim, 1)
        self.head0 = nn.Linear(hidden_dim, 1)
        self.tau_head = nn.Sequential(nn.Linear(3 * hidden_dim, hidden_dim), nn.GELU(approximate="tanh"), nn.Linear(hidden_dim, 1))
        self.policy = nn.Sequential(nn.Linear(3 * hidden_dim + 1, hidden_dim), nn.GELU(approximate="tanh"), nn.Linear(hidden_dim, 1))
        self.theta = nn.Parameter(torch.zeros(1))
        self.dual_tower = dual_tower
        self.use_gate = gate
        self.use_mask = semantic_mask
        self.use_policy = policy_head

    def gate_values(self, batch: Batch) -> tuple[torch.Tensor, torch.Tensor]:
        raw, _ = self.gate_module(batch.attrs, batch.hard_mask)
        if not self.use_gate:
            raw = torch.ones_like(raw)
        mask = batch.hard_mask if self.use_mask else torch.ones_like(batch.hard_mask)
        return raw, raw * mask

    def encode(self, batch: Batch, g: torch.Tensor, treat: torch.Tensor) -> torch.Tensor:
        h = torch.tanh(self.w_in(torch.cat([batch.x, self.type_emb(batch.type_ids)], dim=1)))
        for layer in self.layers:
            h = layer(h, batch, g, treat)
        return h

    def forward(self, batch: Batch, temperature: float = 1.0) -> dict[str, torch.Tensor]:
        _, g = self.gate_values(batch)
        ones = torch.ones(batch.H.shape[1], device=batch.x.device)
        zeros = torch.zeros_like(ones)
        h1 = self.encode(batch, g, ones)
        h0 = self.encode(batch, g, zeros) if self.dual_tower else h1
        diff = h1 - h0
        tau = self.tau_head(torch.cat([h1, h0, diff], dim=1)).squeeze(-1)
        if not self.dual_tower:
            tau = self.tau_head(torch.cat([h1, h1, torch.zeros_like(h1)], dim=1)).squeeze(-1)
        y1 = self.head1(h1).squeeze(-1)
        y0 = self.head0(h0).squeeze(-1)
        gate_per_node = batch.H_norm @ g
        score = self.policy(torch.cat([h1, h0, diff, gate_per_node[:, None]], dim=1)).squeeze(-1)
        # The relaxation must keep gradient: an unclamped score annealed to a
        # small temperature saturates sigmoid() and freezes z at 1.0, which
        # makes the budget multiplier explode without ever cutting allocation.
        # Deployment never uses this relaxation: the plan comes from the exact
        # constrained projection, which the policy head is trained to imitate.
        relaxed = torch.clamp(score - self.theta, min=-4.0, max=4.0)
        z = torch.sigmoid(relaxed) if self.use_policy else torch.sigmoid(torch.clamp(tau, min=-4.0, max=4.0))
        return {"g_raw": _, "g": g, "h1": h1, "h0": h0, "tau": tau, "y1": y1, "y0": y0, "score": score, "z": z}
