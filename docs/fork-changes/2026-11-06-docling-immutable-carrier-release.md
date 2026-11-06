# Pin the qualified Docling content carrier release

- Record ID: 2026-11-06-docling-immutable-carrier-release
- Date / author: 2026-11-06 / repository agent
- Status: verified in dependency-resolution scope; final native release pending
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: no incoming upstream merge reviewed
- Related record: 2026-11-04-docling-single-content-carrier

## Reason and native ownership

The native `DoclingParser` delegates structured conversion to Docling. The
previous formal wheel predates the already qualified content-carrier changes.
The fork release at commit `f7d9f5136f887d03d6bdf43b66f33e60625fe567`
publishes those changes without introducing a reader or runtime checkout.

## Actual changes

Both Docling URL declarations in `pyproject.toml`, `uv.lock`, and all six native
CPU/CUDA/DirectML constraint files now bind the immutable release asset:

`https://github.com/doncat99/docling/releases/download/ontoscience-docling-f7d9f5136f88/docling_slim-2.141.0%2Bontoscience.2-py3-none-any.whl`

SHA256: `84cd130c92c8dc044f52450a1ea645082e420ec52dd5d17fbe456a7004a1d07c`.
Existing IBM wheel URLs/hashes and all dependency versions remain unchanged.
No source consumer, model prompt, embedding space, or persisted schema changes.
Stored-data adoption still requires exact installed parser/processing identity
verification by the consuming application's explicit offline maintenance owner.

## Verification and limits

With uv 0.9.10, `uv lock`, `uv lock --check`, and all six original lock-header
compile commands succeeded. Compared with the pre-integration files, effective
requirement differences are restricted to the Docling URL/hash. Generated
comments additionally identify existing self-constraints and psutil ownership.
`git diff --check` passed. Integration evidence is retained in the consuming
workspace at `.tmp/g8-docling-dependency-integration/verification.json` and
`exact-integration.diff`.

The downloaded released wheel is byte-identical to the previously qualified dev
wheel (all 316 archive members match). Docling's own carrier qualification passed
26 tests, plus its applicable validation hooks and offline lock check. These
results do not establish final Semantica platform or real ESG acceptance.

## Upstream merge assessment

Pending. On an incoming parser/dependency change, compare the native carrier and
installed parser inputs; retain the immutable pin only while it names the current
qualified owner. Re-run parser carrier regressions, dependency resolution and
relocated native acceptance. Do not add an older-wheel fallback.
