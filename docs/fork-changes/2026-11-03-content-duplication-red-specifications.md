# G0 content writer inventory and deletion specifications

- Record ID: 2026-11-03-content-duplication-red-specifications
- Date / author: 2026-11-03 / Codex
- Status: verified-in-stated-scope (inventory and failing specifications only)
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe, including current dirty source and untracked reader modules
- Upstream reference: local merge base 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0; no fetch or merge performed
- Related records: OntoScience G0–G8 plan, `deep-relationship-remediation-plan-2026-11.md`

## Reason and scope

The accepted plan removes unused DocTags, redundant reader content, fork checkpoints
and aggregate snapshots. This record freezes current writer evidence and adds two
failing specifications before implementation. Existing uncommitted implementations
are audited as current behavior; they are not exempt from deletion requirements.
No production implementation, formal profile, model, dependency, or release is changed.

## Native capability assessment

- Inspected native parsing: `parse/document_parser.py`, `parse/docling_parser.py`;
  DoclingDocument and PlainTextDocSerializer supply native content and provenance.
- Inspected fork owners/callers: `source.py::SourceDocument.__post_init__`,
  `semantic_source_artifact`, `parse/document_reader`, `semantic_document_reader`,
  `project_remote_docling`, `project_checkpoint`, `semantic_artifact_builder`,
  `semantic_worker`, `explorer/search_index`, `context/snapshot_search`.
- Merge-base comparison shows checkpoint, remote Docling, semantic artifact/source/
  worker and snapshot search modules are fork additions. The two reader modules
  are currently untracked fork additions. Parser owners predate these additions;
  invoking their serializers does not make the new stored reader copies upstream.
- Decision: tests and documentation only. G1 must prove actual native persistence,
  bounded reads, field fidelity and restart behavior before deleting/replacing carriers.
- No second implementation is introduced: tests invoke existing owners.

## Writer → storage → reader → lifetime inventory

