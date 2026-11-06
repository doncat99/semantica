# Incremental native vector-link publication

- Record ID: 2026-11-03-vector-link-incremental-publication
- Date / author: 2026-11-03 / OntoScience integration
- Status: verified-in-stated-scope (source regressions and complete native artifact)
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing dirty work
- Upstream reference: not reviewed this turn
- Related record: [canonical topology](2026-11-03-canonical-topology-references.md)

## Reason and native owner

`GraphSearchIndex._publish_vectors` rebuilds a second candidate projection and
repeats evidence interval joins for every vector, including unchanged sources.
Repair this owner, called by `_write_reference_index` and
`semantic_artifact_builder.artifact_writing`. Reuse the canonical reference
tables and `SQLiteVecStore.add_groups`; do not introduce a host knowledge store
or an alternate search algorithm. Existing tests are
`test_semantic_reference_topology.py`, `test_semantic_query_worker.py`,
`test_native_snapshot_search.py` and `vector_store/test_sqlite_vec_store.py`.

## Planned change and deletion

Delete the second `iter_snapshot_candidates` pass and copied candidate/source
lookup tables. Derive candidate evidence from the already published canonical
indexes, including evidence candidates' self-reference. Record source-bound
link-input digests and vector source intervals in the native index. With an
authenticated baseline in the identical embedding space, reuse only links with
the same source input digest and interval; remap canonical field/ID to the new
publication's record and position. Changed links recompute in this same owner.
No model/network call, dependency, alternate reader, schema-version dispatcher,
host DTO or UA change is required. Missing link receipts on an embedding baseline
must explicitly require rebuild, not guess reuse or read a legacy format.

## Verification plan and limits

First reproduce the duplicate projection and absent reuse with a red spec.
Cover reorder, changed and withdrawn evidence/candidates, changed vector space,
source withdrawal, zero-link chunks and publication failure without replacement.
Compare new semantic group results against a clean native publication. Keep
batch size 128 and disk staging bounded. Record measured link-join/reuse counts.
This change does not eliminate full immutable snapshot/index/vector payload
writes or the full source fingerprint scan. D04 remains open until those costs
are addressed in the canonical storage contract. The existing dev bundle does
not contain this change; rebuild and qualify it before consumer acceptance.

## Upstream merge assessment

Pending. Retain only while the native publisher lacks equivalent source-bound
link receipts. Recheck the vector store, canonical tables, query ordering and
worker acceptance after upstream changes; never keep two publication owners.

## 2026-11-03 implementation and regression evidence

Repaired `_publish_vectors` and passed its authenticated baseline from the
existing publisher. Removed the second candidate projection and whole copied
candidate/source tables. Native `vector_chunks` holds ID/interval/input-digest
receipts; `vector_links=source-bound` declares their capability without another
format version or reader branch. Source fingerprints stream canonical evidence
positions and candidate field/ID; reused links remap to current record/position
and current authorization scopes. Changed evidence or candidates invalidates the
affected source. A changed embedding space recomputes links in this same owner.
Unqualified embedding baselines require explicit index rebuild; no model rerun.

The first red test failed on the duplicate projection (1 failed), in the host
evidence path `.tmp/deep-vector-links-red.log`. First broad run exposed a real
high-fanout writer/read-lock conflict and an existing atime-sensitive immutable
input test (150 passed, 2 failed, `.tmp/deep-vector-links-regression.log`).
Fixed the conflict by staging just the active 128-vector batch's links/scopes
on disk before vector-store writes; no canonical read cursor survives into that
writer. The unchanged regression group then passed 152 tests in 18.72 seconds
(`.tmp/deep-vector-links-regression-retry.log`). The independent focused set
passed 8 tests. It covers reordered IDs, candidate withdrawal, moved evidence,
source withdrawal, zero-link chunks, incompatible spaces, two consecutive
increments equal to clean publication, absent receipt rejection and failed
second-batch publication preserving existing output bytes. Existing 2,000-group
fanout and 257-vector batching/read-after-reopen tests are retained.

Corrected the immutable-input test to compare body digests, inode, size and
nanosecond write timestamps; read-induced atime changes do not mean mutation.
Final rerun and native artifact qualification remain pending at this entry.
No network/model call or host/UA contract change. Full source fingerprinting,
canonical JSON/topology rebuild and vector/link payload rewrites remain; this
is link-computation reuse, not full delta I/O or a D04 closure.

## 2026-11-03 final source and artifact qualification

The final four-file source regression group passed 152 tests in 30.66 seconds
(`.tmp/deep-vector-links-final.log` in the consumer workspace). A complete native
development artifact was built from frozen Semantica source digest
`50046ec4d9bd67d11ebd17ca2ea35a12b8ee9fe292921c18411ba7f9fabf1b08`:
`sha256:a91478ea6808305470a6b633d29080f3c82ecbe0dd1407f752cc55dfb0e5573f`.
Its 34,717-file inventory and relocated acceptance passed (232,731 ms), as did
subsequent direct cache inventory verification. Qualification uses the bundle's
Python with `-I -B`; no checkout or virtual environment is a runtime input.

An additional 130-vector, two-source bundled regression crosses the 128-vector
batch boundary: initial publication rebuilds 130 links; reordered identities
reuse 130; candidate withdrawal reuses 65 and rebuilds 65. Both increments equal
clean publications for groups, positions and scopes. Missing receipt capability
is rejected without replacing existing bytes; an explicit publication without a
baseline succeeds from saved canonical inputs. Network connections were disabled,
with zero calls. Evidence: `.tmp/deep-vector-artifact-qualification.log`.
The consumer's native publisher to host to UA child/provenance integration also
passed all four tests (`.tmp/deep-vector-native-ua-focused.log`, 36.54 seconds).

This evidence-only entry was appended after source freezing and does not relabel
the frozen input or qualify a release pin. Full delta I/O, production content and
real model quality remain outside these passed checks. No release was published.
