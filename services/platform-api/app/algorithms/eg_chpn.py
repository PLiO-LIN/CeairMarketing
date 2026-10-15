"""Evidence-Gated Counterfactual Hypergraph Policy Network prototype.

The class is the governed entry point for the research model.  Its encoder is
the relation-aware temporal attention module in :mod:`oth_gct`; this wrapper
adds the non-negotiable semantic gate and an auditable prediction trace.  A
future PyTorch implementation can preserve this public contract while making
the encoder end-to-end trainable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .oth_gct import CausalSample, GraphEdge, OTHGCT


@dataclass(frozen=True)
class GateDecision:
    edge_index: int
    accepted: bool
    reason: str


@dataclass(frozen=True)
class EGCHPNTrace:
    accepted_edges: int
    rejected_edges: int
    decisions: tuple[GateDecision, ...]


class EGCHPN:
    """Evidence-gated graph causal predictor with deterministic governance."""

    def __init__(self, input_dim: int, hidden_dim: int = 24, confidence_floor: float = 0.65, seed: int = 17) -> None:
        if not 0.0 < confidence_floor <= 1.0:
            raise ValueError("confidence_floor must be in (0, 1]")
        self.confidence_floor = confidence_floor
        self.encoder = OTHGCT(input_dim=input_dim, hidden_dim=hidden_dim, seed=seed)
        self.trace: EGCHPNTrace | None = None

    def _gate(self, edges: Iterable[GraphEdge]) -> list[GraphEdge]:
        accepted: list[GraphEdge] = []
        decisions: list[GateDecision] = []
        for index, edge in enumerate(edges):
            if edge.evidence_confidence < self.confidence_floor:
                decisions.append(GateDecision(index, False, "evidence_below_floor"))
            else:
                accepted.append(edge)
                decisions.append(GateDecision(index, True, "eligible_evidence_path"))
        self.trace = EGCHPNTrace(len(accepted), len(decisions) - len(accepted), tuple(decisions))
        return accepted

    def fit(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge], samples: Sequence[CausalSample], ridge: float = 0.03) -> "EGCHPN":
        gated_edges = self._gate(edges)
        self.encoder.fit(node_features, gated_edges, samples, ridge=ridge)
        return self

    def predict_uplift(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge]) -> np.ndarray:
        gated_edges = self._gate(edges)
        return self.encoder.predict_uplift(node_features, gated_edges)

    def predict_with_trace(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge]) -> tuple[np.ndarray, EGCHPNTrace]:
        uplift = self.predict_uplift(node_features, edges)
        assert self.trace is not None
        return uplift, self.trace
