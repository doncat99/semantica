# Artifact and durable checkpoint boundary audit

- Date: 2026-10-29
- Inspected revision: 1cdd06566; local upstream ref 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
- Status: boundary audit and remote checkpoint repair implemented; verification limits below

Native owners inspected: ExtractionCache for extraction identities/codecs,
DocumentParser for parsing, GraphStore for graph storage, and ExecutionEngine for
pipeline execution. The latter has no durable remote conversion task store.
SnapshotCheckpoint already supplies atomic immutable records and cross-process
locking; reuse it rather than adding mutable state storage or weakening accepted
results. Current remote Docling overwrites one accepted key at each lifecycle
transition, so running/complete transitions fail with immutable-result conflicts.
It also stores results before checking complete document admission.

Repair plan: distinct immutable submission/task/result records, serialized submit,
validate before result acceptance; explicit offline conversion of legacy task
records, never runtime fallback or automatic resubmission of uncertain requests.
Preserve credentials isolation, cancellation/deadline recovery and no alternate
parser. Callers: native Docling parser and existing source artifact boundary.
Regressions: remote process kill/restart, partial result rejection, deadline,
credential/redirect safety, offline checkpoint conversion and source admission.
No real runtime data or model calls. Upstream merges must preserve one native
algorithm owner; the typed snapshot remains a fork contract, not upstream output.
Case capability-library-prepare / journey-library, delta keep, unchanged gates
and baseline. Focused tests do not establish packaged ESG acceptance.

## Retained boundaries and native alternatives

| Files | Actual responsibility and reason to retain |
| --- | --- |
| semantic_artifact_schema.py | Fork-specific immutable interchange and persisted observation contract: qualified facts, evidence locators, closed references, lineage, manifests and receipts. This snapshot is not an upstream-native output. Schema admission does not perform extraction, ranking, entity resolution or graph inference. Consumers include builder, GraphStore, ContextRetriever, worker/query and the host. |
| semantic_source_artifact.py | Content identity and verified parsed-source serialization/rebinding; parsing delegates through source.parse_source to DocumentParser. Explicit v1-to-v2 migration remains offline; no second parser. |
| project_checkpoint.py | Durable accepted results, rejections, receipts, atomic installation and physical removal of superseded datasets. ExtractionCache supplies extraction identity, not this immutable lifecycle; ExecutionEngine resume is in-memory. |
| project_checkpoint_upgrade.py | Explicit verified conversion of historical paid results without parsing or model calls. Retained until historical migration is complete; runtime rejects unsupported identities rather than guessing or recomputing. |
| project_remote_docling.py | Serve transport and durable task recovery under DoclingParser. Native pipeline has no durable remote-task store. Reuses SnapshotCheckpoint atomic immutable writes and directory lock. |
| semantic_query_schema.py / semantic_query_worker.py | Validated query DTOs and JSONL dispatch. Candidate construction, filtering, ranking and evidence expansion now belong to ContextRetriever. Existing limit of 1000 remains; no true pagination claim. |
| semantic_artifact_errors.py / semantic_worker_context.py | Typed failure and request authorization context; neither decides domain results nor contributes credentials to content identity. |
| project_document_quality.py | Genuine fork extension identifying formula, unmapped-character and fragmented-CJK parsing issues. Located quality observations, not a second OCR or semantic engine; not described as upstream original. |
| project_office.py | Genuine optional binary Office/WordPerfect integration via verified LibreOffice and flatODF mapping, now reached through DocumentParser. Missing runtime fails explicitly; no alternate PDF path. |
| semantic_worker.py | Request admission, target/evidence scope and artifact packaging, including reading-report passage/target assembly and delegation to builder report validation. It is not pure transport or upstream-native code; no separate report-scoring algorithm found in this audit. Concurrent reading-report changes excluded. |

Other alternatives inspected: ProvenanceStorage stores PROV lineage/events,
VersionStorage stores graph versions/tags, and the truth-maintenance checkpoint
codec restores reasoning catalogs. None owns durable paid extraction/conversion
results, rejection evidence and transactional dataset installation. Retaining
these boundaries is based on those concrete differences, not filenames or a
target deletion ratio. Items 1–5 remove or delegate duplicated domain decisions;
moving code between modules alone is not counted as eliminating an algorithm.

## Remote task repair

Submission, task identity and admitted result have separate immutable kinds.
Submission is serialized across callers; a submission without a recorded task
means unknown outcome and stops, never automatically resubmits. An orphan result
also stops. Deadline/cancellation is checked before creating a submission marker.
Only a successful full JSON/text/DocTags document becomes an accepted result;
replays are validated again. Concurrent callers may poll the same known task,
but cannot create a second conversion. Remote cancellation remains unsupported.

The runtime rejects the exact historical remote-docling kind. Explicit offline
conversion verifies fence, digest and key locator, converts known phases, and
validates complete results before installation. Rejected legacy task states
require reconciliation. Conversion does not mutate its input or call a provider;
installed datasets survive restart with their original task/result identity.
No new mutable task database, fallback parser or credentials persistence.

## Verification

- Red specifications: legacy task conversion/restart and invalid legacy result
  admission failed before the repair; four specifications now pass.
- Latest focused run: 99 passed across remote tasks, checkpoint upgrade,
  preflight, source/native routing, reduction boundaries and PDF ownership.
  Covers process kill/restart, deadline, uncertain submission, partial results,
  four simultaneous callers with exactly one submit, redirects and auth safety.
- Broader minimal-runtime selection: 112 passed, 9 failed. The nine existing
  migration/compatibility specifications expect retained whole legacy datasets
  or obsolete identity/runtime-import behavior; HEAD comparisons in earlier
  items reproduced them. No duplicate archive or runtime guessing restored.
- Full Docling conversion is blocked by local Docling/dependency incompatibility;
  transport tests use a controlled local server. No live model calls, real
  dataset migration, immutable release artifact, host pin update or packaged ESG
  acceptance was performed for this change.
