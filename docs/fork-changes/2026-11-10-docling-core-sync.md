# Docling core alignment after upstream sync

- Date: 2026-11-10
- Status: verified on macOS arm64
- Fork base revision: ef512e21d28f94f9efb84dbaf0689ad0243c0ea3

## Reason and native owner

Docling fork 615d436422b7ef4c63aeb3d0d988dcc1c9249834 requires
docling-core>=2.106,<3. The native worker bundle owner
.github/scripts/semantic_worker_release.py::build_bundle supplies platform
constraints fixing core to 2.104, making local packaging unsatisfiable.
All six platform constraint files now pin core to 2.106.0, doclang to 0.9.0,
and docling-parse to 7.25.0. Core requires doclang>=0.9,<0.10; the old parse
constraint excluded Pillow 13. Parse 7.25 accepts Pillow<14, retaining the
worker's Pillow>=13 requirement. Compatibility ranges remain in dependency
metadata; these platform lock files select exact reproducible versions. Existing local
wheel overrides remain the Docling source selection owner; no runtime path or
business-result identity changes. No stored-data migration is needed.

## Verification and limitations

Failed macOS make dev dependency resolution reproduced the incompatibility.
After alignment, the macOS worker resolves all 138 packages successfully.
Native bundle resolution and relocated offline parsing/OCR, model-protocol,
query and inventory acceptance passed (artifact
sha256:2fde7e739808b954cc82f04f59fc1f86dcb22a7a2816ee5da95bef3f9dfdf40a).
Acceptance checks installed Docling versions against the selected release
inventory instead of stale source literals; mismatches remain errors.
20 release-owner tests passed, including selected-version mismatch rejection.
The local model test was blocked by missing pyoxigraph/sqlite-vec in the host
test environment; the complete installed bundle passed that model acceptance.
Dependency-only update: no Acceptance Case behavior changes.
Other platform runtimes have not been executed. No model calls are needed.

## Upstream assessment

Adapt fork runtime constraints to the synced upstream requirement. Reviewed
Docling 615d4364 wheel metadata; dependencies change, not parsing logic.
