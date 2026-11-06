# Certified offline reuse of paid native results after hydration repair

- Record ID: 2026-11-05-paid-native-hydration-rebind
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty checkout)
- Upstream reference: not inspected
- Related issue / PR / commits / records: source projection reader budget repair, pending

## Reason and scope

The current processing identity hashes runtime source files. A repair confined
to consuming source text can therefore change extraction and embedding recipe
identities even when the paid producers and immutable model inputs are identical.
The offline maintenance entry certifies the changed AST seams before adopting
already verified native results into the single current target recipe.

## Native capability assessment

- Existing owners: `OxigraphStore` extraction operations and receipts,
  `SQLiteVecStore` embedding operations, `ExtractionCache` accepted receipts,
  `_load_parsed_source` and `_window_native_ranges` grounding validation.
- Decision: reuse their existing read/adopt APIs; no runtime cache fallback or
  old recipe lookup was added to a build or normal query.
- Callers: only the explicit maintenance CLI; extraction and embedding handoff
  regression tests exercise current production readers after adoption.

## Approach and actual changes

- `.github/scripts/rebind_paid_native_results.py` compares immutable installed
  runtime inventories and all source bytes, permitting only specified hydration
  AST seams. Any producer change or extra runtime file fails certification.
- A mandatory dry run binds old/new runtime digests, the exact serialized build
  request and project. Apply requires the matching certificate. Parsed sources,
  extraction grounding and paid acceptance receipts must validate. Operations
  are visited with a source/project/recipe cursor of at most 128 rows and one
  native producer window at a time.
- Apply uses native acceptance, adoption and handoff release. It preserves
  original model receipts and vector values, and supports idempotent reruns.
- This does not reinterpret incompatible parsed source identities, retire old
  recipe data or mutate original materials. Cleanup and actual artifact/live
  execution belong to the integrating owner after certification.
- No model, network, dependency or paid operation was performed by this change.

## Verification and limitations

### 2026-11-05 exact entity source-span repair

- Added dedicated `--span-repair` admission, fixed to immutable source processing
  `a0eb826d…` / artifact `a4d7ba97…`. Only `extract_entities_llm` in
  `semantic_extract/methods.py` may change, with exact before/after Python AST
  hashes `07feef20…` / `6062e764…`; all other runtime files must be byte-identical.
  The repaired producer emits exact source substrings for strict entity text and
  profile evidence. Native writer validation is unchanged.
- Full adoption visits only already committed native operations. Existing strict
  receipts/readers and target writer revalidate these accepted results. No failed
  pending entity envelope is converted into a successful operation. Existing
  embeddings retain identical values, model receipts and acceptance evidence.
- Stopped-project readonly inventory found 797 current successful operations:
  first source 365 entity / 220 relation, second source 106 entity / 106 relation;
  current space holds 365 vectors. Separately, 103 pending embedding bodies all
  belong to older recipe `83bd8152…`, not the current run; they are outside this
  repair's adoption scope and remain pending obsolete-data review.
- `pytest -q tests/test_paid_native_rebind.py`: 8 passed in 1.55 seconds, including
  exact span-function certification and rejection of extra producer/inventory
  changes.
- Installed artifact `c8cd9c16…`, processing `fc062372…`: stopped-project dry run,
  apply and second apply completed successfully for 797 committed extraction
  operations and 365 native vectors. Both apply reports are identical; target
  recipe is `be48f98e…` and vector space `ef30111f…`. Native readers revalidated
  receipts and target vector values/model receipts/acceptance against their
  sources. No model calls or deletion were performed. All maintenance processes
  exited and handles closed before the integrating owner restarted the build.
  Local evidence: host `.tmp/g4-paid-span-repair-{dry,applied,idempotent}.json`.

- `.venv/bin/python -B -m pytest -q tests/test_paid_native_rebind.py tests/test_native_extraction_handoff.py tests/vector_store/test_embedding_handoff.py`:
  35 passed in 14.44 seconds, including identical vectors/receipts and producer
  branch normalization checks, after the builder-only integration fix.
- Tests reject paid producer and file inventory changes, exercise dry run,
  repeated adoption and production extraction with a provider that raises on
  every generation call. Parsed-source loading is isolated in the adoption
  fixture; live artifact certification and stopped-project dry run remain
  integration gates. Existing missing vectors are counted, never synthesized.
- No live project was changed by the implementation/test agent. Final installed
  old/new packages and exact host request must be certified by the integrator.

### 2026-11-06 native context stream and paid-input proof

- Added explicit `--context-repair-inventory` admission for the stopped c8cd
  project. Its source processing is fixed to `fc062372…`, and its original
  paid-input inventory SHA256 is fixed to
  `ddcfe805f2250f26f445e7bd2a8f6b99c240ce570f2a7ecc0263613ba678395c`.
  Certification requires exact before/after ASTs for the reviewed builder
  functions and exact bytes for the new native context query module; every
  other runtime file, including parser identity owners, stays byte identical.
- Before any adoption, immutable parsed sources are reopened with current
  canonical admission. Every successful extraction window must reproduce its
  exact text, native ranges, ordered context batch and grounding identity.
  Every embedding must reproduce its exact text-list input and canonical
  operation identity. A missing, modified or incomplete inventory fails closed.
- A pure read-only proof against c8cd installed Python/dependencies and repaired
  fork source passed for 875 entity and 707 relation operations over 875
  windows, plus 830 embedding operations/vectors. It opened no native graph or
  vector handle and made zero model calls. Host evidence:
  `.tmp/g4-paid-context-repair-equality-probe.json`. A development virtualenv
  cannot substitute for the fixed dependency environment in this proof.
