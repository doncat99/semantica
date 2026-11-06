# Canonical publication predicate normalization and exact qualifier identity

- Record ID: 2026-11-05-publication-predicate-normalization
- Date / author: 2026-11-05 / Codex publication closure agent
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty ongoing G4 integration)
- Upstream reference: not inspected; local native-owner repair
- Related records: 2026-11-05-native-qualified-fact-index

## Reason and scope

The native builder canonicalizes predicates with whitespace folding and casefold, while PublicationRecords.stage_facts compared literal RDF predicate terms. Two valid observations with ` owns ` and `OWNS` could reconcile to one canonical fact but fail staging. Qualifier identity must remain exact.

## Native capability assessment

- Existing owners inspected: semantic_artifact_builder._build_source, semantic_extract.methods._grounded_qualifiers, semantic_extract.schemas.validate_fact_qualifiers, ExtractionRecords.relation, PublicationRecords.stage_facts and _fact_scene_link.
- Actual callers: OxigraphStore.stage_publication_facts, builder artifact writing, publication native scene readers; tests/triplet_store/test_publication_records.py and test_extraction_records.py.
- Decision: repair the existing native publication owner and share its existing predicate semantics through semantic_extract.schemas.normalize_fact_predicate. No alternate resolution or fact reconciliation path.

## Approach and actual changes

- Added shared normalize_fact_predicate implementing existing split/casefold canonical semantics. Publication staging compares normalized predicates and exact RDF qualifiers; canonical scene predicate uses normalized value. Accepted extraction records remain immutable.
- Corrected expanded extraction fixture to stage its required canonical fact through the production API. Native record_binding checks use the native representative Relation, because canonical fact ID belongs to publication membership.
- Regression covers legitimate merged predicate variants and rejects all five changed qualifier fields. Builder helper adoption is coordinated with the agents owning builder edits.
- No network/model calls, dependencies, paid extraction or migration.
- Lifecycle audit: withdrawal only fences a ready publication; accepted extraction operations and their derived projection graphs persist for reuse. No extraction-operation deletion API exists in this owner. Removing a native carrier removes all graphs; no independent destructive GC policy was introduced. App-side offline cleanup must account for any selective operation deletion it implements.

## Verification and limitations

- Red: expanded extraction fixture failed Canonical fact coverage is incomplete before canonical staging correction.
- Red: legitimate predicate merge failed Canonical fact member qualifier or predicate differs; changed qualifier cases rejected as intended.
- Green: pytest tests/triplet_store/test_publication_records.py tests/triplet_store/test_extraction_records.py tests/triplet_store/test_identity_projection.py tests/test_native_build_lifecycle.py -q -k 'not reopened_production_point_read': 44 passed, 1 deselected (15.83s).
- Initial full publication/extraction run: native process point-read capacity test exceeded its 16MiB gate (20,267,008 bytes); gate retained, not weakened. Follow-up result appended below.
- This validates publication semantics and focused restart/withdraw behavior, not complete ESG capacity, G4 completion or release readiness.

## Upstream merge assessment

- Disposition: retain native semantic consistency fix; incoming upstream revision not reviewed.
- Overlaps: canonical predicate policy and publication comparison/output. Recheck all producer/consumer predicate identities and strict qualifier regressions after merge.

## Dated follow-ups

2026-11-05: Shared helper integration requested in builder's existing normalization location; no direct edits to builder by this agent to preserve disjoint ownership.

2026-11-05 follow-up: Native maintenance/resource selection returned 5 passed and 2 failed. Maintenance expects 4 source operations but the concurrently modified builder produced 2; integration owner notified without changing expected behavior. Standalone native point-read resource gate again failed at 17,137,664 query high-water growth bytes against 16MiB; retained as unresolved evidence. These are not passes.

2026-11-05: Added direct withdrawal/restart regression proving accepted extraction receipt and identity projection remain reusable while publication reads are fenced both before and after restart. Identity projection suite: 5 passed in 2.15s.
