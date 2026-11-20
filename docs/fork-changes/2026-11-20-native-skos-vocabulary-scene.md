# Native SKOS vocabulary scene

- Date: 2026-11-20
- Status: source regression passed; immutable artifact qualification pending
- Owner: `PublicationRecords.vocabulary_scene`

The publication owner now exposes bounded `schemes` and scheme-scoped
`concepts` scene pages over the active immutable publication graph. The query
uses SKOS `ConceptScheme`/`Concept`, `inScheme`/`topConceptOf`, labels,
descriptions, notation, alternate labels and `broader`. Ordered cursor paging
uses a storage-side `LIMIT + 1`; page size is at most 128 rows and serialized
response size at most 256 KiB. Generation fencing and worker cancellation checks
surround iteration.

Regression: `tests/triplet_store/test_publication_records.py::test_native_vocabulary_scene_is_bounded_skos_projection` passes. It covers
scheme and concept identity, scheme isolation, alternate label and parent
projection, continuation, response byte rejection and cancellation. Initial
runtime testing caught and corrected the unsupported `QuerySolution.labels`
access and literal-vs-IRI scheme filter.

This proves behavior against the dirty source checkout only. It does not measure
physical disk bytes or scan depth, establish cancellation inside Oxigraph, or
qualify an immutable artifact. No upstream merge or artifact promotion is
claimed.
