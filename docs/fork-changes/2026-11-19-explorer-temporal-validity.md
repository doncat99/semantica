# Explorer temporal validity behavior

## Reason and scope

The Explorer timeline previously supplied a synthetic 1970-to-current range
when a graph had no effective dates. It continued to request snapshots, making
the play control appear active without changing graph content. This change is
limited to the Semantica fork's native Explorer graph/session/API path.

## Implementation

- Bounds now use explicit `valid_from` and `valid_until` values on both nodes
  and relationships. No report year, upload time, or current date is substituted.
- Snapshot responses include active relationship IDs as well as active node
  IDs. Explorer applies both sets when the scrubber moves or plays.
- The timeline distinguishes loading, ready, no temporal data, and request
  failure. Play is disabled without a non-zero real date range; no-date graphs
  keep their normal graph controls and do not request snapshots.
- Changing or deactivating the graph clears the temporal position and snapshot
  state through the existing graph summary lifecycle.

## ESG source-to-Explorer finding

The current canonical ESG fact artifacts (`KnowledgeAssertion` and
`KnowledgeRelation`) store qualified facts and evidence IDs, but do not have
effective-validity fields. Their qualifier contract allows a textual `time`
qualifier; it is not a `valid_from`/`valid_until` interval. The native
publication builder carries qualifiers into the published fact/relation
artifacts, while Explorer's temporal API reads only explicit validity fields
from graph nodes and edges.

There are two earlier contract gaps in the ESG producer path. The strict
relation extraction wire schema (`GroundedRelationWire`) does not admit
`valid_from` or `valid_until`, and the canonical ESG assertion/relation builder
projects only grounded qualifiers and evidence into `KnowledgeAssertion` and
`KnowledgeRelation`. A separate, non-strict relation extractor can optionally
emit validity fields, but that output is not the canonical ESG publication
path and cannot establish dates for these facts.

There is also a downstream transport gap: `NativeScope.select()` requests only
`id/name/entityType` for nodes and `id/source/target/predicate/status` for links.
It then creates `ContextGraph` nodes and edges from those projections. Thus
explicit validity fields would also need to be added to the single canonical
native scene projection and preserved by that loader before Explorer could
render them. The current evidence therefore points to missing producer
contracts plus a missing scene projection, not a date conversion bug in the
Explorer temporal API.

Report year, upload time and a textual `time` qualifier are not effective
validity dates. ESG facts without explicit, source-grounded effective dates
must remain undated. Extending the strict extraction contract, canonical fact
contract and native scene projection requires a coordinated schema/producer
change with source-evidence tests; this UI/API correction does not fabricate
dates or claim that ESG temporal extraction is complete.

## Verification

- Explorer TypeScript build: passed.
- Temporal lifecycle and scrubber bounds tests: 15 passed.
- Explorer API tests, including relationship-only bounds and snapshots at two
  dates: 139 passed.
- Build emitted the existing Vite warning that the exploration-effects plugin
  is both dynamically and statically imported.

## Delivery boundary

No commit, push, pin update, packaged build, or OntoScience data mutation was
performed. Existing untracked fork files and runtime data were preserved.
