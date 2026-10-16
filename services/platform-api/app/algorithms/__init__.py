"""Research algorithms that can be called by governed marketing tools."""

from .eg_chpn import EGCHPN, EGCHPNTrace, GateDecision
from .eg_chpn_policy import UpliftItem, plan_from_uplift
from .eg_chpn_runtime import (
    ARCHITECTURE,
    MODEL_NAME,
    MODEL_NAME_ZH,
    PAPER_NAME,
    ArtifactSchemaError,
    EGCHPNRuntime,
    RuntimeGateDecision,
    RuntimeTrace,
    load_default_runtime,
)
from .hypergraph_spec import (
    ELIGIBILITY_HOPS,
    NODE_TYPES,
    Hyperedge,
    HypergraphSpec,
    build_from_ontology,
    clique_expansion,
    validate_hyperedge,
)
from .ontology_uplift_policy import (
    Action,
    Candidate,
    EvaluationResult,
    PolicyResult,
    fit_and_optimize,
)
from .oth_gct import CausalSample, GraphEdge, OTHGCT

__all__ = [
    "ARCHITECTURE",
    "Action",
    "ArtifactSchemaError",
    "Candidate",
    "CausalSample",
    "EGCHPN",
    "EGCHPNRuntime",
    "EGCHPNTrace",
    "EvaluationResult",
    "GateDecision",
    "GraphEdge",
    "Hyperedge",
    "HypergraphSpec",
    "MODEL_NAME",
    "MODEL_NAME_ZH",
    "OTHGCT",
    "PAPER_NAME",
    "PolicyResult",
    "RuntimeGateDecision",
    "RuntimeTrace",
    "UpliftItem",
    "build_from_ontology",
    "clique_expansion",
    "fit_and_optimize",
    "load_default_runtime",
    "plan_from_uplift",
    "validate_hyperedge",
]
