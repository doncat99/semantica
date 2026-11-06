# Native reference publication and producer cutover

The build no longer constructs or writes an aggregate `SemanticArtifact`,
`semantic-graph.json`, `retrieval.json`, or a graph-backed keyword SQLite index.
The base-snapshot loader and rebuild baseline have been removed from the producer.
Existing native extraction, classification, resolution, reconciliation and
organization computations remain. Paid final reports use the existing host
product adoption boundary.

Oxigraph remains the unique owner of accepted typed Entity, AttributeValue and
Relation values. The current publication graph contains only input identities,
native operation references, canonical membership, representative references and
field/property selection references. Property selectors target the actual native
AttributeValue. It does not persist canonical names, attributes, bodies, source
text or a second copy of facts. A replacement clears the previous publication
reference graph; it creates no revision history chain.

The producer explicitly collects the actual extraction and classification
operations it used. Admission validates their native operation and owned-fact
digests. Stage recipes differ legitimately; their complete receipts each bind
the actual recipe. Shared source identity must match project, source, material
and representation. Classification facts are included as native references,
not silently omitted. Deterministic pattern production also adopts native Entity
values, instead of maintaining a separate aggregate-only path.

Writes use batches of at most 128 references and a 256 KiB statement budget.
Reads use explicit record IDs or keyset pages, with row and byte ceilings.
Generation compare-and-swap is serialized on the single native owner, with
pending/ready/withdrawn states. The native writer is released on success and
failure, including flush failure; no concurrent `Store.read_only` workaround is
used (that pattern is undefined during an active writer).

The producer returns a **pending** reference publication, store locator and
model receipts. It does not fabricate G5 keyword/vector index receipts or mark a
product build ready before those owners publish verified indexes.

## Verification and remaining gates

- Real model build: no aggregate JSON/SQLite output, extraction plus
  classification references present; second build makes no new model calls and
  leaves native project facts byte-for-byte equivalent.
- Real deterministic build: native pattern contributions and reference-only
  pending publication, no aggregate output.
- Publication owner: restart, withdrawal, CAS concurrency, source isolation,
  stale generation, missing source-operation plan, corrupt native facts, field
  selection, multi-source replacement, 129-record pagination and byte budgets.
- Store close releases the native handle even if flush raises.

G4 is not claimed complete: one canonical record currently has a 128-member /
128-selector object budget. Larger memberships require their own bounded cursor
protocol, not a project-wide cap or truncation. Real scalar evidence grounding,
G5 indexes and all consumer cutovers must pass before product acceptance.
No release, packaging, formal-profile mutation, or old data cleanup was performed
as part of this producer change.

## Aggregate contract deletion follow-up

The unused aggregate `SemanticArtifact`, manifest/lineage/snapshot carriers and
aggregate JSON schema have now been physically removed. Build requests reject
the removed `baseSnapshot` field. Bundle schema identity derives from the current
build-request schema, and release manifests admit exactly the document
representation MIME contract; aggregate graph and retrieval media keys are
rejected. Native individual row models remain the computation contracts.

Focused contract and bundle verification: 45 tests passed in
`tests/test_semantic_artifact_contract.py` and `tests/test_bundle.py`.
This is supporting contract evidence only. It does not close the ready-query,
real-model, immutable release or product acceptance gates described above.
