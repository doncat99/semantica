# Certified offline retirement of obsolete native results

- Record ID: 2026-11-05-obsolete-native-retirement
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope; live retirement not executed
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main checkout)
- Upstream reference: not inspected
- Related record: [paid native adoption](2026-11-05-paid-native-hydration-rebind.md)

## Reason and scope

After certified adoption, obsolete recipe owners still occupy native storage.
The user requires their physical removal while preserving original materials,
current results and required audit evidence. Normal build/query readers must
continue to use only the current contract. This is explicit offline maintenance,
not a runtime fallback or a background cleanup job.

## Native capability assessment

- Inspected `ExtractionRecords` and `ClassificationRecords` operation bindings,
  receipts, owned-record closure and reduction references; `OxigraphStore`
  persistent native graph ownership; `SQLiteVecStore` embedding-space identity,
  operation receipts and publication receipts; `ExtractionCache` accepted keys.
- Existing per-vector deletion retains operation receipts; cache `clear()`
  intentionally preserves accepted receipts. Neither implements complete exact
  obsolete-recipe retirement. Reuse native receipt readers and physical native
  storage primitives through one explicit maintenance command.
- Actual consumers are project facts/projections, current publication and native
  embedding spaces. No runtime modules, exports or normal readers are changed.

## Approach and actual changes

- `.github/scripts/retire_obsolete_native_results.py` builds a disk-backed plan
  for explicitly named obsolete recipes in one project. Native operations are
  selected in cursor pages of 128. Receipt-owned subjects and projection graphs
  are admitted; each subject proof is bounded to 32,768 quads / 2 MiB. Exact
  accepted cache keys and original model receipts are retained in the audit plan.
- Incoming IRI and encoded literal references from outside the deletion closure
  block cleanup. An integrity traversal scans the native store incrementally,
  with closure membership in disk SQLite. Native publication or vector-space
  publication references block retirement. Current recipe is excluded.
- Apply requires the identical dry-run report, freshly regenerated plan, idle
  project execution and unchanged subject/acceptance/vector-owner proofs before
  the first destructive write. A retained plan and original certificate permit
  explicit resume after a partial maintenance failure; changed surviving owners
  block resume. Stop the daemon before opening its native store.
- Deletion removes admitted RDF subjects/projection graphs, exact cache and
  acceptance keys, and entire obsolete vector SQLite owners plus WAL/SHM files.
  Native optimize/flush and acceptance SQLite checkpoint/VACUUM reclaim storage.
  Plan/report files have mode 0600 and must remain outside the native owner root.
- Originals, parsed representations, current spaces and unrelated cache keys are
  not deletion targets. Audit operation/model receipts survive in the retained
  plan. No model/network calls or dependency changes are introduced.

## Verification and limitations

- `.venv/bin/python -B -m pytest -q tests/test_obsolete_native_retirement.py`:
  5 passed in 1.28 seconds. Exercises extraction closure, classification batch
  plus reduction closure, exact cache keys, original receipt retention, direct
  and encoded external references, changed-subject/acceptance rejection before
  deletion, physical obsolete-space removal, current owner preservation,
  process reopen and explicit idempotent resume.
- No live native store was opened; no live project data was deleted. Live dry
  run requires a coordinated stopped-daemon window and confirmed idle jobs.
- This command does not itself certify paid-result adoption or target build
  success. The integrating owner must first review adoption evidence, exact
  obsolete recipes, deletion certificate and protected current owner.
- Maintenance spans native RDF, acceptance SQLite and vector files; it is not
  one atomic transaction. Retain the dry-run certificate and plan until verified
  completion. Never restart ordinary jobs between partial deletion and resume.
- Full product acceptance and change-verification were not run for this tool.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- On merge, inspect native maintenance/retirement APIs and receipt schemas.
  Replace this command's primitive deletion calls if the native owner gains a
  complete equivalent; do not retain competing retirement implementations.
- Re-run the focused retirement, extraction/classification and embedding owner
  regressions after changes to receipt, closure or space schemas.

## Pending paid-envelope closure (2026-11-05)

The same offline owner accepts explicit `--pending-scopes` JSON entries naming
obsolete recipe, source, namespace (`entities` or `embedding`), exact expected
count and optional exact window. Candidate keys are reconstructed through the
current producer's source-window planner, native grounding batch planner,
extraction operation identity, embedding operation identity and cache key owner.
No alternative runtime reader or successful native result is created.

