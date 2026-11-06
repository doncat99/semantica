# Canonical fact publication membership

## Reason and native owner assessment

Inspected canonical fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
with preexisting G4 work. `ExtractionRecords` owns raw grounded relations and
qualifiers. `ConflictDetector` owns qualified canonical fact identity, status and
conflict semantics. `PublicationRecords` previously persisted canonical entity
membership only and scene/incident queried raw extraction Relations, losing
canonical fact grouping and merged provenance. This change extends that single
publication owner; it does not introduce an alternative reconciliation algorithm.

## Implemented

- `stage_facts` appends reference-only canonical fact membership in bounded
  batches. Repeated pages must preserve endpoints, representative, status and
  expected member count. Native observations retain all extraction payloads.
- Validate native Relation ownership, canonical endpoints, identical native
  predicate and qualifier fields, one membership owner, and atomic batch plans.
- Activation rejects incomplete member plans, absent representative membership
  and any admitted native Relation lacking canonical membership.
- Scene/incident read canonical fact membership, dereference representative
  native fields and aggregate all member source/evidence addresses within the
  explicit scene projection budget. Exact node selection accepts canonical fact
  IDs. Both entrypoints share one link hydration implementation.
- `read_publication_fact_members` exposes keyset pages of raw support references;
  raw record bindings continue to resolve each observation's exact source.
  Support groups are not capped at a single staging/read page.

## Regression evidence

Before the change, `/tmp/test_g4_canonical_publication_red.py` reproduced two
raw links for the same canonical qualified fact across two source operations:
1 failed in 0.39s (`/tmp/g4-canonical-publication-red.log`).
After implementation:
`tests/triplet_store/test_canonical_fact_publication.py` and
`tests/triplet_store/test_publication_records.py`: 25 passed in 11.27s.
These verify append/seal, support union, restart, source bindings, scene/incident
agreement, exact canonical fact node selection, withdrawal, wrong endpoints,
changed plans, duplicate ownership and missing raw-relation coverage. No model
or network calls are used.

## Required integration and limitations

This is a breaking publication contract, not a completed G4 build delivery.
The builder must preserve native Relation addresses through grounded windows
and canonical reconciliation and call `stage_publication_facts` before activation.
It currently does not: builds with Relations now fail explicitly at activation
instead of publishing unreconciled facts. All producers/fixtures must migrate in
the parent G4 integration before this change is deliverable.

Assertion/conflict publication remains absent; `status` is supplied by the
canonical reconciliation owner but conflict objects themselves are not staged by
this change. Raw predicate/qualifier equality validation is intentionally strict;
normalization-changing reconciliation needs a canonical field-selection contract
rather than silently mixing inequivalent native fields. The complete scene
support address projection fails explicitly beyond its budget; its support-member
page exists at the native store boundary and still requires worker/application
exposure and consumer integration. Canonical fact IDs cannot be passed as if
they were raw observation IDs to `read_record_binding` or `read_native_records`.

No artifact, dependency pin, release publication, paid model call or ESG scale
qualification was run. Upstream merge assessment remains pending and must preserve
reference ownership, exact activation coverage and canonical scene semantics.