| Category | Current writer and stored fields | Current consumer and lifetime | Required action / blocking dependency |
| --- | --- | --- | --- |
| Local Docling formats | `parse/document_parser.py:294` asks for DocTags and document; `parse/docling_parser.py:322` exports plain text, dictionary, DocTags; wrapper returns `document` and `doctags` | source → parsed source → builder uses text/Docling structure; no direct saved-DocTags consumer found in audited chain; persists in parsed JSON and checkpoint | G2 remove unused request/export/field; G1 select unique native content |
| Remote response | `project_remote_docling.py:98` requests JSON/text/DocTags; line 126 checkpoints complete remote result; line 132 returns JSON/DocTags plus text | remote completion reuse and source parsing; task/submission/result under checkpoint, no expiry in this owner | G3 remove checkpoint requirement at line 53; host task identity must support uncertain submission without duplicate conversion |
| Remote submission identity | `project_remote_docling.py:55` loads complete original bytes and keys by content hash/name/OCR/profile; lines 95/105 store submitting marker and running task ID, plus external `.remote-docling-<hash>.lock` | serializes process submissions; Serve has no idempotency key, cancellation/resume keep uncertain task state; no explicit expiry/disposition operation in this owner | G3 preserve minimal submission/task identity in existing task owner; delete complete-result checkpoint after unique parse adoption, without resubmitting uncertain tasks |
| Relay inputs and outputs | `semantic_artifact_builder.py:798` embedding key retains input payload/model/binding; non-embedding key retains business context; line 900 stores complete response and receipt | `_relay_json` restores the complete response; embedding vectors can be copied alongside request text; retained by generic checkpoint indefinitely | G3 retain vectors in native VectorStore, extraction in ExtractionCache, product outputs at final product owner; receipts use digests/identity rather than repeated request/response bodies |
| Reader projection | `source.py:45` injects `reader`; `parse/document_reader.py:75` chunks store serialized text; line 127 stores block text; `_page_parts` stores same text in page and blocks | `semantic_document_reader.py:18` writes parsed JSON plus offset/digest SQLite; `read_document_reader` returns requested chunks/page parts; no owner deletion policy | G2 replace body projection with native references/range access, preserving ordering and locators |
| Parsed content rebinding | `semantic_source_artifact.py:79` adds text; line 156 writes parsed JSON and reader index; line 241 rebuilds projection and line 249 writes entire second document | `_load_parsed_source` reads/parses complete file; source ID participates in output filename; no content reuse at binding | G2 binding adds zero parsed-content bytes; first prove native carrier and source identity separation |
| Checkpoint keys and payload | `project_checkpoint.py:464` stores full key and full payload, digest/fence; line 480 archives rejected full entries in evidence | `read` validates whole JSON and returns payload; immutable accepted results remain; archive replacement persists | G3 delete mechanism, migration/import/locks/rejections and all kinds; paid-result reuse belongs to ExtractionCache/VectorStore |
| Pipeline checkpoint kinds | builder lines 450/535/810/1030/1124/1681/2348: window-contexts, source-windows, relay, extraction-entities/relations, product-result, grounded-explanation, project-stage; parsed source adds document | same pipeline reads each stage after restart; relay can contain vectors, extraction backend carries result plus receipt; keys may contain full context | G3 field-specific replacement by existing native cache, vector and final owners; no renamed general stage archive |
| Aggregate knowledge | builder `artifact_writing` at 2562 assembles `SemanticArtifact`; line 2610 contains representations, mentions, facts, evidence, identity, communities, topics, receipts; graph/index publisher writes `semantic-graph.json`; retrieval.json contains embedding metadata | semantic query, explanation/report and graph consumers; base snapshot lineage used by rebuild; retained output directory | G4 remove aggregate and all consumers together; G1 native typed storage is a real unresolved gate |
| Search persistent index | `explorer/search_index.py:815` stores terms/postings/positions, byte/digest addresses, source associations; line 45 topology tables duplicate relation endpoints/predicates, membership and evidence links; sqlite_vec contains vectors | GraphSearchIndex queries canonical graph byte ranges, sources, positions and vector groups; immutable new index required per publication | G5 field-by-field necessity; addresses currently depend on snapshot; cannot claim graph removed merely because index stores offsets |
| Search temporary data | index reindex at 1237 stages `snapshot.sqlite`, table `values_by_field.body` holds every graph JSON record; `context/snapshot_search.py:69` stages evidence→representation and entity→name lookup SQLite | maintenance publisher/candidate iterator; TemporaryDirectory cleanup normally removes both; prepare_snapshot at 129 builds complete evidence/representations/candidates memory | G5 delete graph staging/global lookup consumers; bounded rebuild alone does not remove redundant I/O |
| Report/explanation | `semantic_worker.py:87` loads entire snapshot; lines 121/162 write evidence-explanation.json / reading-reports.json including body and receipts | worker returns path/digest; host adoption and deletion lifecycle require host-side proof; direct report invocation not established by fork source alone | G6 existing product owner stores one output; remove whole-snapshot input protocol; do not assume every reachable writer ran |

## Approach and actual changes

- Added two G0 red specifications to existing `tests/test_document_reader_index.py`:
  a real Docling text item must add zero copied body bytes to reader projection;
  a second source binding of identical text must add zero parsed-content bytes.
- Tests are ordinary failing tests, not xfail or relaxed assertions. They must turn
  green through owner fixes after G1, and may move with the current owner when old
  modules are physically removed.
- Fixed-input baseline, no models/network:
  - Docling native body 13,312 UTF-8 bytes; reader adds 39,936 bytes of exact body
    content (chunks, page text, page block text). This is three additional copies.
  - Plain source body 16,896 bytes; second source binding writes 47,033 output
    bytes, of which 33,792 are duplicated exact body content (two copies).
  - Counts are fixture measurements, not a real ESG profile savings estimate.
- Production code, requests and persistent contracts remain unchanged this stage.

## Verification and limitations

- `.venv/bin/python -m pytest -q -s tests/test_document_reader_index.py -k 'adds_no_second or adds_zero'`
  → 2 failed, 2 deselected, 1.18 seconds. Both failures reach the intended zero-copy
  assertions with the exact baseline above; no environment failure masks them.
- `.venv-audit/bin/python` and `.venv-page-progress/bin/python` are broken symlinks
  to deleted host packaged runtimes; no environments or dependencies were changed.
- Complete reader-index file: 2 passed, 2 failed (the two new red specifications).
- Existing `tests/test_document_reader_projection.py`: 4 passed, 1 failed.
  `test_native_reader_preserves_interleaved_table_order_and_unicode_spans` loses
  the expected second Unicode span after an interleaved table. This is a current
  G2 content/order defect, not a zero-copy red specification or environment failure.
