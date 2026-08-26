# Domain Glossary

## Tenant

An independent marketing operating organization whose campaigns, model providers, agent runs, ontology data and imports are isolated from every other tenant. A tenant is not an airline passenger or customer.

## Platform User

An employee or operator who authenticates to the platform. Access to a tenant is granted through a tenant membership.

## Tenant Membership

The relationship between a platform user and a tenant, including the user's role in that tenant. Roles are `admin`, `manager`, `analyst`, and `viewer`.

## Ontology Entity

A tenant-owned business object with a stable external identifier, type, label, properties, provenance and confidence. Typical types include Customer, Audience, Flight, Route, Product, ProductPackage, Campaign, Content, Channel and ConversionResult.

## Ontology Relation

A typed, directed relationship between two ontology entities in the same tenant, with evidence, provenance and confidence.

## Import Batch

An auditable attempt to ingest entity or relation data from CSV or JSON. It records validation results, accepted rows, rejected rows and error details before data becomes available to agents.
