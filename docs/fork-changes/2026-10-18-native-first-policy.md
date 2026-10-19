# Native-first development policy and fork change records

- Record ID: 2026-10-18-native-first-policy
- Date / author: 2026-10-18 / Codex, at repository owner's request
- Status: verified-in-stated-scope (documentation checks only)
- Fork base revision: `c1fe1d203766c00186e59a19ec27050133d86c14`
- Upstream reference: local `origin/main` observed at
  `ca6c9f1918ad05e2bbaa4922fb32f34e2a508bb9`; not refreshed for this change
- Related branch: `codex/native-first-development-policy`; commit/PR pending

## Reason and scope

The owner prohibits parallel implementations of existing Semantica capabilities.
Moving a new algorithm into the fork or using a native provider does not satisfy
native reuse. Future upstream merges also need a durable record of the reasons,
approach and evidence for each fork change.

This change establishes development/review requirements and their change log.
It does not implement entity fixes, deploy dependencies or resume ESG production.

## Native capability assessment

- Inspected documentation owners: root `AGENTS.md`, `CONTRIBUTING.md`,
  `.github/pull_request_template.md` and release `CHANGELOG.md`.
- `semantica/change_management/change_log.py` owns runtime ontology/graph mutation
  metadata, not repository development decisions. It is not changed or duplicated.
- Decision: docs-only. Reuse the existing contribution and PR entry points; add
  Markdown records, not a new logging service, pipeline or dependency.
- No algorithm, identity scorer, prompt, model invocation or fallback is added.

## Approach and actual changes

- Root `AGENTS.md`: require native inspection, reuse/repair of existing owners,
  regression evidence and maintained fork change records; prohibit duplicates.
- `CONTRIBUTING.md`: link the authoritative policy and required records.
- `.github/pull_request_template.md`: require native assessment and record links.
- `docs/fork-changes/`: add workflow, record template and this initial record.
- No runtime contract, stored data, model/network calls or dependencies change.

### Approved direction, not implemented by this change

- Entity recognition, candidate detection, similarity and merging must use the
  latest fork's existing native chain; defects belong in the corresponding owner.
- ESG passes, persists and reuses company identity, source context and Review
  results; it must not compute a parallel identity score.
- Existing business Review decides company/period/material admission; entity
  similarity is not admission evidence and no extra LLM disambiguation is added.
- Future native regressions must include same-name distinct companies, aliases,
  conflicting identifiers and insufficient information, preserving native-owner
  delegation and no-extra-model-call constraints.

## Verification and limitations

- `git diff --check`: passed for tracked changes. Explicit
  `git diff --no-index --check /dev/null <file>` checks passed for the new root
  policy and all three new log files.
- Shell `test -f` checks passed for all six changed/new documents, resolving the
  new local Markdown link targets; the PR template has exactly one Testing section.
- No runtime tests or paid model evaluations are needed or run for this docs-only
  change. Native semantic correctness and ESG delivery are not established here.
- No automatic semantic duplicate detector or CI enforcement is introduced.
- Prior fork modifications have not been retrospectively inventoried in this log.
- Changes are local; no commit, push or PR has been made for this change.

## Upstream merge assessment

- Disposition: pending; no incoming upstream merge is evaluated in this change.
- Likely overlap: upstream contribution rules, PR template and a future root
  `AGENTS.md`; reconcile these files without weakening the fork's no-duplicate rule.
- Keep the fork-specific rationale/history. Adapt links and contribution entry
  points if upstream restructures them. Drop duplicated guidance only when the
  upstream rule is equivalent and these records remain discoverable.
- After merge: inspect effective agent/contribution/PR requirements, verify local
  links and whitespace, and run relevant native regressions for any code conflicts.

## Dated follow-ups

- 2026-10-18 / Codex: initial policy and logging requirements recorded together;
  earlier fork history remains explicitly outside this initial inventory.
