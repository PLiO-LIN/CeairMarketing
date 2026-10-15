"""Ontology-aware temporal heterogeneous graph causal transformer.

This is a dependency-light reference implementation of the AI component in
OC-DRUP.  It uses relation-aware attention over the marketing ontology and a
causal two-head predictor.  NumPy is used deliberately so the experiment can
run in the current repository without a GPU; a production run can replace the
encoder with an equivalent PyTorch module without changing the data contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class GraphEdge:
    source: int
    target: int
    relation: str
    delta_days: float = 0.0
    evidence_confidence: float = 1.0


@dataclass(frozen=True)
class CausalSample:
    node: int
    treatment: int
    outcome: float


class OTHGCT:
    """Relation-aware temporal graph attention plus a causal response head."""

    def __init__(self, input_dim: int, hidden_dim: int = 16, seed: int = 17) -> None:
        if input_dim <= 0 or hidden_dim <= 0:
            raise ValueError("input_dim and hidden_dim must be positive")
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        rng = np.random.default_rng(seed)
        scale = 1.0 / sqrt(input_dim)
        self.w_in = rng.normal(0, scale, (input_dim, hidden_dim))
        self.w_q = rng.normal(0, 1 / sqrt(hidden_dim), (hidden_dim, hidden_dim))
        self.w_k = rng.normal(0, 1 / sqrt(hidden_dim), (hidden_dim, hidden_dim))
        self.w_v = rng.normal(0, 1 / sqrt(hidden_dim), (hidden_dim, hidden_dim))
        self.w_out = rng.normal(0, 1 / sqrt(hidden_dim), (hidden_dim, hidden_dim))
        self.relation_vectors: dict[str, np.ndarray] = {}
        self.temporal = rng.normal(0, 0.08, (2, hidden_dim))
        self.beta0: np.ndarray | None = None
        self.beta1: np.ndarray | None = None

    def _relation(self, name: str) -> np.ndarray:
        if name not in self.relation_vectors:
            # Stable hash avoids Python's process-randomised hash function.
            seed = sum((i + 1) * ord(c) for i, c in enumerate(name)) % (2**32)
            self.relation_vectors[name] = np.random.default_rng(seed).normal(0, 0.08, self.hidden_dim)
        return self.relation_vectors[name]

    def encode(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge]) -> np.ndarray:
        x = np.asarray(node_features, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.input_dim:
            raise ValueError("node_features shape must be [node_count, input_dim]")
        h = np.tanh(x @ self.w_in)
        edges = list(edges)
        incoming: list[list[GraphEdge]] = [[] for _ in range(len(h))]
        for edge in edges:
            if not (0 <= edge.source < len(h) and 0 <= edge.target < len(h)):
                raise ValueError("edge endpoint outside node_features")
            if not (0.0 < edge.evidence_confidence <= 1.0):
                raise ValueError("evidence_confidence must be in (0, 1]")
            incoming[edge.target].append(edge)
        q, k, v = h @ self.w_q, h @ self.w_k, h @ self.w_v
        updated = h.copy()
        for target, links in enumerate(incoming):
            if not links:
                continue
            scores, messages = [], []
            for edge in links:
                temporal = np.array([np.sin(edge.delta_days / 7.0), np.cos(edge.delta_days / 7.0)]) @ self.temporal
                relation = self._relation(edge.relation)
                score = float(np.dot(q[target], k[edge.source] + relation) / sqrt(self.hidden_dim))
                score += float(np.dot(q[target], temporal)) + log(edge.evidence_confidence)
                scores.append(score)
                messages.append(v[edge.source] + relation + temporal)
            scores = np.asarray(scores)
            weights = np.exp(scores - scores.max())
            weights /= weights.sum()
            updated[target] = np.tanh(h[target] + np.sum(np.asarray(messages) * weights[:, None], axis=0) @ self.w_out)
        return updated

    def fit(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge], samples: Sequence[CausalSample], ridge: float = 1e-2) -> "OTHGCT":
        if not samples:
            raise ValueError("samples cannot be empty")
        z = self.encode(node_features, edges)
        rows = np.asarray([[1.0, *z[s.node]] for s in samples], dtype=float)
        if any(s.treatment not in (0, 1) for s in samples):
            raise ValueError("treatment must be 0 or 1")
        for treatment in (0, 1):
            mask = np.asarray([s.treatment == treatment for s in samples])
            if not mask.any():
                raise ValueError("samples must contain both treatment groups")
            a = rows[mask]
            y = np.asarray([s.outcome for s, keep in zip(samples, mask) if keep], dtype=float)
            penalty = ridge * np.eye(a.shape[1])
            penalty[0, 0] = 0.0
            beta = np.linalg.solve(a.T @ a + penalty, a.T @ y)
            if treatment == 0:
                self.beta0 = beta
            else:
                self.beta1 = beta
        return self

    def predict_uplift(self, node_features: Sequence[Sequence[float]], edges: Iterable[GraphEdge]) -> np.ndarray:
        if self.beta0 is None or self.beta1 is None:
            raise RuntimeError("fit must be called before predict_uplift")
        z = self.encode(node_features, edges)
        rows = np.asarray([[1.0, *row] for row in z], dtype=float)
        return rows @ (self.beta1 - self.beta0)
