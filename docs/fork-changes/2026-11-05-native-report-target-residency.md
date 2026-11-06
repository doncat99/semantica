# Admit report targets before materializing their memberships

- Record ID: 2026-11-05-native-report-target-residency
- Date / author: 2026-11-05 / Codex
- Status: planned; red reproduced
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty remediation workspace)
- Upstream reference: not inspected
- Related records: 2026-11-04-native-community-topology-resource-gap.md

## Reason and scope

`_explanation_reports` creates every concept/community/topic target and copies all
membership sets before filtering an explicit target request. Production build asks
for only the project overview, so unrelated memberships create unnecessary global
working-set copies. Red specification fails when an unrequested membership is read.

## Native capability assessment

The existing owner is `semantic_artifact_builder.py::_explanation_reports`, called
by build organization and the native explanation worker. Existing admission tests
cover default targets, explicit topic/community scopes, citations and product report
recovery. Repair this owner in place; no second storage, algorithm or fallback.

## Approach and actual changes

Determine requested/default target IDs first, validate explicit IDs, then construct
only admitted targets in the existing overview/concept/community/topic order.
No report content, digest, support or citation changes; no stored-data migration,
model/network request, dependency or release artifact change.

## Verification and limitations

- Red: `.venv/bin/python -m pytest -q tests/test_native_report_target_residency.py`:
  1 failed at `set(community.entity_ids)` before any model call.
- Planned: rerun report admission, product recovery and native explanation tests.
- This does not bound full selected DTOs, report quote hydration, exact community
  algorithms or total builder RSS; G4 is not closed by this change.

## Upstream merge assessment

Pending; upstream not reviewed. Retain only while upstream eagerly creates rejected
target memberships. Recheck explicit/default target order and complete report
content/citation/recovery regressions after merging.

## 2026-11-05 implementation and verification

Implemented target admission before membership materialization, with a lazy chain
that creates only the current report's target set. A second red specification
showed both selected memberships were constructed before the first report; after
repair the observed order is membership(first), report(first), membership(second),
report(second). The original red rejects any access to unrequested memberships.

Status: verified in stated scope. Expanded command:

```
.venv/bin/python -m pytest -q tests/test_native_report_target_residency.py tests/test_reading_report_admission.py tests/test_organization_report_product.py tests/test_native_explanation_worker.py tests/test_native_reduction_boundaries.py tests/test_kernel_owner_regressions.py tests/test_semantic_artifact_long_context.py
```

Result: **100 passed in 11.63s**. This includes report target admission, grounded
content/citations, product recovery, native explanation worker, budget-before-call,
kernel owner and long-context regressions. These are offline fixture tests, not a
real ESG build or fixed artifact qualification. Full chosen DTO/context hydration,
report batch planning and total RSS still require independent remediation and proof.