- Not run: production parse/build, paid extraction, real ESG token baseline,
  formal profile inventory, packaging or product acceptance. No G0/G1 pass claimed.
- Additional required failure specifications: no checkpoint directory after
  parse/build/restart; paid result cross-process reuse; input/model/recipe cache
  invalidation; no snapshot/index body staging; exact native field persistence;
  scoped query read budgets; report atomic adoption and crash cleanup.

## No-model continuous fixture baseline

Reused existing `test_worker_processes_parse_build_and_query_share_canonical_artifact`
in `tests/test_semantic_artifact.py`; added filesystem-size observations, process
wall timings, a fresh-process keyword repeat and a fresh-process rebuild. No generic
harness was added. The source is the existing 44-byte Ada Lovelace plain-text fixture;
the deterministic recipe performs no fake paid extraction and no model extraction.
Both builds assert empty model and embedding receipts. This is not real ESG, not a
paid warm-rebuild reuse proof, and not a native knowledge-storage acceptance proof.

Command: `.venv/bin/python -m pytest -q -s tests/test_semantic_artifact.py -k worker_processes_parse_build_and_query_share_canonical_artifact`

Initial instrumentation result: 1 passed, 45 deselected, 2.85 seconds. The table
below records that initial run. Subsequently the same test gained the required
no-checkpoint/snapshot red assertion after printing its measurements, plus a
foreign-project query rejection check. Final result: 1 expected failure in
12.02 seconds, reaching only the no-checkpoint/snapshot assertion after all parse,
build, query, restart and scope checks succeeded. Four obsolete outputs are found:
semantic-graph, checkpoint manifest, project-stage and recipe-provenance.
The earlier intermediate rerun mistakenly called the raw query handler expecting
an error envelope; it raised the correct scope error directly. The test was corrected
to invoke the worker `serve` boundary, without changing production code.
Each invocation uses a new Python process; timings include startup and imports,
and are not stable performance budgets under concurrent local test execution.

| Stage | Total file bytes | Net byte delta | Process wall ms |
| --- | ---: | ---: | ---: |
| Original material | 44 | 44 | 0 |
| Parse | 13,361 | 13,317 | 191.704 |
| Build | 182,551 | 169,190 | 733.211 |
| Keyword query | 182,551 | 0 | 200.572 |
| Keyword after process restart | 182,551 | 0 | 205.193 |
| Rebuild after process restart | 182,551 | 0 | 629.238 |

Final measured files: original 44; parsed JSON 1,029; reader SQLite 12,288;
keyword index 155,648; retrieval metadata 68; semantic graph 9,903; checkpoint
manifest 2,324; project-stage checkpoint 849; recipe-provenance checkpoint 398;
checkpoint lock 0 bytes. Full per-stage file sizes print in the test output.
Net size delta is not bytes written: rewriting same-size graph/index remains I/O
and is not shown as growth. Index fixed page overhead dominates this tiny fixture;
do not extrapolate its ratio or timings to ESG. Model calls are zero only for this
deterministic/no-credential fixture; real model-cache/rebuild validation remains open.

## Existing isolation, cost and bounded-read specifications reused

No duplicate harness or checkpoint tests were added. This exact selection was run:

```sh
.venv/bin/python -m pytest -q tests/test_semantic_query_worker.py tests/test_semantic_artifact.py tests/test_project_checkpoint.py -k 'cold_keyword or records_protocol or queries_prepare or ranks_before_hydrating or filters_sources_before_limit or empty_scope or another_project or worker_process_restart_reuses or model_switch or corrupt_payload or description_contract_change or formula_requirement_change'
```

13 passed, 119 deselected in 26.74 seconds; repeated using the 12 exact test node
IDs (formula parameterization gives 13 executions): 13 passed in 12.94 seconds.
Scope and limits of this evidence:

- `test_worker_process_restart_reuses_durable_parse_and_model_calls` uses a fake
  loopback HTTP model, kills the worker after a completed entity extraction and
  resumes in a new process. It asserts exactly **one entity extraction call**,
  **zero additional calls** on the next completed build and **zero calls** after
  undeclared source-byte mutation is rejected. This proves current checkpoint
  reuse, not reuse after checkpoint deletion. It does not meter real tokens.
