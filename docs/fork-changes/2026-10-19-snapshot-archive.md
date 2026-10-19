# Immutable snapshot export for controlled migrations

- Record ID: 2026-10-19-snapshot-archive
- Date / author: 2026-10-19 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `28728581` on governed `main`
- Upstream reference: origin/main `9fac58a4`; upstream not inspected
- Related record: [native center](2026-10-19-esg-native-center.md)

## Reason and native capability assessment

The ESG read-only audit rejected all 20,635 previously migrated scopes: an older
uncommitted schema had serialized an experimental `formula_bindings` section.
Governed main deliberately did not import the unrelated formula feature. Its
strict semantic reader correctly rejects this unknown contract. No production
reader should discard unknown fields or fall back to unchecked data.

Existing owners inspected: `GraphStore.read_snapshot/commit_snapshot`,
`Neo4jStore.read_snapshot/commit_snapshot`, their public exports and
`tests/test_native_persistent_center.py`. The backend already reads sealed
immutable payloads and verifies their digest. Reuse that owner to export archival
payloads for backup and explicit migrations, without semantic interpretation.
No new schema, formula engine, provider, identity algorithm or dependency.

## Approach

Add `GraphStore.export_snapshot`: expose the backend's existing digest-checked
payload without interpreting it as current semantic state. The ordinary
`read_snapshot` delegates to this byte-preserving transport and still performs
strict native validation. Callers must authorize scope; exports are archival
data, never decision context. ESG may use this in an explicit, versioned
migration, preserving original payloads and only publishing validated new
revisions through the existing CAS commit owner.

## Verification and limitations

Pending regression: unsupported schema remains rejected by semantic reads;
archive exports preserve it exactly; corrupt stored bytes remain rejected.
No deployment, data conversion or paid call is authorized by a passing test.

### 2026-10-19 verification

The archival regression first failed with `AttributeError: export_snapshot`.
After extending the existing owner, all eight persistent-center tests passed
against isolated Neo4j (`SEMANTICA_TEST_NEO4J_URI=bolt://127.0.0.1:17687`),
13.83 seconds. The regression covers exact exports, strict semantic rejection,
unknown scopes and stored digest corruption. No original snapshot is rewritten.
An independent read-only inventory found 41,268 stored snapshots with the empty
experimental field and zero populated occurrences. This is evidence for an
explicit empty-section contraction, not permission to discard nonempty data.

Before this follow-up, the installed wheel from `28728581` passed all 150 native
tests from `/private/tmp` using Python isolated mode and pytest importlib mode
(51.32 seconds), eliminating the earlier source-path ambiguity. Those tests do
not validate this additional method or prove the historical data readable.

## Upstream merge assessment

Pending: compare incoming native archive/export and snapshot owners. Reuse an
equivalent upstream export rather than maintaining two implementations. Re-run
snapshot integrity, strict validation, isolation and consumer migration tests.
