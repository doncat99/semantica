# Native identity semantic context

## Reason and inspected owner

Inspected main revision `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus existing working changes. `EntityDisambiguator.prepare` in `semantica/normalize/entity_normalizer.py` already owns grounded definitions, owners, instances and support semantics. Callable cursors avoid input DTO retention but left all of its semantic dictionaries in project memory. `IdentityCandidateIndex` already owns persisted candidate connectivity and delegates merge authority to `EntityResolver`.

## Implementation and consumers

Extend the existing disambiguator with a native context argument and retain its semantic passes unchanged. `triplet_store/identity_context.py` supplies keyed semantic indexes in the current publication graph; no alternate identity rules or decision engine. `IdentityCandidateIndex.build` supplies this context. Candidate component resolution continues to use `context_prepared=True` against the same resolver. No builder or publication-record implementation changes in this change.

Map keys are hashed, except keys required for streamed definition/variant/member traversal. Context prose is not stored as an index key. Distinct grounded referents use individual indexed membership keys rather than one project-size set. Native reads enforce 128 values and 256 KiB per semantic group; oversized groups fail explicitly. Context reset and sealing prevent rebinding an incomplete preparation. Generation fences reject stale contexts. The graph is deleted through the existing publication-generation lifecycle.

## Regression evidence

New `tests/triplet_store/test_native_identity_context.py` failed before implementation with `ModuleNotFoundError` for the missing native context. Its assertions compare candidate keys and every pair decision to the existing in-memory oracle, exercise over 128 distinct definitions, rebind persisted indexes, reject oversized semantic groups and stale generations.

- Focused identity tests: 173 passed in 18.51 seconds (before adding explicit context sealing).
- Existing semantic oracle suites forced through native preparation using a temporary pytest plugin: 164 passed in 90.38 seconds; no model/network calls. This run loaded the implementation before the final sealing change.
- After explicit sealing and correcting the pre-existing local variable name collision with the context parameter: native-context and candidate-index tests, 6 passed in 12.23 seconds.

## Limits and upstream merge assessment

This removes project-size Python semantic dictionaries in native candidate builds. It does not prove complete G4 capacity, total RSS, resolver oversize-component capacity, topology success, packaging or real ESG acceptance. More than 128 values under one semantic key fails rather than truncating semantics. Memory-mode preparation remains the same owner for existing direct in-memory library callers; production persisted builds select the native context explicitly. Native stores and per-key reads increase I/O; total build throughput remains to be measured in the integrated capacity run.

Upstream assessment: pending; no incoming upstream revision inspected. Preserve the existing disambiguator semantics and replace this persistence mechanism if upstream supplies the equivalent native indexed context.

### Final verification

After sealing and the context parameter correction, the same combined focused command passed all 173 tests in 21.84 seconds. Native context tests and native component tests are included in that run.