- Parser processing was deliberately preserved by keeping
  `semantic_document_reader.py` and `semantic_source_artifact.py` byte identical
  to c8cd. No parsed-artifact metadata migration, identity relaxation, runtime
  fallback or additional vector space is introduced by this repair.
- Source certification, final installed target certification and stopped-project
  dry run/apply remain separate gates. The equality proof alone does not claim
  that adoption or the full ESG build has completed.
- Frozen source preflight certified exactly the two builder functions plus
  query module SHA256 `68786f79…`, giving processing `36b721dd…`. Native dry-run
  validation then revalidated 1,582 committed extraction operations and 830
  vectors/receipts with no writes or model calls. The 7,519 missing embeddings
  represent unfinished current windows and were neither synthesized nor counted
  as completed. Evidence: host `.tmp/g4-paid-context-source-preflight.json`.
- Maintenance, native extraction handoff, native embedding handoff and obsolete
  retirement regression suites: 50 passed in 20.99 seconds. Negative cases
  reject altered context functions, unrelated producers, runtime file additions,
  mutated query bytes and changed/truncated original paid inventories.
- Final installed artifact `18e96970…` passed strict installed manifest/source
  certification, paid-input proof, dry run, apply and repeated apply. Both apply
  reports are identical: 1,582 successful extraction operations and 830 vectors
  adopted, with unchanged vector values, original model receipts and acceptance
  evidence. Current recipe is `48ab6c6b…`, current vector space `e660ce5b…`.
  Host evidence: `.tmp/g4-paid-context-repair-{dry,applied,idempotent}.json`.
  All native handles closed before notifying the integrating owner to resume.
  No obsolete data was deleted; ready-build cleanup remains a separate gate.

## Upstream merge assessment

- Disposition: pending. This is an explicit maintenance operation for a reviewed
  consumption-only repair, not general permission to rebind processing changes.
- Incoming upstream revision reviewed: not yet reviewed.
- Likely conflicts: processing identity and native handoff APIs.
- Retain only while this offline certified repair is required; reject wider
  producer changes and rerun all native adoption/handoff regressions after merge.

## Dated follow-ups

- 2026-11-05: parser processing identity also hashes reader/source artifact
  files. Integrating owner implemented a builder-only traversal repair; actual
  installed old artifact versus current fork certification confirms those files
  are identical and only `semantic_publication_builder.py` changed. The certificate
  now permits only builder hydration seams. `_build_source` remains compared in
  full after normalizing the exact projection read assignment and equivalent
  text accesses; changes to its deterministic producer branch fail certification.
- 2026-11-05: combined maintenance, extraction handoff, embedding handoff,
  builder and long-context regression suite: 80 passed in 16.12 seconds. The
  helper now consumes the canonical `_source_windows` iterator and requires
  its verified vector total to equal the old native owner's exact vector
  count. A missing current address therefore fails dry-run certification,
  rather than silently discarding a paid vector. Source-level counts are
  included in the report. No apply or live data modification occurred.
- 2026-11-05: the final builder repair also partitions previously unreadable
  native producer extents. Existing valid producer addresses stay identical;
  only invalid extents split contiguously. Certification pins the exact Python
  3.12 AST before/after hashes of `_source_windows`,
  `_source_window_addresses` and `_bounded_native_source_end`; it rejects a
  changed or missing reviewed body. All other producer code remains compared.
  This is a specific reviewed repair, not a general producer exemption.
  Integrator strict reads verified all 38 sources and 8,349 resulting windows
  in 17.47 seconds, with the first source's 365 paid windows unchanged.
  Old installed versus frozen fork certification passes: target processing
  `sha256:91809b19b892fdac5ffcb7c78c7bf9e5c19d65b183207ce733a64295879e7d55`;
  only builder bytes change, to
  `42e2d86e9451103b518e40e6f2c2ef652df1aefca89ed7b51a4143a185f4bc93`.
  Reader, source artifact and parser files remain byte identical. Final
  installed-artifact dry run and any apply remain integrator-owned gates.
- 2026-11-05: installed final renamed artifact certification passes against the
  original paid runtime. Final processing is
  `sha256:a0eb826dc1bd23a00f40a7ef6203a33968b2bdec9465480eb920bdafb291a4db`.
  Only the reviewed builder repair and exact worker module-import rename differ;
  a retained obsolete module, altered producer, extra file or unrelated source
  modification fails certification. No runtime compatibility module is kept.
- 2026-11-05: explicit generation-provider changes use a separate vector-only
  target request. Extraction results are never adopted across that change.
  Embedding provider/model, material, parsed references, input revision, recipe,
  document-processing and native owner paths must remain identical. Only the
  known immutable source release can transition to a target release verified
  against its installed manifest descriptor, complete runtime Python inventory
  and source bytes. The exact releases and both serialized request digests are
  bound into the dry-run certificate and checked again before apply. Generation
  transport, generation-derived report identity and ephemeral output directory
  may change; embedding transport alone may change, preserving model identity.
- 2026-11-05: combined adoption, native handoff, builder and long-context suites
  pass 82 tests in 18.46 seconds. An additional artifact-manifest test passes
  alongside all six maintenance tests, covering tampered bytes, extra files,
  incorrect target release and an unapproved source release. Vector-only
  dry-run/apply is idempotent, retains exact vector values and original receipts,
  creates no generation extraction operations and makes zero provider calls.
  Live default-provider target preparation and apply remain integrator-owned.
