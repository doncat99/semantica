# Native TypeDB semantic snapshots

Reason: consumers already operate TypeDB. Reusing that service avoids adding a
second database solely for Semantica persistence.

Owner: graph_store.GraphStore; native SemanticArtifact validates identity,
references, lineage and payload. TypeDBStore implements atomic immutable revisions
and optimistic head advancement using TypeDB keyed entities and transactions.
The host retains driver, credentials, database lifecycle and authorization.

Affected callers/data: new explicit GraphStore(backend="typedb", driver=...,
database=...) snapshot calls. Existing backends and their data are unchanged.
No Cypher emulation, domain-specific schema, credentials or automatic fallback.
Initialization is a host-run schema migration before concurrent writers start.

Verification: isolated TypeDB contract tests cover restart, replay, scope isolation,
stale writes, conflicts, rollback and concurrent commits. Results are recorded after
execution; this change alone does not establish application cutover or live success.

Upstream: additive optional TypeDB driver; no new mandatory dependency. The generic
snapshot contract is backend-explicit and raises when unsupported.
