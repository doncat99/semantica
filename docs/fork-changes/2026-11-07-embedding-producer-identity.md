# Embedding identity belongs to its vector producer

- Record ID: 2026-11-07-embedding-producer-identity
- Date: 2026-11-07
- Status: implemented; focused verification passed
- Fork base revision: 765c0ef2d1e868e074ca31068e9db90a0672a9c2
- Upstream reference: not inspected

## Reason and native capability assessment

The existing `_embedding_owner_binding` in `semantic_publication_builder.py`
uses extraction/publication `source['recipe']` for both vector space and operation
identity. Unrelated query, classification and publication changes therefore cause
physical vector copies despite identical embedding input, model and paid receipt.
The native SQLiteVecStore remains the sole vector owner. Its existing
`pack_embedding_vectors` owns float32 validation/encoding; `_embedding_payload`
and `_embedding_values` own request parameters and response-to-vector conversion.
Transport and receipt bookkeeping in `_request_embedding` are excluded.
Existing builder process-boundary specifications exercise their actual callers.

## Approach and data boundary

Repair the existing builder binding to use `embedding_recipe(relay)`, whose
positive dependencies are the embedding model/binding, actual request parameters
(currently no optional parameters), request/conversion function source, native
vector encoder source and its NumPy dependency version. Checkout paths, generation
model, classification, query and project processing digests are excluded.
The operation still binds actual text digest, source provenance and exact ranges.
No vector owner, model algorithm, fallback or compatibility reader is introduced.

Existing recipe-bound spaces require the separately coordinated offline identity
migration; runtime will not dispatch to old recipes. No models, account/native
databases, packaging, commits or publication are performed by this work.

## Verification and limitations

The old binding was reproduced red: publication recipe changes changed both the
embedding operation and its physical space. The corrected producer identity and
real crash/restart embedding handoff pass 14 focused specifications. Combined
embedding, native handoff and in-place migration verification passed 42 tests in
16.26 seconds. After extending pre-index vector and classification/reduction
migration coverage, all six offline migration specifications passed in 3.44 seconds.

The offline migration entrypoint now accepts one request, an explicit old
extraction/vector recipe and an optional exact old classification recipe. It
reindexes native facts and vectors in place, preserves physical operation IDs,
vector BLOBs and paid ledger keys, checks complete vector coverage, and renames
the closed vector owner after a successful checkpoint. Its dry run opens vector
storage read-only. Historical AST certificates and copying adoption paths were
physically deleted. Interruption/reentry, pre-index/current-index vector paths,
classification batch/reduction references, and unchanged accepted ledgers are
covered. Target publication rebuild remains required; unknown withdrawn physical
operations fail closed. Live project migration and product acceptance remain
the integrating owner's responsibility.

Extraction/classification maintenance flushes in batches of 128. Its full physical
receipt verification admits pre-index data only within the explicit offline tool;
normal runtime reads still require the current identity index. Removing both
extraction and classification mapping graphs reproduced two failures before this
correction. The migrated builder also proves paid vectors reuse their original
physical acceptance key with model calls forbidden.

## Upstream merge assessment

Pending; preserve the sole vector owner and producer-scoped identity if upstream
changes the builder or encoder. Re-run identity and process-restart specifications.
