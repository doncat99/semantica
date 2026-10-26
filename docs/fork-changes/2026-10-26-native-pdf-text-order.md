# Native PDF text order in the existing processing profile

Status: implemented and tested locally; not installed into the managed runtime.

## Reason and inspected owner

Inspected main at 5bbf5516, including existing uncommitted profile/source changes.
`source.parse_source` hardcoded coordinate sorting even though native
`parse.pdf_parser.PDFParser` already accepts `sort`. Interleaved double-column
coordinates can split continuous source sentences, breaking truthful quote
validation. A caller could not select the existing reader's content order through
`DocumentProcessingProfile`.

## Approach and boundaries

Expose `pdfTextOrder` (`coordinates` or `content`) in the existing strict profile;
delegate it to the existing PDFParser `sort` option. Preserve the default and
Docling local/remote behavior. No second parser, OCR, quote rewriting, company
exception or model invocation. Consumers selecting a different order must publish
an explicit processingRevision and use its separate representation cache.

Affected: semantic_artifact_schema.DocumentProcessingProfile, source.parse_source,
tests/test_native_grounded_source.py; ESG's existing PDF profile consumer.

## Regression and upstream merge

The existing native owner test covers both orders and prohibits a Docling call.
Reader-ownership and relevant parsed-source tests must also pass. Real-document
acceptance is tracked by the ESG consumer, not asserted by the unit test.
Upstream assessment: keep until upstream exposes the same native reader setting;
then adapt to its field and remove this extension rather than keeping two options.
No existing artifacts are deleted or silently reinterpreted.

## Verified consumer result

Both native PDF profile orders pass the existing owner regression (2 cases).
ESG's profile/configuration and historical recovery tests pass (47 cases).
For the unchanged 25-page ADM 2023 original, the consumer selected content order
with an explicit processing revision and replayed the previously recorded model
assessment. Existing quote validation succeeded without a new model call.
Object checksum, current matched Review, native readback and accepted target
binding were independently checked. This does not establish content order as a
better default for every PDF; production retains coordinate order.
