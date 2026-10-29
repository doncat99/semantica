# Native snapshot search ownership

- Date: 2026-10-29
- Inspected revision: 1f5d4734a; local upstream reference 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
- Status: implemented; focused retrieval regressions verified
- Native owners: context.context_retriever.ContextRetriever, vector_store.VectorRetriever

ContextRetriever already owns keyword scoring and explicit snapshot context;
VectorRetriever owns cosine ranking. Neither public snapshot context nor generic
hybrid retrieve implements explicit keyword/vector search over grounded artifact
records. Generic retrieve also enables expansion/fallback and can generate query
embeddings, which violates this caller's explicit-mode contract. Extend the
existing native retriever with public snapshot preparation/search. Projection of
typed artifact records is a necessary contract mapping, not a new scorer.

Remove candidate creation, source admission and evidence ranking from
semantic_query.py. Keep immutable file/digest/manifest admission and wire DTOs
there. Preserve native scores/order, all-provenance source scoping, warm reuse,
negative/retracted fact display and fail-closed embedding-space checks. No model
calls, hybrid rescoring, duplicate graph files or pagination changes.

Consumers: semantic_query_worker, tests/test_semantic_query_worker.py. Acceptance
Case capability-library-prepare / journey-library, delta keep; no gate or baseline
change. New delegation spec must fail before implementation. Full packaged/ESG
acceptance remains outside focused test evidence. Upstream merge: adapt if native
snapshot search changes; retain one scoring owner, remove superseded adapters.

Verification: delegation spec failed before implementation. Query worker,
native snapshot context/search, existing hybrid and grounded context retrieval:
99 passed; additional direct scope/vector-order spec passed (2 new specs total).
Native keyword and VectorRetriever scores/order stay unchanged, including zero
vector similarity; no reranking or implicit embedding is introduced. Preparation
remains bounded to two immutable artifacts and scope is reapplied for every query.
The new context/snapshot_search.py only maps artifact records and vector evidence
overlap; it computes no similarity score. ContextRetriever owns selection and
ranking, semantic_query.py contains file admission and DTO translation only.
This is ownership consolidation, not a claim of deleting all moved mapping lines.
No user runtime data or paid model calls. Artifact publication and App not updated.
