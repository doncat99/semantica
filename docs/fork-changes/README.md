# Fork change records

This directory tracks why and how `doncat99/semantica` differs from upstream,
so later upstream merges can evaluate each change instead of blindly retaining
patches. It is a development decision log, not a second runtime change-management
system or a replacement for the release `CHANGELOG.md`.

## Required workflow

1. Before implementation, inspect native ownership under [AGENTS.md](../../AGENTS.md)
   and start a record from [TEMPLATE.md](TEMPLATE.md). Use
   `YYYY-MM-DD-short-description.md`; add a unique suffix for name collisions.
2. One record covers one coherent change, including documentation-only changes.
   Keep it in the same commit/PR as that change and link it in the PR template.
   Record inspected revisions, not an assumed latest version. Reference commits
   or PRs when known; do not create a self-referential commit hash requirement.
3. Before review, record what actually changed and exact checks/results. Explicitly
   mark work not implemented, checks not run, unknowns and remaining risks. Link
   repository-relative evidence; do not include secrets or private report contents.
4. On follow-up changes or upstream merges, append a dated assessment to the
   relevant record and link any new record. Preserve earlier reasons and results;
   correct mistakes with a dated explanation, not a rewritten history.
5. Missing records, missing native assessment or unverified claims block review.
   These are contributor/review requirements, not an automated semantic CI gate.

## Upstream merge review

For each affected record, inspect the incoming upstream revision, compare native
owners and behavior, then record **keep**, **adapt**, **drop**, or **pending** with
evidence. A textual merge without conflicts does not establish compatibility.

- If upstream now provides the capability, reuse its owner and remove obsolete
  fork code; never retain both implementations as fallbacks.
- List affected consumers, contract/data migration needs and tests that establish
  compatibility, including no-network/no-model-call guarantees where applicable.
- Record conflicts, their resolution, actual checks, unresolved risks and reviewer.
  Do not label an untested resolution verified.

## Existing history

The first record covers the native-first policy and this logging requirement.
Earlier fork changes are **not yet inventoried here**. If backfilled, identify the
source commits and mark the entry retrospective; unknown motivations and missing
test receipts must remain unknown.
