# Native knowledge query relation text

- Record ID: 2026-11-07-native-query-relation-text
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 765c0ef2d1e868e074ca31068e9db90a0672a9c2
- Upstream reference: not inspected

## Reason and scope

The packaged Summary query failed host validation with `contexts[0].text is invalid`.
The native relation producer writes `urn:semantica:field:predicateName`; the query
projection instead selected the nonexistent `predicate` field, producing empty
relation text. Preserve host rejection of empty contexts and repair the producer's
existing native query consumer.

## Native capability assessment

- Owner: `semantic_query.py::_knowledge_hits`, called by `query_semantic_artifact`.
- Producer: `triplet_store/extraction_records.py::ExtractionRecords.write_relation`;
  `publication_records.py::_read` preserves its `predicateName` field unchanged.
- Consumer: OntoScience `querySemanticaNative`, then wiki compiler retrieval.
- Tests: `tests/test_native_query.py` exercises the actual producer, acquired
  publication and semantic hydration but previously checked kinds, not text.
- Decision: repair this projection in place; no alternate query path.

## Approach and actual changes

Replace the obsolete projected field with `predicateName`; require real semantic
query output to have nonempty text and the relation's exact stored predicate.
No storage, extraction, vector space or paid recipe change. No migration or
paid recomputation is required; the packaged native query artifact must change.
No new model calls, network access or dependencies.

## Verification and limitations

Red: the strengthened real-producer test failed at the nonempty hit assertion
(`1 failed in 2.38s`). Green: `.venv/bin/python -m pytest -q
tests/test_native_query.py tests/test_semantic_query_worker.py` passed all 16
tests in 5.91s. These tests use local fixtures without model/network calls.
Packaged product acceptance belongs to the host integration and is not claimed
by this source-only record.

## Upstream merge assessment

Pending: no incoming upstream revision reviewed. Retain until the same native
projection consumes the current relation producer field; rerun native query tests.
