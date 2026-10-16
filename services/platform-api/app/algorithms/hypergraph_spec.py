"""Ontology-validated eligibility hypergraph specification.

This module is the single source of truth shared by the PyTorch trainer
(``research/egchpn_torch``) and the numpy inference runtime: the node
vocabulary, the canonical eligibility hop template (validated against the
platform ontology at import time), dense incidence construction and the
clique expansion used by the pairwise-graph ablation.

A hyperedge spans a complete eligibility path (audience snapshot, route,
flight, cabin, fare, product, product package, business rule, evidence).
Paths whose endpoints violate the registered relation definitions are
rejected before any neural aggregation, so the semantic mask is a property
of the data contract rather than of trained weights.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .oth_gct import GraphEdge


def _load_semantic_model():
    """Import the ontology vocabulary without pulling in the DB layer.

    ``app.ontology.__init__`` re-exports the SQLAlchemy service and also
    exposes a same-named ``semantic_model()`` function, so the vocabulary
    module is loaded directly from its file: it is pure data and must stay
    importable in numpy-only training and CI-adjacent environments.
    """

    path = Path(__file__).resolve().parents[2] / "app" / "ontology" / "semantic_model.py"
    spec = importlib.util.spec_from_file_location("ceair_semantic_model_for_algorithms", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_semantic = _load_semantic_model()
validate_relation_endpoints = _semantic.validate_relation_endpoints

NODE_TYPES: tuple[str, ...] = (
    "AudienceSnapshot",
    "Route",
    "Flight",
    "Cabin",
    "Fare",
    "Product",
    "ProductPackage",
    "BusinessRule",
    "Evidence",
)

FEATURE_DIM = 6
FEATURE_SLOTS = ("signal", "fit", "quality", "value", "fare", "strictness")

# Canonical eligibility path, stored in ontology direction.  Every hop is
# checked against RELATION_TYPES at import time; a drift in the ontology
# therefore fails fast instead of silently weakening the semantic mask.
ELIGIBILITY_HOPS: tuple[tuple[str, str, str], ...] = (
    ("targets_audience", "ProductPackage", "AudienceSnapshot"),
    ("contains_product", "ProductPackage", "Product"),
    ("uses_product", "Fare", "Product"),
    ("has_fare", "Cabin", "Fare"),
    ("has_cabin", "Flight", "Cabin"),
    ("operates_on", "Flight", "Route"),
    ("evidence_for", "Evidence", "ProductPackage"),
    ("evidence_for", "Evidence", "Route"),
    ("evidence_for", "Evidence", "BusinessRule"),
)

STATUS_ELIGIBLE = "eligible"
STATUS_PENDING = "pending"
STATUS_INELIGIBLE = "ineligible"


def _validate_hop_template() -> None:
    for relation, source_type, target_type in ELIGIBILITY_HOPS:
        error = validate_relation_endpoints(relation, source_type, target_type)
        if error:
            raise ValueError(f"ELIGIBILITY_HOPS no longer matches the ontology: {error}")
    for _, source_type, target_type in ELIGIBILITY_HOPS:
        for node_type in (source_type, target_type):
            if node_type not in NODE_TYPES:
                raise ValueError(f"hop endpoint {node_type} missing from NODE_TYPES")


_validate_hop_template()


@dataclass(frozen=True)
class Hyperedge:
    """One eligibility path over the marketing ontology.

    ``hops`` are stored in ontology direction as ``(relation, source_type,
    target_type)``; ``member_nodes``/``member_types`` list the distinct nodes
    the path touches.  ``status`` is the deterministic ontology gate result:
    ``pending``/``ineligible`` force the evidence gate to zero and can never
    be compensated by a model score.
    """

    member_nodes: tuple[int, ...]
    member_types: tuple[str, ...]
    hops: tuple[tuple[str, str, str], ...]
    status: str
    confidence: float
    freshness_days: float
    rule_agreement: float
    source_stability: float
    delta_days: float

    @property
    def key(self) -> str:
        return "|".join(relation for relation, _, _ in self.hops)

    def gate_vector(self) -> tuple[float, float, float, float]:
        return (
            self.confidence,
            float(np.exp(-max(self.freshness_days, 0.0) / 14.0)),
            self.rule_agreement,
            self.source_stability,
        )


@dataclass(frozen=True)
class HypergraphSpec:
    node_features: np.ndarray
    node_types: tuple[str, ...]
    hyperedges: tuple[Hyperedge, ...]

    def incidence(self) -> np.ndarray:
        matrix = np.zeros((len(self.node_types), len(self.hyperedges)), dtype=np.uint8)
        for index, edge in enumerate(self.hyperedges):
            for node in edge.member_nodes:
                matrix[node, index] = 1
        return matrix

    def gate_attrs(self) -> np.ndarray:
        return np.asarray([edge.gate_vector() for edge in self.hyperedges], dtype=float).reshape(-1, 4)

    def hard_mask(self) -> np.ndarray:
        return np.asarray([1.0 if edge.status == STATUS_ELIGIBLE else 0.0 for edge in self.hyperedges], dtype=float)

    def delta_days(self) -> np.ndarray:
        return np.asarray([edge.delta_days for edge in self.hyperedges], dtype=float)

    def keys(self) -> tuple[str, ...]:
        return tuple(edge.key for edge in self.hyperedges)


def validate_hyperedge(edge: Hyperedge, node_count: int, node_types: Sequence[str]) -> str | None:
    if edge.status not in (STATUS_ELIGIBLE, STATUS_PENDING, STATUS_INELIGIBLE):
        return f"unknown gate status {edge.status}"
    if len(edge.member_nodes) != len(set(edge.member_nodes)):
        return "member_nodes must be distinct"
    if len(edge.member_nodes) != len(edge.member_types):
        return "member_nodes and member_types length mismatch"
    for node, node_type in zip(edge.member_nodes, edge.member_types):
        if not 0 <= node < node_count:
            return f"member node {node} outside node_features"
        if node_type not in NODE_TYPES or node_types[node] != node_type:
            return f"member type {node_type} inconsistent with node vocabulary"
    covered = {edge.member_types[i] for i in range(len(edge.member_nodes))}
    for relation, source_type, target_type in edge.hops:
        error = validate_relation_endpoints(relation, source_type, target_type)
        if error:
            return error
        if source_type not in covered or target_type not in covered:
            return f"hop {relation} references a type absent from member_types"
    for value in edge.gate_vector():
        if not 0.0 < value <= 1.0:
            return "gate attributes must lie in (0, 1]"
    return None


def clique_expansion(spec: HypergraphSpec) -> list[GraphEdge]:
    """Pairwise star expansion used by the no-hypergraph ablation.

    Each member is connected to the hyperedge's audience anchor with the hop
    relation that introduces its type, so the ablation nests exactly inside
    the v1 ``OTHGCT`` pairwise encoder instead of comparing unrelated graphs.
    """

    edges: list[GraphEdge] = []
    for edge in spec.hyperedges:
        anchor_type = "AudienceSnapshot"
        if anchor_type not in edge.member_types:
            continue
        anchor = edge.member_nodes[edge.member_types.index(anchor_type)]
        for position, node_type in enumerate(edge.member_types):
            if node_type == anchor_type:
                continue
            relation = next(
                (rel for rel, src, dst in edge.hops if src == node_type or dst == node_type),
                "supports_product",
            )
            edges.append(
                GraphEdge(
                    edge.member_nodes[position],
                    anchor,
                    relation,
                    edge.delta_days,
                    edge.confidence,
                )
            )
    return edges


def _feature_row(attributes: dict[str, float] | None) -> list[float]:
    row = [0.0] * FEATURE_DIM
    if not attributes:
        return row
    for slot, name in enumerate(FEATURE_SLOTS):
        value = attributes.get(name)
        if isinstance(value, (int, float)):
            row[slot] = float(min(max(value, 0.0), 1.0))
    return row


def build_from_ontology(session, tenant_id: int, snapshot_external_id: str, package_external_ids: Sequence[str]) -> HypergraphSpec:
    """Project recorded ontology instances into eligibility hyperedges.

    Only relations that match :data:`ELIGIBILITY_HOPS` are admitted.  A path
    missing any hop degrades to ``pending``; a linked business rule marked
    blocked, or evidence below the confidence floor, degrades to
    ``ineligible``.  Node features come from the frozen ``attributes_json``
    slots, never from free text.
    """

    import json
    from datetime import datetime, timezone

    from ..db_models import OntologyEntityRecord, OntologyRelationRecord

    entities = session.query(OntologyEntityRecord).filter(OntologyEntityRecord.tenant_id == tenant_id).all()
    by_id = {record.id: record for record in entities}
    by_external = {record.external_id: record for record in entities}
    outgoing: dict[tuple[int, str], list[int]] = {}
    incoming: dict[tuple[int, str], list[int]] = {}
    for row in session.query(OntologyRelationRecord).filter(OntologyRelationRecord.tenant_id == tenant_id).all():
        outgoing.setdefault((row.source_entity_id, row.relation_type), []).append(row.target_entity_id)
        incoming.setdefault((row.target_entity_id, row.relation_type), []).append(row.source_entity_id)

    def forward(record, relation: str, wanted: str):
        for target_id in outgoing.get((record.id, relation), []):
            target = by_id.get(target_id)
            if target is not None and target.entity_type == wanted:
                yield target

    def backward(record, relation: str, wanted: str):
        for source_id in incoming.get((record.id, relation), []):
            source = by_id.get(source_id)
            if source is not None and source.entity_type == wanted:
                yield source

    def attributes(record: OntologyEntityRecord) -> dict:
        try:
            payload = json.loads(record.attributes_json or "{}")
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    node_indexes: dict[str, int] = {}
    node_types: list[str] = []
    feature_rows: list[list[float]] = []

    def add(record) -> int:
        index = node_indexes.get(record.external_id)
        if index is None:
            index = len(node_types)
            node_indexes[record.external_id] = index
            node_types.append(record.entity_type)
            feature_rows.append(_feature_row(attributes(record)))
        return index

    now = datetime.now(timezone.utc)
    hyperedges: list[Hyperedge] = []
    for package_external in package_external_ids:
        package = by_external.get(package_external)
        if package is None or package.entity_type != "ProductPackage":
            continue
        members: dict[str, object] = {"ProductPackage": package}
        hops: list[tuple[str, str, str]] = []

        snapshot = by_external.get(snapshot_external_id)
        if snapshot is not None and snapshot.entity_type == "AudienceSnapshot":
            members["AudienceSnapshot"] = snapshot
            hops.append(("targets_audience", "ProductPackage", "AudienceSnapshot"))
        product = next(forward(package, "contains_product", "Product"), None)
        route = None
        if product is not None:
            members["Product"] = product
            hops.append(("contains_product", "ProductPackage", "Product"))
            fare = next(backward(product, "uses_product", "Fare"), None)
            if fare is not None:
                members["Fare"] = fare
                hops.append(("uses_product", "Fare", "Product"))
                cabin = next(backward(fare, "has_fare", "Cabin"), None)
                if cabin is not None:
                    members["Cabin"] = cabin
                    hops.append(("has_fare", "Cabin", "Fare"))
                    flight = next(backward(cabin, "has_cabin", "Flight"), None)
                    if flight is not None:
                        members["Flight"] = flight
                        hops.append(("has_cabin", "Flight", "Cabin"))
                        route = next(forward(flight, "operates_on", "Route"), None)
                        if route is not None:
                            members["Route"] = route
                            hops.append(("operates_on", "Flight", "Route"))
        evidence = next(
            (
                candidate
                for candidate in entities
                if candidate.entity_type == "Evidence" and package in forward(candidate, "evidence_for", "ProductPackage")
            ),
            None,
        )
        rule = None
        if evidence is not None:
            members["Evidence"] = evidence
            hops.append(("evidence_for", "Evidence", "ProductPackage"))
            rule = next(forward(evidence, "evidence_for", "BusinessRule"), None)
            if rule is not None:
                members["BusinessRule"] = rule
                hops.append(("evidence_for", "Evidence", "BusinessRule"))
            if route is not None and route in forward(evidence, "evidence_for", "Route"):
                hops.append(("evidence_for", "Evidence", "Route"))
        if len(hops) < len(ELIGIBILITY_HOPS):
            status = STATUS_PENDING
        else:
            status = STATUS_ELIGIBLE
        confidence = float(getattr(evidence, "confidence", 0.0) or 0.0) if evidence is not None else 0.0
        if confidence and confidence < 0.65:
            status = STATUS_PENDING
        blocked = bool(rule is not None and str(attributes(rule).get("status", "")) == "blocked")
        if evidence is None or rule is None or blocked or confidence == 0.0:
            status = STATUS_INELIGIBLE if blocked or evidence is None else status
        freshness_days = 0.0
        if evidence is not None and getattr(evidence, "updated_at", None) is not None:
            stamp = evidence.updated_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            freshness_days = max(0.0, (now - stamp).total_seconds() / 86400.0)
        ordered = [name for name in ("ProductPackage", "AudienceSnapshot", "Product", "Fare", "Cabin", "Flight", "Route", "Evidence", "BusinessRule") if name in members]
        member_nodes = tuple(add(members[name]) for name in ordered)
        hyperedges.append(
            Hyperedge(
                member_nodes=member_nodes,
                member_types=tuple(node_types[index] for index in member_nodes),
                hops=tuple(hops),
                status=status,
                confidence=max(confidence, 1e-3),
                freshness_days=freshness_days,
                rule_agreement=0.1 if blocked else (0.9 if rule is not None else 1e-3),
                source_stability=max(confidence, 1e-3),
                delta_days=freshness_days,
            )
        )

    features = np.asarray(feature_rows, dtype=float).reshape(len(node_types), FEATURE_DIM)
    spec = HypergraphSpec(features, tuple(node_types), tuple(hyperedges))
    for edge in spec.hyperedges:
        error = validate_hyperedge(edge, len(node_types), spec.node_types)
        if error:
            raise ValueError(f"ontology projection produced an invalid hyperedge: {error}")
    return spec
