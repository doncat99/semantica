# Bounded contextual identity repair

- Record ID: 2026-10-30-bounded-identity-resolution
- Date / author: 2026-10-30 / repository contributor
- Status: verified-in-stated-scope (source tests and offline replay, not deployed)
- Fork base revision: d0f7088490bca5b782d16549b3b00e45d97925b3, plus pre-existing uncommitted identity work
- Upstream reference: not inspected for this repair
- Related records: [deep review](2026-10-30-identity-deep-review-repair.md), [scope and sense](2026-10-30-identity-scope-and-sense.md)

## Reason and scope

Missing/complementary descriptions must not become proof of different identities.
A conflict in another document must not poison otherwise supported local identity.
An indirect conflict must not discard every supported subgroup. Unknown-candidate
diagnostics must not retain a Python tuple for every unresolved pair.
The stopping point is deterministic source-grounded linking, not perfect semantic
inference, entity-specific exceptions or extra per-mention model calls.

## Native capability assessment

- Repair `EntityDisambiguator.prepare/compare` in `normalize/entity_normalizer.py`;
  `DuplicateDetector._build_duplicate_groups/_contextual_candidates` in
  `deduplication/duplicate_detector.py`; empty state in `kg/entity_resolver.py`;
  and `_resolve_native_entities` in `semantic_artifact_builder.py`.
- Actual caller chain remains builder -> EntityResolver -> DuplicateDetector ->
  EntityDisambiguator. Existing exports/configuration and contextual regression
  suites are reused; no alternate resolver, adapter, identity store or model path.
- Existing worktree changes to extraction, schema and merger predate this repair.
  They must not be described as newly implemented by this record.

## Approach and actual changes

- Complementary grounded descriptions are neutral; explicit shared-content
  negation remains an ambiguity hint. Identifier, owner, kind, version and type
  barriers remain. Scoped defining facts are prepared once and reused; global
  descriptive/fact vetoes are removed.
- Partition existing positive groups under explicit conflict constraints. Preserve
  supported subgroups; isolate direct contradictory bridges. Stable normalized IDs
  order residual constrained unions. This is not a uniquely optimal semantic
  partition and does not guess a missing identity.
- Unknown diagnostic edges use per-mention/reason integer bitsets. After canonical
  remapping, stream each mention's exact distinct candidate/reason count and at
  most eight deterministic samples, excluding self-candidates. Clear per-run state
  on empty and singleton inputs. Common-name candidate buckets still have quadratic
  worst-case comparisons/storage bits; no claim of constant total cost.
- Corpus inspection additionally exposed `Board of Directors` interpreted as
  owner `Directors`. Generic role-headed body expansions remain owner-dependent;
  completing a body name is not evidence of its named owner. This is a grammatical
  category boundary, not an issuer/acronym allowlist.
- Processing version changes from `project-contextual-identity-v7` to `v8` so graph
  stages cannot reuse old linking results. Paid parsing/extraction is not invalidated
  by this processing-only version. No new dependencies or model/network calls.
- No production graph deletion/rebuild, host pin change, artifact publication,
  packaged rebuild, git commit or push is included.

## Verification and limitations

- Regression-first: complementary profiles, remote homonym isolation and indirect
  conflict partition all failed before repair. Both generic-body counterexamples
  and sentence-end punctuation also failed before their source fixes. Final focused
  suite: 164 passed in 1.33 seconds.
- Compact-review regression checks 128 unknown mentions, canonical remapping,
  exact counts, eight samples and no self-reference. Source projection checks
  preserve mention immutability, occurrences and provenance.
- Intermediate expanded suite: 1393 passed, 45 skipped, five subtests passed.
  Final expanded result and corpus replay recorded in dated follow-up below.
- Host typecheck passed. Host guard failed on three unrelated missing Explore
  screenshot links in `docs/engineering/explore-graph-routing-20261029.md`.
  No host changes were selected by change-verification; this is not App acceptance.
- Real replay consumes raw stored mentions and original source text/offsets, never
  old canonical aliases. Network connection is forbidden; every mention must map
  exactly once and preserve its exact located quote. Old extraction is almost
  description-free, so replay cannot certify current model extraction quality.
- Remaining limits include ambiguous acronyms, company-name fragmentation,
  role/report ownership, arbitrary semantic paraphrases and old extraction errors.
  Group counts are diagnostics, not accuracy labels. Do not hardcode known names
  or require extra model evidence to force them to one group.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Overlap: normalization, native deduplication, resolver state and project builder.
- Retain only while these invariants are absent upstream; adapt or remove when
  native upstream behavior supersedes them, without adding fallback owners.
- After merge rerun contextual identity, grouping/veto, grounded extraction,
  project checkpoint/local reuse and multi-family offline replay; immutable
  dependency adoption requires separate host product acceptance.

## Dated follow-ups

- 2026-10-30 correction: the body/complement phrase list was too specific to call
  a general grammatical boundary. It is removed by
  `2026-10-30-generalization-boundary.md`; ambiguous ownership inference is repaired
  at the native owner instead. Earlier results below describe the prior v8 code.

- 2026-10-30: final expanded native suite: 1397 passed, 45 skipped, five subtests
  passed, 14 existing warnings in 102.82 seconds. Command: `.venv/bin/python -m
  pytest -q tests/kg tests/deduplication tests/normalize tests/test_project_identity.py
  tests/test_native_grounded_source.py tests/test_semantic_artifact.py
  tests/test_project_source.py tests/test_project_stages.py
  tests/test_project_local_reuse.py tests/test_project_checkpoint.py
  tests/test_kernel_owner_regressions.py
  tests/semantic_extract/test_grounded_llm_extraction.py
  tests/semantic_extract/test_grounded_wire_contract.py`. Final focused seven-file
  suite: 164 passed. `git diff --check` passed.
- 2026-10-30 final corpus replay: 36,082/36,082 grounded mentions retained once,
  20,048 entities, 158.069 seconds native resolution plus 20.352 seconds grounding,
  zero network calls. Baseline had 20,196 entities. Exact-name SASB: 158 mentions,
  157 -> 52 groups; exact-name TCFD: 86 mentions, unchanged 11 groups. Full TCFD
  family: 135 mentions, largest group 124; not semantically adjudicated in full.
  GRI and Home Depot main families remain intact. TriStar/TCFD/TNFD/Home Depot
  cross-name contamination assertion passed. Board: 220 mentions, 146 -> 201
  groups; the prior 67-member group spanning 12 sources no longer exists. All
  groups containing exact-name Board mentions now have one source (largest eight).
  This removes a demonstrated false merge; it does not certify 201 correct identities.
  HCA Healthcare remains 157 mentions / 157 groups, a known unresolved fragmentation
  limit, not a success. No force-merge or extra evidence collection was added.
- Evidence: host ignored `.tmp/snapshot-audit/bounded-identity-verification.md`,
  `bounded-identity-final-replay.log`, `identity-corpus-current.json` and
  `identity-corpus-before-bounded-repair.json`. Product data and baselines unchanged.
