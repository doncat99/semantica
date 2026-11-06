# Native restore verification and bounded Explorer

## Owners and data boundary

`native_maintenance.py` is an offline integrity operation over the existing
Oxigraph, keyword index and SQLiteVec owners. It creates no knowledge carrier,
graph export, checkpoint, snapshot or content copy. The input is an existing
installation and its exact reference-only publication receipt. A live Oxigraph
writer prevents verification; the host must first close its worker owner.

The request file is at most 64 KiB. `deadlineSeconds` is 1–600 seconds. The host
must enforce a subprocess hard deadline because a single PyOxigraph operation
is not cooperatively interruptible. Traversal is incremental: RDF/record pages
are bounded to 128 rows/256 KiB, file hashing uses 256 KiB blocks, and vector
verification reads one bounded accepted vector at a time. No model is invoked.

Verification compares the complete publication reference before and after the
operation, accepted extraction/classification receipts, native source bindings,
keyword file digest and SQLite integrity, accepted vector receipts/digests and
vector-to-record/evidence links. Pending and withdrawn publications preserve
accepted operations but do not admit query indexes. Existing source references
are logical identities; they contain no installation-specific absolute paths.

Native vector publication digests use canonical key order, not producer iterator
order. `SQLiteVecStore.native_publication_digest` streams reference rows and
association rows in fixed SQL `ORDER BY`, hashes each bounded JSON row and is
used by both the producer and offline verifier. The processing recipe changes
with this rule; there is no old-recipe reader or compatibility dispatch.

The output's five keyword installation identity values are decimal strings,
preserving nanosecond timestamps beyond JavaScript integer precision. Restore
can update installation identity after verifying the relocated file without
rewriting content or changing logical provenance.

## Explorer

The host starts native Explorer with an authenticated ephemeral loopback relay,
not a copied graph file or a second RocksDB handle. Relay reads run through the
existing worker owner. The session contract is `{projectId,generation,url}`.
The random bearer token exists only in the native child environment. Bodies and
responses have a 256 KiB limit, one request may run at a time, and requests have
a 15-second deadline with owner cancellation on disconnect/shutdown.

Opening Explorer does not load the project. The user explicitly selects a source,
community, or 1–128 node identities. Each scene contains at most 128 nodes and
128 links. Continuation is exposed. Excess links fail explicitly and request a
smaller node selection; they are not sampled away. Existing native `ContextGraph`
and `GraphSession` hold this bounded, read-only transient scene only. No new
persistent graph or independent entity/relationship semantics are introduced.

The existing renderer/layout remains the visual owner. Navigation holds at most
64 explicit page selectors. Cancellation prevents installing the cancelled
selection, checked between bounded relay reads; an in-flight native HTTP read
may take up to its 16-second timeout before cancellation is observed.

## Verification boundary

Focused native maintenance/vector/publication/Explorer regression: **36 passed**.
Host Explorer lifecycle and Web session-contract tests passed. These are focused
implementation checks, not packaged ESG acceptance or search-performance proof.
No formal profile migration, data cleanup, release, model call or token claim is
part of this evidence.
