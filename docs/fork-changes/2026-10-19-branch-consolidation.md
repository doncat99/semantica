# Consolidate fork development branches

- Record ID: 2026-10-19-branch-consolidation
- Date / author: 2026-10-19 / fork maintainer
- Status: verified-in-stated-scope
- Fork base revision: `f38a0be8`
- Upstream reference: not merged; this is a fork-branch consolidation
- Related commits: `f69d5984`, `1c9fb99f`, `7b7a902b`, `9b9ee65e`, `34ff29cf`

## Reason and scope

Consolidate fork development history into `main` while preserving the released
per-source progress commit and native strict typed output. An unqualified merge
of the older `native-strict-output-20261019` branch reintroduced an obsolete
parallel project worker; its focused tests had 12 failures against the current
checkpoint and parsed-source contracts. Historical release tags remain intact.

## Native capability assessment

- Inspected `f38a0be8` and the candidate merge: the current transport owner is
  `semantica/semantic_worker.py`, which invokes
  `semantica/semantic_artifact_builder.py` and the shared semantic schemas.
- OntoScience consumes the semantic-worker artifact bundle, not the old
  `project_snapshot_worker`/`project_query_worker`. Within this fork, only the
  old project-worker modules, their tests, CI, and entry point reference that
  parallel worker. `OpenAIProvider.generate_typed` is the native typed-output
  owner and the identity changes extend the existing deduplication owners.
- Decision: retain the native fixes and remove the obsolete parallel worker
  entry point, modules, tests, dedicated CI assets and unrelated lock churn.
  Existing immutable tags still identify their original trees.

## Approach and actual changes

- Merged the development branch histories, resolving the scheduling assertion
  conflict to retain both total-count and per-source assertions.
- Kept source-progress, relay checkpoint retry, native identity constraints,
  fork development policy, and strict OpenAI JSON Schema output.
- Retired the old project-worker-only files and CLI script. The current
  semantic-worker public contract and OntoScience pin are unchanged.
- No migration of stored snapshots is attempted; this merge does not rewrite
  historical artifacts or tags. No new model calls or dependencies are added.

## Verification and limitations

- Initial unqualified candidate: 71 passed, 12 failed in focused tests; all
  failures were from the old project-worker contract mismatch.
- Post-retirement checks using the existing fork Python environment: 64 passed
  across strict OpenAI output, source scheduling, relay retry, grounding and
  native identity constraints; 67 passed across checkpoint/process restart,
  native extraction, identity and semantic-worker contract; 104 passed across
  semantic artifact, query worker, bundle and kernel owner regressions. One third-party
  `google.generativeai` deprecation warning; no network model call in these
  tests. `git diff --check` passed.
- One combined run was manually interrupted after six passes while waiting for
  the real process-restart test; the same test then passed in the verbose run.
- This consolidation is not an upstream merge or a new signed release bundle.
  External consumers of the old, unpublished project-worker entry point were
  not independently inventoried beyond this fork and OntoScience.

## Upstream merge assessment

- Disposition: keep fork changes pending a future upstream revision review.
- Incoming upstream revision reviewed: none.
- A future upstream merge must compare native semantic-worker, typed provider,
  identity constraints and checkpoint owners, then run their regressions.

## Dated follow-ups

- 2026-10-19: old parallel worker removed from the consolidated tree; historical
  branch commits and immutable tags remain in Git history for audit.
