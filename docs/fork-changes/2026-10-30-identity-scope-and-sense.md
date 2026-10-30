# 2026-10-30 — Identity scope and sense

## Reason and native ownership

Inspection baseline: main at d0f7088490bca5b782d16549b3b00e45d97925b3 (working tree contains earlier contextual-identity changes).
Native owner: normalize/entity_normalizer.py::EntityDisambiguator, called by
deduplication/DuplicateDetector and kg/EntityResolver(strategy="contextual").
semantic_artifact_builder::_build_source supplies located mentions and identity profiles;
semantic_extract/schemas.py and methods.py own the existing extraction contract/prompt.
No parallel disambiguator, model decision path or runtime checkout dependency is added.

Broad offline review exposed cross-company Board/Company/Foundation merges, SIG
incorrectly linked to NYSE by parentheses, and fragmented same-name concepts.
Plan: encode owner-level regressions first, repair the existing owner and profile
grounding, version processing caches, run affected tests and real-corpus replay.
Do not delete product data or rebuild summaries until quality is assessed.

## Validation / limits

Implementation and verification pending. A deterministic linker cannot establish
arbitrary semantic equivalence between conflicting descriptions. Such cases must
remain explicit unknowns, not fabricated successful decisions.
Upstream assessment: pending; preserve native ownership on future merges.

## 2026-10-30 implementation and verification follow-up

- Record ID: 2026-10-30-identity-scope-and-sense
- Date / author: 2026-10-30 / Codex
- Status: verified-in-stated-scope (focused regressions and offline replay only)
- Fork base revision: d0f7088490bca5b782d16549b3b00e45d97925b3
- Upstream reference: not inspected this turn; merge assessment pending
- Related records: 2026-10-29-contextual-identity.md; publication pending

### Approach and actual changes

- Repaired `EntityDisambiguator` in `semantica/normalize/entity_normalizer.py`.
  Grounded same-name concepts can link without a bracket definition. Precise
  same-occurrence evidence precedes noisy type labels. Conflicting grounded
  descriptions remain unknown, and description-less mentions cannot bridge them.
  Per-run description indexes reset with the existing definition indexes.
- Owner-dependent bodies, roles and policies require matching grounded owners
  across sources. The existing owner recognizes unqualified organizational noun
  phrases when no profile is available; explicit profile classification wins.
  This includes type-noisy CEO and Code of Conduct examples found during replay.
- Bracket expansions require abbreviation letters in the order of full-name
  initials; NYSE (SIG) is not an identity definition. This is a conservative
  literal check, not a general abbreviation inference algorithm.
- `semantic_extract/schemas.py::IdentityProfileOut` and the existing prompt in
  `semantic_extract/methods.py` carry referent kind and a source-quoted owner.
  The existing extraction, window assembly and `_build_source` path retains
  these fields and validates owner support. No extra LLM operation was added.
- `semantic_artifact_builder.py` advances the extraction contract to
  `grounded-identity-profile-v2` and project processing to
  `project-contextual-identity-v6`. Single-source completed results now carry a
  processing-version key. A source extraction contract marker rejects old or
  incompatible checkpoint work before new paid extraction. Processing-only
  changes reuse compatible raw extraction to recompute native identities.
- Tests: new `tests/kg/test_identity_scope_and_sense.py`, extended wire-contract,
  source retry, profile projection and existing identity integration tests.
  Updated concept expectations deliberately: same grounded concept can span
  sources while undeclared person identity remains separate.
- No second disambiguator, registry, dependency, fallback or model call path.
  No product data deletion, graph adoption, Summary generation or deployment.
  Old extraction lacking the new profiles is not a substitute for fresh extraction.

### Verification and limitations

- New scope/sense regressions reproduced defects before fixes; an additional
  three red cases caught local roles/policies after the first concept-link change.
  Source completed-result contract mismatch also reproduced red before repair.
- `.venv/bin/python -m pytest -q tests/kg/test_identity_scope_and_sense.py
  tests/kg/test_contextual_identity.py tests/deduplication/test_native_resolution_veto.py
  tests/normalize/test_entity_normalizer.py
  tests/semantic_extract/test_grounded_llm_extraction.py
  tests/semantic_extract/test_grounded_wire_contract.py tests/test_project_identity.py
  tests/test_project_stages.py tests/test_semantic_artifact.py
  tests/test_native_grounded_source.py tests/test_project_checkpoint.py
  tests/test_project_local_reuse.py tests/test_kernel_owner_regressions.py`:
  **297 passed**, 8 dependency warnings, 107.08 seconds.
- `git diff --check`: passed.
- Read-only private corpus replay through `_build_source` and
  `_resolve_native_entities`: all 36,082 mentions retained exactly once;
  21,765 baseline entities -> 17,514 entities; network calls blocked, zero calls.
  Native identity took 80.661 seconds, separate grounding 25.454 seconds.
  Cross-source unowned Board/Company/Foundation/CEO/policy groups split;
  Scope 1/2/3 repeated mentions each form one concept group. SIG separated
  from NYSE. Tracked TriStar/TCFD/TNFD/Home Depot do not cross-merge.
- Replay uses saved raw names, types, attributes and locations, not previous
  merged aliases/IDs. It does not include new profile extraction or test an
  adopted runtime. Private evidence stays in the host's ignored audit directory:
  `.tmp/snapshot-audit/entity-resolution-scope-sense-verification-20261030.md`.
- Counts are not semantic acceptance. TCFD still has 11 tracked groups with a
  124-mention largest group; institution/framework/report/index senses are not
  certified. GRI 2's 50 exact-name mentions still span three groups due to type
  and support differences. Owner-free source boundaries can over-split the same
  company across documents; matching owners need grounded new profiles.
- Different supported descriptions produce unknown, even if semantically
  equivalent. Shared-owner reuse does not distinguish every temporal/local
  instance. Irregular abbreviations are not inferred. Profile classification is
  supplied on defining mentions, not fabricated for every missing description.
- Full upstream suite, released dependency artifacts, packaged runtime and
  generated Summary acceptance were not run; no claim of release readiness.
- Host Acceptance Case delta: no-case for this external-owner repair-only turn;
  these native regressions support later host entity-integrity acceptance.
  Host primary owner/change-verification/baseline remain unrun and unpromoted.

### Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed this turn.
- Overlap: native normalization/disambiguation, duplicate detection/merging,
  extraction schemas/prompt, artifact builder and checkpoint consumers.
- Retain only while upstream lacks equivalent grounded owner/sense handling;
  adapt to an equivalent native implementation and remove superseded fork code.
- After merge rerun the command above, source cache contract tests and a bounded
  no-network corpus replay before updating a consumer pin. Publication remains
  distinct from product adoption and semantic quality acceptance.
