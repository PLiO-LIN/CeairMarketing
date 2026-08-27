# China Eastern Data Processing and AI Marketing Full Flow v1.0

> Review document for business, product, data and engineering teams. Based on the current repository implementation, ontology semantic model and production UI. The document separates implemented, partial and recommended capabilities.

## 1. Overall Positioning

Marketing operators should not maintain ontology entities or relations manually. They should drop business files or use approved data sources. The system parses, cleans, extracts, validates and stores business knowledge, then makes it available to six marketing agent domains.

Main chain:

    Documents / APIs / Databases
      -> Unified ingestion
      -> Parsing, OCR and table extraction
      -> Cleaning, deduplication and standardization
      -> Data Processing Agent
      -> Business objects, relations, evidence and confidence
      -> Knowledge base + ontology graph
      -> Opportunity -> Audience -> Product -> Activity -> Content
      -> Approval and compliance -> Channel execution -> Feedback
      -> Attribution -> Review and strategy learning

The platform already has file ingestion, MinerU integration, a shared Harness, six agent-domain contracts, tenant isolation, model configuration, knowledge storage and ontology storage. Production gaps include durable workers, API/database connectors, candidate-fact review, real channel callbacks and complete object-level write-back from every agent domain.

## 2. Operator-facing Workspaces

| Workspace | Operator action | Automated work |
| --- | --- | --- |
| Data ingestion | Drop news, notices, service files or operation reports | Parse, clean, classify, extract and update the knowledge foundation |
| Opportunity and audience | Review market signals, anomalies and audience evidence | Link route, flight, operation, profile and historical data |
| Products and benefits | Select fare, ancillary, coupon, loyalty or intermodal products | Check eligibility, inventory, validity, rules and delivery |
| Content workshop | Review and edit channel versions | Generate content from approved product facts and audience context |
| Campaign center | Create, approve, publish and monitor campaigns | Link opportunity, audience, package, content, budget and channels |
| Performance review | Inspect delivery, ticketing, coupon, ancillary and revenue | Attribute results and generate next-cycle recommendations |
| Governance center | Inspect graph, providers, batches, permissions and audit | Maintain tenant, model, source and action records |

The UI should hide external IDs, ontology types and relation endpoints. Review screens should show business name, source file, evidence excerpt, confidence, validity, proposed action and review state.

## 3. Data Sources

### 3.1 File Sources

The current UI supports drag-and-drop and multiple file selection for TXT, Markdown, HTML, CSV, JSON, PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, PNG, JPG and JPEG.

Typical China Eastern materials include news, route opening notices, seasonal schedule changes, passenger notices, special passenger services, transfer and air-rail rules, fare and refund rules, baggage and seat services, loyalty benefits, coupons, route operation reports, load-factor analysis, price monitoring, campaign plans, channel delivery logs and review reports.

### 3.2 API Sources

Administrators should configure connectors instead of asking operators to upload API response files. Priority sources are the user profile platform, product management platform, flight and route systems, operations analytics, channel systems, and transaction and fulfillment systems.

Every connector should record source, version, sync time, incremental cursor, field mapping, quality result and failures. Agents may read only connector-authorized data and may not call arbitrary systems.

### 3.3 Database Sources

Database ingestion should use read-only credentials, table/view allow-lists, field allow-lists, incremental timestamps, masking and tenant ownership. The platform maps source rows into canonical business objects. Agents must not execute arbitrary write SQL.

## 4. File Processing Pipeline

Each file creates one DataPipelineJob. The create endpoint returns the job immediately and the UI polls the job endpoint.

    queued -> running -> received -> extracting -> extracted
             -> classifying -> classified -> persisting
             -> ontology-updated
             -> failed

Business-facing stages:

1. File receipt and security check: extension, size, tenant and submitter.
2. Content parsing and structure recognition: text, Office, PDF, image and table content.
3. Cleaning and knowledge chunking: headings, pages, sections, tables and source positions.
4. AI business extraction: routes, flights, products, services, rules, opportunities and campaigns.
5. Airline semantic validation: object types, relation direction, time windows and constraints.
6. Knowledge and ontology persistence: raw evidence, chunks, candidate objects and relations.

Current UI progress is a stage mapping, not a precise parser or model percentage. Production workers should report item counts, elapsed time, retry count and per-stage progress.

## 5. Document Parsing and Error Handling

PDF, Office and image documents are parsed through the configured MinerU integration. Administrators configure endpoint, key and parser options. The key is encrypted server-side and never returned to the browser.

Recommended metadata includes file name, hash, size, source, uploader, tenant, submission time, parser version, MinerU task ID, elapsed time, page and section positions, table and image references, OCR confidence, parse errors and human review state.

