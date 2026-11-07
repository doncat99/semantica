# Account for withdrawn paid operations during offline rebind

- Record ID: 2026-11-07-paid-rebind-withdrawn-operation-scope
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 919efd53791f910800cb0c2a923489de6d29822c
- Upstream reference: not inspected; maintenance-only local repair
- Related records: G56 immutable three-source acceptance journal

## Reason and scope

The offline adoption owner compared current required vectors against every historical vector in the same old recipe space. G56 has five current vectors and four precisely identified withdrawn-source vectors. This incorrectly blocked current results reuse. Runtime readers, frozen artifact and model recipes are unchanged.

## Native capability assessment

The existing `.github/scripts/rebind_paid_native_results.py:adopt`, SQLiteVecStore operation identity/read validation and ExtractionCache accepted receipts already own the necessary verification. Reuse these owners; no alternate runtime or reader is introduced.

## Approach and actual changes

Accept optional complete retired bindings in the maintenance API. Verify project, recipe, model, space, inactive source, uniqueness, actual vector/receipt digests and accepted receipt. Audit their operation identities and counts without adopting them. Require current plus verified historical vectors to equal the original owner count; unknown extras and missing current data still fail. No deletion, network, model call or dependency changes.

## Verification and limitations

` .venv/bin/python -m pytest -q tests/test_paid_native_rebind.py --override-ini addopts=''`: 12 passed, 5.59 seconds. Before source change the new specification failed twice for the missing API argument. Covers dry/apply/idempotence, no historical adoption, unknown extras, fabricated/duplicate/active bindings, corrupt accepted receipt, missing producer windows and zero recomputation. Historical document-to-binding evidence remains the invoking offline operator's responsibility; the canonical owner verifies the complete persisted operation and receipt.

Full runtime qualification is not repeated: only maintenance tooling and its tests changed, independently of the frozen release artifact.

## Upstream merge assessment

- Disposition: keep pending upstream review; this is offline audit scope, not compatibility logic.
- Incoming upstream revision reviewed: none.
- Likely conflicts: maintenance rebind owner and its tests.
- Retain only while exact operation and receipt verification remain canonical; rerun this test file after owner merges.

## Dated follow-ups

2026-11-07: G56 dry/apply evidence recorded separately under the host ignored scratch area; no real App or jobs started by this change.
