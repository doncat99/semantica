# Parser recipe identity independent of installation location and time

- Record ID: 2026-11-05-parser-recipe-installation-independence
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty checkout preserved)
- Upstream reference: not inspected
- Related records: 2026-11-05-explicit-parsed-reader-reference.md

## Reason and scope

Two native bundles with identical parser execution bytes produced different
`documentParserDigest` values. Host diagnostic `g4-parser-input-diff.json`
identified 115 selected input changes: 68 console script staging paths,
43 RECORD files, two local wheel URLs and two installation timestamps.
The complete artifact digest must still identify every installed byte.

## Native capability assessment

- Owner: `semantica/bundle.py::document_parser_digest`; bundle assembly supplies
  the installed dependency closure from `parser_dependency_files`.
- Inspected callers and tests: bundle assembly and `tests/test_bundle.py`.
- Inspected runtime: worker executes isolated Python with `-m`; parser adapters
  use library APIs. `project_office.py` executes its receipt-bound Office binary;
  `parse/media_parser.py` executes ffprobe. Both remain fingerprint inputs.
- Repair the existing identity owner, with no second parser or compatibility path.

## Approach and actual changes

- Exclude only declared unused installed console/gui wrappers and exact
  dist-info installation metadata (RECORD, direct_url.json, uv_cache.json)
  from the parser recipe. Interpreter, stdlib, package metadata, native code,
  parser source, models, ffprobe and Office receipt/binary remain inputs.
- Preserve every file and its byte hash in the immutable artifact manifest;
  artifact inventory validation and receipts remain unchanged.
- No model calls, network access or new dependencies.
- Existing derived data will rebuild once under the corrected recipe identity;
  no compatibility reader or hand-edited digest is introduced.

## Verification and limitations

- Before repair: new regression selection produced 5 failures and 10 passes;
  evidence `/tmp/g4-parser-recipe-red.log`.
- Full artifact rebuilding, fixed artifact delivery and real ESG acceptance are
  outside this focused change and have not been performed.

## Upstream merge assessment

- Disposition: pending; upstream not reviewed.
- Re-evaluate the same bundle identity owner on merge; preserve separation of
  execution recipe identity from exact artifact identity and run bundle tests.


## 2026-11-05 verification follow-up

- Console entry-points alone missed six wheel script-files (dill profiling tools,
  mpire dashboard, ANTLR test runner and XlsxWriter VBA utility). Selection now
  also uses installed distribution RECORD paths plus a bounded Python launcher
  header check. Unregistered Python scripts, native bin tools and paths escaping
  the bundle remain included rather than being classified as unused wrappers.
- `pytest -q tests/test_bundle.py`: **30 passed**;
  `/tmp/g4-parser-recipe-green.log`. Existing inventory tests still reject extra,
  missing and changed artifact files. New invalidation tests cover interpreter,
  stdlib, native library, dependency metadata, parser source, models and Office.
- Initial regression: **5 failed, 10 passed** before the repair;
  `/tmp/g4-parser-recipe-red.log`. Script-files-specific regression also failed
  against the entry-points-only implementation loaded in memory (no tracked
  source reset), then passed; `/tmp/g4-parser-wheel-scripts-red.log`.
- Read-only recomputation over the two real pre-existing artifact manifests and
  their installed dependency metadata now yields the identical parser recipe:
  `sha256:f186d3fb5ffc1fc6f5c574769e8ef945259c7f594edb86e4e2d278ce1a12809c`.
  All previously differing selected entries are eliminated. Evidence:
  `/tmp/g4-parser-recipe-compare.json`. No manifest/receipt/artifact was modified;
  this verifies the corrected recipe computation, not a rebuilt artifact.
- Full artifact rebuild, real ESG build and release acceptance remain unverified.
- Complete rebuilt artifact acceptance subsequently exposed an unaligned caller:
  `semantic_worker_acceptance.py` recomputed the recipe without installed script
  classification. It now delegates with the same dependency and script inputs
  as assembly. The executable acceptance-boundary regression failed before the
  repair (`/tmp/g4-parser-acceptance-red.log`); full rebuilding must pass again.
- Final affected-owner/release-tooling selection:
  `pytest -q tests/test_bundle.py tests/test_semantic_worker_release.py`:
  **45 passed in 6.26s**, `/tmp/g4-parser-recipe-full-green.log`.
  `git diff --check` passed for the changed owner, tests and this record.

- Acceptance caller follow-up verification: `.venv/bin/python -m pytest -q tests/test_bundle.py tests/test_semantic_worker_release.py`: **46 passed in 6.77s**, `/tmp/g4-parser-acceptance-green-native.log`. An initial run through ambient uv Python had 45 passed and one environment failure because that interpreter lacked pyoxigraph; it is not counted as passing.
