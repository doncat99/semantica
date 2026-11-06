# Native identity index durability checkpoints

IdentityCandidateIndex.build previously called PublicationRecords.mutate for each evidence chunk and native identity row. Each call flushed the native RocksDB owner, making a 280-row build perform 562 flushes. Reference-only storage still suffered synchronous per-record durability cost.

Index construction now writes directly through the canonical derived-graph owner and checkpoints after at most 128 completed rows or 262144 staged triple bytes. Native writes remain visible immediately to connectivity lookups. The lock, pending generation fence, cancellation checks, complete input count, final flush and sealed index contract remain authoritative. A canceled partial index cannot be queried after restart; explicit retry replaces its unsealed rows.

Regression evidence:
- tests/triplet_store/test_identity_candidate_index.py::test_native_index_checkpoints_bounded_rows_and_reopens_complete failed before the fix with 562 flushes versus the limit of 20.
- The same file now has 10 passing tests, including a cancellation after the first durable checkpoint, reopen/retry and generation replacement between rows.
- Focused run: 10 passed in 4.58s. This proves the identity index boundary, not complete G4 or product acceptance.

The byte threshold describes serialized mutation input and the row threshold describes completed identities between durability checkpoints. They are not a claim about total native index size or RSS. Existing semantic component hydration limits remain separately enforced.
