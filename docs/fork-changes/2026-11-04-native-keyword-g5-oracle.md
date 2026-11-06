# Native keyword G5 occurrence and publication oracle

- Record ID: 2026-11-04-native-keyword-g5-oracle
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe; preexisting dirty main
- Upstream reference: not inspected
- Related issue / PR / commits / records: native G5 migration; pending

## Reason and scope

The prior keyword owner regression checked five occurrences. It did not establish
complete results above 1000, three-page navigation, deep continuation after reopen,
or two successive add/change/withdraw publications. Extend the existing tests;
no production owner, dependency, schema, baseline or release pin changes.

## Native capability assessment

- Owner: `GraphSearchIndex.publish_native_positions`, `open_native_positions` and
  `search_native_positions` in `semantica/explorer/search_index.py`.
- Consumers inspected: `semantic_query.query_semantic_artifact`,
  `SemanticQueryRequest`, `_publish_native_indexes`, existing keyword/document
  reader/query tests and installed acceptance consumer.
- Decision: reuse as-is. The tested capability already works; no source fix needed.
- Tests change in `tests/test_native_keyword_owner.py` and
  `tests/test_native_vector_incremental_builder.py`. Native range hydration uses
  the existing `read_document_reader`, not another body reader.

## Approach and actual changes

- Exact independent content oracle: 1440 occurrences across three native PDF-text
  page scalars, 39 forward pages, backward traversal, explicit page navigation,
  and direct resume at offset 1110 after closing/reopening the owner. A foreign
  source containing 2000 occurrences must not enter the authorized result set.
- Hydrate every selected range and compare its original mixed-case Unicode-aware
  content and page coordinates. Assert every measured lexical query is <3000ms.
- Three publications perform two add/change/withdraw transitions; check new/old
  terms, withdrawn membership, old publication descriptor rejection, withdrawn
  cursor rejection and unchanged original reader/index byte+filesystem identity.
- No model calls/network, no new runtime dependencies or formal data.

## Verification and limitations

- Source keyword selection: 4 passed in 1.02s; 1440 hits, 39 pages, 81 queries,
  max query 3.36ms, aggregate selected-range physical reads 5902560 bytes.
- Both new functions also passed with isolated installed bundle interpreter
  `2e9a2f8d4c5b1dda9a588bb758a51db02c14c49269033ca2c0fd49688492a47a`,
  checking imported owners reside under `bundle/python/`. The test-only tests
  namespace was provided explicitly; pytest was imported from the existing
  source venv after installed owner import. No source package root on sys.path.
  Installed max query: 3.27ms; same occurrence/pages/query/read-byte counts.
- This is reopen evidence, not OS process-restart/cold-I/O/physical-scan proof.
  It does not test vector incremental publication, RSS/cache budgets or storage
  write interception. Range reads are bounded individually; the stated aggregate
  includes repeated selected-segment reads, not whole-dataset query loading.
- A bare four-field position has no generation. Old descriptor/generation is
  rejected and missing addresses are rejected; reusing an address that exists in
  a different generation is not rejected by this lower-level owner. Host cursor
  generation binding remains a separate acceptance requirement.
- Initial test runs failed on test construction (unvalidated range dict and Path
  input, then missing explicit range byte budget), not a native product defect.
  No native red-to-green product repair is claimed.

## Upstream merge assessment

- Disposition: keep the oracle while literal scalar positions remain canonical.
- Incoming upstream revision: not reviewed.
- Likely overlap: native lexical owner, reader range schema, test fixture helpers.
- Adapt if that single owner changes; do not retain a compatibility implementation.
- Required checks: keyword, native reader/query and isolated installed oracle.

## Dated follow-ups

- 2026-11-04: expanded source regression and isolated installed proof as above;
  overall G5 and immutable release qualification remain open.
- 2026-11-04: final rerun after asserting old changed terms disappear:
  `python -m pytest -q -s tests/test_native_keyword_owner.py
  tests/test_native_document_reader.py tests/test_native_query.py`: 26 passed
  in 5.04s, max lexical query 4.74ms. Both final test functions passed against
  the same isolated installed artifact, max query 3.22ms. Three generations,
  two changes/withdrawals and zero unchanged-reader rewrites verified.
- 2026-11-04: extended the same oracle with two sequential isolated Python
  processes (`-I -B`), each opening the existing publication and querying offset
  0 then 1110. No fixture build occurs in either child. PIDs differ; the first
  process exits before the second starts. Each result matches the parent oracle.
  Request timing includes lexical retrieval plus bounded original-range hydration
  and must be <3000ms; heavy imports and open costs are reported separately.
  Source owner: 26 passed in 3.39s; child imports 113.51/114.01ms, open
  0.59/0.51ms, process wall 165.45/163.84ms. Four request times were
  4.18/3.16/4.77/3.32ms; peak RSS 40042496 bytes.
  Installed owner: both fresh processes imported exclusively from the current
  `2e9a...` bundle, imports 366.92/354.99ms, open 0.50/0.46ms, process wall
  475.87/446.99ms. Request times were 3.48/3.26/3.34/3.09ms; peak RSS
  59244544 bytes; request RSS high-water growth at most 229376 bytes.
  Each request made 37 measured native-content Python stream reads, each exactly
  4099 requested/returned bytes (151663 total); offset 16528 for first page,
  57560 for deep page. The instrumented sum equals reader `readBytes`; no
  full-source read is requested. This probes the canonical source file stream
  at its fd-backed buffered read boundary, not kernel syscalls or disk sectors.
  SQLite C/native physical I/O remains unmeasured; ru_inblock was zero in these
  requests, which is not proof of zero native reads. OS caches were not dropped.
  No new source, artifact, paid model, dependency or production data changes.
- 2026-11-04: added a separate current-builder vector incremental oracle. It
  invokes the current `build_semantic_artifacts` builder through the existing
  producer fixture for three ready publications. Both transitions replace one
  material revision, add one source and withdraw the previous added source;
  unchanged source-1 retains its accepted parsed input reference. The builder's
  current `_publish_native_indexes` / `SQLiteVecStore.publish_native_ranges`
  chain is exercised; the retired vector publication route is not used.
  Source focused selection (new oracle, native producer publication, native
  vector owner audit, embedding handoff): 19 passed in 3.41s. The new oracle
  also passed with isolated installed builder imported from the same `2e9a...`
  bundle (`sha256:e2afa291bd1181767def94d7121a699982686b17d729aa5b3bc6dd5b8dead612`).
  Each transition records two INSERTs into vector bodies, two INSERTs into
  accepted-operation records and 20 generation/address statements. SQL trace,
  byte-for-byte rows and complete accepted-operation snapshots jointly assert
  zero unchanged-body/operation writes. The unchanged canonical JSON and native
  reader retain their path, filesystem identity and digest. Active native links
  contain only current sources and the new generation. The embedding relay and
  adoption spies assert source-1 is never called again; only changed/added
  sources call the local embedding fixture each round.
  Generation/address link replacement is intentionally distinguished from
  vector body writes. This is real current-owner publication with deterministic
  local model/embedding transport, not a paid live-model or formal-data run.
  Test setup initially reparsed the unchanged input and rewrote identical JSON;
  that fixture write was removed by reusing its accepted parse reference. A
  single-slot organization-product fixture is reset for changed input identity.
  These setup failures are not production regressions or product fixes.
