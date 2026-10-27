# Expose the existing PDF dependency's content-stream ordering

## 2026-10-27 correction: superseded implementation, not a release candidate

This draft describes the pre-PyMuPDF implementation. The owner subsequently
selected `use_text_flow=False`, then authorized the PyMuPDF migration committed
as `4c44ad19`; see `2026-10-19-pdf-page-lifecycle.md` and
`2026-10-19-pymupdf-native-parser.md`. Restoring this draft over the migrated
parser is an unauthorized backend rollback, not an option-forwarding fix.
The local rollback has been removed. Use the current PyMuPDF owner and its
`sort` contract; the two libraries' boolean options are not interchangeable.
Historical results below are retained and do not qualify the current runtime.

- Record ID: 2026-10-19-pdf-native-text-flow
- Date / author: 2026-10-19 / Codex
- Status: implemented; native installed-wheel tests passed, full ESG qualification pending
- Fork base revision: f69d598466e7877a795b1bbccd35231910858558 (dirty checkout; unrelated native identity changes preserved)
- Upstream reference: not inspected remotely
- Related records: ESG registry-rollout-parser-order-diagnostic-20261018.json

## Reason and scope

Five existing ESG original-PDF regression cases lost contiguous quotations when
switching to native PDFParser. Default geometric ordering interleaves columns
or cover text. Diagnostic selected-page extraction with pdfplumber's existing
use_text_flow=True recovers all five quotations. This is compatibility evidence,
not proof that content-stream order is universally the correct reading order.

## Native capability assessment

- Owner: semantica/parse/pdf_parser.py, PDFParser._parse_page / parse / config.
- Inspected callers: DocumentParser, parse.methods, PDFParser.extract_text;
  exports in parse.__init__; parse_usage.md; existing parse tests and PDF history.
- Existing pdfplumber supports use_text_flow; native owner currently ignores it.
- Decision: repair option forwarding in the existing owner; preserve False default.
  No new extractor, fallback, model, network request or company-specific rule.

## Approach and actual changes

- Added parameter-forwarding regression in test_pdf_scanned_detection.py first.
- Planned: forward parse option, then constructor config, then False to existing
  page.extract_text; document consumer opt-in.
- ESG consumer must bind the selected option to its parser/cache identity and
  evaluate unchanged real originals. No stored original or gold-label migration.
- No dependency or model cost changes.

## Verification and limitations

- Pending failing-before/fixed-after test execution and consumer regression.
- Full release, paid semantic/multihop and continuous operation not verified.
- Content streams can themselves have poor reading order; measure regressions.

## Upstream merge assessment

- Disposition: pending. Incoming upstream revision not reviewed.
- Owner overlap: PDFParser._parse_page and parse documentation.
- Adapt or drop if upstream exposes equivalent native configuration; never retain
  two extraction implementations. Verify defaults, option precedence, physical
  page identity and ESG frozen-original compatibility after merge.

## Dated follow-ups

- 2026-10-19: assessment and regression recorded before implementation.
- 2026-10-19: implemented option forwarding in the existing `_parse_page` owner.
  The regression failed in four subcases before the fix; after the fix, native
  unittest passed six tests. An isolated installed-wheel run passed nine tests
  and 24 subtests, covering defaults, constructor configuration, per-call
  override, scanned detection and parser construction. ESG's contract test
  passed and verifies that extraction options equal evidence-cache identity.
- 2026-10-19: the first diagnostic wheel included six unrelated, unqualified
  identity modules from the dirty checkout. It is not a deployment artifact.
  The release candidate was rebuilt from base `f69d598466e7877a795b1bbccd35231910858558`
  plus this PDF change only, preserving the unrelated working-tree edits.
  All 435 Python files match the isolated source; compared with ESG's installed
  native package, only `semantica/parse/pdf_parser.py` differs. Release wheel
  SHA256: `9c153b032549094d15ff2b4c28a36cea691326f79df722182cdb3857ba9e5d6b`.
  Receipt: ESG `data/audits/native-text-flow-isolated-wheel-20261019.json`.
- 2026-10-19: one broader parser test invocation failed because the candidate
  environment lacks the optional BeautifulSoup dependency; no full parser-suite
  pass is claimed. A preliminary 80-case real-PDF run passed 80/80, but used the
  dirty source, so it is diagnostic only. Frozen full-corpus runs against the
  isolated PDF-only source are pending. No deployment or paid calls yet.
- 2026-10-19: subsequent isolated-source runs completed at v1 80/80 and v2
  97/104; historical red cases remain red. ESG consumer tests passed 29 and
  isolated PostgreSQL/Redis lifecycle tests passed 101 without skips. The
  PDF-only wheel above was installed into ESG's actual semantic environment;
  all 435 installed Python files were verified against the wheel. API,
  scheduler and workers were restarted at unchanged capacity, with business
  projects stopped. The first v4 run exceeded the evaluator's 900-second
  timeout; a standalone retry is pending. This is not release qualification.
- 2026-10-19: standalone v4 completed 134/151; all outcomes and actual values
  match the pre-registry baseline, with one inspected traceback line offset.
  Bounded paid Sonoco 2023 acceptance produced no new delivery: interactive
  navigation reached a security-verification stop, then candidate downloads
  returned 403 and 404. The PDF fix is deployed and tested but this run obtained
  no new original to review. It does not qualify end-to-end discovery, economics
  or continuous operation. The immutable fork revision/provisioning pin is still
  pending; the verified wheel must not be represented as a reproducible clean
  source install. Full evidence is recorded in ESG's
  `docs/audits/2026-10-19-native-pdf-release-acceptance.md`.
