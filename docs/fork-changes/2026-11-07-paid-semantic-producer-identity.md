# Bind paid extraction and classification to their actual semantic producers

- Record ID: 2026-11-07-paid-semantic-producer-identity
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 765c0ef2d1e868e074ca31068e9db90a0672a9c2
- Upstream reference: not inspected; local fork repair
- Related records: 2026-11-07-stable-embedding-operation-identity; offline migration changes are coordinated separately

## Reason and scope

The native builder used the complete `PROJECT_PROCESSING_DIGEST` and the whole
publication `RecipeRef.lineage_payload()` as paid extraction/classification
recipe inputs. Thus native query, publication index and receipt-accounting
repairs changed paid identities even when the prompt, evidence and model had not
changed. Offline re-adoption then created another operation's owned RDF facts.
The full project digest remains useful publication provenance; it is not a paid
computation recipe.

This change separates computation identity without adding another extractor,
classifier, cache, compatibility reader or model path. It does not migrate or
remove active user data, build frozen artifacts, run ESG acceptance, or establish
that G4 or release acceptance has passed.

## Native capability assessment

- Existing owners inspected: `semantic_publication_builder._extract_project_sources`,
  `_classify_source_batch`, `_product_json`, `_ProjectModelProvider`,
  `semantic_extract.grounded_window`, native LLM methods/schema/grounding helpers,
  `triplet_store.classification_records.ClassificationRecords`, inherited
  `ExtractionRecords.commit/receipt`, and OxigraphStore wrappers.
- Actual paid classification is `_classify_source_batch` cache miss ->
  `_product_json(relay, 'source_classification', ...)`; it has the same broad-hash
  defect as extraction and therefore is included.
- Decision: repair the current native owner and share the exact recipe helpers
  with explicit offline migration. No old executable contract is supported by
  normal reads.

## Approach and actual changes

- `semantic_extraction_recipe.py` positively enumerates the actual prompt,
  schema, grounding, typed-output validation, generation payload and bounded
  context producer callable closure. It hashes callable source plus Pydantic and
  Pydantic-core versions. It does not hash native cache-read, store, publication,
  query, embedding, or unrelated classification functions for extraction.
- Extraction binds admitted generation binding/model/context/output capacity and
  extraction specification. Source revisions, parser, exact text window, scalar
  ranges and hydrated grounding values remain independently bound by the native
  operation. Publication/classification profile fields and embedding settings do
  not alter extraction identity.
- Classification has its own closure, actual instruction, generation parameters,
  output/citation schemas and conversion. Exact profile and evidence context
  remain native operation inputs; classification read/reduction code does not
  redefine paid generation.
- `grounded_window` moves the two existing paid invocation argument lists into
  private producer functions. The native restore/accept/adopt orchestrator still
  owns the same path and delegates to these functions only on a cache miss.
- Builder dispatch calls `_extraction_recipe(request)`. Classification dispatch
  calls `_classification_recipe(relay)` and delegates the existing cache-miss
  body to `_produce_source_classification` without changing prompt semantics.
- `ClassificationRecords` gains a single logical-to-physical native index.
  `OxigraphStore.rebind_classification(previous, current)` is an explicit offline
  migration that permits only recipe changes. It verifies the full old binding
  and receipt, preserves paid assignments/receipt nodes and original `paidRecipe`,
  and atomically changes recipe metadata/digest/index. Runtime operation IDs
  resolve physical ownership so durable paid cache keys remain stable. Normal
  reads never fall back to unindexed historical data; normal adoption rejects it.
- Existing scheduling fixture now supplies its actual model ID, required by the
  recipe contract. New recipe and native classification regression specs cover
  the repaired identities.
- Model/network/dependency cost: no new dependency, model call or network action.
  Source inspection is cached in bounded LRU entries; native artifacts must keep
  producer source, as the pre-existing full processing digest already requires.

## Verification and limitations

- Before source changes, extraction specs: 13 failed / 7 passed (missing narrow
  recipe helper). After classification specs were added: 6 failed / 20 passed.
  The complete recipe file is now 26 passed.
- Before native classification index/rebind: 2 failed / 8 passed. After source
  changes: 10 passed, including restart, stable physical operation and exact
  source-context rejection.
- Extraction caller selection passed 104 tests: recipe, typed output owner,
  native extraction handoff, semantic native extraction, window-reference
  handoff, long context, structured grounding, and semantic scheduling.
- The historical `test_grounded_window.py` regression was aligned with the
  existing bounded owner: durable receipts contain `rejected_count == 2` and no
  candidate body array; its assertion still verifies both exact rejected
  candidates on the transient provider. The coordinated owner fix resolved the
  initial inherited classification-index failure.
- Transport/audit isolation red specification: 4 failed / 26 passed. The pure
  `_validate_generation_model` and `_generation_content` functions preserve model
  admission and response acceptance semantics; the transport wrapper and usage
  receipt accounting do not participate in paid computation identity.
- Final focused union: 153 passed in 20.78 seconds across recipe, grounded
  window, classification records, reduction boundaries, typed output, native
  extraction/window-reference handoff, long context, structured grounding and
  scheduling. `git diff --check` passed. This is focused source evidence, not
  whole-repository or real ESG acceptance.
- Callable bodies are deliberately complete, not AST exclusions. An edit inside
  an actual semantic producer (including a conservative nonsemantic edit in that
  callable) may change its identity. Pure cache/store/read module changes do not.
- Positive dependency closure is a review obligation when a semantic producer
  acquires a new dependency. Missing callable source fails explicitly; there is
  no fallback identity or manually bumped cache version.
- Live 47-classification migration, paid reuse receipts, obsolete generation
  retirement, artifact rebuild and real ESG acceptance remain separate pending
  evidence. Source tests do not certify those operations.

## Upstream merge assessment

- Disposition: keep; fixes fork-native paid identity and ownership.
- Incoming upstream revision reviewed: none.
- Likely overlap: grounded extractor invocation, LLM methods/schema/provider,
  publication builder dispatch and native classification persistence.
- After merge, audit the positive producer dependency closure and rerun recipe,
  extraction/classification handoff, restart and explicit migration regressions.

## Dated follow-ups

- 2026-11-07: Native classification recipe/index added after confirming this is a
  paid producer; omitting it would leave the same broad-digest defect unresolved.
- 2026-11-07 independent identity audit: native receipt proofs now bind the logical
  identity as well as the physical operation, check the acquired index link before
  cache hits, reject stale acquired handles with `ExtractionIdentityStaleError`,
  and reject orphan index references instead of reporting unpaid misses. Explicit
  extraction/classification rebind fully verifies the source receipt without
  trusting a cached proof. Offline retirement includes exact logical-index subjects
  in its certified deletion closure and protects other operations' links, including
  partial-deletion resumes. It reads the native stage rather than recomputing a
  physical ID from a migrated recipe. Vector retirement already deletes the entire
  certified SQLite owner, including its metadata index. Focused extraction,
  classification, publication and retirement run: 83 passed plus one invalid new
  publication fixture (missing required fact coverage); the fixture was completed
  without weakening the gate. Targeted old-publication/rebound-retirement/native
  extraction-recovery/embedding-builder selection then passed 31 tests in 28.42s.
  Existing publication entity reads remain identical after metadata rebind and
  process restart. No active user database or model endpoint was accessed.

- 2026-11-07: Removed unreachable generic chunking, ungrounded relation parsing
  and generic context-batching helpers from the native extraction recipe closure.
  Removed unused manual `EXTRACTION_CONTRACT_VERSION`; no identity uses it.
