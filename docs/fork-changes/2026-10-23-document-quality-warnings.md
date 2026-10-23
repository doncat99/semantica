# Local transcription defects must not abort a project

- Date: 2026-10-23
- Status: verified-in-stated-scope
- Fork base revision: 3a2a9e5c1c4a92bd8242bfa0206cd937055d9020
- Upstream reference: not inspected

## Reason and scope

ESG project builds aborted because a few PDF lines carried encoding defects.
The user explicitly requires readable content and other reports to continue.
Quality review is a warning about transcription coverage, not an artifact integrity failure.

## Native capability assessment

Inspected `semantic_source_artifact._admit_document_quality`, its parse/cache/bind/load
callers, `project_document_quality.assess_document_quality`, `source.SourceDocument`,
`semantic_artifact_builder._build_source` and `tests/test_project_document_quality.py`
at the revision above. Native representations already persist the complete document,
including quality status and located issues. Repair this native owner; no second parser
or pipeline is introduced.

## Approach and actual changes

Retain located quality findings without throwing for `needs_review`, including after OCR.
Immutable-byte, artifact-digest, processing-profile and representation checks remain hard errors.
Original parsed text and issue locations are retained; missing characters are never invented.
No new dependencies or model calls. Consumer must display coverage warnings and must not
interpret task completion as proof of perfect transcription.

## Verification and limitations

Red spec: two cases failed before the change. `pytest tests/test_project_document_quality.py
tests/test_semantic_artifact.py tests/test_semantic_artifact_contract.py -q`: 85 passed.
Cache/load preserves warning metadata; artifact tampering remains rejected. Local test
environment required the declared optional OpenAI dependency; no live model calls made.
Native release and packaged consumer real-project replay remain pending. Completely unusable sources
remain a separate parser error; this correction concerns readable documents with local defects.

## Upstream merge assessment

Pending upstream review. Retain until upstream supports nonfatal located quality findings.
Recheck parse/cache/bind/load and immutable artifact integrity regressions after merging.
