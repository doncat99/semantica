# Native builder source plan and identity candidate components

- Reason: pending traversal was inaccessible until artifact writing, and source entity DTOs survived into project computation. Identity must consume complete candidate components using globally prepared native context.
- Native owners inspected: ExtractionRecords, PublicationRecords build fence/canonical references, IdentityCandidateIndex, NativeIdentityContext, EntityResolver, semantic artifact builder at base `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
- Complete source operation plan stages in `source_projection` before identity/fact/organization reads. Late duplicate source-plan staging was deleted.
- Source processing persists only native identity scalars, evidence addresses and context ranges through ExtractionRecords, then removes source `entities` and `native_entity_refs`. Original accepted extraction digest remains immutable; context text is hydrated from bounded reader ranges.
- Entity resolution pages native Entity records, reopens typed projections, prepares NativeIdentityContext from repeatable cursors, and resolves one complete indexed candidate component at a time with the existing EntityResolver. Completed component canonical membership and field/property selectors are staged immediately. Global source entity aggregation and global native selection staging were removed.
- Deterministic recipe uses the same native index with exact mention keys only: overlapping accepted windows retain every native member reference without introducing name-based identity merging. Model candidates include exact mention keys alongside the native detector's keys.
- Oracle: multi-source model-recipe fixture compares every canonical KnowledgeEntity JSON value, representative native reference, complete member references, field selectors and native property selectors to the existing whole-project resolver. The fixture repeats against the same store to cover restart/rebuild.
- Canonical writer has one current six-key schema: id, representative, members, member_count, selectors, selector_count. All callers/fixtures use this schema. Builder stages the representative in the first membership page, all member pages before selector pages, then activation requires exact totals.
- Red specifications: incomplete source plan failed at native fence; source DTO weakrefs must be released before native identity reads; exact-mention native component API first failed without support.

## Verification

- `tests/test_project_identity.py tests/test_native_extraction_handoff.py tests/triplet_store/test_identity_projection.py tests/triplet_store/test_identity_candidate_index.py tests/kg/test_contextual_identity.py tests/kg/test_identity_cursor_preparation.py`: **84 passed in 18.89s**.
- Canonical append contract affected run: **83 passed in 29.68s**. After ordering all member pages before selector pages and accumulating paged oracle captures, pipeline/report/publication regression run: **49 passed in 27.13s**. Concurrent stage ordering is aligned in that run.
- Updated the existing nested-evidence allocation observer to forward the current resolver keyword contract. No behavior expectation was weakened.

## Remaining resource and delivery boundaries

- Existing resolver still retains one complete connected candidate component. This implementation introduces no arbitrary candidate cap or alternate algorithm; giant-component capacity remains to be proven/implemented in the canonical resolver.
- Native canonical staging now uses required total member/selector counts with bounded append pages and an exact activation fence. The greater-than-128 regression covers incomplete members, incomplete selectors, changed plans, duplicate pages, and restart. Ready read consumers still need scoped member/selector traversal; paged staging alone does not prove product read capacity.
- Canonical output entities and remap still survive for existing fact/topology consumers. Source DTO residency is removed; complete project resource boundedness is not established.
- No paid model call, formal-data cleanup, release pin change, packaged artifact publication or real ESG acceptance was performed by this change. G4 completion is not claimed.
- Upstream merge assessment remains pending; upstream was not inspected.

## Pending canonical reference traversal

- `IdentityCandidateIndex` now indexes existing identity evidence addresses in bounded batches; the current resolver still owns all merge semantics.
- `canonical_references` supplies pending canonical id/representative pages using native keyset queries. An optional evidence-address filter selects canonical members through the native evidence index. `canonical_reference` supplies one exact representative address. Both enforce the pending build fence; pages bind cursors to project, generation and evidence scope, row and byte budgets.
- This enables explicit maintenance traversal and targeted exact component hydration without persisting canonical DTOs. The builder/organization consumer cutover remains a separate integration boundary.
- Verification: reference pagination past 128, exact point lookup, evidence filters, continuation after restart, foreign-scope cursor, byte limit and stale-generation rejection: candidate-index suite **5 passed in 6.86s**.
- `_native_canonical_entities` now supplies exact full DTOs from native references through the existing resolver, one complete component at a time. Requested canonical IDs use point lookups; evidence scopes use the native evidence index. A native-reference set prevents repeated component hydration. No persisted DTO/cache or alternate merger is introduced. Existing full-group resolver residency remains explicit.
- Helper oracle regressions cover deterministic/model output, aliases/evidence/metadata/context/attributes, complete traversal without duplicate hydration and targeted requests that do not hydrate unrelated components. Helper + native pipeline + index: **12 passed in 10.07s**.

## Complete identity-unit hydration and query capacity

Identity components now have a native materialized root (`identityComponent`),
with native candidate-key roots (`identityKeyComponent`). Index construction
joins candidate-key components and relabels existing native memberships when a
later alias bridges earlier groups. Roots and component pages use direct native
predicates. The superseded transitive property-path reads were removed: dense
shared keys made the default4096-member read exceed90 seconds without finishing.
Rebuilding clears both derived root predicates before sealing the new index.

`hydrate_component` bounds one complete resolver input at4096 native members and
16MiB compact UTF8 serialized DTO bytes. Callers may lower these limits, but
cannot raise them. A native count rejects oversized units before hydration;
byte overflow fails before retaining the violating DTO or invoking the resolver.
No partial component is returned. These are hydrated-input bounds, not a claim
about resolver transient RSS or target ESG build success.

Validation:24 focused identity/index/context/canonical-helper tests passed in
18.21s, including cross-page131-member exact DTO equivalence, restart, late
bridges, rebuild, exact16MiB acceptance and one-byte rejection. A synthetic
native-reference index capacity probe accepted4096 members in1.815s (process
peakRSS196116480 bytes) and rejected4097 before hydration in0.019s. Probe output:
`/tmp/g4-identity-capacity-probe.jsonl`. This isolates native-index reads and does
not qualify the complete ESG pipeline. The realistic8-source body-budget build
was still running after70s; native sampling showed quad iteration dominating,
so end-to-end capacity remains a separate integration gate.
