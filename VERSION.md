# Version History

## v2.8 - 2026-08-31

- Added tenant-scoped activity product package persistence and CRUD APIs.
- Replaced static product package rows in the production workbench with live API data.
- Added product package creation, detail, rename and deletion flows with campaign reference protection.
- Added regression coverage for persistence and tenant isolation.

## v2.9 - 2026-08-31

- Added tenant-scoped content asset persistence for campaign channel content.
- Added content asset CRUD APIs with campaign reference validation.
- Replaced static content rows in the production workbench with live content data.
- Persisted AI-generated content drafts for review and added content detail, edit and delete flows.
- Added regression coverage for content persistence and tenant isolation.

## v3.0 - 2026-08-31

- Added tenant-scoped audience snapshot persistence derived from audience packages.
- Added versioned audience snapshot API for freezing campaign audience scope before execution.
- Added audience workbench snapshot action and snapshot status display.
- Added regression coverage for snapshot versioning and tenant isolation.

## v3.1 - 2026-08-31

- Added persistent campaign versions with audience snapshot, product package, content, budget and channel references.
- Added approval task creation and approve/reject decision APIs with campaign state transitions.
- Protected campaigns with versions from direct deletion to avoid orphaned lifecycle records.
- Connected the production workbench to live approval task data.
- Added end-to-end regression coverage for campaign version approval flow.
## v2.7 - 2026-08-27

- Changed file processing to persist source knowledge first and hold extracted ontology objects and relations as candidates until human confirmation.
- Added checkpointed processing events for parsing, knowledge persistence, Harness/model execution, semantic validation, review and ontology update.
- Added a marketing Copilot API with authorized knowledge search, ontology query, campaign inspection and product lookup tools through the shared Harness.
- Added unified Marketing Knowledge workspace combining the ontology graph and traceable knowledge search.
- Added drag-and-drop pipeline monitoring with live polling, candidate object preview and confirm/reject controls.
- Added provider workspace with model discovery, connection status and tenant-scoped usage distribution.
- Fixed repository-root environment loading so local development and tests do not depend on the process working directory.

## v2.6 - 2026-08-27

- Expanded the airline marketing ontology from operational lifecycle objects to a complete objective, need, value proposition, strategy, touchpoint, attribution, and learning chain.
- Mapped marketing planning, segmentation, value proposition, integrated communication, channel management, loyalty, lifetime value, and performance control concepts to executable China Eastern business objects.
- Extended all six intelligent-domain contracts so agents share governed marketing context while retaining human approval boundaries.
- Added a richer Shanghai-Sanya lifecycle graph covering measurable objectives, customer needs, product value, strategy, touchpoint planning, and multi-dimensional attribution.
- Updated the data processing agent to extract the extended marketing semantic objects and removed duplicate knowledge-document persistence.
- Added model discovery and tenant-scoped token usage accounting for OpenAI-compatible providers.

## v2.4 - 2026-08-26

- Added the China Eastern marketing operations ontology semantic registry covering data, opportunity, audience, product, content, campaign, approval, execution, feedback, and review.
- Added registered relation types, governed business actions, reusable business functions, and ontology read/write contracts for all six intelligent domains.
- Added ontology semantic model and conformance status APIs without changing the existing platform workbench layout.
- Extended governed data imports to accept registered ontology object types while retaining legacy compatibility.
- Added an idempotent end-to-end marketing lifecycle ontology instance for the Shanghai-Sanya campaign.
- Added ontology context events to agent runs so every run records the objects and functions it used.
- Added registered relation endpoint validation while retaining tenant-defined extension relations.
- Expanded the idempotent lifecycle instance with ticket, ancillary, coupon, channel and complete campaign spine objects.

## v2.5 - 2026-08-27

- Added the data processing pipeline for text, structured files, and MinerU-supported documents.
- Added a shared provider-neutral Harness used by the data processing agent and the six marketing intelligent domains.
- Added the knowledge base layer for versioned documents and traceable knowledge chunks linked to ontology objects.
- Added administrator-managed MinerU integration configuration and tenant-scoped pipeline and knowledge search APIs.

## v2.3 - 2026-08-26

- Updated the platform overview to reflect the meeting-defined loop: external signals, internal route operations, aggregated ToB/ToC audiences, AI suggestions with human approval, scheduled channel delivery, and anomaly-based learning.
- Replaced the placeholder sidebar character mark with the China Eastern brand symbol asset.


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
