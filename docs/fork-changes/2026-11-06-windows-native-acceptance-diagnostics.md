# Windows native acceptance diagnostics and targeted qualification

- Record ID: 2026-11-06-windows-native-acceptance-diagnostics
- Date / author: 2026-11-06 / fork contributors
- Status: verified-in-stated-scope
- Fork base revision: 52fa9451cf1ab863c560c342f047ad49be66916d
- Upstream reference: not inspected; release harness only
- Related issue / PR / commits / records: GitHub Actions run 42141214034

## Reason and scope

The Windows installed-worker acceptance failed after a query produced no stdout
within its existing 180-second deadline. Context-manager exit then replaced the
primary assertion with an empty-stderr exit assertion. macOS and Linux passed.
The existing log cannot establish whether keyword or semantic query failed, or
whether the cause was an exception, blocked pipe, or native computation.

## Native capability assessment

- Existing owners: `.github/scripts/semantic_worker_model_acceptance.py::QuerySession`,
  `.github/scripts/semantic_worker_release.py::release_matrix`, and
  `.github/workflows/semantic-worker-native.yml`.
- Inspected caller: installed acceptance query loop; native
  `semantic_query_worker.main` and `_serve_line` executor exception propagation;
  existing `tests/test_semantic_worker_release.py` matrix and release checks.
- Decision: repair the current acceptance and qualification owners.
- Production `semantica/**` is unchanged. The acceptance subprocess still invokes
  the installed native worker and delegates every operation to its existing owner.

## Approach and actual changes

- Capture stderr in a temporary file so undrained PIPE capacity cannot block the
  acceptance worker. Report operation/mode/target and retain primary failures.
- Add acceptance-only uncaught exception printing and periodic Python stack
  dumps through the installed worker entrypoint. Preserve the 180-second deadline.
- Add an explicit single-platform qualification input to the existing workflow;
  default remains all platforms. Disable publication for targeted qualification.
- Add focused regression checks for target selection, publication guard, primary
  exception preservation, diagnostic context and stream cleanup.
- Stored-data contracts, runtime algorithms, model calls and dependencies do not
  change. CI uses its existing loopback model relay; no paid model calls added.
- Planned but not implemented: diagnosing and repairing the actual Windows query
  failure after the qualified run exposes its stack.

## Verification and limitations

- New focused specifications first failed: 4 failed, 16 deselected.
- `.venv/bin/python -m pytest -q tests/test_semantic_worker_release.py`:
  20 passed in 5.29 seconds; host evidence `.tmp/g8-windows-diagnostics-green.log`.
- `git diff --check`: passed.
- Windows installed qualification remains pending. Focused local tests do not
  establish Windows success or formal release acceptance; a targeted success
  cannot authorize a partial release.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Likely overlap: release matrix, installed acceptance process lifecycle and CI.
- Retain only while these native harness owners remain canonical; adapt directly
  if upstream supplies equivalent diagnostics or qualification controls.
- Re-run release harness tests and verify full-matrix default plus publication
  exclusion for targeted qualification after merges.

## Dated follow-ups

2026-11-06: implementation and local regression scope recorded; Windows root cause
and release qualification remain explicitly unresolved.
