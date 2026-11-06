# Native builder fact membership

## Owner and replaced gap

Inspected the existing dirty canonical fork at main 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe. ExtractionRecords owns native Relation identity; ConflictDetector and EntityMerger own canonical qualified fact identity and complete support reduction. PublicationRecords owns reference membership. The builder previously discarded native Relation references during window restoration and never staged canonical facts; the native activation coverage check therefore rejected real ready builds.

## Change

Extraction and accepted-window restore now carry exact native Relation addresses through context namespacing, semantic deduplication and source projection. Native addresses are excluded from semantic dedup keys; semantically equal observations retain every raw native member. Source projection maps each original observation identity plus its exact evidence IDs to native refs. This preserves the canonical reducer's deterministic representative observation and avoids confusing same-semantic-ID observations at different locations.

After canonical entities are staged, the builder translates the existing reducer's sorted support observations into complete canonical fact membership and writes at most 128 member references per call. The existing publication owner checks canonical endpoint membership, qualified identity, single ownership and exact final coverage. No fact DTO values, alternate identity algorithm, fallback path or new store were added.

## Verification

Before source changes, tests/test_native_build_lifecycle.py::test_rebuild_invalidates_ready_generation_before_reading_source failed with Canonical fact coverage is incomplete (/tmp/g4-fact-builder-red.log). The same real no-network model build now activates successfully. A new lifecycle regression reopens the store, reads canonical scene links and follows canonical fact support membership to native Relation records. Existing split-window restoration regression now verifies that two independent native relation references survive namespacing and restart and point to actual native Relation records.

Focused pipeline, lifecycle, split-window handoff, fact identity and accepted-extraction suites: 27 passed in 20.07s (/tmp/g4-fact-builder-green.log). No live model, paid run, artifact pin, packaging or release.

## Remaining integration boundary

This fixes missing canonical fact coverage; it does not integrate QualifiedFactIndex or eliminate project-wide DTO collections. A correct native indexed callback must reconstruct builder's current grounded qualifiers, normalized predicates, occurrence IDs, exact supports and canonical endpoints from native records and reader references. Retaining all DTOs in a callback lookup map would disguise the same residency defect, so no such adapter was added. Raw native qualifier comparison versus builder normalization also requires one explicit owner contract. G4 remains unclosed until native hydration, whole-process resource bounds and all consumers are verified. Upstream merge assessment remains pending.