Each candidate body is read with a 1 MiB SQL projection, verified against its
SHA256, accepted digest and durable acceptance receipt, then admitted only once.
Exact-count mismatch, current recipe, unknown namespace, duplicate native owner,
corruption or missing original model audit blocks admission. Disk-backed
`pending_audit` retains only binding/input/acceptance identity and original model
receipts. Full obsolete bodies are removed, not copied into audit storage.
Apply rechecks all pending bodies before any RDF write. Resume requires either
an unchanged body or both body and receipt absent after the atomic cache phase.
Original materials and current accepted results are untouched.

Focused verification: 8 tests passed in 1.25 seconds, including pending failure
retirement without native adoption, current-body preservation, audit retention,
count/current/duplicate/corruption rejection and changed-body rejection before
RDF deletion. No live native/cache handle was opened, and no cleanup applied.
Real stopped-window canonical key attribution and the final exact-count dry
certificate remain required for physical-cleanup signoff.

## Complete identity inventory gate (2026-11-07)

Inspected fork revision: `2cf2e28f5cb1dd40c91429c94d924cf9f8551a9d`.
The existing maintenance script and `tests/test_obsolete_native_retirement.py`
remain the implementation and regression owners. Its host offline cleanup
wrapper is the only current caller; historical scratch preparations are audit
evidence, not runtime consumers. Native `ExtractionRecords`,
`ClassificationRecords`, `ExtractionCache`, publication graph ownership and
SQLite vector-space receipts were inspected and reused.

The allowlist selector previously omitted unknown recipes and unowned cache
keys. Its successful certificate could therefore only prove the named deletion
scope, not that every result in the project native root was classified. The
same maintenance owner now traverses **all** project binding recipes in cursor
pages of 128, all named/default graphs, embedding-space files, durable accepted
receipts and residual cache bodies. Unknown recipe/graph/subject/namespace/key,
unattributed acceptance or invalid receipt/body identity blocks dry, apply and
resume. Nothing unknown is inferred obsolete or automatically deleted.

Current extraction and classification recipes are derived from the frozen
runtime and protected. Current embedding protection requires the exact current
binding/model/recipe space, not merely a matching recipe. Native record codecs
verify operation identities and receipt closures; original model receipts are
read through their canonical owners. Accepted keys are attributed through native
operation key derivation or explicit pending scopes. Current owner keys are
never inserted into deletion tables. A successful run therefore cannot silently
ignore other accepted namespaces or leftover pending bodies.

The complete identity certificate and native membership indexes use temporary
disk SQLite with a 4 MiB page cache; no whole-project DTO collection is retained.
One native operation remains subject to existing cardinality/byte limits, and
cache body SQL projections are bounded to 1 MiB. All graph quads are streamed
for a commutative SHA256 multiset proof; facts subject membership is checked
against the disk index. This is an authorized offline integrity traversal, not
a normal product read. It may take time proportional to retained native data.

Plan table `inventory(kind,id,disposition,digest)` records protected and explicit
obsolete identities; `protected_receipts(receipt_id,operation,recipe,space,
source,receipt_digest)` exposes the current accepted model receipt closure for
usage reconciliation without a second traversal. Here `operation` is the native
operation URN, and `receipt_digest` hashes the full canonical compact sorted JSON
receipt. This table does not claim exact publication dependency membership or
count historical receipts as API attempts. Report identity additionally binds
artifact digest, input revision and exact current embedding space.

Resume checks surviving identities against the original inventory and requires
all protected identities to remain. Only certified obsolete identities may be
absent. The mixed project facts graph can shrink through admitted obsolete
subjects; independent per-subject proofs preserve protected facts and the
existing apply admission checks preserve surviving obsolete facts. The retained
certificate includes inventory and protected receipt table digests.

Verification: the new isolated full-inventory specification was red before the
implementation (`inventory_all` absent). The focused retirement suite now has
10 passing tests, including unknown recipe/vector/graph/accepted-key blockers,
current result and original receipt protection, protected mutation rejection,
physical obsolete deletion and inventory-aware resume. No live native owner
was opened; no real data was deleted; no runtime, package recipe or frozen
artifact changed. Product/CV qualification is intentionally not repeated for
this maintenance-only change. Live ready/stopped dry/apply remains outstanding.

The interruption fixture also removes an operation subject before its owned
subjects and removes one projection subject before the rest of its graph.
Resume attributes only those surviving obsolete subjects present in the retained
certificate and rechecks their exact per-subject proofs. Projection proof lookup
is once per distinct subject, backed by disk membership, rather than once per
quad. New or changed subjects still block. Deletion orders each operation URN
before its own suffixed subjects, with each subject deletion an atomic native
update; normal readers must stay stopped through all maintenance phases.
