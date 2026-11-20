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


def test_vector_document_hydration_preserves_serializer_boundary_joins(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_query import _document_hit
    from semantica.semantic_document_reader import write_reader_artifact
    from tests.test_native_document_reader import payload, request as reader_request
    path = tmp_path/'reader.json'
    reader = reader_request(path, write_reader_artifact(path, payload(dict(format='text', text='Acme'))))
    request_value = SimpleNamespace(source_artifacts={reader.source_id: reader}, mode='semantic')
    hit = _document_hit(request_value, dict(sourceId=reader.source_id,
        ranges=[dict(nativeRef='#/document/text', start=0, end=4, joinBefore='\n', joinAfter='\n\n')]),
        dict(canonicalBytes=0), 0)
    assert hit.text == '\nAcme\n\n'
    assert hit.locator.quote == 'Acme'
    reference = hit.model_dump(by_alias=True,exclude_none=True)['documentReference']
    assert reference == dict(materialRevision=reader.material_revision,
        representationRevision=reader.representation_revision,
        ranges=[dict(nativeRef='#/document/text', start=0, end=4, joinBefore='\n', joinAfter='\n\n')])


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
    assert all(hit.text.strip() for hit in knowledge.contexts)
    assert next(hit for hit in knowledge.contexts if hit.kind == 'relation').text == 'designed'


def test_actual_native_path_reads_only_scoped_publication_pages(ready, monkeypatch):
    import semantica.semantic_query_worker as worker
    from semantica.semantic_worker_context import query_diagnostics
    result, _, session = ready
    reference = request(result).semantic_store
    owner = session.borrow(reference, 'project-1')
    topology = owner.read_publication_scene('project-1', reference.generation, dict(
        kind='topology', fields=['id', 'source', 'target', 'predicate'], limit=32, maxBytes=262144))
    assert topology['links'], 'fixture publication must contain a relation'
    relation = topology['links'][0]
    monkeypatch.setattr(worker._native_store, 'borrow', lambda selected, project: session.borrow(selected, project))
    metrics = {}
    token = query_diagnostics.set(metrics)
    try:
        response = worker.handle_request(dict(id='native-path', method='path', protocol='semantica.semantic-query.v1',
            params=dict(projectId='project-1', semanticStore=result['semantic_store'],
                source=relation['source'], target=relation['target'], maxPages=32, maxEdges=1024,
                maxNodes=256, maxDepth=6, maxMillis=2000, maxBytes=2097152)))
    finally:
        query_diagnostics.reset(token)
    assert response['ok'] and response['result']['status'] == 'found'
    assert response['result']['relations'][0]['id'] == relation['id']
    assert response['result']['readBytes'] > 0
    assert metrics['pathPages'] >= 2 and metrics['pathIncidentPages'] >= 1
    assert metrics['pathIncidentEdges'] >= 1 and metrics['pathReadBytes'] > 0


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


def test_hybrid_native_knowledge_fuses_ids_preserves_evidence_and_reopens(ready, monkeypatch):
    from semantica.vector_store.hybrid_search import SearchRanker
    result, reader, session = ready
    space = result['native_indexes']['semantic']['space']
    raw = request(result).model_dump(by_alias=True)
    raw.update(mode='hybrid', target='knowledge', topK=3, limit=1,
        embedding=dict(bindingId=space['bindingId'], modelId=space['modelId'], vector=[.25,.5,.75]))
    query = SemanticQueryRequest.model_validate(raw)
    calls = []
    original = SearchRanker.rank
    def rank(self, results, **kwargs):
        calls.append(results)
        return original(self, results, **kwargs)
    monkeypatch.setattr(SearchRanker, 'rank', rank)
    selected = query_semantic_artifact(query, session=session)
    assert selected.contexts == [] and selected.required_source_ids == ['source-1']
    hydrated = SemanticQueryRequest.model_validate({**raw,
        'sourceArtifacts': {'source-1': reader.model_dump(by_alias=True)}})
    answer = query_semantic_artifact(hydrated, session=session)
    assert calls and all(len(channels) == 2 for channels in calls)
    assert len(answer.contexts) == 1 and answer.next_offset == 1
    hit = answer.contexts[0]
    assert hit.evidence_ids and hit.source_ids == ['source-1']
    keyword, semantic = calls[-1]
    assert hit.retrieval.keyword_rank == next(n for n, row in enumerate(keyword, 1) if row['id'] == hit.id)
    assert hit.retrieval.semantic_rank == next(n for n, row in enumerate(semantic, 1) if row['id'] == hit.id)
    assert hit.score == pytest.approx(1 / (60 + hit.retrieval.keyword_rank)
        + 1 / (60 + hit.retrieval.semantic_rank))
    assert hit.retrieval.method == 'reciprocal_rank_fusion'
    assert answer.hybrid_candidates.keyword_positions == 1
    pages = answer.contexts[:]
    offset = answer.next_offset
    while offset is not None:
        page = query_semantic_artifact(hydrated.model_copy(update={'offset': offset}), session=session)
        pages.extend(page.contexts)
        offset = page.next_offset
    assert len(pages) == len({item.id for item in pages}) == 3
    session.close()
    session.acquire(query.semantic_store)
    assert query_semantic_artifact(hydrated, session=session) == answer
    for scope in ([], ['not-granted']):
        empty = query_semantic_artifact(hydrated.model_copy(update={'source_ids': scope}), session=session)
        assert empty.contexts == []
    stale = hydrated.model_dump(by_alias=True)
    stale['nativeIndexes']['semantic']['receipt']['recipe_digest'] = '0'*64
    with pytest.raises(QueryError, match='index differs'):
        query_semantic_artifact(SemanticQueryRequest.model_validate(stale), session=session)


def test_hybrid_rejects_missing_embedding_document_units_and_unbounded_candidates(ready):
    from pydantic import ValidationError
    result, _, _ = ready
    raw = request(result).model_dump(by_alias=True)
    space = result['native_indexes']['semantic']['space']
    raw.update(mode='hybrid', target='knowledge',
        embedding=dict(bindingId=space['bindingId'], modelId=space['modelId'], vector=[.25,.5,.75]))
    for changes in ({'embedding': None}, {'target': 'documents'}, {'topK': 129},
                    {'position': ['source-1', '#/document/text', 0, 3]}):
        with pytest.raises(ValidationError):
            SemanticQueryRequest.model_validate({**raw, **changes})


def test_hybrid_union_and_candidate_bounds_do_not_depend_on_last_channel_metadata():
    from types import SimpleNamespace
    from semantica.semantic_query import _hybrid_records

    class Owner:
        def read_grounded_candidates(self, project, generation, positions, **budgets):
            assert project == 'project' and generation == 'generation'
            assert positions == [dict(source='lexical-source', nativeRef='#/document/text', start=0, end=1)]
            assert budgets == dict(limit=128, max_bytes=262144)
            return [dict(id='shared', evidenceIds=['lexical-evidence'], sourceIds=['lexical-source']),
                dict(id='lexical-only', evidenceIds=['lexical-evidence'], sourceIds=['lexical-source'])]

    request_value = SimpleNamespace(project_id='project', generation='generation', top_k=2, limit=1, offset=0)
    page = dict(items=[dict(sourceId='lexical-source', nativeRef='#/document/text', start=0, end=1)],
        nextCursor=('lexical-source', '#/document/text', 0, 1))
    vector_rows = [dict(id='shared', evidenceIds=['vector-evidence'], sourceIds=['vector-source'],
        evidenceNextCursor=('shared', 'vector-evidence')),
        dict(id='vector-only', evidenceIds=['vector-evidence'], sourceIds=['vector-source'])]
    selected, metadata, following = _hybrid_records(request_value, Owner(), page, vector_rows)
    assert selected[0]['id'] == 'shared'
    assert selected[0]['evidenceIds'] == ['lexical-evidence', 'vector-evidence']
    assert selected[0]['sourceIds'] == ['lexical-source', 'vector-source']
    assert selected[0]['evidenceNextCursor'] == ('shared', 'vector-evidence')
    assert metadata['keyword_truncated'] and metadata['semantic_budget_reached']
    assert metadata['fused_records'] == 3 and metadata['fused_truncated']
    assert following == 1


def test_document_hit_retains_every_scalar_range_and_identity(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_query import _document_hit
    from semantica.semantic_document_reader import write_reader_artifact
    from tests.test_native_document_reader import payload, request as reader_request
    path = tmp_path/'reader.json'
    reader = reader_request(path, write_reader_artifact(path, payload(dict(format='text', text='Acme emits less.'))))
    request_value = SimpleNamespace(source_artifacts={reader.source_id: reader}, mode='semantic')
    ranges = [dict(nativeRef='#/document/text', start=0, end=4),
        dict(nativeRef='#/document/text', start=5, end=16, joinBefore=' ')]
    hit = _document_hit(request_value, dict(sourceId=reader.source_id, ranges=ranges), dict(canonicalBytes=0), 0)
    assert hit.text == 'Acme emits less.'
    assert hit.model_dump(by_alias=True,exclude_none=True)['documentReference']['ranges'] == ranges
    changed = _document_hit(request_value, dict(sourceId=reader.source_id,
        ranges=[ranges[0], {**ranges[1], 'joinBefore':'\n'}]), dict(canonicalBytes=0), 0)
    assert changed.id != hit.id
