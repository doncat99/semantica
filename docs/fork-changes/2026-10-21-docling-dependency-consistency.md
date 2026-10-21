# Align Docling contributor and native dependency resolution

- Record ID: 2026-10-21-docling-dependency-consistency
- Date / author: 2026-10-21 / OntoScience maintainers
- Status: verified-in-stated-scope
- Fork base revision: 8c4c96fe1af73f7103307d68fd7ba9b41ecc7c93
- Upstream reference: no incoming upstream revision reviewed

## Reason and scope

The declaration and all three native-worker constraints select Docling 2.139.0
and the immutable fork docling-slim 2.139.0+ontoscience.2 wheel, but the root
uv.lock still resolves both distributions to upstream 2.135.0. An older draft
checkout additionally has an independently modified environment with slim .1.
Repair main's dependency resolution; preserve unrelated draft checkouts.

## Native capability assessment

- Owners: pyproject.toml extras, uv.lock, .github/requirements/semantic-worker-*.lock.
- Existing verification: ci.yml runs uv lock --check with pinned uv 0.9.10;
  semantic_worker_acceptance.py checks installed slim version and formula API.
- Docling is the upstream meta-package; docling-slim owns the Python modules.
  Retain this intentional packaging split and the existing DoclingParser owner.
- Reuse the native lock and acceptance checks; no new resolver, parser or CI gate.

## Approach and actual changes

- Regenerate uv.lock without requesting unrelated upgrades.
- Document locked contributor installation and how it differs from native release.
- No snapshot/data migration, model calls, App pin change or artifact publication.

## Verification and limitations

- Before repair: uv lock --check failed: lockfile needs to be updated.
- `uv lock --check --quiet`: passed.
- `.venv/bin/pytest -q tests/test_pyproject_extras.py tests/test_pdf_reader_ownership.py`: 18 passed.
- `.venv/bin/pytest -q tests/parse/test_docling_lifecycle.py`: 6 passed.
- Fresh Python 3.12 environment with `uv sync --locked --extra semantic-worker --no-install-project`: installed 216 packages; metadata check confirmed docling 2.139.0, docling-slim 2.139.0+ontoscience.2, and native formula import.
- `uv pip check` in that environment: all installed packages compatible.
- `git diff --check`: passed.
- No Auto Test or App release requested here; this verifies source dependency resolution, not a published worker bundle.

## Upstream merge assessment

- Disposition: keep while the Docling fork patch is required.
- Incoming upstream revision: not reviewed in this repair.
- On future merges, reconcile declarations and lockfiles together, then run the
  existing locked-resolution and native artifact acceptance checks.
