"""The worker reads bounded native records, never an aggregate graph artifact."""
import pytest

from semantica.semantic_query_worker import handle_request
from semantica.semantic_extract.types import Entity
from semantica.triplet_store.oxigraph_store import OxigraphStore


def release_request(ref):
    return dict(id='release', method='release_store', params=dict(
        semanticStore={key: ref[key] for key in ('path', 'project')}))


def test_release_before_initial_publication_requires_no_fabricated_generation(tmp_path):
    from semantica.semantic_query_worker import _native_store
    _native_store.close()
    location = dict(path=str(tmp_path / 'not-created'), project='project-1')
    assert handle_request(release_request(location))['result'] == dict(project='project-1', released=True)
    assert not (tmp_path / 'not-created').exists()


@pytest.fixture
def publication(tmp_path, request):
    path = tmp_path / 'facts'
    owner = OxigraphStore(path)
    binding = dict(project='project-1', source='source-1', material='m', representation='r',
        recipe='recipe', model='model', specification='spec', parser='parser',
        grounding='grounding', window_start=0, window_end=4)
    entity = Entity('Acme', 'ORG', 0, 4, .9, {'mention_id': 'mention:0',
        'span_occurrence': 0, 'model': 'model', 'provider': 'fixture',
        'extraction_method': 'llm_typed'})
    owner.adopt_extraction(binding, 'entities', [entity], text='Acme', native_ranges=[dict(nativeRef='#/document/text', start=0, end=4, windowStart=0, windowEnd=4)], accepted_digest='paid')
    identity = next(q.subject.value for q in owner.store
        if q.predicate.value == 'urn:semantica:field:name')
    generation = owner.begin_publication('project-1', expected_generation=None,
        source_count=1, canonical_count=1)['generation']
    owner.stage_publication_sources('project-1', generation, [dict(source='source-1', material='m',
        representation='r', recipe='recipe', operation_count=1,
        operations=[owner.extraction_operation_id(binding, 'entities')])])
    owner.stage_publication_canonical('project-1', generation, [dict(id='urn:canonical:acme',
        representative=identity, members=[identity], selectors=[], member_count=len([identity]), selector_count=len([]))])
    evidence = owner.read_grounded_reference_page('project-1', generation,
        dict(source='source-1', nativeRef='#/document/text', start=0, end=4))['items'][0]['evidence']
    owner.stage_publication_topics('project-1', generation, [dict(id='topic:acme', title='Acme theme',
        report_id='report:overview', input_digest='sha256:input', members=['urn:canonical:acme'],
        member_count=1, evidence_ids=[evidence], evidence_count=1)])
    for index in range(getattr(request, 'param', 0)):
        owner.stage_publication_topics('project-1', generation, [dict(id=f'topic:batch:{index:04}', title='测量' * 100,
            report_id='report:overview', input_digest='sha256:input', members=['urn:canonical:acme'],
            member_count=1, evidence_ids=[evidence], evidence_count=1)])
    owner.activate_publication('project-1', generation, indexes={
        'keyword': dict(kind='native-keyword', store_id='keyword', recipe_digest='recipe'),
        'semantic': dict(kind='native-vector', store_id='vector', recipe_digest='recipe', space_id='space')})
    owner.close()
    del owner
    ref = dict(path=str(path), project='project-1', generation=generation)
    handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    try:
        yield ref, identity
    finally:
        from semantica.semantic_query_worker import _native_store
        _native_store.close()


def request(ref, selection):
    return dict(id='records', method='records', params=dict(projectId='project-1',
        semanticStore=ref, selection=selection))


def test_native_worker_exposes_topics_and_selected_members(publication):
    from semantica.utils.exceptions import ProcessingError
    ref, _ = publication
    def scene(selection):
        return handle_request(dict(id='scene', method='scene', params=dict(projectId=ref['project'],
            semanticStore=ref, selection=selection)))['result']
    result = scene(dict(kind='topics', limit=1))
    assert result['generation'] == ref['generation']
    assert result['nodes'][0]['id'] == 'topic:acme'
    assert result['nodes'][0]['organization']['basis'] == 'grounded-overview-section'
    assert [n['id'] for n in scene(dict(kind='nodes', topicId='topic:acme'))['nodes']] == ['urn:canonical:acme']
    assert scene(dict(kind='topics', after='topic:acme'))['nodes'] == []
    with pytest.raises(ProcessingError, match='byte budget'):
        scene(dict(kind='topics', maxBytes=8))


def test_native_record_worker_reads_exact_typed_fields(publication):
    ref, identity = publication
    result = handle_request(request(ref, dict(ids=[identity])))['result']
    assert result['generation'] == ref['generation']
    assert result['records'][0]['id'] == identity
    assert result['records'][0]['fields']['urn:semantica:field:name'][0]['value'] == 'Acme'
    assert result['next_cursor'] is None


