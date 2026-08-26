# ADR 0001: Tenant Isolation And Ontology Storage

## Status

Accepted

## Decision

All business records are scoped by `tenant_id`. API access requires an authenticated user and a tenant membership. Tenant selection is explicit through `X-Tenant-ID`; the server validates membership and never trusts a client-side filter.

Ontology entities and relations are stored in PostgreSQL rather than generated in application code. Imported records retain source, batch, attributes and confidence metadata. Relations may only connect entities belonging to the same tenant.

## Consequences

- Every repository query and mutation must include tenant scope.
- Cross-tenant reporting requires a separate privileged aggregation path and is not implemented by ordinary tenant APIs.
- Existing records are migrated to the default tenant.
- Import is a governed batch process rather than direct graph mutation.
