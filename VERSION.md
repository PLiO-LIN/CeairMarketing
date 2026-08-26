# Version History

## v2.2 - 2026-08-26

- Fixed repeated navigation and login labels caused by non-idempotent DOM localization updates.
- Prevented the localization observer from reacting to its own text normalization mutations.
- Synchronized the web fix to the production release and verified the web container health endpoint.
- Initialized Git repository management for the complete production system workspace.

## v2.1 - 2026-08-25

- Restored the approved v3.2 competition prototype as the production web interface.
- Preserved the four navigation groups and eleven airline marketing workbenches.
- Connected the v3.2 interface to tenant authentication, campaign data, dynamic ontology graph, imports, model providers, agent runs, and platform administration APIs.
- Added production-only governance pages without replacing the approved marketing workflow or visual system.

## v2.0 - 2026-08-25

- Replaced the single-organization prototype with tenant, user, membership, and role management.
- Added token authentication and mandatory server-side tenant context validation.
- Scoped campaigns, model providers, agent runs, ontology data, and import jobs by tenant.
- Replaced hardcoded graph responses with PostgreSQL ontology entities and relations.
- Added governed CSV and JSON imports with validation, upsert, provenance, confidence, batch history, and row-level errors.
- Added tenant-aware graph exploration, data import, model configuration, and platform administration workbenches.
- Added PostgreSQL initialization locking for safe multi-worker startup and legacy schema migration.
- Added responsive small-screen layouts and deployed the release at `/ceair-marketing/`.

## v1.0 - 2026-08-24

- Created the production system workspace under the competition directory.
- Added a React and TypeScript operations console.
- Added a FastAPI platform API with campaign and agent-domain endpoints.
- Added a governed agent runtime with append-only execution events.
- Added a marketing ontology graph with evidence and confidence metadata.
- Added API tests and production frontend build verification.
