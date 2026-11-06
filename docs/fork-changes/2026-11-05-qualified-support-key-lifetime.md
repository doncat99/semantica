# Qualified support encoding lifetime

- Inspected revision: dirty fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
- Native owner: `semantica/deduplication/entity_merger.py::EntityMerger.merge_qualified_facts`.
- Sole production consumer: `ConflictDetector.reconcile_qualified_facts`; builder aliases that owner.
- Related record: [qualified support copying](2026-11-04-qualified-support-copy-residency.md).

## Reason and native assessment

The native merger already groups qualified identities, deduplicates complete audit
observations by their exact sorted JSON encoding, and yields one independent
canonical group at a time. No alternate algorithm or storage is needed. However,
the generator retained its `observations` dictionary while yielding the completed
canonical group. The dictionary keys contain complete JSON bodies, so all encoded
support bodies stayed resident beside their already-cloned canonical observations
until consumption resumed. These keys have no remaining use after ordered clones
are constructed.

## Implemented change

Delete the transient deduplication dictionary immediately after constructing its
ordered independent observation copies. Keep exact full-record representative
selection, full JSON equality and order, independent withdrawn observations,
status reduction, evidence selection and output/input independence unchanged.
No caller contract, persisted representation, fixture, configuration, export,
dependency or package pin changes are required.

## Regression evidence

Added `test_qualified_support_releases_full_json_keys_before_yield` to the existing
support residency suite. It wraps the actual JSON encoder's returned strings with
weak-referenceable strings, passes 32 complete audit observations through the
native merger, and inspects them while the generator is suspended at its first
canonical output. Before the fix: **1 failed, 6 passed in 0.12s**, because full
encoded keys remained alive. After the fix, all keys are released while all 32
canonical supports remain available.

Focused support/conflict/identity/status tests: **15 passed in 1.24s**.
Affected native owner run (offline, no model/network calls):

```text
.venv/bin/python -m pytest -q tests/conflicts tests/deduplication tests/test_native_support_copy_residency.py tests/test_native_conflict_relation_access.py tests/test_project_fact_identity.py tests/test_native_snapshot_context.py tests/test_native_reduction_boundaries.py
225 passed, 31 subtests passed in 1.73s
```

## Limits and upstream assessment

This removes redundant encoding lifetime, not canonical audit bodies or the
all-fact initial grouping. Initial model dumps, a large single group's transient
encoding/sort peak, required canonical observations and project-global working
sets still need a resource contract. This patch does not qualify complete G4,
fixed artifacts, paid ESG execution or release. Upstream merge assessment is
pending; preserve exact encoding/order and suspended-generator lifetime tests.
