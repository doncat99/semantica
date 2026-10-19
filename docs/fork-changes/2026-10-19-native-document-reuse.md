# Native document materialization reuse

- Record ID: 2026-10-19-native-document-reuse
- Date / author: 2026-10-19 / Codex
- Status: implemented-and-focused-verified
- Fork base revision: 0992201f
- Upstream reference: not inspected in this change
- Related records: `2026-10-19-pdf-reader-ownership-review.md`, `2026-10-19-pymupdf-native-parser.md`

## Reason and scope

ESG's grounded single-source build reparsed immutable bytes instead of consuming the native parsed-source artifact. Docling page projection repeatedly traversed all document items and exported DocTags twice. PDF consumers also need links and bounded page rendering without importing a reader outside PDFParser. This change repairs those owners; it does not add a registry, semantic algorithm, model call, or business admission rule.

## Native capability assessment

- Existing owners: `semantic_artifact_builder.py::{parse_source_artifact,bind_parsed_source_artifact,_load_parsed_source,build_grounded_source_snapshot}`, `source.py::parse_source`, `parse/docling_parser.py::DoclingParser`, and `parse/pdf_parser.py::PDFParser`.
- Callers/tests inspected: semantic worker protocol, project artifact builder, grounded-source tests, Docling parser tests, PDF lifecycle and ownership gates.
- Decision: repair and expose existing native owners.
- No second implementation: grounded builds consume `ParsedSourceRef`; page links/rendering remain methods of PDFParser; Docling remains the structured conversion owner.

## Approach and actual changes

- Parsed-source v2 binds a processing revision derived from source/adapter implementations, processing profile and local Docling dependency versions.
- Grounded-source accepts and verifies a parsed-source ref, activates its existing checkpoint for direct parsing fallback, and always resets context.
- Project builds derive page count from parsed data instead of reopening PDFs.
- Docling page projection indexes items once and reuses the first DocTags export.
- PDFParser now owns link observation and bounded page rendering.
- Parsed-source v1 artifacts are intentionally invalidated; consumers rematerialize them through the same owner.
- `native` is an explicit processing profile for text-layer PDFs. It uses `PDFParser`, retains page text and links,
  and does not import or run Docling. `local` remains the explicit Docling/DocTags structural profile.
- Materialization and semantic admission are separate phases. A readable PDF container with missing text is persisted
  as a page representation so an authorized OCR consumer can repair it; `_load_parsed_source` still applies the
  existing quality gate before knowledge extraction.
- No network or model calls were added. Parsing work should decrease after materialization.

## Verification and limitations

- Focused native grounded-source, document quality and PDF page lifecycle regression: 27 passed. The native-only
  grounded-source/PDF lifecycle subset independently passed 11 tests.
- The broader available Python 3.12 run produced 115 passed, 7 failed, 1 skipped. Six failures are the environment's
  older Docling API lacking `recover_formula_regions`; one existing worker restart test exceeded its 30-second
  limit. This record does not report the full fork suite green.
- The fork was reinstalled into ESG's pinned Python 3.13 `.venv-semantic` runtime. That runtime intentionally does
  not contain pytest; execution was verified through ESG's process boundary.
- Real 210-page text-layer PDF: 210 pages, 1,987,221 characters and 62 links; initial isolated cold materialization
  21.519s and hot read 0.034s. Two simultaneous filesystem requests executed one parser builder, returned the same
  reference and published one object. The prior Docling default path exceeded the explicit 1500-second limit.
- The qualified wheel is `sha256:8562aeea9f8ff3404cb310975953cbebedac4fb305d2278d7fdc962445f33846`.
  Its isolated cold runs were 40.067s, 60.395s and 63.216s; hot read was 0.046s and every run retained identical
  page/character/artifact digests. The last two exceed the proposed 60s controlled-load threshold. During these runs
  an unrelated long-lived VM used about 330% CPU and 4 GB RSS; direct parsing used 13.51 CPU seconds over 39.38 wall
  seconds. This explains observed scheduling pressure but does not qualify the continuous-three-run performance gate.
- ESG affected regression after the final owner migration: 299 passed. A focused ingestion/OCR/audit group later
  passed 136 with 14 database-dependent skips; its one obsolete fake-store failure was corrected to use the existing
  ObjectStore protocol and the narrowed group passed 9 with the same 14 skips. The final qualified-wheel regression,
  including the no-low-level-parser consumer gate and stable OCR key, passed 328 tests.
- No paid model call or production project was started.

## Upstream merge assessment

- Disposition: pending. Retain until upstream offers equivalent parsed-source consumption, processing identity, linear page projection and reader-owner capabilities.
- Incoming upstream revision reviewed: not yet reviewed.
- Likely conflicts: source parsing identity, semantic artifact builder and Docling/PDF parser adapters.
- After merge, rerun native artifact, Docling, PDF lifecycle and reader-ownership regressions plus ESG consumer tests.

## Dated follow-ups

2026-10-19: Initial implementation and focused regression recorded.

2026-10-20: Added the native PDF profile after a real 210-page Docling materialization exceeded 1500 seconds.
Connected parse/bind/load to the same profile, separated materialization from semantic quality admission, installed
the fork into the pinned runtime, and verified cold/hot/concurrent reuse. ESG now owns only business bindings and
object-store coordination; every PDF read/render remains under Semantica's native parser owners.
