# Native scene demand-driven field projections

- Record ID: 2026-11-07-native-scene-field-projection
- Date / author: 2026-11-07 / native owner remediation
- Status: verified-in-stated-scope (native owner and worker suites)
- Fork base revision: 356332b994a7ba7d872a4a7011e1cbcfa6cdf014
- Upstream reference: not newly inspected; existing native owner repaired in place
- Related issue / records: OntoScience G4/G56 acceptance, captured request #96

## Reason and scope

A real G56 build failed while enumerating a community's member identities:
`scene(kind=nodes, communityId=community:d9ee7a78ace79c7787476296,
limit=128,maxBytes=262144)` returned `Canonical read exceeds byte budget`.
The caller needed only IDs, but scene hydrated all canonical membership, selectors,
fields and provenance. Incident traversal similarly hydrated all endpoints and fact
qualifiers although its consumer needed four relation fields.

## Native capability assessment

Existing canonical owners are `PublicationRecords.scene`, `_incident`, `_read`,
`_canonical_references` and `_selected_scene_fields`, inspected at the base above.
Actual consumers are OntoScience understanding-worker and its current indexed UA
organizer. `_read(fields=...)` already performs indexed native predicate reads.
Repair extends these owners; no second query method, knowledge store or body cache.

## Approach and actual changes

- `publication_records.py`: strict explicit fields projections for catalog nodes
  (`id,name,sourceIds`), membership (`id`) and incidents
  (`id,source,target,predicate`). The response echoes the requested fields and
  contains exactly their DTO fields. Existing full UI scene reads stay complete.
- Name reads retain selected-member/source-scope scalar conflict semantics while
  reading only name predicates and selectors. Source references join admitted
  operation ownership without loading evidence. ID reads perform no hydration.
- Incident reads retain current publication focus admission and seek pagination,
  project only the representative predicate and never load endpoint bodies.
- `semantic_query_schema.py`: selection field-count allowance increases by one
  for fields, without changing paid build input schemas or resource limits.
- Tests cover exact shapes, source scope, selected name equivalence, stale/withdrawn
  generations, cancellation, keyset traversal beyond 128, byte budgets and rejection
  of invalid projections. Full-hydration budget failure is injected for captured
  request #96; its explicit identity projection succeeds with hydration forbidden.

All generation fences, cancellation, row and byte limits remain. No model/network
calls are added. Query code participates in PROJECT_PROCESSING_DIGEST, therefore
any fixed artifact needs the explicitly verified offline paid-result adoption
boundary; the digest algorithm is unchanged. Original accepted payloads are not
modified by this query repair.

## Verification and limitations

- Red: two focused owner specs failed on the previous implementation rejecting
  the fields selector. Green: the same two passed after the repair.
- Equivalent one-node native fixture: `_read` emits nine actual field terms / 1310
  JSON bytes for full hydration versus one field term / 308 bytes for projected
  name. One sample measured 1.24ms versus 0.92ms; these small fixture timings are
  supporting evidence, not real ESG capacity acceptance or a stable benchmark.
- Related owner/worker suites: `.venv/bin/python -m pytest -q
  tests/triplet_store/test_publication_records.py tests/test_semantic_query_worker.py
  tests/test_native_record_worker.py` — 65 passed in 18.59s. The existing native
  worker fixture now explicitly closes its writer before worker acquisition;
  `del` alone retained an Oxigraph lock through the owner's reference cycle.
- Worker protocol tests verify exact projection passthrough alongside the full
  scene contract. `git diff --check` passed.
- Product/native artifact integration and real ESG acceptance belong to the host
  delivery. These tests do not claim those gates pass.

## Upstream merge assessment

- Disposition: keep/adapt until upstream's same native owner has equivalent demand
  projections. Incoming upstream revision not newly reviewed.
- Likely overlaps: native scene selectors, canonical name hydration, incident
  traversal. Preserve one native implementation and current host DTO validation.
- Required merge checks: publication record, query worker and native record suites,
  host projected DTO boundary, understanding catalog and real product acceptance.
