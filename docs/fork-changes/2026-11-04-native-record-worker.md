# Native record worker boundary

## Reason and inspected owner

G4 replaces the aggregate JSON/keyword-reference-index route for exact record
reads. The existing `OxigraphStore` is the unique fact owner; its
`publication_status`, `read_native_records` and `read_publication_records`
implement the publication fence, membership checks and bounded typed fields.
Inspected fork main `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus the current
G1–G4 work in progress. No alternate graph store or record index is added.

## Implementation and deletion boundary

`CanonicalRecordRequest` now accepts the worker-only `semanticStore` reference
`{path, project, generation}` and either exact native IDs or a source-scoped
IRI cursor. The obsolete snapshot path/digest/ID, keyword index dependency and
aggregate field selector are deleted from this request. Old inputs fail schema
validation; there is no compatibility reader.

`semantic_query.read_canonical_records` delegates directly to the native owner.
`NativeQueryStore` holds one exclusive native handle in the existing serial
query worker. `acquire_store` checks the existing store location and exact ready
publication; records borrow that handle and recheck the fence. Switching
path/project requires an acknowledged `release_store`. Release checks path and
project only; its location-only DTO rejects a generation. Releasing an absent
reader is idempotent and never opens or creates a store.
The worker closes its handle on shutdown. Reads enforce 128 records and 256KiB, preserve typed
RDF fields, and fail on missing/outside-publication records. Cancellation is
checked before admission and before returning. No original body, whole graph or
keyword index is read or copied on this path.

Opening a store held by another writer fails explicitly. Native read-only
opening is deliberately not used: PyOxigraph documents concurrent writer plus
read-only-process access as undefined behavior. Product lifecycle integration
must drain queued native reads, release this reader, and only then open the
writer. The worker protocol enforces the handoff identities; the corresponding
host lifecycle integration still needs product verification.

## Regression evidence

Two positive worker specifications failed against the old snapshot request
contract before the producer change. `pytest -q tests/test_native_record_worker.py`:
**14 passed**. Real native stores cover typed fields, source cursors, project and
generation mismatch, missing stores, pending/withdrawn state, writer lock,
response budget, cancellation, stable reader reuse and reader/writer handoff. No model, network or formal profile
was used.

The real JSONL worker test keeps its reader alive across release ACK, allows a
separate writer to acquire the store, then reacquires and reads after writer
closure. This verifies the process boundary rather than just local handles.

## Exact source ranges and publication build transport

The existing `DocumentReaderSelection` accepts `field: ranges` with explicit
`ranges: [{nativeRef, start, end}]`. References are exact scalar addresses in
the unique parsed-source JSON; offsets are scalar-local Unicode codepoints.
No keyword index or source-body projection is used. The existing reader owns
installation fences, segment addresses and digest-checked range decoding.
Ranges are limited to 128 and 65536 codepoints each, with physical and transport
budgets at most 256KiB. Exact reads reject an incomplete scalar or exceeded
budget instead of returning a partial selection. They do not accept pagination.
The combined native reader/record/build-worker regression suite passed **33
tests**. Build-worker tests assert pending remains pending and no aggregate
artifact metadata is returned; the schema test rejects retired validation.

Build transport now returns only publication status, the native store reference
and relay receipts. It does not turn producer results into graph, retrieval or
document-body artifact copies. The obsolete semantic graph schema output and
`validate_artifact` consumer are removed. This transport change awaits complete
producer and host integration verification; pending publication is not ready.

## Remaining integration and upstream assessment

The separate keyword/semantic query route and report/explanation route still
need their native consumer migrations. Their existing aggregate dependencies
are explicit G4/G5 remaining work, not fallback for record reads. This scoped
result does not establish whole-system deletion, published artifacts or App
acceptance. Report context must be bounded by selected references and source
ranges, never reconstructed as a `SemanticArtifact`.

The worker protocol is a fork integration boundary; native RDF storage and
publication semantics remain in the existing triplet-store owner. No upstream
algorithm is replaced.
