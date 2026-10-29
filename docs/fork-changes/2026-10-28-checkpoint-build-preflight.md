# Checkpoint migration before project builds

- Inspected revision: 53a860172 (local Explorer edits preserved).
- Status: regression specification added; implementation and verification pending.

## Native capability assessment

`project_checkpoint_upgrade.canonicalize_checkpoint` and `upgrade_checkpoint`
already own offline conversion. `SnapshotCheckpoint._import` deliberately accepts
only canonical data. The JSONL worker dispatches builds without first invoking
the migration owner, so relocated legacy manifests block even empty projects.
The consumer's `checkpoint-storage.ts` only routes directories by project.

## Approach

Add an explicit offline preflight to the native worker's build entry, reusing
the existing converter and transactional installer. Retain strict runtime reads,
validate project identity, preserve paid entries, and expose checkpoint failures
as typed recovery errors. Cover empty and populated legacy carriers, nested
imports, restart, corruption, foreign projects, and no network/model calls.

## Verification and limitations

Pending. Upstream merge assessment pending; no upstream revision inspected.

## 2026-10-28 implementation and verification update

The public `semantic_artifact_builder.build_semantic_artifacts` entry now invokes
the existing offline converter before activating its checkpoint. Both direct
library calls and worker calls use that owner. The converter returns the verified
checkpoint, avoiding a second full import. Identical saved source representations
are deduplicated before extraction identity recovery; distinct representations
continue to require proof. Recovery failures use `COMPLETED_WORK_RECOVERY_GAP`.

Regression evidence: the direct-builder test failed in all four legacy/nested
combinations before moving the preflight. Automatic paid-extraction conversion
also exposed duplicate parsed-source admission; both paid cases failed before
deduplication. After repair, 44 tests passed across build preflight, offline
checkpoint upgrade and relay failure tests. No model/network execution is used.

Broader checks found nine failures in canonical storage/compatibility tests;
all nine reproduce against an isolated archive of inspected HEAD 53a860172.
Their expectations and gates were not changed. Full acceptance is not green.
Live inventory contains one empty Default Project legacy carrier and six legacy
paid carriers in another project. The latter contain opaque prompt-bound relay
results, whose full business identity has not been recovered. They remain
untouched and must block rather than trigger paid recomputation.

The first development App packaging attempt passed guard and compilation but
failed its workspace-output check for packages/contracts/dist/index.d.ts.
Packaged App runtime verification remains pending. No upstream merge was run.

## 2026-10-28 interrupted-write and saved-document checks

Automatic preflight now loads current parsed sources only for historical source
identities without a saved document. Regression failed when a saved parse was
available but the current artifact loader was forbidden; it now reuses the saved
document without loading current artifacts. Unpublished regular `.pending-*`
files are ignored during conversion, matching the strict import owner's atomic
write semantics. Both canonical and legacy interrupted-write cases failed before
this change. Symlinks and unknown completed files remain rejected.

Focused checkpoint/preflight/relay suite: 46 passed. Live read-only inventory:
8 datasets, one empty convertible Default Project carrier, one verified canonical
dataset with 10,863 entries, six opaque paid legacy carriers blocked on missing
business identity. No live datasets changed by this audit. App packaging and
consumer acceptance remain pending; root typecheck exposed an existing consumer
query snapshot narrowing error, corrected locally before the packaging retry.

## 2026-10-28 packaged verification update

Consumer guard/typecheck and library change-verification passed (run
`b1bbb573-a6cf-449a-8889-f2569c6d4dd3`); Case `capability-library-prepare`,
primary owner `journey-library`, delta keep, no baseline or pass criteria change.
Relocated native bundle acceptance passed. A development App built from a frozen
consumer source snapshot passed artifact scanning (52,748 files, zero violations)
and launched as `0.10.0-local.20261028.144305Z`. Development-only local artifact
receipt records this fork's exact dirty source digest; no release pin was changed.

Real Default Project build `cd2e69a1-e11a-45a6-baac-a3904eebe92e` completed
at 15:09:55Z and adopted snapshot
`snapshot:library-default-project:27bd6ba426f46ea702086063ff0882559fce1a1fe4ecd7bbca5e7888ea5701db`.
Normal packaged snapshot API returned HTTP 200 with one document, 3,821 entities,
4,504 relations, 984 communities, and 961 original execution receipts.
The fresh Electron profile shows onboarding; this run validates the packaged
authenticated HTTP/native build and adoption, not the research page's visual state.

Six CFA legacy paid carriers still lack verifiable business identities. Their
887 unique receipts and outputs remain intact; no admission bypass, deletion or
paid recomputation was used to turn those gaps into passes. Nine broader native
test failures described above remain baseline failures. No upstream merge tested.

## 2026-10-29 pre-push verification

Re-ran checkpoint preflight/upgrade, semantic query worker, Explorer workspace
data and PDF ownership regressions together: 91 passed. Explorer workspace UI
regressions: 2 passed; `tsc -b` passed. These focused checks do not supersede the
baseline failures and paid-carrier recovery limitations recorded above.
