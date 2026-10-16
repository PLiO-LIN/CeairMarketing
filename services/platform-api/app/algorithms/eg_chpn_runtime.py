"""Torch-free inference runtime for Marsh-Echo (九皋 / marshecho).

The deployed model is the exported ``weights/marshecho_v2_0.npz`` plus this
module: a plain NumPy re-implementation of
``research/egchpn_torch/model.py``.  Keeping inference torch-free is what lets
the competition image stay small and lets the bundle run on any machine with
NumPy alone, while ``tests/test_eg_chpn_parity.py`` proves the two
implementations compute the same function.

No module in this import path may pull in torch; the runtime contract
(gate decisions, trace objects) is preserved from the v1 prototype so the
governance semantics stay identical.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_NAME = "marshecho"
MODEL_NAME_ZH = "九皋"
PAPER_NAME = "Marsh-Echo"
ARCHITECTURE = "EG-CHPN v2"
SCHEMA_VERSION = "marshecho-egchpn-v2.0"
WEIGHTS_PATH = Path(__file__).resolve().parent / "weights" / "marshecho_v2_0.npz"


class ArtifactSchemaError(RuntimeError):
    """The exported weights were produced by an incompatible trainer."""


@dataclass(frozen=True)
class RuntimeGateDecision:
    edge_index: int
    accepted: bool
    reason: str
    gate_value: float
    status: str


@dataclass(frozen=True)
class RuntimeTrace:
    accepted_edges: int
    rejected_edges: int
    decisions: tuple[RuntimeGateDecision, ...]
    schema_version: str
    parameters: int
    unmatched_paths: int = 0
    vocab_note: str = ""


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))


def _softmax_columns(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=0, keepdims=True)
    weights = np.exp(shifted)
    return weights / weights.sum(axis=0, keepdims=True)


def _linear(x: np.ndarray, weight: np.ndarray, bias: np.ndarray | None = None) -> np.ndarray:
    out = x @ weight.T
    return out if bias is None else out + bias


class EGCHPNRuntime:
    """Deterministic NumPy forward pass mirroring the trained torch model."""

    def __init__(self, params: dict[str, np.ndarray], meta: dict) -> None:
        if meta.get("schema_version") != SCHEMA_VERSION:
            raise ArtifactSchemaError(f"权重 schema 不匹配：期望 {SCHEMA_VERSION}，实际 {meta.get('schema_version')}")
        # A shipped model may be an ensemble of same-configuration checkpoints
        # trained on independent synthetic populations; averaging tau across
        # members measurably improves ranking quality (see the ensemble A/B in
        # docs/实验).  A single-member artifact keeps the old key layout.
        self.members: list[dict[str, np.ndarray]] = []
        for index in range(int(meta.get("members", 1))):
            prefix = f"m{index}::"
            subset = {key[len(prefix):]: value for key, value in params.items() if key.startswith(prefix)}
            self.members.append(subset or params)
        self.params = self.members[0]
        self.meta = meta
        self.config = meta["config"]
        self.node_type_vocab: list[str] = list(meta["node_types"])
        self.relation_vocab: list[str] = list(meta["relation_vocab"])
        self.parameters = int(meta["parameters"])

    @classmethod
    def load(cls, path: Path | str = WEIGHTS_PATH) -> "EGCHPNRuntime":
        file = Path(path)
        if not file.exists():
            raise ArtifactSchemaError(f"缺少模型权重文件：{file}")
        with np.load(file, allow_pickle=False) as archive:
            meta = json.loads(str(archive["_meta"][0]))
            params = {key.replace("__", "."): archive[key] for key in archive.files if not key.startswith("_")}
        return cls(params, meta)

    @staticmethod
    def _embedding(params: dict[str, np.ndarray], table: str, ids: np.ndarray) -> np.ndarray:
        return params[table][ids]

    def _encode(self, params: dict[str, np.ndarray], x: np.ndarray, type_ids: np.ndarray, H: np.ndarray, H_norm: np.ndarray, g: np.ndarray, delta: np.ndarray, rel_ids: np.ndarray, treat: np.ndarray, temporal_on: bool) -> np.ndarray:
        dim = int(self.config["hidden_dim"])
        joined = np.concatenate([x, self._embedding(params, "type_emb.weight", type_ids)], axis=1)
        h = np.tanh(_linear(joined, params["w_in.weight"], params["w_in.bias"]))
        for index in range(int(self.config["n_layers"])):
            prefix = f"layers.{index}."
            w_q = params[prefix + "w_q.weight"]
            w_k = params[prefix + "w_k.weight"]
            w_v = params[prefix + "w_v.weight"]
            q, k, v = h @ w_q.T, h @ w_k.T, h @ w_v.T
            degree_e = np.clip(H.sum(axis=0), 1.0, None)
            key_e = (H.T @ k) / degree_e[:, None]
            logits = (q @ key_e.T) / math.sqrt(dim) + np.log(g + 1e-6)[None, :]
            logits = np.where(H > 0, logits, -1e9)
            alpha = _softmax_columns(logits) * H
            if temporal_on:
                phase = np.stack([np.sin(delta / 7.0), np.cos(delta / 7.0)], axis=1)
                temporal = _linear(phase, params[prefix + "temporal.weight"])
            else:
                temporal = np.zeros((H.shape[1], dim), dtype=np.float32)
            relation = self._embedding(params, prefix + "relation.weight", rel_ids)
            treat_embedding = self._embedding(params, prefix + "treat.weight", treat.astype(np.int64))
            messages = (alpha * H).T @ v + relation + (temporal + treat_embedding) * treat[:, None]
            messages = messages * g[:, None]
            h = np.tanh(h + (H_norm @ messages) @ params[prefix + "w_o.weight"].T)
        return h

    def gate(self, params: dict[str, np.ndarray], attrs: np.ndarray, hard_mask: np.ndarray, use_gate: bool = True, use_mask: bool | None = None) -> tuple[np.ndarray, np.ndarray]:
        raw = 1.0 / (1.0 + np.exp(-_linear(attrs, params["gate_module.linear.weight"], params["gate_module.linear.bias"]).squeeze(-1)))
        if not use_gate:
            raw = np.ones_like(raw)
        mask = hard_mask if (self.config.get("semantic_mask", True) if use_mask is None else use_mask) else np.ones_like(hard_mask)
        return raw, raw * mask

    def spec_arrays(self, spec) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Encode a spec exactly the way the trainer encoded it.

        The node-type vocabulary is ``sorted(set(node_types))`` — the same rule
        ``research/egchpn_torch/data.py`` uses — not the declaration order of
        ``NODE_TYPES``.  Mixing the two silently scrambles the type embedding
        and degrades inference while parity tests still pass.
        """

        types = sorted(set(spec.node_types))
        if len(types) != len(self.node_type_vocab):
            raise ArtifactSchemaError(
                f"节点类型数与训练词表不一致：{len(types)} vs {len(self.node_type_vocab)}"
            )
        type_ids = np.asarray([types.index(name) for name in spec.node_types], dtype=np.int64)
        training_vocab = list(types)
        unknown_relations = [key for key in spec.keys() if key not in self.relation_vocab]
        H = spec.incidence().astype(np.float32)
        degree_v = np.clip(H.sum(axis=1), 1.0, None)
        degree_e = np.clip(H.sum(axis=0), 1.0, None)
        H_norm = (H / degree_v[:, None]) / np.sqrt(degree_e)[None, :]
        rel_ids = np.asarray(
            [self.relation_vocab.index(key) if key in self.relation_vocab else 0 for key in spec.keys()],
            dtype=np.int64,
        )
        self.last_encoding = {"node_types": training_vocab, "unknown_relations": unknown_relations}
        return type_ids, H, H_norm, spec.gate_attrs().astype(np.float32), spec.hard_mask().astype(np.float32), spec.delta_days().astype(np.float32), rel_ids

    def _forward_member(self, params, x, type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids, *, use_gate: bool = True) -> dict[str, np.ndarray]:
        """NumPy mirror of ``EGCHPNv2.forward`` for pre-built arrays."""

        raw, g = self.gate(params, attrs, hard_mask, use_gate)
        treat_on = np.ones(H.shape[1], dtype=np.float32)
        treat_off = np.zeros_like(treat_on)
        features = np.asarray(x, dtype=np.float32)
        temporal_on = bool(self.config.get("temporal", True))
        h1 = self._encode(params, features, type_ids, H, H_norm, g, delta, rel_ids, treat_on, temporal_on)
        h0 = (
            self._encode(params, features, type_ids, H, H_norm, g, delta, rel_ids, treat_off, temporal_on)
            if self.config.get("dual_tower", True)
            else h1
        )
        diff = h1 - h0
        stacked = np.concatenate([h1, h0, diff], axis=1)
        tau = _linear(_gelu(_linear(stacked, params["tau_head.0.weight"], params["tau_head.0.bias"])), params["tau_head.2.weight"], params["tau_head.2.bias"]).squeeze(-1)
        gate_per_node = H_norm @ g
        score = _linear(
            _gelu(_linear(np.concatenate([stacked, gate_per_node[:, None]], axis=1), params["policy.0.weight"], params["policy.0.bias"])),
            params["policy.2.weight"],
            params["policy.2.bias"],
        ).squeeze(-1)
        z = 1.0 / (1.0 + np.exp(-np.clip(score - float(params["theta"][0]), -4.0, 4.0)))
        y1 = _linear(h1, params["head1.weight"], params["head1.bias"]).squeeze(-1)
        y0 = _linear(h0, params["head0.weight"], params["head0.bias"]).squeeze(-1)
        return {"g_raw": raw, "g": g, "h1": h1, "h0": h0, "tau": tau, "y1": y1, "y0": y0, "score": score, "z": z}

    def forward_arrays(self, x, type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids, *, use_gate: bool = True) -> dict[str, np.ndarray]:
        """Average the per-member outputs of an ensemble artifact."""

        outputs = [
            self._forward_member(params, x, type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids, use_gate=use_gate)
            for params in self.members
        ]
        if len(outputs) == 1:
            return outputs[0]
        averaged = dict(outputs[0])
        for key in ("tau", "y1", "y0", "score", "z"):
            averaged[key] = np.mean([output[key] for output in outputs], axis=0)
        averaged["members"] = float(len(outputs))
        return averaged

    def predict_from_spec(self, spec, *, use_gate: bool = True, with_factual: bool = False, temperature: float = 0.5):
        type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids = self.spec_arrays(spec)
        result = self.forward_arrays(spec.node_features, type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids, use_gate=use_gate)
        trace = self._trace(result["g_raw"], hard_mask, spec)
        self.last_trace = trace
        if with_factual:
            return result["tau"], result["y1"], trace
        return result["tau"], trace

    def predict_uplift(self, spec) -> np.ndarray:
        tau, _ = self.predict_from_spec(spec)
        return tau

    def predict_with_trace(self, spec) -> tuple[np.ndarray, RuntimeTrace]:
        return self.predict_from_spec(spec)

    def _trace(self, raw: np.ndarray, hard_mask: np.ndarray, spec) -> RuntimeTrace:
        decisions = []
        accepted = 0
        for index, edge in enumerate(spec.hyperedges):
            if edge.status != "eligible":
                reason = f"ontology_gate:{edge.status}"
            elif raw[index] < 0.5:
                reason = "learned_gate_low"
            else:
                reason = "eligible_evidence_path"
                accepted += 1
            decisions.append(
                RuntimeGateDecision(
                    edge_index=index,
                    accepted=edge.status == "eligible",
                    reason=reason,
                    gate_value=float(raw[index] * hard_mask[index]),
                    status=edge.status,
                )
            )
        unmatched = len(getattr(self, "last_encoding", {}).get("unknown_relations", []))
        note = (
            "所有路径均与训练关系词表完全匹配"
            if unmatched == 0
            else f"{unmatched} 条路径的资格跳组合未出现在训练词表中，其 τ̂ 仅用于诊断；这些路径已被本体门禁判为不可执行，不进入选择"
        )
        return RuntimeTrace(accepted, len(decisions) - accepted, tuple(decisions), SCHEMA_VERSION, self.parameters, unmatched, note)


@lru_cache(maxsize=1)
def load_default_runtime() -> EGCHPNRuntime:
    return EGCHPNRuntime.load(WEIGHTS_PATH)
