# Independent CUDA and DirectML worker artifacts

- Record ID: 2026-10-22-gpu-runtime-profiles
- Date / author: 2026-10-22 / Codex
- Status: implemented; verified only in the stated host-independent scope
- Fork base revision: 17b0c0f9 (local main inspected)
- Upstream reference: not reviewed in this change
- Related records: platform acceleration configuration and diagnostics in Docling fork

## Reason and scope

Existing Linux/Windows worker releases install CPU dependencies even though native
Docling inference owners support acceleration. Prepare separate complete artifacts;
do not mutate an installed runtime or label CPU CI runs as GPU acceptance.

## Native capability assessment

- Reuse `semantica/bundle.py::build_bundle`, `acceleration_inventory`,
  `parser_dependency_files` and the `.github/scripts/semantic_worker_release.py`
  release owner. Existing callers are the native release workflow and bundle tests.
- Reuse Docling's device/provider owners through `DoclingParser`; no second GPU
  dispatcher, PDF parser, model implementation or downloader is introduced.
- Repair dependency selection and publication, which previously had only CPU locks.

## Approach and actual changes

- Factor common worker dependencies and add mutually separate CUDA/DirectML extras.
  Linux/Windows CUDA uses cu130 Torch and ORT GPU; Windows DirectML uses CPU Torch
  and ORT DirectML. Only ONNX OCR benefits from DirectML, not Torch layout/tables.
- Add three exact platform/profile constraints, profile-aware release matrix and
  archive names, build-time provider checks, release capability metadata and
  acceptance receipts. Default release remains three CPU variants; dispatch with
  `gpu_profiles=true` additionally builds three GPU variants.
- Include the selected ORT distribution in the parser dependency digest, even
  when RapidOCR has no dependency declaration pointing to it.
- DirectML acceptance requires the native RapidOCR session fix: memory patterns
  disabled and ORT_SEQUENTIAL. Current pinned dependencies do not yet consume
  the corrected RapidOCR/Docling releases; GPU publication is not claimed ready.
- No stored-data migration. Models unchanged. No model/API cost in focused tests.

## Verification and limitations

- Regression-first release routing: 4 failed / 2 passed before implementation.
- Focused pytest: 35 passed across bundle, release, native download and PDF owner
  suites. Covers profile routing, unsupported platforms, ORT exclusivity,
  CUDA build vs hardware availability, locks and parser digest dependency closure.
- Constraints resolved with uv for Python 3.12 on each target. This establishes
  dependency resolution, not native import/inference or cross-platform performance.
- No NVIDIA/DirectML hardware available on this macOS host. No GPU release or
  installed application updated. Hosted CI deliberately validates CPU inference
  and reports `gpuInferenceValidated=false` even for GPU-capable artifacts.
- CUDA 13 requires a compatible NVIDIA driver; DirectML requires Windows/DX12.
  Neither provider enumeration nor build metadata proves model execution on GPU.
- `uv lock` resolved 487 packages and refreshed development extra metadata. GPU
  releases use their platform constraints, not this universal development lock.
- Wider parser/lifecycle tests: 9 passed, 12 failed in this local venv, which lacks
  `docling_core` and Docling model dependencies. No parser source changed here;
  focused success does not establish full parser/release health.

## Upstream merge assessment

- Disposition: pending upstream comparison. Preserve only while upstream lacks
  equivalent immutable platform/profile artifact release support.
- Overlapping owners: bundle assembly, pyproject extras and native release workflow.
  After merges, rerun bundle/release tests, dependency resolution, native installed
  acceptance, GPU model inference and equal-output ESG performance comparisons.
