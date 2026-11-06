# Native pending-build read protocol

## Owner and reason

Inspected dirty main at 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe.
ExtractionRecords owns paid typed values; PublicationRecords owns selected input
membership and generation fences. Existing extraction pages address one operation;
existing publication pages require ready state and reconstruct all record fields.
The builder currently aggregates the project before beginning publication.

## Planned implementation

Extend PublicationRecords with pending-only, generation-bound projected record
pages and point reads. Reuse its current native record reader; no secondary store,
knowledge JSON, model calls, compatibility path or alternate semantic algorithm.
Require the complete staged source/operation plan before traversal. Bind cursors
to project, generation, kind, source and projection; enforce row and byte budgets
and cancellation. OxigraphStore exposes direct delegates.

## Scope and evidence

Affected: publication_records.py, oxigraph_store.py, native build cursor tests.
This is a prerequisite for builder migration, not proof that G4 is complete.
Regression results and limitations will be appended after implementation.
Upstream merge must preserve the pending/ready separation and scoped cursors.
