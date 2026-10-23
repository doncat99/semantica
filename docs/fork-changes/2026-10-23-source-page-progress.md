# Forward native Docling page progress to source workers

- Record ID: 2026-10-23-source-page-progress
- Date / author: 2026-10-23 / repository contributor
- Status: implemented and locally verified; unreleased
- Fork base revision: e761a647 (fast-forwarded from 506ae4de before final verification)
- Upstream reference: local Docling progress API inspected; Semantica upstream not reviewed this turn
- Related issue / PR / commits / records: pending

## Reason and scope

The parse_source JSONL worker did not forward its progress callback through the
source boundary and Docling adapter. Consumers could not display live page work.
This change wires the existing native capability; no OCR/reader implementation,
estimated page counts, quality admission change or model calls are introduced.

## Native capability assessment

- Existing owners: DoclingParser.parse delegates conversion to Docling's converter;
  source.parse_source chooses the admitted format; semantic_source_artifact owns
  source identity and worker event translation; semantic_worker owns JSONL output.
- Inspected callers/tests: tests/parse/test_docling_parser.py,
  tests/test_project_source.py and tests/test_pdf_reader_ownership.py at base above.
- Decision: repair native callback plumbing, reuse Docling page_completed events.
- No second parser, progress estimator or processing pipeline is introduced.

## Approach and actual changes

- Pass an optional native callback through parse_source and DoclingParser.parse.
- parse_source_artifact translates completed_pages and total_pages, binds sourceId,
  and counts success=False events separately for each conversion (including OCR retries).
- Page work may finish before document assembly/enrichment; only the artifact
  response terminates the worker request. Failed-page events are not build errors.
- Additive optional JSONL metadata failedPages is included in completedPages.
  Consumers retain their existing protocol and require no stored-data migration.
- No new dependencies or network/model requests. Other parser backends emit no
  fabricated page progress. Native Docling callback support is required when used.
- Not implemented: release/pin/package delivery and real ESG acceptance.

## Verification and limitations

- Red spec: source callback test failed with unexpected keyword progress_callback.
- Focused checks: 63 passed (parser, source, PDF owner, worker validation and
  project document quality), with one dependency deprecation warning.
- Actual offline native conversion through JSONL serve -> artifact -> source ->
  Docling: three-page PDF emitted 1/3, 2/3, 3/3, then the successful artifact
  response at 17.029 seconds. Forced OCR emitted the same real page counters with
  stage recognizing, then the successful artifact response at 14.362 seconds.
- These native checks used the current pinned Docling dependencies, local
  Semantica source and cached model weights, not a published replacement worker.
- Fixture coverage: out-of-order page numbers, failure counts, OCR retry reset,
  request identity, no document path/text in progress, no terminal at last page.
- Real model/ESG requests and application project data are not touched.

## Upstream merge assessment

- Disposition: pending; no incoming Semantica upstream revision reviewed.
- Likely overlap: source/artifact/worker callback signatures and Docling conversion.
- Retain only while needed to connect the native event API; adapt or drop when
  upstream owns equivalent wiring. Re-run source, worker and PDF ownership tests.

## Dated follow-ups

- 2026-10-23: focused and native offline checks passed. Fork commit/push,
  native Actions release, immutable consumer pin and packaged App acceptance
  remain pending; no release or installed-App delivery is claimed.
