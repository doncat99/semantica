# Main-only branch consolidation

- Date / author: 2026-10-19 / Codex, authorized by repository owner.
- Status: implemented; verification recorded below.
- Fork base: a1019e63ba550ca6e9a5a2eca91ae2c3d53f2f89.
- Upstream: not fetched for this branch cleanup; no upstream merge performed.

## Reason and native capability assessment

Consolidate development into main and preserve branch history. Inspected all local
heads, remote heads, GraphStore snapshot methods and TypeDBStore/tests. The sole
ancestrally unique commit cedb1967 is already represented by cherry-picked TypeDB
changes on main (f38a0be8/bd671778). Its store and tests are identical to main.
This merge records ancestry; it adds no second implementation or backend.

## Approach and impact

Merge the old branch, retaining main's newer append_snapshot and export_snapshot
methods at both conflicts. Native implementation code remains identical to the
pre-merge main. Existing TypeDB development record remains in modification-log;
this record describes this merge only. All other development heads are ancestors.
Dirty obsolete drafts are preserved outside the repository in a verified local
bundle/patch/untracked archive before branch deletion; not resurrected into main.
No consumer, dependency, schema, model-call, runtime or storage change.

## Verification and limitations

Compared GraphStore and TypeDB code/tests to a1019e63: no implementation difference.
Focused native tests with SEMANTICA_TEST_NEO4J_URI=bolt://127.0.0.1:17687:
18 passed, 4 skipped (TypeDB unconfigured), in 27.31 seconds. Covered persistent
center, append, scoped context and grounded sources; no model calls. Diff whitespace
check passed. The initial run without the isolated Neo4j URI had 10 passed and
12 skipped; it was rerun with the explicit isolated URI to exercise persistence.
Real TypeDB is not part of ESG acceptance and is not substituted for ESG's Neo4j.
Branch consolidation is not application deployment or production qualification.

## Upstream merge assessment

Disposition: keep this governance history. Future upstream merges must inspect
native snapshot owners and preserve append/export contracts or migrate consumers.
No incoming upstream revision reviewed in this operation.

Main-only development is now explicit in AGENTS.md; no long-lived development
branches are created. Dirty detached workspaces remain recoverable locally.
