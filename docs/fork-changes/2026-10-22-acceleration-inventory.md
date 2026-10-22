# Native bundle acceleration evidence

- Record ID: 2026-10-22-acceleration-inventory
- Date / author: 2026-10-22 / doncat99
- Status: focused-tests-passed; native artifact validation pending
- Fork base revision: 76dbced6456d6ead7a70b249800243957ea13154
- Upstream reference: not refreshed for this change
- Related records: Docling `docs/usage/platform_acceleration.md`

## Reason and scope

Native acceptance forces CPU and previously reported no hardware inventory.
Linux/Windows bundles contain CPU Torch and CPU ONNX Runtime. A successful
acceptance run must not be mistaken for proof of GPU execution.

## Native capability assessment

- Owner: `semantica.bundle`, installed dependency inventory and bundle receipts.
- Caller: `.github/scripts/semantic_worker_acceptance.py`, relocated bundle gate.
- Tests: `tests/test_bundle.py`; existing parser owner remains
  `semantica.parse.docling_parser.DoclingParser`.
- Decision: extend the existing inventory, do not create another device selector,
  PDF reader, or OCR implementation.

## Approach and actual changes

Record Torch build/runtime capabilities and ORT providers in the acceptance
receipt. Keep available capabilities separate from CPU-only acceptance evidence.
No runtime dependency replacement or application pin is implied by this record.

## Verification and limitations

41 focused tests passed using the dependency-complete Docling candidate environment
(bundle inventory, PDF reader ownership, Docling parser and lifecycle). The minimal
Semantica environment lacks optional docling_core and cannot run parser tests.
No NVIDIA, DirectML, or Intel GPU host is available in
this session. The current immutable bundles remain CPU-only on Linux/Windows.
GPU-capable release variants and their hardware acceptance remain outstanding;
installing two ONNX Runtime distributions in one prefix is not a solution.

## Upstream merge assessment

- Disposition: keep while upstream lacks equivalent native acceptance evidence.
- Overlap: bundle inventory and native release acceptance only.
- Required checks: bundle tests, relocated acceptance, and real hardware checks
  before claiming a GPU-capable release.
