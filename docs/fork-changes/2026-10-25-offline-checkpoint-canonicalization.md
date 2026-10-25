# Explicit checkpoint canonicalization and durable context plans

- Record ID: 2026-10-25-offline-checkpoint-canonicalization
- Date / author: 2026-10-25 / engineering
- Status: source and packaged migration verified; real project build blocked by upstream HTTP 524
- Fork base revision: 2d20ba37d2ca1bd77e197322292081d005661a85
- Upstream reference: not inspected for this local recovery
- Related record: 2026-10-25-parsed-source-carrier-upgrade.md

## Reason and scope

Historical project results use several execution-bound hash-only identities.
The user authorized retaining the latest complete verified variant and physically
removing unselected variants after canonical readback. Migration must not parse
documents, call a model, or merge fields from different executions.

## Native capability assessment

Inspected `SnapshotCheckpoint._import`, `_import_entry`, `_ProjectExtractionCache`,
`_extract_window`, `_source_windows`, native cache encoding and grounding methods,
their callers and `tests/test_project_checkpoint.py`. Also inspected the removed
chunk carrier in `c1fe1d20^` and the intermediate packaged cache identity formula.
The native checkpoint remains the sole runtime result owner. Its deliberate
rejection of opaque historical identities remains intact. Explicit offline
identity recovery was absent; it is isolated in `project_checkpoint_upgrade.py`.
Historical projection formulas are migration-only, never runtime fallbacks.

## Approach and actual changes

- Recover source/window/context identity only after reproducing the original
  filename hash and checking its original fence and payload digest.
- Delegate windowing, encoding, grounding and cache identity to native owners.
- Preserve entity-result dependencies on relation candidates for selection.
- Select whole payloads by original receipt time, with deterministic digest and
  origin tie breaks; copying an old file does not make it the latest result.
- Persist window context batches in the native checkpoint. `_extract_window`
  uses that data plan on restart instead of invalidating paid work when code
  changes context projection. This extends the existing persisted window plan.
- The consumer performs explicit canonical staging, readback, installation and
  exact-file pruning. The native module never deletes user data itself.
- No model calls, document parsing, new dependencies or alternate extraction
  algorithm are introduced by migration.

## Verification and limitations

The migration identity tests first failed with the missing migration module.
The durable-context regression failed before the owner fix with `replanned paid
context`. The focused checkpoint/parsed-source/worker suite passed 46 tests;
the projected-context suite passed 10 tests. The consumer packaged the immutable
native artifact `sha256:922a9586059e312e3f4e0e80a148e1b72de851098e113ffc535c8b981c39e9cb`.
The real ESG profile migration installed and read back 1,318 extraction entries,
45 source plans and 575 context plans, then physically removed superseded
carriers and full-payload migration copies. Two older opaque chunk identities
were not admitted: exact unique grounding and fully selected newer whole-window
results proved supersession before deletion. The native key admission remains
strict. The packaged ESG run restored cached windows; its last nonterminal
sample showed 407 / 2,994 windows processed, including 278 restored windows.
After two automatic attempts it failed at `2026-10-24T21:21:49.777Z` with
`HTTP 524 / UPSTREAM_UNAVAILABLE` from the configured upstream model provider.
The project build did not pass final acceptance. The skip counter (67 in the
last sample) counts batch rejection records, not unique source windows.
Incomplete model responses are not promoted into complete extraction results.
Post-failure readback verified all original 1,318 selected payloads unchanged
and all 1,332 current extraction payload digests, plus 645 context plans.
No duplicate checkpoint archive remained; no third attempt or model switch
was initiated by the consumer.

## Upstream merge assessment

Disposition: pending. No incoming upstream revision reviewed. Reassess checkpoint
identity and persisted planning ownership on merge; retain one runtime owner and
rerun migration/no-network, context persistence and project restart regressions.
