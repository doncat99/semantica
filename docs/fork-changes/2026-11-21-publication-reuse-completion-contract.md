# Preserve completion identity when reusing a publication

- Record ID: 2026-11-21-publication-reuse-completion-contract
- Date / author: 2026-11-21 / OntoScience contributor
- Status: verified-in-stated-scope
- Fork base revision: 5fea771900748d49ab09f7e1bc5e258053d48fe1
- Upstream reference: not inspected

## Reason and scope

The packaged consumer failed after "Completed publication reused" with KeyError:
completion_input. The reuse branch omitted a required result field, although the
first-build branch returned it. Repair the native owner, not the host consumer.

## Native capability assessment

Owner: semantic_publication_builder.py::_build_semantic_artifacts; actual consumer:
semantic_worker.py::_dispatch indexes built['completion_input']. The existing
native pipeline reuse regression covered rebuild avoidance but not this contract.
No second implementation, default, compatibility reader or fallback is introduced.

## Approach and actual changes

Return the same validated completion_key from the completed-publication branch.
Extend test_native_build_pipeline.py's existing reuse test to compare completion
identity, publication and indexes, and prove no additional model/embedding calls.
No storage migration, cache deletion, model call or dependency change is needed.

## Verification and limitations

Regression before fix: failed with KeyError completion_input. After fix:
.venv/bin/python -m pytest -q tests/test_native_build_pipeline.py
 tests/test_native_build_worker.py tests/test_native_extraction_handoff.py
— 32 passed. These tests use fixture transports, not paid remote models.
Packaged consumer verification is separate; this result is not UI acceptance.

## Upstream merge assessment

Pending; upstream not reviewed. Retain while this native builder/worker contract
exists. Re-run the three affected suites when merging overlapping pipeline code.
