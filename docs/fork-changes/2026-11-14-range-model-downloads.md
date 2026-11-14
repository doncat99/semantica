# Bounded parallel model downloads

- Record ID: 2026-11-14-range-model-downloads
- Date / author: 2026-11-14 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `2980f289`
- Upstream reference: not inspected; pending upstream assessment
- Related issue / PR / commits / records: local `make dev` model download timed out

## Reason and scope

`make dev` invokes `.github/scripts/semantic_worker_models.py` from the local
Semantica source snapshot. The script downloaded manifest files serially with a
single `urlopen` per file, wrote bytes directly to the final filename, and
treated a timed-out partial file as a completed file on the next run. A
171,658,996-byte Docling model stalled and raised a socket read timeout.

Scope is bounded range transfer, resumability at completed-range boundaries,
and verified atomic publication of each model file. Model selection, immutable
revision pins and admitted SHA-256 digests are unchanged.

## Native capability assessment

- Existing owner and inspected files/symbols: `.github/scripts/semantic_worker_models.py::main`; model inventory in `.github/requirements/semantic-worker-models.json`.
- Actual callers / config / exports / tests / recent removals checked: OntoScience `engineering/scripts/dev-dependencies.ts` invokes this script from the Semantica source snapshot; `.github/workflows/semantic-worker-native.yml` invokes it for native builds; regression tests are in `tests/test_semantic_worker_release.py`.
- Decision: repair native owner.
- Evidence no second implementation is introduced: only this script downloads the locked model files; no OntoScience-side model downloader or fallback was added. A live CDN probe returned `206 Partial Content` with the expected `Content-Range` for the pinned 171,658,996-byte model.

## Approach and actual changes

- Changed files and why: the native model downloader now requests 4 MiB byte ranges with at most 32 concurrent workers, validates each range response, resumes complete verified-length parts, assembles into a sibling partial file, validates total length and the lock's SHA-256, then atomically replaces the destination. Invalid old final files and stale parts are removed by this owner.
- Contract / consumer / stored-data impact and migration or deletion targets: caller CLI and manifest schema are unchanged. Existing incomplete final files are rejected and removed before redownload. Completed ranges remain under `<model>.parts` after transfer failure and are removed after successful publication.
- Model / network / dependency / cost impact: no dependency or model-pin changes. At most 32 simultaneous HTTP requests for one file; each range is 4 MiB. The server must honor byte ranges. A failed in-flight range restarts as a whole; completed ranges are reused.
- Planned but not implemented: none.

## Verification and limitations

- Commands and results: `uv run --no-project --python 3.12 pytest -q tests/test_semantic_worker_release.py` passed (22 tests); `python -m py_compile .github/scripts/semantic_worker_models.py` and scoped `git diff --check` passed. The regression test uses a local HTTP Range server, verifies concurrent requests stay at or below 32, forces a range failure, then confirms the retry requests only the missing range and yields exact expected bytes. A live CDN run fetched all nine locked model files into the active dev-runtime model directory; the 171,658,996-byte Heron and 212,758,388-byte TableFormer weights and all other model hashes matched the immutable manifest.
- Checks not run and why: complete `make dev` packaging did not finish. It built the Semantica wheel, then blocked on the separate `semantic_worker_native.py` single-connection Python runtime download. That independent path had transferred only about 3.5 MB and has no resume support; the run was stopped to avoid an unbounded wait. Its exact incomplete `.partial` was removed after confirming no process remained. The App was not launched.
- Known risks / unresolved questions: parallelism may not improve throughput if the CDN throttles the aggregate transfer; the downloader fails explicitly if a server does not honor HTTP byte ranges.

## Upstream merge assessment

- Disposition: pending; native upstream implementation not inspected.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: `.github/scripts/semantic_worker_models.py`.
- Conditions to retain, adapt or remove this change: inspect upstream's corresponding model downloader and use a single native owner after merge.
- Required consumer/regression checks after merge: native model download tests, full worker build, artifact model inventory verification and dev packaging.

## Dated follow-ups

2026-11-14: Implementation and model-download verification completed at the recorded source revision. End-to-end App packaging remains blocked by the independent native Python runtime downloader described above; no claim of App startup is made.