def test_native_record_worker_reads_only_selected_bindings(publication):
    ref, identity = publication
    raw = dict(id='bindings', method='bindings', params=dict(projectId=ref['project'],
        semanticStore=ref, ids=[identity]))
    assert handle_request(raw)['result'] == dict(project=ref['project'], generation=ref['generation'],
        bindings=[dict(id=identity, source='source-1', material='m', representation='r')])
    for ids in ([identity] * 2, [str(index) for index in range(33)]):
        with pytest.raises(ValueError):
            handle_request(dict(raw, params=dict(raw['params'], ids=ids)))


def test_native_record_worker_enforces_explicit_source_grant(publication):
    ref, identity = publication
    assert handle_request(request(ref, dict(ids=[identity], sourceIds=['source-1'])))['ok']
    with pytest.raises(RuntimeError, match='outside'):
        handle_request(request(ref, dict(ids=[identity], sourceIds=['other-source'])))
    for sources in ([], ['source-1', 'source-1'], ['x' * 4097]):
        with pytest.raises(ValueError):
            handle_request(request(ref, dict(ids=[identity], sourceIds=sources)))
    with pytest.raises(ValueError):
        handle_request(request(ref, dict(sourceId='source-1', sourceIds=['source-1'])))


def test_native_record_worker_source_cursor_is_bounded(publication):
    ref, _ = publication
    result = handle_request(request(ref, dict(sourceId='source-1', limit=1)))['result']
    assert len(result['records']) == 1
    assert result['next_cursor']
    second = handle_request(request(ref, dict(sourceId='source-1', limit=1,
        after=result['next_cursor'])))['result']
    assert second['records'][0]['id'] != result['records'][0]['id']


@pytest.mark.parametrize('mutation', ['project', 'generation', 'missing', 'outside'])
def test_native_record_worker_rejects_unadmitted_identity(publication, mutation, tmp_path):
    ref, identity = publication
    if mutation == 'project':
        ref = dict(ref, project='another')
    elif mutation == 'generation':
        ref = dict(ref, generation='stale')
    elif mutation == 'missing':
        ref = dict(ref, path=str(tmp_path / 'missing'))
    else:
        identity = 'urn:another:record'
    with pytest.raises((ValueError, RuntimeError)):
        handle_request(request(ref, dict(ids=[identity])))
    assert not (tmp_path / 'missing').exists()


def test_native_record_worker_rejects_snapshot_and_excess_budget(publication):
    ref, identity = publication
    raw = request(ref, dict(ids=[identity]))
    raw['params']['snapshotId'] = 'obsolete'
    with pytest.raises(ValueError):
        handle_request(raw)
    for selection in (dict(ids=[str(n) for n in range(129)]),
                      dict(ids=[identity], maxBytes=262145)):
        with pytest.raises(ValueError):
            handle_request(request(ref, selection))


@pytest.mark.parametrize('state', ['pending', 'withdrawn'])
def test_native_record_worker_refuses_unpublished_native_state(publication, state):
    ref, identity = publication
    handle_request(release_request(ref))
    owner = OxigraphStore(ref['path'])
    if state == 'withdrawn':
        owner.withdraw_publication(ref['project'], expected_generation=ref['generation'])
    else:
        ref = dict(ref, generation=owner.begin_publication(ref['project'],
            expected_generation=ref['generation'], source_count=0, canonical_count=0)['generation'])
    owner.close()
    with pytest.raises(RuntimeError, match='not ready'):
        handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))


def test_native_record_worker_does_not_hide_native_lock_or_budget_failure(publication):
    ref, identity = publication
    handle_request(release_request(ref))
    owner = OxigraphStore(ref['path'])
    try:
        with pytest.raises(RuntimeError, match='initialize|lock|Lock'):
            handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    finally:
        owner.close()
    handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    with pytest.raises(RuntimeError, match='byte budget'):
        handle_request(request(ref, dict(ids=[identity], maxBytes=32)))


def test_native_record_worker_honors_cancellation_before_read(publication):
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    ref, identity = publication
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(RuntimeError, match='cancel'):
            handle_request(request(ref, dict(ids=[identity])))
    finally:
        query_cancellation.reset(token)


def test_native_store_handoff_reuses_owner_and_releases_only_exact_identity(publication):
    from semantica.semantic_query_worker import _native_store
    ref, identity = publication
    owner = _native_store.owner
    handle_request(request(ref, dict(ids=[identity])))
    handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    assert _native_store.owner is owner
    with pytest.raises(RuntimeError, match='identity'):
        handle_request(release_request(dict(ref, project='another')))
    assert _native_store.owner is owner
    ack = handle_request(release_request(ref))['result']
    assert ack == dict(project=ref['project'], released=True)
    with pytest.raises(RuntimeError, match='acquired'):
        handle_request(request(ref, dict(ids=[identity])))
    writer = OxigraphStore(ref['path'])
    writer.close()
    handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    assert handle_request(request(ref, dict(ids=[identity])))['ok']


