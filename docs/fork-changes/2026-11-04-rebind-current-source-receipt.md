# Keep rebound source receipt identical to parse receipt

- Record ID: 2026-11-04-rebind-current-source-receipt
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe with dirty remediation changes
- Upstream reference: not inspected
- Related records: native-source-builder-cutover and native-source-admission-header
  (2026-11-04)

## Reason and native capability assessment

The actual host cross-repository parse/rebind test failed host strict identity
validation after parse succeeded. Native reader metadata had gained private
source-map counts and document MIME/page fields. bind_parsed_source_artifact
spread that internal header into the public sourceHeader receipt. Quality
needs_review metadata also leaked private issueCodes. parse_source_artifact's
explicit receipt remained correct. Inspected both producers, reader header
creation and host worker.ts strict bounded receipt allowlist; repair the existing
producer, without widening host validation or changing the stored reader schema.

## Approach and actual changes

Both parse and bind now share _source_header_receipt in
semantic_source_artifact.py. It projects only the current public receipt fields
and quality version/status/issueCount. SourceId is the requested binding while
material/profile/processing/representation identity remains unchanged. Private
native reader fields remain available only through the native reader header.
No compatibility reader, fallback, extra content copy, model/network/dependency
change, migration or host change is introduced.

## Verification and limitations

- Exact receipt keys and full parse/rebind equality (except requested sourceId)
  were added to test_document_reader_index.py with ordinary and needs_review
  quality. Both cases failed before repair due leaked private keys/issueCodes.
- Source reader index, office adapter rebind, cold lightweight-worker imports,
  native source header and real RSS admission suites: 28 passed in 7.19s.
- Actual OntoScience daemon cross-repository reader test with explicit canonical
  fork Python/PYTHONPATH: 2 passed, 1.58s command duration. It verifies strict
  host parse/rebind, zero-copy installation reuse and exact Unicode ranges.
  Focused diff whitespace check passed.
- These are focused evidence, not G4 completion or release qualification.

## Upstream merge assessment

Pending; incoming revision not reviewed. Preserve one public source receipt
projection when adapting reader metadata. Recheck strict host parse/rebind,
quality metadata, zero-copy identity and native document reader regressions.