Errors should be separated into ingestion, parsing, data-quality, semantic, model and persistence errors. Each error should include file, page or row, reason, source excerpt, batch and recommended action. Retries must be idempotent. ZIP should be represented as a parent batch with child files, child jobs, a manifest, isolated failures and overall progress.

## 6. Data Processing Agent

The Data Processing Agent converts unstructured or semi-structured material into searchable knowledge and computable business objects. It is not a summarizer and must not directly change product, flight, customer or channel source systems.

Outputs:

- Raw knowledge: source file, parsed text and knowledge chunks.
- Business facts: explicit route, flight, service, rule, product or campaign facts.
- Candidate inferences: possible market signals, opportunities or customer needs inferred from multiple facts.
- Relations and evidence: object links with source, excerpt, confidence, validity and batch.

Processing steps are: load tenant and job context; read authorized documents and chunks; load ontology reads, writes and functions; extract objects and relations using China Eastern marketing semantics; separate facts from candidates; bind evidence and confidence; validate object types and relation endpoints; write to the knowledge foundation.

The agent uses the shared Harness for MinerU, model calls, structured JSON, token usage, runtime events and controlled fallback. A fallback result must not be presented as a high-confidence fact.

## 7. Knowledge Base and Ontology Foundation

The knowledge base and ontology are complementary:

| Layer | Stores | Answers |
| --- | --- | --- |
| Knowledge document | Original file, title, source, version and hash | What was the source? |
| Knowledge chunk | Content with section and page context | What evidence supports the statement? |
| Ontology object | Route, flight, product, audience, opportunity, campaign, approval and result | What business object is this? |
| Ontology relation | Business links among objects | How are objects connected? |
| Evidence | Source, confidence, validity and batch | Why should the operator trust it? |

Lifecycle:

    Market signal -> Opportunity -> Customer need -> Marketing objective
    -> Audience snapshot -> Value proposition -> Product package
    -> Strategy plan -> Touchpoint plan -> Content and campaign
    -> Approval -> Execution -> Feedback -> Attribution -> Review

The model should cover passenger tickets, fares, fare rules, routes, flights, air-rail intermodal products, baggage, seat selection, lounges, insurance, coupons, mileage, loyalty benefits, enterprise products, OTA/NDC channels and service rules.

Labels are configurable attributes of customer aggregates or audience snapshots, not the whole audience model. They may come from the existing profile platform, authorized external data, travel and purchase behavior, loyalty and service behavior, or agent suggestions. Each label needs source, update time, calculation definition, consent usage, marketing eligibility and review state. A campaign uses a versioned audience snapshot rather than a label name alone.

## 8. Six Marketing Agent Domains

### Opportunity Insight

Reads market interest, routes, flights, load factor, price, inventory, operation status, historical review and business rules. Detects demand/supply changes and unusual combinations. Outputs opportunity candidates, opportunity score, customer-need candidates, objectives and evidence. A business owner confirms whether an opportunity becomes a campaign.

### Audience Insight

Reads profile indicators, existing labels, customer relations, journey stage, history, consent, contact frequency and protection rules. Produces a versioned aggregate audience snapshot with size, evidence, label sources, exclusions and reachability. It cannot enlarge the approved audience scope.

### Product Matching

Reads customer needs, audience snapshots, value propositions, product-management versions, fare, inventory, flight, membership qualification and service rules. Matches fare, ancillary, intermodal, coupon and benefit packages. Outputs recommendation, fit score, qualification, limitations and evidence. It cannot invent price, inventory or benefit eligibility.

### Activity Orchestration

Reads objective, audience, product package, channel, budget, timing, frequency and compliance rules. Creates campaign version, touchpoint plan, schedule, budget, fallback contact and monitoring metrics. It produces an approval-ready plan and cannot bypass approval.

### Content Generation

Reads approved product facts, customer need, audience context, value proposition, campaign strategy, channel rules and brand policy. Generates App, SMS, WeChat, website and enterprise-channel variants. It must return fact-check and compliance-check results; humans approve brand, legal and price expressions.

### Effect Analysis

Reads delivery, send, open, click, ticket, coupon, ancillary, refund, complaint, fulfillment, revenue and control-group data. Produces feedback, attribution, review, anomaly findings and next-cycle recommendations. Attribution definitions and rule changes require human confirmation.

## 9. Shared Harness and Governance

All data and marketing agents use one provider-neutral Harness. Every run has tenant ID, run ID, agent ID, allowed reads, allowed writes and allowed functions. The Harness records context loading, tool calls, model calls, structured parsing, token usage, failures and fallback behavior.

Agent results should use explicit states: fact, candidate, recommendation, human_confirmed, rejected and expired. A model output is not automatically a formal product, audience, strategy, compliance decision or campaign. Formal actions require a business confirmation event and preserve the original recommendation, edits, reviewer, time and reason.

