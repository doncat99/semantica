# Keep isolated operations inside an immutable native runtime

- Record ID: 2026-11-05-immutable-isolated-runtime
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main)
- Upstream reference: not inspected; this concerns the fork's isolated operation owner.
- Related records: [community queue maintenance](2026-11-05-community-queue-maintenance.md)

## Reason and scope

The installed lifecycle build created 1,075 untracked `.pyc` files in its native
artifact. Strict host inventory validation then correctly rejected App startup.
All extra files were written during 07:14:04–07:14:07, after native acceptance
ended at 07:12:50. Parent workers already use `-B`; their isolated topology child
did not inherit that interpreter flag.

## Native capability assessment

- Owner: `semantica/pipeline/parallelism_manager.py::ParallelismManager.execute_isolated_task`.
- Caller: `semantica/semantic_artifact_builder.py` isolated topology calculation.
- Related owners: `semantica/bundle.py::verify_bundle_inventory` and
  `.github/scripts/semantic_worker_acceptance.py`.
- Tests inspected: `tests/pipeline/test_isolated_task.py` and native bundle tests.
- Decision: repair the existing subprocess command and strict verifier. No new
  runtime, compatibility path or artifact contract is introduced.

## Approach and actual changes

- Pass `-B` explicitly to the isolated Python operation before importing any
  modules. Keep source/test import behavior and existing resource limits.
- Remove the verifier's `remove_untracked_bytecode` option and acceptance's use
  of it. Post-run inventory checking must reveal mutations rather than delete
  their evidence and report success.
- Pin the child's actual `sys.dont_write_bytecode` behavior with a regression;
  update bundle tests to require rejection without removal of extra bytecode.
- Consumer support: OntoScience's installed native lifecycle test now performs
  strict native inventory verification after publish, restart, cancellation,
  withdrawal and restart, including process shutdown.
- No persisted knowledge migration, dependency, model call or network cost change.
- Existing polluted dev artifacts remain invalid; rebuild from source rather
  than altering their manifests or silently repairing them during reads.

## Verification and limitations

- Red: isolated immutability regression failed (`False is True`), 1 failed,
  19 deselected; local evidence `/tmp/g4-bytecode-red.log`.
- Green: isolated operations and bundle regression selection, 36 passed in
  16.60 seconds; local evidence `/tmp/g4-bytecode-green.log`.
- Rebuilt fixed-artifact lifecycle and full host change-verification remain
  pending at this record update. Source regression success is not artifact or
  real ESG capacity acceptance.
- This change prevents this owner from generating bytecode; it does not prove
  every third-party subprocess is immutable. Strict post-run inventory remains
  the acceptance boundary for all mutations.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely overlap: isolated subprocess startup and bundle inventory acceptance.
- Retain the behavior until the canonical owner demonstrably disables bytecode
  before imports. Remove obsolete patch code if upstream supplies that behavior.
- After merge, rerun isolated cancellation/resource/failure tests, bundle extra
  file rejection, and installed lifecycle with strict post-run inventory.
