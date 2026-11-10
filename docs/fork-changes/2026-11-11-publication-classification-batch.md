# Bounded publication classification batch reads

- Record ID: 2026-11-11-publication-classification-batch
- Date / author: 2026-11-11 / OntoScience development
- Status: implemented-unverified (focused tests passed; packaged acceptance pending)
- Fork base revision: bf72221141e8ecac431778e118a8223b70d4d494
- Upstream reference: not inspected; current local main owner inspected
- Related issue / PR / commits / records: OntoScience Explore restoration; publication classification consumer

## Reason and scope

Explore must read the classification already bound to the current publication without restoring snapshots, reclassifying documents, or one process call per node. Missing completion must remain distinguishable from corrupt results.

## Native capability assessment

- Existing owner: PublicationRecords.classification_dimension delegates to ClassificationRecords; runtime read_native_classification_dimension exposes the bound result. semantic_query_worker and semantic_query_schema own query transport.
- Actual worker classification callers, publication bindings, classification tests and bounded indexed reads inspected. The source relation builder helper has no production callers and is not evidence of a published source-relationship completion.
- Decision: extend the existing query owner with batching; retain one classification result owner.
- No second store, classifier, inference algorithm, or compatibility reader.

## Approach and actual changes

- semantic_query_schema.py validates 1..32 unique selections scoped to one project and generation.
- semantic_query_worker.py delegates each selection to the current native reader with cancellation, publication fences and an aggregate 262144-byte response budget.
- publication_records.py exports the stored taxonomyDigest and distinguishes ClassificationMissingError from invalid completion. Classification pages retain indexed bounded reads.
- PublicationRecords.source_scene accepts 1..128 exact source IDs via indexed VALUES selection before ordering and pagination; search context reads remain publication-bound and byte-bounded. Duplicate IDs are rejected.
- Consumers: OntoScience canonical-records, SemanticaRuntime, source graph projection and worker fixtures. No stored-data migration or new production write path.
- Model/network/dependency/cost impact: none for reads; no re-extraction or paid classification.
- Planned but not implemented: publishing upstream artifacts is outside this local make dev delivery. No fabricated source relations.

## Verification and limitations

- Exact source scene and publication tests passed (67); focused semantic query worker batch tests passed (2); publication/classification focused tests previously passed (35). Final run and relocated packaged verification are recorded in OntoScience .tmp/explore-final.
- Full upstream suite and merge not run. Real ESG publication coverage and App interaction acceptance remain separate evidence.
- Batch failures retain native typed failure rather than returning empty success.

## Upstream merge assessment

- Disposition: pending; retain only while native transport lacks equivalent bounded batching.
- Incoming upstream revision: not reviewed.
- Likely overlap: semantic query schema/worker and PublicationRecords classification reader.
- After merge: rerun worker identity/budget/cancellation tests, classification paging tests, relocated native acceptance and OntoScience source graph contract tests.

## Dated follow-ups

2026-11-11: Local source snapshot will be consumed only through make dev's complete native artifact; canonical checkout is never a runtime import.
