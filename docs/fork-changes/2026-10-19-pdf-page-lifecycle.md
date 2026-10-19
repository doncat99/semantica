# Release native PDF page caches and honor text flow

- Record ID: 2026-10-19-pdf-page-lifecycle
- Date / author: 2026-10-19 / Codex
- Status: focused verification passed; stable performance qualification incomplete
- Fork base revision: 7999636854d50bd497f9ec284960b8c519e5e86a
- Upstream reference: not inspected for this change
- Related: ESG docs/audits/2026-10-19-pdf-parsing-root-cause.md

## Reason and scope

A retained 210-page original exceeded the consumer's 180-second process boundary.
Native PDFParser retained pdfplumber page layouts/objects until the whole document
closed. A diagnostic using Page.close after extraction preserved all 210 page text
hashes and reduced peak RSS from 2,747,695,104 to 590,938,112 bytes. Host load varied;
this is not a stable throughput guarantee. The supplied use_text_flow option was
also ignored; this is a separate contract defect, not a proven primary timeout cause.

## Native capability assessment

- Owner: semantica/parse/pdf_parser.py, PDFParser.parse / _parse_page.
- Callers: native extract_text/tables/images, parse facade, document_parser export;
  ESG scripts/semantica_capabilities_worker.py delegates with PDF_OPTIONS.
- Tests: tests/parse/test_pdf_scanned_detection.py, test_parse_comprehensive.py;
  new test_pdf_page_lifecycle.py reproduces lifecycle and option defects.
- Decision: repair the native owner using existing pdfplumber Page.close and
  extract_text(use_text_flow=...). No parallel parser, model or network dependency.

## Approach and actual changes

Implemented: release each selected page in finally after text/tables/images finish;
forward explicitly supplied use_text_flow without changing default extraction.
Native implementation hash already participates in consumer cache identity, so
changed extraction cannot reuse old text. No stored original or business state migration.

## Verification and limitations

Native regression: 18 passed in 14.19 seconds using
`tests/parse/test_pdf_page_lifecycle.py tests/parse/test_pdf_scanned_detection.py
tests/parse/test_parse_comprehensive.py`. Before the fix, the lifecycle tests had
2 failures / 1 pass. They cover close before the next page, close on extraction
failure, explicit option forwarding and unchanged defaults.

Built wheel SHA256:
`1f52fc24d45610dadc82981b8fc8661e15fff837b183e84a7ce7976f3c68fb85`.
Installed into an independent consumer environment; wheel/file verification and
dependency compatibility passed. The ongoing migration runtime was not modified.

An initial real-original consumer check exposed an ordering compatibility issue:
the consumer historically supplied use_text_flow=True but this owner ignored it.
Honoring it changed text order and correctly failed a quoted-text check. ESG now
explicitly selects False to preserve the native default previously in effect;
its historical originals/Reviews and quote validation remain unchanged. Final
consumer results will be recorded below.

2026-10-19 consumer verification: with explicit use_text_flow=False, the isolated
210-page original/Review check passed (201.14 seconds for the entire test, not
the parse call). The existing 180-second parse boundary was unchanged. It verified
one actual parse across repeated checks using new disk-store instances, and still
rejected a fabricated quote. Historical fixture expectations were not edited.
An earlier False run under concurrent host/test load exceeded the same parse
boundary. Both results are retained: this change proves lifecycle/contract and
focused correctness, not a guaranteed latency bound under contention.
Consumer option/cache/timeout checks: 8 passed; durable bounded-review recovery:
1 passed; remaining release-evidence checks: 4 passed. These checks do not qualify
deployment, sustained throughput, OCR or real browser multi-hop delivery.

No new OCR path, parser switch, timeout increase or PDF-specific shortcut.

2026-10-19 follow-up: after a same-original reader comparison, the owner authorized
replacing the native PDFParser reader with PyMuPDF. This record remains historical;
the new implementation and verification are in
[PyMuPDF switch](2026-10-19-pymupdf-native-parser.md).

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Overlap: PDFParser.parse and _parse_page. Drop/adapt if upstream releases pages
  and honors the option. Re-run lifecycle, scanned-PDF, parse and consumer quote/cache checks.
