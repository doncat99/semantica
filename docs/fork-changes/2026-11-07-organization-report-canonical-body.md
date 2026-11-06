# One canonical organization report body

- Date: 2026-11-07
- Status: verified-in-stated-scope
- Fork base revision inspected: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty canonical main checkout)
- Upstream revision: not inspected; merge assessment pending.

## Reason and native assessment

`semantic_publication_builder._explanation_reports` joined every ReportSection.text into KnowledgeReport.summary, duplicating the entire paid body. KnowledgeReport is the canonical owner; its consumer `_grounded_topics_from_reports` already consumes sections. `_organization_report_product` hands this exact schema to the host durable product owner. The host organization-reports adapter only requires summary during validation, without rendering it. Independent kg.community_summarizer CommunityReport.summary is a different native object and is not changed.

## Actual change and contract boundary

Delete KnowledgeReport.summary and its join producer. Keep complete sections, citations, receipts and content hash unchanged. Reject obsolete summary inputs, update all constructors and host adoption contract/fixtures. No replacement summary, truncation, duplicate owner, fallback or model requests. Existing incompatible derived report products require explicit offline cleanup/rebuild by the coordinating task; normal reads do not migrate them. This patch does not touch live data or fixed artifacts.

## Verification and limitations

Red schema regression: host `.tmp/g6-organization-body-red.log`. Focused native: 31 passed, 3 deselected (`tests/test_organization_report_product.py tests/test_reading_report_admission.py tests/test_native_organization_topology_projection.py -k "not native_canonical_identity_does_not_depend_on_build_directory and not projection_keeps_exact_identity_check"`). Full three-file run: 31 passed, 3 failed; two existing assertions expect retired snapshot wording, and the build-directory identity test patches the retired stage_publication_canonical path. These are outside the canonical-body seam. Host: 14 passed across organization product and storage tests, including actual offline CLI dry/apply/idempotence and existing exclusive-profile reader protection. Host offline maintenance verifies opaque identity/digest and exact summary equality to complete section concatenation before atomically removing only that duplicate, retaining receipt/body data; mismatch is typed and blocks. No live apply was executed. Packaged artifact, live ESG and release acceptance remain outside this seam.

## Upstream merge assessment

Pending. Retain only if incoming owner still permits duplicate report prose; adapt to upstream's canonical section schema if provided. Recheck schema, builder, topology organization, product handoff, report admission, host receipt integrity and fixed artifact acceptance after merge.