- `test_model_switch_preserves_generation_but_rebuilds_embedding_space` asserts
  fake chat **1**, fake embedding **2** over three provider/space configurations.
  Current policy intentionally reuses accepted generation across model changes;
  it cannot be presented as proving model-sensitive extraction invalidation.
  G3 must distinguish paid accepted-result reuse from incompatible extraction
  contracts and vector spaces explicitly.
- `test_description_contract_change_does_not_reuse_legacy_results_or_silently_buy_new_work`
  rejects incompatible extraction-contract reuse with zero additional fake calls.
  Formula enable/disable tests require new work for changed requirements and
  preserve unchanged work; corrupt digest/changed OCR is rejected explicitly.
- Foreign base project is rejected; selected source filters apply before limit;
  an empty source set returns no results. The continuous fixture additionally
  rejects a mismatched project ID at the actual query worker envelope boundary.
- Cold keyword forbids `_load_json` and index rebuild. Point-read test observes
  exactly five small header reads plus the selected entity. Ranking fixture has
  200 topics, limit 3, fewer than 25 unique hydrated records and at most 3 topics.
  These are call/record counts, not physical SQLite page reads or RSS measurements.

Additional native-cache/read selection:

```sh
.venv/bin/python -m pytest -q tests/semantic_extract/test_cache_backends.py tests/test_document_reader_index.py -k 'sensitive_params or different_params or content_identity or sqlite_persists_across_restart or stable_fingerprint or seeks_only'
```

The six exact nodes were run: **6 passed in 2.48 seconds**. Default cache rejects
changed model parameters; content-identity policy deliberately reuses models but
rejects changed project/extraction specification; persistent backend survives a
new instance and has process-stable keys. Reader fixture has 1,000 chunks and a
large unrelated text field; selected tail item reports `readBytes < 4096` and
byte-limited continuation is preserved. The budget is owner-reported selected
content bytes; it excludes SQLite page I/O and OS cache reads. It is not proof of
total process reads/allocation. None of these green tests satisfy G1 by themselves.

Disk baseline measures final file sizes after each subprocess and includes the
original source; it excludes deleted temporary files, SQLite page write counts,
system cache/bytecode outside the fixture, peak RSS and transient allocation.
The printed deterministic `modelCalls: 0` is bounded to the no-credential recipe,
empty receipts and unreachable configured loopback endpoint; it is not external
network syscall instrumentation. Actual model request counting is supplied only
by the fake relay tests above. Real ESG parse/build/query/restart counters remain
a gap, with no paid invocation authorized or performed by this audit.

## Upstream merge assessment

- Disposition: pending; no upstream merge performed.
- Incoming upstream revision reviewed: not applicable; local merge-base only.
- These specifications express the accepted content ownership contract. Adapt their
  invocation to the eventual native owner, retaining zero duplicate content checks.
- Required post-merge checks: document content/provenance fidelity, reader range
  budgets, source binding identity/isolation and repeated binding disk byte delta.

## Dated follow-ups

2026-11-03: Source inventory and two expected-red tests completed. Implementation
remains gated by G1. Existing uncommitted reader code demonstrably violates the
zero-copy contract and must be corrected rather than preserved as unrelated work.

2026-11-03, process measurement follow-up: the same continuous worker red
specification now reports per-process `/usr/bin/time -l` metrics. The measured
run reached the final forbidden-checkpoint/snapshot assertion: **1 failed,
45 deselected, 16.43s**; preceding parse/query/project-isolation/restart/rebuild
checks passed. The failure is the intended producer baseline, not G1 acceptance.

| Stage | Final fixture bytes | Worker process time | Peak process RSS |
| --- | --- | --- | --- |
| parse | 13,361 | 3,047.976 ms | 41,844,736 B |
| build | 182,551 | 1,873.436 ms | 106,889,216 B |
| query | 182,551 | 631.783 ms | 47,382,528 B |
| restart-query | 182,551 | 579.865 ms | 47,546,368 B |
| rebuild | 182,551 | 2,216.477 ms | 106,414,080 B |

These process RSS measurements supersede the earlier statement that no RSS was
measured for this fixture. They still do not measure transient files or total
write volume. OS block input/output counters were zero at every stage; cached
I/O means this is not proof of zero bytes read/written. The test remains a
44-byte synthetic no-model fixture, not a real ESG or paid-token benchmark.
