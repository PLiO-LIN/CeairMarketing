# Reference Adoption

## DeepSeek Harness

Adopted patterns:

- Agent domains are registered capabilities rather than hard-coded UI actions.
- Runtime facts are append-only events that can be audited and replayed.
- Governance runs before tool execution and can reject a run.
- Human approval is an explicit run status for orchestration and content.

Primary reference areas:

- `docs/architecture.zh.md`
- `docs/agent-lifecycle.zh.md`
- `docs/tool-execution-pipeline.zh.md`
- `packages/core/session`
- `packages/core/tools`
- `packages/core/agent-loop`

The full Harness repository is not embedded because it is a developer-preview
general-purpose harness and would add unrelated shell, workspace, and coding
agent capabilities.

## Semantica

Adopted patterns:

- Graph nodes and edges carry provenance.
- Relationship assertions carry evidence and confidence.
- Campaign results feed back into audience entities.
- Ontology is a decision service, not only a visualization.

Primary reference areas:

- `ARCHITECTURE.md`
- `semantica/kg/graph_builder.py`
- `semantica/kg/entity_resolver.py`
- `semantica/ontology/ontology_validator.py`
- `semantica/provenance/manager.py`
- `semantica/context/decision_recorder.py`
- `semantica/context/policy_engine.py`

The full Semantica dependency set is not installed in the first vertical slice.
The platform keeps its ontology contracts small so Neo4j, RDF, SHACL, and
reasoning adapters can be introduced behind the service boundary later.