## 10. End-to-end Marketing Process

    01 Opportunity discovery
    02 Audience identification
    03 Product package matching
    04 Campaign creation and versioning
    05 Content generation and review
    06 Budget, consent, protection, frequency and compliance checks
    07 Approval and controlled publication
    08 Channel delivery and state callback
    09 Ticket, coupon, ancillary, fulfillment and complaint feedback
    10 Attribution, review and strategy learning

Recommended campaign states are Draft, Content Review, Business Approval, Compliance Review, Ready to Publish, Running, Paused, Completed, Under Review and Archived. State transitions record operator, time, approval comment, version and evidence. No agent can move a campaign directly from Draft to Running.

Before delivery, the system checks consent, protection lists, complaint protection period, cross-channel frequency, product validity, fare and inventory, membership qualification, coupon conditions, transfer/MCT constraints, content facts, budget and channel publication capability.

## 11. Current Implementation Assessment

### Implemented

- Multi-tenant login, workspace and tenant-scoped queries.
- Drag-and-drop multi-file data ingestion UI.
- Pipeline creation, list query and single-job query.
- Basic TXT, Markdown, JSON and CSV reading.
- MinerU integration configuration with encrypted server-side key storage.
- Knowledge documents, chunks, ontology objects and relations.
- Data Processing Agent structured extraction, relation extraction and fallback.
- Shared Harness context, tool, model, event and token-usage handling.
- Six agent-domain contracts with reads, writes and functions.
- Ontology semantic model, relation endpoint validation and knowledge search.
- Model provider configuration, model listing, connection testing and usage statistics.

### Partially implemented

- Background task execution exists, but there is no durable queue, worker fleet, retry policy, cancel operation or cross-instance recovery.
- Progress is mapped by stage rather than measured by parser/model item counts.
- Candidate object persistence exists, but a full candidate-review, conflict-resolution and release workflow is still required.
- Agent runs and events are recorded, but not every domain writes a complete business object chain back to the ontology.
- Activity, approval, execution and review screens have platform data and sample records, but real channel callbacks and transaction reconciliation remain to be connected.
- File ingestion is available; API and database connectors, scheduling and source management are still required.

### Recommended production work

- Durable object storage, virus scanning, hash deduplication, retention and ZIP parent/child batches.
- Connector framework for APIs and databases with read-only credentials, mapping, incremental sync and quality rules.
- Human review workbench for object, relation and evidence confirmation.
- Ontology versioning, effective dates, conflict detection, merge and decision history.
- Campaign state machine, approval nodes, compliance execution, publish rollback and idempotent channel commands.
- Real App, SMS, WeChat, website, enterprise, OTA and NDC delivery callbacks.
- Unified transaction, coupon, ancillary, fulfillment, refund and complaint attribution.
- Agent evaluation sets, model and prompt versioning, quality scoring, cost controls and feedback loops.

## 12. Decisions Required

1. Which extracted objects may be auto-confirmed, and which must wait for human review?
2. Should every ontology assertion be candidate-first, or can trusted master data become formal immediately?
3. What exact versioned interfaces are available from the product management platform?
4. Does the profile platform return passenger-level data, aggregate audiences or only label metrics? Is the marketing platform restricted to aggregate use?
5. Can external data become ontology instances, or only market signals and evidence?
6. Are channel delivery, ticketing, coupon and ancillary callbacks available in one event contract?
7. Does approval remain in OA with integration, or become a marketing-platform workflow?
8. Must candidate, formal and expired ontology objects be separated by status and version?
9. Can each agent domain use a different model, or is there one tenant default with optional overrides?
10. What evidence and explanation must an operator see before approving content, product matching or attribution?

## 13. Recommended Delivery Priority

### P0: Business-usable ingestion

Finish drag-and-drop processing details, durable raw-file storage, candidate review, and the first approved interfaces to the profile and product management platforms.

### P1: Closed-loop campaign

Connect opportunity, audience, product, content, campaign, approval, execution, feedback and review. Integrate at least one official touchpoint and one real result source. Enforce product, consent, budget, frequency and compliance checks.

### P2: Scale and governance

Add API/database connectors, durable workers, large-file handling, ontology versioning, agent evaluation, model routing, cost monitoring, quality monitoring and cross-source conflict handling.

## 14. Review Checklist

- [ ] Operators submit business files or configure approved sources; they do not manually import ontology entities and relations.
- [ ] The Data Processing Agent extracts facts and candidates, binds evidence and confidence, and does not bypass human governance.
- [ ] Knowledge documents preserve source evidence; the ontology expresses business objects and relationships.
- [ ] All six marketing agent domains use the same governed context and ontology foundation.
- [ ] Product management platform and user profile platform are upstream systems, not replaced by this platform.
- [ ] Real channel and transaction callbacks are required for production attribution.

Open comments:

Record business-flow, data-source, agent-boundary, ontology, approval or production-operation changes here.
