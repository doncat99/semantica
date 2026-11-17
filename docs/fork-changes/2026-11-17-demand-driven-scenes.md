# Demand-driven native scenes

Status: source implementation verified; immutable artifact and App qualification pending.

## Reason and native owner

Inspected main b6912a6c02da5ac9fb2d91e43cdbc807705d895f. The current owner is
PublicationRecords.scene/_relation_page in semantica/triplet_store/publication_records.py.
Source/Explore callers omitted fields, implicitly expanding support and evidence.
_fact_scene_link repeated a broad operation/source provenance join for every relation.
Reuse existing indexed _scene_references and canonical field owners; no second engine.

## Approach and callers

Require explicit field selections for entity/relation/incident scenes, including
explicit detail fields where eligibility/complexity require evidence and members.
Display requests select scalars and endpoints only. Replace the broad provenance
join with indexed member/address lookup with cancellation and byte bounds.
Update native tests and host consumers together. No stored-data migration is needed:
this changes the query contract, not publication identity or stored RDF.

## Verification and limitations

Planned: regression for rejected implicit expansion, support fanout, current scene
regressions, immutable worker qualification and same-project read-only acceptance.
Upstream merge: fork-specific publication owner; retain current semantics, no version dispatch.

Source verification: 219 related tests passed before the final phase counters.
The remaining build lifecycle assertion also fails on unmodified b6912a6c: it
incorrectly expected beginning a pending generation to invalidate an explicitly
selected active generation. Corrected the test to verify the existing atomic
activation contract: active stays readable, pending is rejected, including after
a failed build. No production activation semantics changed.

Read-only same-user-store benchmark: nodes128 compact 857ms; links57 compact
769ms; links57 detail771ms, of which indexed provenance17ms. These are source
measurements, not HTTP/App acceptance or an exact replay of the old64 row page.
Diagnostics record numeric phase durations, query/lookup/row counts and encoded
response bytes, never source bodies, evidence text or full SPARQL.
