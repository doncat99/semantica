# Docling 2.141 and IBM models 4.0.4.3

Updated the Semantica fork's parser inputs to the immutable OntoScience fork
artifacts published from their respective `main` branches:

- `docling-slim` `2.141.0+ontoscience.2`, SHA256
  `525c2fcfb06cdc6f5860736c824b033ecbf81e2230b8e149982788f0ee97a814`.
- `docling-ibm-models` `4.0.4+ontoscience.3`, SHA256
  `fad09be297a3c9152ba801931b1d76a201e5a6abd7a8a81220e0402b2a5f8d87`.

The universal lock and all six semantic-worker platform locks were regenerated
from `pyproject.toml`. The direct wheel requirements are intentional: the
fork artifacts are not published to public PyPI. Native worker release jobs
must consume these immutable URLs and publish only after all platform
acceptance jobs pass.

Native owners reused: `DoclingParser` for document conversion and `bundle.py`
plus `.github/scripts/semantic_worker_release.py` for immutable packaging;
no parser or runtime fallback was added. Inspected main: `8fe1491cd112`.
Callers affected: parse-docling and all semantic-worker platform profiles.

Verified 2026-10-22: `uv lock --check` resolved successfully; existing release,
bundle and PDF ownership tests passed (33 tests). These checks establish lock
and packaging contracts only; native platform acceptance and the consuming
App's ESG Report rebuild remain required. Upstream merge impact is limited
to fork-specific dependency pins and generated locks.
