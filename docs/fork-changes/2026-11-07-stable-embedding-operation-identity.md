# Stable physical embedding operations with current logical identity

- Record ID: 2026-11-07-stable-embedding-operation-identity
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 765c0ef2d1e868e074ca31068e9db90a0672a9c2
- Upstream reference: not inspected
- Related work: host G4–G8 identity and paid-result migration

## Reason and scope

Artifact-derived recipes previously changed native embedding operation keys even
when paid inputs and computation were equivalent. Re-adoption copied vectors and
receipts under new IDs. The current logical calculation identity must instead
resolve to the stable physical operation inside its existing SQLite owner.

## Native capability assessment

- Existing owner: `SQLiteVecStore` in `vector_store/sqlite_vec_store.py`.
- Inspected methods: `open_embedding_space`, `embedding_operation_id`,
  `read_embedding`, `adopt_embedding`, `publish_native_ranges` and native queries.
- Existing callers: publication builder, native query, offline rebind script.
- Existing tests: embedding handoff, native range publication and native builder.
- Decision: repair the same SQLite owner, adding only a logical-to-physical
  metadata index. No second database, vector owner or compatibility read path.

## Approach and actual changes

`embeddings_embedding_bindings` maps one current logical input identity to one
stable physical paid operation and records its exact current `binding_json`.
Adoption writes this index atomically with its sole vector/receipt rows. Normal
reads, acceptance-key lookup and publication use only the index; they never try
the previous operation hash when a mapping is missing.

`migrate_embedding_identity(target_space, bindings)` is an explicit offline,
single-transaction operation. Its iterable items contain exact `previous` and
`current` complete bindings. Only recipe and space identity may differ; model,
project, source, material, representation, parser, text digest and ranges must
match. The caller establishes computation equivalence before maintenance. Every
physical operation, including historical withdrawn source operations, must be
covered exactly once. Missing, duplicated, corrupt or changed-input entries
abort the transaction. Old hash lookup exists only inside this explicit migration.

Migration replaces the small index and space identity, preserving physical
vector IDs, sqlite-vec rowids, BLOBs, receipts and accepted digests. It does not
rename files or update the external acceptance ledger. The builder can retain
the paid ledger key using `embedding_physical_operation_id(binding)`.

Existing publication metadata and vectors remain untouched, but its old
`space_id` receipt is explicitly invalid. Rebuild publication references with
the current space using the same accepted physical vectors. Handles acquired
before migration fail with `EmbeddingSpaceStaleError` on paid reads, adoption,
publication or native query. Offline orchestration owns file rename, descriptor
updates and restart recovery; no automatic migration occurs in normal reads.

## Verification and limitations

`.venv/bin/python -m pytest -q tests/vector_store/test_embedding_handoff.py
tests/vector_store/test_native_range_publication.py
tests/test_native_embedding_builder.py`: **47 passed in 15.82s**.

Coverage includes unchanged vector BLOBs and sqlite-vec rowids, unchanged receipt
rows, an SQLite authorizer that rejects vector/receipt writes during migration,
reopen under the current identity, rollback for incomplete coverage, duplicate
mapping, changed input and injected metadata-write failure, stale acquired owner
rejection, old publication rejection and successful publication rebuild/query
without adopting another vector body. Scoped `git diff --check` passed.

The new specifications were added with the implementation; no pre-change red run
is claimed. Native incremental-builder validation initially encountered the
concurrent extraction migration's `ClassificationRecords.indexed` initialization
failure; that owner is outside this change. No network or paid model calls were
run. End-to-end offline maintenance and packaged host validation remain the
parent integration's responsibility.

After the extraction owner repaired that initialization, the handoff,
range-publication and native incremental-builder selection passed: **35 passed
in 8.84s**. This includes fail-closed orphan-index coverage: a logical mapping
whose physical paid operation is missing raises an explicit error on reads and
physical-key resolution rather than appearing as an unpaid cache miss. Read,
adopt and publication paths all resolve the stable physical operation key;
migration never changes the accepted digest or external ledger key.

## Upstream merge assessment

Pending: incoming upstream has not been reviewed. Retain only while the native
owner needs logical-to-physical identity indirection; merge must preserve one
vector owner, atomic migration and no normal-read legacy-key lookup. Re-run
handoff, range-publication, builder and offline maintenance integration tests.
