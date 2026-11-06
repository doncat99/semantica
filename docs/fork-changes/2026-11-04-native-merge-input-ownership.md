# Native merge input ownership

- Record ID: 2026-11-04-native-merge-input-ownership
- Date: 2026-11-04
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main)
- Upstream reference: not inspected; incoming merge assessment pending.
- Related record: 2026-11-04-native-merge-selection-provenance.md

## Reason and scope

Retrospective same-change record: native metadata merging mutated source lists
and dictionaries; provenance writes mutated existing source provenance. Builder
protected immutable mentions by deep-copying every projected entity, including
nested evidence. Repair the native writes and remove that complete copy.

## Native capability assessment

Inspected MergeStrategyManager.merge_entities/_merge_metadata/_merge_properties,
EntityMerger.merge_entity_group/_add_provenance and EntityResolver.resolve_entities.
Callers include merge_duplicates, incremental_merge and builder
_resolve_native_entities. Built-in property merge already copies lists before
append; relationships are read into a fresh collection. Native owners are reused;
no algorithm, adapter, export, fixture, dependency or storage owner added.

## Approach and actual changes

Metadata list concatenation and dictionary merging now allocate the container
being written; provenance copies its dictionary before recording the operation.
Builder projects fields by reference and deletes its deepcopy import/call.
Output merge order, duplicates, dictionary overwrite and provenance fields stay
the same. No stored format change or migration; no models/network/profile writes.
Custom callback implementations remain responsible for their own input writes;
the production contextual builder config does not register custom merge callbacks.

## Verification and limitations

Two native regression tests first failed on source mutation. Builder residency
probe first failed because its nested metadata had been copied. After repair:

`.venv/bin/python -m pytest -q tests/deduplication tests/kg/test_entity_resolver_exact.py tests/kg/test_identity_review_regressions.py tests/test_project_identity.py tests/test_native_identity_candidate_budget.py tests/test_native_identity_partition_residency.py tests/test_native_global_body_budget.py tests/test_native_support_copy_residency.py`

**266 passed in 29.28s**. Checks cover native output fields, source model dumps,
input container identity and existing candidate/support lifetime regressions.
Scoped git diff --check passed. This removes one full nested copy, not the rows
projection or all global working sets. Fixed artifact, host primary Case and
change-verification were not rerun: source G4 work remains incomplete.

## Upstream merge assessment

Disposition pending; no incoming upstream revision reviewed. Preserve input
immutability and native output semantics when merging metadata/provenance owner
changes. Remove this patch only if the incoming native owner supplies both
guarantees and passes these regressions. Rerun identity/build consumer checks.
