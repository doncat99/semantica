# One parsed-document carrier

- Record ID: 2026-10-29-parsed-source-single-carrier
- Date / author: 2026-10-29 / Codex
- Status: planned
- Fork base revision: d0f7088490bca5b782d16549b3b00e45d97925b3
- Upstream reference: 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0 (fixed comparison baseline, not a claim about latest upstream)
- Related records: 2026-10-29-native-owner-consolidation

## Reason and scope

Knowledge artifacts embed full parsed documents and serialize another representation
file despite an already admitted parsed-source object. Remove these duplicate
carriers within OntoScience's fork chain. Other projects and databases are excluded.

## Native capability assessment

- Parser owner: semantic_source_artifact.parse_source_artifact and _load_parsed_source.
  These already persist and verify the v2 envelope, content revision and digest.
- Callers: semantic_artifact_builder source_projection; semantic_worker.handle_request;
  OntoScience parsed-source.ts, worker.ts and build.ts. Grounded-source callers inspected.
- Decision: reuse the existing parsed-source owner. Keep in-memory document access
  for extraction, location and evidence. Knowledge metadata carries format and refs only.
- EntityResolver, GraphBuilder, CommunityDetector, CommunitySummarizer,
  TemporalVersionManager and VectorRetriever remain the existing decision owners.
  Fork-added protocol/qualified-fact extensions are not described as upstream code.

## Approach and actual changes

- Planned: return admitted parsed-source path/digest instead of representation serialization;
  remove metadata.document; preserve recipe digest and business-content reuse semantics.
- Consumer impact: worker admission and publication must verify/reuse the same envelope.
  Historical carriers require explicit offline migration before runtime admission.
- No additional model, network or dependency work is introduced by this consolidation.
- Unrelated contextual-identity and report-scope drafts are excluded from this change.

## Verification and limitations

- Regression: tests/test_parsed_source_single_carrier.py; red/green evidence pending.
- Publication, installed-artifact tests and real ESG acceptance pending.

## Upstream merge assessment

- Disposition: keep necessary artifact reference translation; pending upstream review.
- Incoming revision: not reviewed beyond the fixed baseline.
- Overlap: native parsing, semantic artifact builder and worker protocol.
- Retain only while the product requires the portable protocol; remove duplicate
  adapters if upstream adopts equivalent artifact references.
- Re-run parser ownership, immutable-input, incremental reuse and consumer admission tests.
