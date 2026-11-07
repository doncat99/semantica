# Stable physical paid extraction identities

- Record ID: 2026-11-07-stable-extraction-operation-identity
- Date: 2026-11-07
- Status: verified-in-stated-scope; installed migration pending
- Fork base revision: 765c0ef2d1e868e074ca31068e9db90a0672a9c2
- Upstream reference: not reviewed
- Related: paid-semantic-producer-identity and stable-embedding-operation-identity records of this date

## Reason and native assessment

The prior offline rebind copied entire paid entities/relations under every new recipe. Native `ExtractionRecords` already owns those facts and receipts, `OxigraphStore` exposes adoption/read, and `PublicationRecords` verifies operation references. Repair those owners in place. The logical-to-physical index is metadata in the same native store, not another fact carrier.

## Changes and consumers

`ExtractionRecords` commits one current logical binding to its stable physical operation. `OxigraphStore` resolves operation IDs through that index. Explicit offline rebind verifies the exact prior input, allows only recipe changes, atomically updates binding metadata/index, preserves owned fact subjects, paid receipts and accepted digest, and rejects collisions. Original paid recipe remains audit metadata. `ClassificationRecords` uses the same native mechanism with its own binding fields. `PublicationRecords` verifies physical references through the current index and explicit extraction stage. Normal reads do not discover or adopt pre-index data; that requires the explicit offline maintenance tool.

Proof-cache hits validate the current index before returning and include logical identity. Stale acquired handles and orphan index links fail explicitly. Retirement deletes incoming logical links with their exact obsolete physical operation; protected-current links are not historical result copies. No model, network, dependency or extra fact store is introduced.

## Verification and limits

Red specifications reproduced missing metadata rebind, then proved stable fact subjects and receipts, relation references, target collision rejection, pre-index explicit admission, stale handles and orphan rejection. Focused extraction/native-record/explanation regressions passed before the independent proof-cache review; final integrated run is recorded in the implementation handoff. No full-repository suite or live-data migration is claimed here. Original materials and edits are outside the mutation scope.

## Upstream merge assessment

Pending incoming-upstream review. Preserve one native owner and rerun extraction/classification rebind, publication reference and retirement closure tests after conflicts. Remove this patch only if upstream provides the same stable physical-identity contract.

## Integrated verification, 2026-11-07

The focused native extraction, classification, embedding, recipe, publication, query and retirement selection passed 205 tests in 47.50s. Final offline pre-index migration regression physically removed logical mapping graphs, reproduced two failures, and passed all 8 migration tests after full offline receipt verification (6.06s). `git diff --check` passed. Installed migration remains pending; this result does not claim live-data or packaged-product acceptance.
