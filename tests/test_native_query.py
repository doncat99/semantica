"""Real producer → acquired native owners → bounded query, without graph carriers."""
from hashlib import file_digest
import json

import pytest

from semantica.semantic_query import NativeQueryStore, QueryError, query_semantic_artifact
from semantica.semantic_query_schema import DocumentReaderRequest, NativeStoreRef, SemanticQueryRequest
from tests.test_native_extraction_handoff import build_child


@pytest.fixture
def ready(tmp_path, monkeypatch):
    # The fixture replaces network transport inside build_child. Restore it on exit.
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    result = build_child(tmp_path, stop_before_publication=False)
    path = next((tmp_path / 'published' / 'parsed').glob('*.json'))
    payload = json.loads(path.read_text())
    def ref(file, kind):
        with file.open('rb') as stream:
            digest = 'sha256:' + file_digest(stream, 'sha256').hexdigest()
        stat = file.stat()
        return dict(path=str(file), kind=kind, digest=digest, mediaType='application/json',
            installation=dict(digest=digest, identity=':'.join(map(str,
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))))
    reader = DocumentReaderRequest.model_validate(dict(id='reader', sourceId='source-1',
        materialRevision=payload['materialRevision'],
        representationRevision=payload['document']['representation_revision'],
        artifact=ref(path, 'document-representation'),
        readerIndex=ref(path.with_suffix('.reader.sqlite'), 'document-reader-index'),
        selection=dict(field='chunks', limit=128, maxBytes=262144)))
    product = result['semantic_store']
    result['semantic_store'] = dict(path=product['path'], project=product['projectId'], generation=product['generationId'])
    reference = NativeStoreRef.model_validate(result['semantic_store'])
    session = NativeQueryStore()
    session.acquire(reference)
    try:
        yield result, reader, session
    finally:
        session.close()


def request(result, **extra):
    return SemanticQueryRequest.model_validate(dict(id='query', method='query',
        projectId='project-1', generation=result['publication']['generation'],
        semanticStore=result['semantic_store'], nativeIndexes=result['native_indexes'],
        query='Ada', target='documents', **extra))


def test_actual_native_keyword_two_phase_hydration_and_reopen(ready):
    result, reader, session = ready
    selected = query_semantic_artifact(request(result), session=session)
    assert selected.required_source_ids == ['source-1']
    assert selected.contexts == [] and selected.total == 1
    metrics = {}
    query = request(result, sourceArtifacts={'source-1': reader.model_dump(by_alias=True)})
    answer = query_semantic_artifact(query, session=session, metrics=metrics)
    assert [hit.text for hit in answer.contexts] == ['Ada']
    assert answer.contexts[0].locator.native_ref == '#/document/text'
    assert 0 < metrics['canonicalBytes'] < 262144
    session.close()
    session.acquire(query.semantic_store)
    assert query_semantic_artifact(query, session=session) == answer


def test_actual_native_semantic_and_grounded_knowledge(ready):
    result, reader, session = ready
    descriptor = result['native_indexes']['semantic']['space']
    base = request(result, mode='semantic', embedding=dict(bindingId=descriptor['bindingId'],
        modelId=descriptor['modelId'], vector=[.25,.5,.75]),
        sourceArtifacts={'source-1':reader.model_dump(by_alias=True)})
    answer = query_semantic_artifact(base, session=session)
    assert len(answer.contexts) == 1
    assert answer.contexts[0].text == 'Ada Lovelace designed the Analytical Engine.'
    knowledge = query_semantic_artifact(base.model_copy(update={'target':'knowledge'}), session=session)
    assert {hit.kind for hit in knowledge.contexts} == {'entity','relation'}
    assert all(hit.evidence_ids and hit.source_ids == ['source-1'] for hit in knowledge.contexts)


def test_native_query_rejects_stale_receipt_and_source_binding(ready):
    result, reader, session = ready
    raw = request(result).model_dump(by_alias=True)
    raw['nativeIndexes']['keyword']['receipt']['store_id'] = 'sha256:'+'0'*64
    raw['nativeIndexes']['keyword']['installation']['digest'] = 'sha256:'+'0'*64
    with pytest.raises(QueryError, match='index differs'):
        query_semantic_artifact(SemanticQueryRequest.model_validate(raw), session=session)
    bad = reader.model_copy(update={'representation_revision':'representation:other'})
    with pytest.raises(QueryError, match='source membership'):
        query_semantic_artifact(request(result, sourceArtifacts={'source-1':bad.model_dump(by_alias=True)}), session=session)


def test_native_query_preserves_owner_scores_order_and_empty_source_scope(ready, monkeypatch):
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    from semantica.vector_store.vector_store import VectorRetriever
    result, reader, session = ready
    original = SQLiteVecStore.search_native_records
    selected = []
    def search(owner, *args, **kwargs):
        rows = original(owner, *args, **kwargs)
        assert len(rows) >= 2
        # Ascending, negative scores deliberately expose any query-side rerank.
        selected.extend(dict(row, score=-.75 + index*.25)
            for index, row in enumerate(reversed(rows)))
        return selected
    monkeypatch.setattr(SQLiteVecStore, 'search_native_records', search)
    monkeypatch.setattr(VectorRetriever, 'search_similar', lambda *args, **kwargs:
        pytest.fail('query must use the scoped native vector owner'))
    space = result['native_indexes']['semantic']['space']
    query = request(result, mode='semantic', embedding=dict(bindingId=space['bindingId'],
        modelId=space['modelId'], vector=[.25,.5,.75]),
        sourceArtifacts={'source-1': reader.model_dump(by_alias=True)})
    answer = query_semantic_artifact(query.model_copy(update={'target':'knowledge'}), session=session)
    assert [(hit.id, hit.score) for hit in answer.contexts] == [
        (row['id'], row['score']) for row in selected]
    # The same real native publication admits an explicit empty scope in both modes.
    monkeypatch.setattr(SQLiteVecStore, 'search_native_records', original)
    for candidate in (query, request(result, sourceArtifacts={'source-1':reader.model_dump(by_alias=True)})):
        empty = query_semantic_artifact(candidate.model_copy(update={'source_ids': []}), session=session)
        assert empty.contexts == [] and empty.required_source_ids is None


def test_retired_aggregate_snapshot_query_api_is_not_available():
    from importlib.util import find_spec
    from semantica.context.context_retriever import ContextRetriever

    assert find_spec('semantica.context.snapshot_search') is None
    assert not hasattr(ContextRetriever, 'prepare_snapshot_search')
    assert not hasattr(ContextRetriever, 'search_snapshot')