def test_jsonl_native_store_release_ack_precedes_writer_open(publication):
    import json
    import select
    import subprocess
    import sys
    from semantica.utils.exceptions import ProcessingError
    ref, identity = publication
    handle_request(release_request(ref))
    child = subprocess.Popen([sys.executable, '-m', 'semantica.semantic_query_worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def exchange(raw):
        child.stdin.write(json.dumps(raw) + '\n')
        child.stdin.flush()
        assert select.select([child.stdout], [], [], 10)[0], 'native worker response deadline'
        return json.loads(child.stdout.readline())

    try:
        assert exchange(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))['ok']
        assert exchange(request(ref, dict(ids=[identity])))['ok']
        with pytest.raises(ProcessingError, match='lock|Lock'):
            OxigraphStore(ref['path'])
        assert exchange(release_request(ref))['result']['released'] is True
        writer = OxigraphStore(ref['path'])
        writer.close()
        assert exchange(dict(id='acquire-again', method='acquire_store',
            params=dict(semanticStore=ref)))['ok']
        assert exchange(request(ref, dict(ids=[identity])))['ok']
        child.stdin.close()
        assert child.wait(timeout=10) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        child.stdout.close()
        child.stderr.close()


def test_build_streams_are_explicit_interleaved_and_bound(publication):
    ref, _ = publication
    def call(method, **params):
        return handle_request(dict(id=method, method=method, params=dict(
            projectId=ref['project'], semanticStore=ref, buildId='build-1', **params)))['result']
    nodes = call('open_stream', selection=dict(kind='nodes', fields=['id'], limit=1))
    topics = call('open_stream', selection=dict(kind='topics', limit=1))
    assert nodes['streamId'] != topics['streamId']
    assert call('next_stream', streamId=nodes['streamId'], sequence=0)['page']['nodes'] == [dict(id='urn:canonical:acme')]
    assert call('next_stream', streamId=topics['streamId'], sequence=0)['page']['nodes'][0]['id'] == 'topic:acme'
    members = call('open_stream', selection=dict(kind='members', limit=1))
    assert call('next_stream', streamId=members['streamId'], sequence=0)['page']['members'] == [dict(parent='topic:acme', child='urn:canonical:acme')]
    with pytest.raises(Exception, match='stream'):
        call('next_stream', streamId=nodes['streamId'], sequence=0)
    assert call('close_stream', streamId=nodes['streamId'])['closed']


@pytest.mark.parametrize('publication', [260], indirect=True)
@pytest.mark.parametrize('budget', [262144, 2048])
def test_build_streams_cross_pages_once_without_losing_byte_lookahead(publication, monkeypatch, budget):
    import json
    from semantica.semantic_query_worker import _native_store
    ref, _ = publication
    native = _native_store.owner.store
    queries = []
    class ObservedStore:
        def query(self, query, *args, **kwargs):
            queries.append(query)
            return native.query(query, *args, **kwargs)
        def __getattr__(self, key):
            return getattr(native, key)
    monkeypatch.setattr(_native_store.owner, 'store', ObservedStore())
    def call(method, **params):
        return handle_request(dict(id=method, method=method, params=dict(
            projectId=ref['project'], semanticStore=ref, buildId='build-many', **params)))['result']
    handles = {kind: call('open_stream', selection=dict(kind=kind, limit=128, maxBytes=budget))['streamId']
               for kind in ('topics', 'members')}
    rows = {kind: [] for kind in handles}
    sequence = dict.fromkeys(handles, 0)
    while handles:
        for kind, handle in list(handles.items()):
            result = call('next_stream', streamId=handle, sequence=sequence[kind])
            sequence[kind] += 1
            assert len(json.dumps(result, ensure_ascii=False).encode()) <= budget
            batch = result['page']['nodes' if kind == 'topics' else 'members']
            assert len(batch) <= 128
            rows[kind].extend(batch)
            if result['done']:
                del handles[kind]
    assert len(rows['topics']) == 261
    assert len({row['id'] for row in rows['topics']}) == 261
    assert {row['id'] for row in rows['topics']} == {row['parent'] for row in rows['members']}
    assert len(rows['members']) == 261
    primary = [query for query in queries if 'ORDER BY ?id LIMIT' in query or 'ORDER BY ?id' in query or 'ORDER BY ?parent ?child' in query]
    assert len(primary) == 2, primary
    assert not _native_store.streams


def test_build_stream_lifecycle_rejects_foreign_replay_and_release(publication):
    from semantica.semantic_query_worker import _native_store
    ref, _ = publication
    def call(method, build='build', **params):
        return handle_request(dict(id=method, method=method, params=dict(
            projectId=ref['project'], semanticStore=ref, buildId=build, **params)))['result']
    handles = [call('open_stream', selection=dict(kind='topics'))['streamId'] for _ in range(8)]
    with pytest.raises(Exception, match='capacity'):
        call('open_stream', selection=dict(kind='topics'))
    with pytest.raises(Exception, match='identity'):
        call('next_stream', build='foreign', streamId=handles[0], sequence=0)
    with pytest.raises(Exception, match='sequence'):
        call('next_stream', streamId=handles[0], sequence=1)
    assert len(_native_store.streams) == 8
    call('close_stream', streamId=handles[0])
    assert len(_native_store.streams) == 7
    handle_request(release_request(ref))
    assert not _native_store.streams
    handle_request(dict(id='acquire', method='acquire_store', params=dict(semanticStore=ref)))
    with pytest.raises(Exception, match='missing'):
        call('next_stream', streamId=handles[1], sequence=0)
