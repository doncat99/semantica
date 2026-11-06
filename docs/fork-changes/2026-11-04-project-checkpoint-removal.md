# Remove the fork project-checkpoint owner

- Date: 2026-11-04
- Scope: current Semantica fork production modules and their direct regression contracts.
- Status: focused owner verification passed; packaged/product acceptance remains pending.
- Supersedes the remaining-integration statements in `2026-11-04-native-extraction-accepted-handoff.md` concerning checkpoint callers. The earlier record remains historical evidence, not a description of current wiring.

## Replacement and physical deletion

The current builder delegates source parsing to the single canonical parsed-source
carrier, paid entity/relation acceptance to `ExtractionCache`, and adopted typed
facts/operation receipts to the existing Oxigraph owner. Classification uses the
same native ownership boundary. No project checkpoint, stored context plan,
raw model response, source quote mirror or completed result-body cache is needed
to restore accepted extraction stages.

Physically deleted `semantica/project_checkpoint.py` (493 lines) and
`semantica/project_checkpoint_upgrade.py` (468 lines), along with nine exclusively
checkpoint/upgrade/old-hook test modules. No compatibility export, import,
runtime migration, old/new dispatch or silent regeneration path remains.
The replaced owner is not renamed or moved into another JSON directory.

Valuable source, grounding-budget, structural-fact and entity-before-relation
reuse contracts now exercise the native store and accepted-cache boundary.
Changed grounding input produces a different operation binding and therefore
does not reuse facts generated for the old table context. Invalid report-output
validation remains tested directly against the native typed provider; removed
report-body-cache tests no longer require a deleted persistence mechanism.

Native receipt restoration deduplicates a receipt already present on a reused
provider and rejects conflicting payloads for the same ID. Persisted rejection
diagnostics contain only `rejected_count`; candidate bodies remain transient.
Operation digests bind owned-record and model-receipt links, so deleting a
model-receipt edge cannot silently discard audit evidence.

## Verification

Focused combined regression: **195 passed in 21.67 seconds**. Selection covers
removed-module import failures; parser no-checkpoint output; worker imports;
native extraction handoff and retry; entity/relation grounding and structural
facts; typed-output rejection; bundle manifest; accepted-cache/backend/isolation;
Oxigraph extraction/classification records; native adoption reuse telemetry.
Four additional stale transport/citation fixtures were corrected and passed:
bounded response reads accept a size argument and report citation rejection
tests call the report generator rather than bypassing the new product owner.

Additional production-stage integration passed (**1 test / 2.07 seconds**):
`tests/test_native_extraction_handoff.py::test_actual_build_restarts_without_rebuy_or_checkpoint_before_publication`.
This invokes the real build entry, parse owner, extraction, source projection,
classification, identity resolution, reconciliation and organization stages in
two separate processes. Only remote transport is replaced by a no-network
fixture, including the host final-business-report product. Both processes exit
at the first `artifact_writing` progress event, before the still-in-progress G4
publisher. Across both processes entities, relations, embedding, classification
and organization each perform exactly one fixture-model request. Native pending
accepted bodies are released, the final host product is reusable, and no
checkpoint or aggregate publication JSON is created. This is production-stage
integration evidence, not a claim that G4 publication has passed.

Search across production/tests/CI Python and YAML found no surviving import or
use of the removed project checkpoint or its restoration attributes. The two
module names occur only in negative import specifications. Unrelated upstream
agent-context and truth-maintenance features are not project-checkpoint callers
and were not deleted merely because they use the same word.

Broader semantic-artifact integration is not declared green: the earlier
109-pass/15-failure run exposed stale index-publication fixtures and the new
host organization-report authorization boundary. Those integrations are owned
by the parent delivery and must close before G4/product acceptance. This record
does not claim formal-profile cleanup, historical paid-data transfer, release,
real-model token verification or App acceptance. No formal profile was written,
and no commit or release was performed by this scoped change.

## Reset and data boundary

There is no runtime reader for the obsolete checkpoint format. Required
historical paid results must be inventoried and explicitly transferred or
declared unrecoverable under the delivery's offline data gate before deleting
formal data. Source materials, user edits and required audit receipts are
protected. Removing the executable owner is not evidence that historical files
have been cleaned, nor permission to rebuy missing paid output automatically.
