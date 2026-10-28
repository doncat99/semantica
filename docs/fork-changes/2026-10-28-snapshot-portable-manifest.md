# Portable immutable snapshot manifest

- Record ID: 2026-10-28-snapshot-portable-manifest
- Date / author: 2026-10-28 / Codex
- Status: implemented; focused regression passed, packaged integration pending
- Fork base revision: a6900100d25b51990cbebee1b28b7fafc9f7b7b9
- Upstream reference: not inspected
- Related issue / PR / commits / records: repeated OntoScience snapshot adoption

## Reason and scope

Identical input snapshots differed only in 39 artifact_manifest.artifact_ref
absolute build paths. The host correctly rejected different bytes under the
same immutable snapshot identity. Use digest-addressed internal manifest refs;
the worker's transport manifest continues carrying actual artifact paths.

## Native capability assessment

- Owner: semantic_artifact_builder.py::build_semantic_artifacts manifest writing.
- Consumers inspected: semantic_worker.py exports actual artifact paths;
  semantic_artifact_schema.py validates reference IDs and hashes;
  context/context_retriever.py uses artifact reference IDs, not local paths.
- Decision: repair serialized native manifest, no host collision bypass.
- Regression: same source and input revision in two output directories must
  produce the same semantic graph digest.

## Approach and actual changes

- Planned: replace per-run artifact_ref paths with existing artifact digests.
- Transport paths and stored historical snapshots remain unchanged. No model,
  network or dependency changes; no identity validation weakening.

Representation and retrieval manifests now store their existing artifact digest
as artifact_ref. The worker transport manifest still exports actual local paths.
The repeat-build regression resumes the same logical checkpoint in a different
output directory, preserving the legitimate checkpoint creation timestamp, and
asserts identical semantic graph digests. The original regression went red before
the native fix; unrelated build timestamps are not treated as portable content.

## Verification and limitations

- Repeat-build regression passed as part of the 69-test native selection;
  another 126 contract/query/worker/community tests passed. Isolated installed
  artifact build/query and inventory acceptance passed for development artifact
  `sha256:0bf5f8af85e456b4f8b374351fc40db920ecba8d74a1da148b60a5ae071e95ef`.
  Historical polluted snapshots are not rewritten; fresh adoption needs the
  consumer's normal rebuild flow.

## Upstream merge assessment

- Pending incoming upstream inspection; retain portable content identity.
- Re-run native artifact/worker/query and repeat-build regressions after merge.

## Dated follow-ups

- 2026-10-28: record started before implementation.
- 2026-10-28: inspected current fork main `9bb3ad16ea62`. Portable manifest
  references alone cannot adopt a corrected publication over an existing
  immutable input-only snapshot. Native `build_semantic_artifacts` now derives
  publication identity from inputRevision, producer artifactDigest, schemaDigest
  and the portable-manifest format. ExtractionCache and paid checkpoint identity
  remain business-content scoped. Historical snapshots are not modified and the
  host collision check remains strict. A regression first reproduced identical
  IDs across producer changes, then verified distinct IDs, preserved entities
  and receipts, and equal graph digests across relocated output directories with
  the same logical checkpoint. Native artifact, admission, long-context,
  grounding, worker diagnostic and PDF ownership selection: 92 passed, one known
  baseline retry-count assertion deselected. Published-artifact and real ESG
  repeat-build acceptance remain pending.
