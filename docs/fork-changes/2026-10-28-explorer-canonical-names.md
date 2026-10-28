# Explorer native canonical names

- Date: 2026-10-28
- Status: focused regressions and packaged native Explorer verified
- Fork base revision: 972a907452b91fb56da0365a2be5c95fdc40aa8a
- Upstream reference: not inspected

## Reason and native capability assessment

KnowledgeEntity defines canonical_name, but ContextGraph.add_nodes omitted that
field when selecting content. GraphSession.from_file delegates to this owner;
Explorer renders content, consequently displaying mention IDs for native artifacts.
The existing demo name/content inputs concealed this mismatch. Inspected native
schema, ContextGraph ingestion, GraphSession loading and Explorer useLoadGraph.

## Approach and actual changes

Repair ContextGraph.add_nodes by accepting canonical_name after explicit content,
including the existing metadata/properties path. No frontend adapter or additional
implementation. IDs, relations and stored artifacts remain unchanged. No new
dependencies, model calls or network requests. Regression coverage lives in the
existing tests/explorer/test_semantic_artifact_loading.py owner.

## Verification and limitations

Before repair: two new regressions failed with raw IDs. After repair: native
artifact loading, Explorer API and ContextGraph Markdown tests: 38 passed,
2 skipped. The rebuilt OntoScience App (0.10.0-local.20261028.090929Z)
started the native Explorer on the real ESG Report artifact: 431 nodes, 14,933
edges; all 431 node contents are readable names, none use mention IDs as labels.
The native UI search for Sustainability Accounting Standards Board returned one
named result. Electron host mount and native browser interaction were checked
separately. Evidence: OntoScience-od/.tmp/dev-explorer-labels/verification.md.

## Upstream merge assessment

Pending upstream review. Retain until ContextGraph accepts canonical_name from
native semantic artifacts. Re-run Explorer loading/API and ContextGraph persistence
regressions after merging overlapping ingestion changes.
