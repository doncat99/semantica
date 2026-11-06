# Cancellation during immutable-byte admission

- Record ID: 2026-11-04-source-hash-cancellation
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing dirty native changes
- Upstream reference: not inspected
- Related records: 2026-11-04-native-build-body-budget.md

## Reason and scope

G4/G5 build admission hashes immutable source and parsed-artifact bytes before
extraction. Existing reads are streamed, but do not check the request cancellation
context. A canceled build can continue hashing a large file before returning.
Use the existing request-local cancellation owner between bounded reads.

## Native capability assessment

- Owners: source.py::source_content_revision (BLAKE3 material identity),
  semantic_source_artifact.py::_digest_file (SHA256 parsed artifact identity),
  semantic_worker_context.py::check_query_cancellation (existing ProcessingError).
- Callers: parsed-source parse/bind/load and source identity checks; existing
  tests/test_project_source.py and parsed-source single-carrier tests inspected.
- Repair these owners; do not introduce another hash, credential or cancellation
  implementation. No protocol, digest semantics or supported format changes.

## Approach and actual changes

- Red tests exercise both actual owners before open and after an in-flight block,
  assert at most one 1 MiB read after cancellation and stream closure, and verify
  unchanged digests without cancellation.
- Both owners now check the existing cancellation context before opening, before
  every 1 MiB read and after EOF; SHA256 uses incremental reads like BLAKE3.
- Updated the superseded snapshot-oriented single-carrier test to exercise the
  current worker publication contract, unchanged parser file identity/digest and
  absence of duplicate JSON/SQLite output. No aggregate output was restored.
- No model/network/dependency cost, stored-data migration or deletion.
- Full JSON decode, native structure traversal and global algorithm cancellation
  remain separate gaps; this change only covers hash admission.

## Verification and limitations

- Before repair, the five new tests gave four failures (cancellation did not
  raise) and one digest-contract pass. After repair, the hash, project-source,
  parsed-source single-carrier and native scalar-grounding suites all pass:
  `32 passed in 1.35s` using the fork `.venv/bin/python -m pytest -q`.
- No physical disk latency or process-level cancellation guarantee claimed.

## Upstream merge assessment

- Pending; no incoming revision reviewed. Likely overlaps source identity and
  parsed-artifact admission. Retain only while equivalent request cancellation
  coverage is absent; rerun hash, project source and parsed-source regressions.

## 2026-11-04 fixed-buffer RSS follow-up

[Native source builder cutover](2026-11-04-native-source-builder-cutover.md)
measured retained allocator growth from repeatedly allocating 1 MiB read blocks.
Both digest owners now reuse one bytearray with readinto while preserving all
cancellation checks and exact digest semantics. Admission/hash/traversal tests:
19 passed, including actual 16 MiB source RSS below 8 MiB admission growth.
