# Project identity uses exact native resolution

- Record ID: 2026-10-27-project-identity-exact
- Date / author: 2026-10-27 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 22da616fd4a74b3f850d1c9c198c75efb2833004
- Upstream reference: not inspected in this change
- Related issue / PR / commits / records: pending

## Reason and scope

The ESG project build used Semantica's default fuzzy resolver for project-wide
identity admission. The existing production artifact reduced 36,082 mentions to
431 entities and showed severe transitive over-merging: common values such as
`25` and `CO2` were merged across dozens of sources and unrelated aliases were
attached to canonical entities. The same native exact resolver produced 17,728
entities in an offline replay and completed in about 11.9 seconds. This change
keeps identity remapping and fact reconciliation, but removes fuzzy identity
admission from the project default.

## Native capability assessment

- Existing owner and inspected files/symbols: `semantica/kg/entity_resolver.py::EntityResolver`, `semantica/semantic_artifact_builder.py::_resolve_native_entities` and `build_semantic_artifacts`.
- Actual callers / config / exports / tests / recent removals checked: project identity resolver construction at `build_semantic_artifacts`; `_resolve_native_entities`; `tests/test_project_identity.py`; native deduplication tests.
- Decision: repair native owner usage by selecting its existing exact strategy.
- Evidence no second implementation is introduced: only the existing `EntityResolver(strategy="exact")` is configured; no new matcher, registry, or merge path is added.

## Approach and actual changes

- Changed files and why: `semantica/semantic_artifact_builder.py` selects exact strategy for project identity; `semantica/kg/entity_resolver.py` implements exact canonical/declared-alias indexing with native compatibility checks and connected components; `tests/test_project_identity.py` covers alias preservation, conflict splitting, and near-name rejection; this record documents the fork change.
- Contract / consumer / stored-data impact and migration or deletion targets: no schema change. Existing identity registry, remap, fact reconciliation, provenance, and downstream organization remain in use. Existing fuzzy-produced snapshots are not silently rewritten; a fresh build is required to materialize corrected identity output.
- Model / network / dependency / cost impact: no model or network calls. Exact matching avoids the quadratic fuzzy similarity scan for project identity.
- Planned but not implemented: no removal of entity resolution; exact same-name normalization remains intentional.

## Verification and limitations

- Commands and results (include scope and evidence paths): offline replay of `semantic-graph.json` from build `66023ae0-32c9-4b0d-b89c-03647a7d0f62`; exact resolver produced 17,728 entities from 36,082 mentions in 11.876 seconds, with zero cross-type groups. Focused native identity suite: `/Users/huangdon/miniconda3/envs/ontosynth/bin/pytest -q tests/test_project_identity.py tests/deduplication/test_native_resolution_veto.py tests/deduplication/test_identity_constraints.py` -> 60 passed, 1 warning in 12.49s. Broader deduplication plus identity suite: `/Users/huangdon/miniconda3/envs/ontosynth/bin/pytest -q tests/deduplication tests/test_project_identity.py` -> 154 passed, 1 warning in 15.88s.
- Checks not run and why: full production build and App packaging were not run; user did not authorize them in this turn.
- Known risks / unresolved questions: exact matching does not resolve spelling/abbreviation aliases unless declared aliases are already present. A new build must compare downstream assertion/relation and organization quality before release. The complete production build and App packaging remain unverified.

## Upstream merge assessment

- Disposition: pending; this is a consumer policy selection using an existing native strategy.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream changes to `EntityResolver` strategy defaults or project builder construction may overlap.
- Conditions to retain, adapt or remove this change: retain only while project identity admission has no trusted cross-document alias contract; if upstream supplies a validated scoped resolver policy, adapt the call site and keep the regression.
- Required consumer/regression checks after merge: run project identity tests, semantic artifact tests, and an offline real-artifact comparison.

## Dated follow-ups

2026-10-27: Offline comparison found the current fuzzy artifact materially over-merged; exact strategy is the selected corrective baseline. The first implementation exposed missing alias/compatibility coverage; the native exact resolver was repaired and the 60-test focused suite passed. No production artifact was regenerated.
