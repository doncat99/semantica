# Specific native identity validation feedback

- Record ID: 2026-10-31-identity-validation-feedback
- Date / author: 2026-10-31 / OntoScience development
- Status: verified-in-stated-scope
- Fork base revision: fa32c4087c9f42b559e7c3f94e1f7798428e3045
- Upstream reference: not refreshed for this focused repair

## Reason and scope

Packaged ESG run 20d78629-d717-4004-b090-0d6f768aef0e parsed 38 documents,
then failed schema admission during extraction. Its durable progress identifies
two identity_profile value_error failures but cannot distinguish their invariant.
The same generic error is fed back to the model by the native typed retry owner.
This does not establish which of the three invariants failed in that run.

## Native capability assessment

Repair IdentityProfileOut.grounded_owner in semantic_extract/schemas.py.
BaseProvider.generate_typed already supplies safe location/type diagnostics to
bounded regeneration; methods.extract_entities_llm and _ProjectModelProvider use
that owner. Reuse this path, without JSON repair, parallel extraction or fallback.

## Approach and actual changes

Replace generic ValueError with three PydanticCustomError codes describing exact
owner/instance containment and missing identity facts. Admission rules are
unchanged. No source values are added to feedback or durable diagnostics.
No checkpoint identity change, new dependency, data migration or deletion.
No additional retries; any real model retry still incurs provider usage.

## Verification and limitations

Three red cases proved that retry feedback lost the constraint identity.
After repair, tests/test_native_typed_output_owner.py, tests/test_project_identity.py,
tests/semantic_extract/test_grounded_llm_extraction.py and
tests/test_semantic_worker_validation_diagnostics.py: 70 passed.
These are offline regressions, not a completed packaged ESG or warm rebuild.
The real model may still exhaust bounded retries; acceptance remains outstanding.

## Upstream merge assessment

Pending: incoming upstream not reviewed. Retain only while the native owner lacks
specific safe error types; adapt or drop if upstream provides equivalent feedback.
Recheck whole-response rejection, strict identity admission and retry privacy.
