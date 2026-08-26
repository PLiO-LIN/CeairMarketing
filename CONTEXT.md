# Domain Glossary

## Tenant

An independent marketing operating organization whose campaigns, model providers, agent runs, ontology data and imports are isolated from every other tenant. A tenant is not an airline passenger or customer.

## Platform User

An employee or operator who authenticates to the platform. Access to a tenant is granted through a tenant membership.

## Tenant Membership

The relationship between a platform user and a tenant, including the user's role in that tenant. Roles are `admin`, `manager`, `analyst`, and `viewer`.

## Ontology Entity

A tenant-owned business object with a stable external identifier, type, label, properties, provenance and confidence. It represents a real airline marketing concept rather than a source-system table.

## Ontology Relation

A typed, directed relationship between two ontology entities in the same tenant, with evidence, provenance and confidence.

## Marketing Case

The end-to-end business spine that connects a confirmed marketing opportunity to its audience snapshot, product package, campaign versions, content, approvals, execution batches, feedback, review and next-cycle recommendations.

## Configurable Attribute

A governed business attribute attached to an ontology object. It can reuse an existing profile-system label, be configured by an operator, or be proposed by an agent; the ontology does not prescribe concrete label values.

## Candidate Fact

A fact or relationship extracted or inferred by an agent that retains evidence, provenance, confidence and validity information. It does not become a confirmed business decision until accepted by a platform user or governed action.

## Audience Snapshot

An immutable, versioned aggregate audience used by one campaign version. It contains selection semantics and population counts without exposing individual passenger details in the marketing workspace.

## Product Package

An approved, versioned combination of ticket, fare, ancillary service, coupon, member benefit or intermodal product that can be referenced by a campaign.

## Import Batch

An auditable attempt to ingest entity or relation data from CSV or JSON. It records validation results, accepted rows, rejected rows and error details before data becomes available to agents.
