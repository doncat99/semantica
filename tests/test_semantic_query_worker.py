"""JSONL lifecycle guarantees shared by every native query method."""
import io
import json
from hashlib import sha256
from pathlib import Path

import pytest


def _digest(path):
    return 'sha256:' + sha256(Path(path).read_bytes()).hexdigest()


def _installation(path, digest):
    from semantica.explorer.search_index import _file_identity
    return dict(digest=digest, identity=':'.join(map(str, _file_identity(Path(path)))))


def test_cancel_interrupts_active_query_and_reuses_worker(monkeypatch):
    import threading
    import semantica.semantic_query_worker as worker
    from semantica.semantic_worker_context import query_cancellation
    started = threading.Event()
    threads = []
    def handle(raw):
        threads.append(threading.get_ident())
        if raw['id'] == 'slow':
            started.set()
            assert query_cancellation.get().wait(1)
            raise worker.QueryError('query canceled')
        return dict(id=raw['id'], ok=True, result={})
    monkeypatch.setattr(worker, 'handle_request', handle)
    class Input(io.StringIO):
        def readline(self, size=-1):
            line = super().readline(size)
            if 'cancel' in line:
                assert started.wait(1)
            return line
    output = io.StringIO()
    assert worker.serve(Input('{"id":"slow"}\n{"id":"slow","method":"cancel","protocol":"semantica.semantic-query.v1"}\n{"id":"next"}\n'), output) == 0
    assert [(r['id'],r['ok']) for r in map(json.loads,output.getvalue().splitlines())] == [('slow',False),('next',True)]
    assert len(set(threads)) == 1


def test_worker_startup_does_not_import_aggregate_retrieval():
    import subprocess
    import sys
    result = subprocess.run([sys.executable,'-I','-B','-c',
        "import sys;sys.path.insert(0,sys.argv[1]);import semantica.semantic_query_worker;"
        "assert 'semantica.context.context_retriever' not in sys.modules;"
        "assert 'semantica.vector_store.sqlite_vec_store' not in sys.modules",
        str(Path(__file__).resolve().parents[1])],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('mode', ['semantic', 'hybrid'])
def test_semantic_query_initializes_native_vector_dependency_on_serving_thread(monkeypatch, mode):
    import builtins
    import threading
    import semantica.semantic_query_worker as worker
    imports, executions = [], []
    original_import = builtins.__import__
    serving_thread = threading.get_ident()
    def importing(name, *args, **kwargs):
        if name == 'vector_store.sqlite_vec_store':
            imports.append(threading.get_ident())
        return original_import(name, *args, **kwargs)
    def handle(raw):
        executions.append(threading.get_ident())
        assert imports == [serving_thread]
        return dict(id=raw['id'], ok=True, result={})
    monkeypatch.setattr(builtins, '__import__', importing)
    monkeypatch.setattr(worker, 'handle_request', handle)
    output = io.StringIO()
    assert worker.serve(io.StringIO(json.dumps(dict(id='semantic', method='query',
        params=dict(mode=mode))) + '\n'), output) == 0
    assert imports == [serving_thread]
    assert len(executions) == 1 and executions[0] != serving_thread
    assert json.loads(output.getvalue())['ok']


@pytest.mark.parametrize('ensure_ascii',[True,False])
def test_worker_rejects_oversized_input_before_parsing(monkeypatch,ensure_ascii):
    import semantica.semantic_query_worker as worker
    monkeypatch.setattr(worker,'MAX_FRAME_BYTES',256)
    monkeypatch.setattr(worker,'handle_request',lambda raw: pytest.fail('oversized frame reached handler'))
    output = io.StringIO()
    assert worker.serve(io.StringIO(json.dumps(dict(id='x',padding='界'*100),ensure_ascii=ensure_ascii)+'\n'),output) == 1
    assert 'budget' in json.loads(output.getvalue())['error']['message']


def test_worker_bounds_response_and_continues_session(monkeypatch):
    import semantica.semantic_query_worker as worker
    monkeypatch.setattr(worker,'MAX_FRAME_BYTES',256)
    monkeypatch.setattr(worker,'handle_request',lambda raw: dict(id=raw['id'],ok=True,
        result=dict(text='界'*(1000 if raw['id']=='large' else 1))))
    output = io.StringIO()
    assert worker.serve(io.StringIO('{"id":"large"}\n{"id":"small"}\n'),output) == 0
    lines = output.getvalue().splitlines()
    assert all(len(line.encode()) < 256 for line in lines)
    assert not json.loads(lines[0])['ok']
    assert json.loads(lines[1])['result']['text'] == '界'
@pytest.mark.parametrize('fields', [None, ['id'], ['id', 'name', 'sourceIds']])
def test_scene_rpc_delegates_exact_scope_and_selection(monkeypatch, fields):
    from semantica import semantic_query_worker as worker
    from pydantic import ValidationError
    import pytest
    selected = dict(fields=['id', 'type', 'recordId', 'fields', 'sourceIds', 'evidenceIds', 'members', 'selectors'], kind='nodes', limit=17, maxBytes=8192)
    if fields is not None:
        selected['fields'] = fields
    calls = []
    class Owner:
        def read_publication_scene(self, project, generation, selection):
            calls.append((project, generation, selection))
            return dict(project=project, generation=generation, nodes=[], links=[], next_cursor=None)
    monkeypatch.setattr(worker._native_store, 'borrow', lambda reference, project: Owner())
    raw = dict(id='scene',method='scene',protocol='semantica.semantic-query.v1',
        params=dict(projectId='project-p',semanticStore=dict(path='/tmp/semantica-scene-test',project='project-p',generation='g'),selection=selected))
    assert worker.handle_request(raw)['result']['generation'] == 'g'
    assert calls == [('project-p', 'g', selected)]
    raw['params']['projectId'] = 'other'
    with pytest.raises(ValidationError,match='project'):
        worker.handle_request(raw)
    assert len(calls) == 1


def test_analysis_rpc_fences_project_before_and_after_calculation(monkeypatch):
    from semantica import semantic_query_worker as worker
    from semantica.kg import publication_analysis
    from pydantic import ValidationError
    calls = []
    owner = object()
    def borrow(reference, project):
        calls.append((reference.generation, project))
        return owner
    def analyze(selected, project, generation):
        assert selected is owner
        return dict(project=project, generation=generation, status='incomplete', metrics={})
    monkeypatch.setattr(worker._native_store, 'borrow', borrow)
    monkeypatch.setattr(publication_analysis, 'analyze_publication', analyze)
    raw = dict(id='analysis', method='analyze', protocol='semantica.semantic-query.v1',
        params=dict(projectId='project-p', semanticStore=dict(path='/tmp/native-analysis-test', project='project-p', generation='g')))
    assert worker.handle_request(raw)['result']['status'] == 'incomplete'
    assert calls == [('g', 'project-p'), ('g', 'project-p')]
    raw['params']['projectId'] = 'other'
    with pytest.raises(ValidationError, match='project'):
        worker.handle_request(raw)
    assert len(calls) == 2


def test_native_neighborhood_contract_is_page_and_byte_bounded():
    from pydantic import ValidationError
    from semantica.semantic_query_schema import NativeSceneRequest

    base = dict(projectId='project-p',
        semanticStore=dict(path='/tmp/semantica-scene-test', project='project-p', generation='g'),
        selection=dict(kind='neighborhood', nodeId='urn:entity:one',
            fields=['id', 'source', 'target', 'predicate', 'status', 'validTime'], limit=32, maxBytes=262144))
    request = NativeSceneRequest.model_validate(base)
    assert request.selection['kind'] == 'neighborhood'
    for changes in ({'limit': 33}, {'limit': 0}, {'maxBytes': 262145}, {'after': ' '}, {'depth': 2}):
        with pytest.raises(ValidationError):
            NativeSceneRequest.model_validate({**base, 'selection': {**base['selection'], **changes}})


def test_fact_members_rpc_preserves_budget_and_fences_publication(monkeypatch):
    from semantica import semantic_query_worker as worker
    from pydantic import ValidationError
    calls, borrows = [], []
    class Owner:
        def read_publication_fact_members(self, project, generation, identity, **kwargs):
            calls.append((project, generation, identity, kwargs))
            return dict(id=identity, members=['urn:member:1'], member_count=1, next_cursor=None)
    def borrow(reference, project):
        borrows.append(project)
        return Owner()
    monkeypatch.setattr(worker._native_store, 'borrow', borrow)
    raw = dict(id='members', method='fact_members', protocol='semantica.semantic-query.v1', params=dict(
        projectId='project-p', semanticStore=dict(path='/tmp/native-facts', project='project-p', generation='g'),
        identity='urn:fact:1', after='urn:member:0', limit=17, maxBytes=8192))
    assert worker.handle_request(raw)['result']['members'] == ['urn:member:1']
    assert calls == [('project-p', 'g', 'urn:fact:1', dict(after='urn:member:0', limit=17, max_bytes=8192))]
    assert borrows == ['project-p', 'project-p']
    raw['params']['projectId'] = 'other'
    with pytest.raises(ValidationError, match='project'):
        worker.handle_request(raw)


def test_classification_rpc_preserves_dimension_and_budget_and_fences_borrow(monkeypatch):
    from semantica import semantic_query_worker as worker
    calls, borrows = [], []
    class Owner:
        def read_native_classification_dimension(self, project, generation, source, dimension, **kwargs):
            calls.append((project, generation, source, dimension, kwargs))
            return dict(project=project, generation=generation, sourceId=source, assignments=[])
    def borrow(reference, project):
        borrows.append(project)
        return Owner()
    monkeypatch.setattr(worker._native_store, 'borrow', borrow)
    raw = dict(id='classification', method='classification', protocol='semantica.semantic-query.v1', params=dict(
        projectId='project-p', semanticStore=dict(path='/tmp/native-classification', project='project-p', generation='g'),
        selection=dict(sourceId='source-s', dimensionId='framework', after='gri', limit=5, maxBytes=8192)))
    assert worker.handle_request(raw)['result']['sourceId'] == 'source-s'
    assert calls == [('project-p', 'g', 'source-s', 'framework', dict(after='gri', limit=5, max_bytes=8192))]
    assert borrows == ['project-p', 'project-p']
    raw['params']['selection']['limit'] = 129
    with pytest.raises(ValueError):
        worker.handle_request(raw)
    assert len(calls) == 1


def test_native_path_is_project_scoped_budgeted_and_cancellable(monkeypatch):
    from threading import Event
    from semantica import semantic_query_worker as worker
    from semantica.semantic_worker_context import query_cancellation, query_diagnostics
    from semantica.utils.exceptions import ProcessingError

    calls, borrows = [], []
    canceled = Event()
    class Owner:
        def read_publication_scene(self, project, generation, selection):
            calls.append((project, generation, selection))
            if selection['kind'] == 'nodes':
                return dict(project=project, generation=generation,
                    nodes=[dict(id='urn:node:a'), dict(id='urn:node:b')], links=[], next_cursor=None)
            canceled.set()
            return dict(project=project, generation=generation, nodes=[], links=[
                dict(id='urn:edge:ab', source='urn:node:a', target='urn:node:b', predicate='supports')], next_cursor=None)
    def borrow(reference, project):
        borrows.append(project)
        return Owner()
    monkeypatch.setattr(worker._native_store, 'borrow', borrow)
    reference = dict(path='/tmp/native-path', project='project-p', generation='generation-g')
    params = dict(projectId='project-p', semanticStore=reference,
        source='urn:node:a', target='urn:node:b', maxPages=2, maxEdges=8,
        maxNodes=8, maxDepth=2, maxMillis=1000, maxBytes=2048)
    diagnostics = {}
    metric_token = query_diagnostics.set(diagnostics)
    cancellation_token = query_cancellation.set(canceled)
    try:
        with pytest.raises(ProcessingError, match='query canceled'):
            worker.handle_request(dict(id='path', method='path', protocol='semantica.semantic-query.v1', params=params))
    finally:
        query_cancellation.reset(cancellation_token)
        query_diagnostics.reset(metric_token)
    assert calls[0][2] == dict(kind='nodes', fields=['id'], nodeIds=['urn:node:a', 'urn:node:b'], limit=2, maxBytes=2048)
    assert calls[1][2]['kind'] == 'incident' and calls[1][2]['limit'] == 32
    assert calls[1][2]['maxBytes'] < 2048
    assert borrows == ['project-p', 'project-p']
    assert diagnostics['pathPages'] == 2
    assert diagnostics['pathIncidentPages'] == 1 and diagnostics['pathIncidentEdges'] == 1
    assert diagnostics['pathReadBytes'] > 0


def test_native_path_rejects_aggregate_budget_overrides():
    from pydantic import ValidationError
    from semantica.semantic_query_schema import NativePathRequest
    base = dict(projectId='project-p',
        semanticStore=dict(path='/tmp/native-path', project='project-p', generation='generation-g'),
        source='urn:node:a', target='urn:node:b')
    for changes in ({'maxPages': 33}, {'maxEdges': 1025}, {'maxNodes': 257},
                    {'maxDepth': 7}, {'maxMillis': 2001}, {'maxBytes': 2097153}):
        with pytest.raises(ValidationError):
            NativePathRequest.model_validate({**base, **changes})


def test_classification_batch_fences_project_and_limits_total_bytes(monkeypatch):
    from semantica import semantic_query_worker as worker
    from semantica.utils.exceptions import ProcessingError
    calls, borrows = [], []
    class Owner:
        def read_native_classification_dimension(self, project, generation, source, dimension, **kwargs):
            calls.append((source, dimension))
            return dict(project=project, generation=generation, sourceId=source, assignments=[])
    def borrow(reference, project):
        borrows.append(project)
        return Owner()
    monkeypatch.setattr(worker._native_store, 'borrow', borrow)
    raw = dict(id='batch', method='classification_batch', protocol='semantica.semantic-query.v1', params=dict(
        projectId='project-p', semanticStore=dict(path='/tmp/native-classification', project='project-p', generation='g'),
        selections=[dict(sourceId='s1'), dict(sourceId='s2', dimensionId='framework')], maxBytes=2048))
    result = worker.handle_request(raw)['result']
    assert [page['sourceId'] for page in result['pages']] == ['s1', 's2']
    assert calls == [('s1', None), ('s2', 'framework')]
    assert borrows == ['project-p', 'project-p']
    raw['params']['maxBytes'] = 1
    with pytest.raises(ProcessingError, match='byte budget'):
        worker.handle_request(raw)
    raw['params']['projectId'] = 'other'
    with pytest.raises(ValueError, match='project'):
        worker.handle_request(raw)


def test_section_rpc_delegates_only_requested_native_ranges(monkeypatch):
    from semantica import semantic_query_worker as worker
    calls = []
    class Owner:
        def read_native_section_records(self, project, generation, selection):
            calls.append((project, generation, selection))
            return dict(project=project, generation=generation, sourceId=selection['sourceId'], records=[], next_cursor=None)
    monkeypatch.setattr(worker._native_store, 'borrow', lambda reference, project: Owner())
    selection = dict(sourceId='source-s', positions=[dict(nativeRef='#/texts/0', start=10, end=20)], limit=8, maxBytes=8192)
    raw = dict(id='section', method='section', protocol='semantica.semantic-query.v1', params=dict(projectId='project-p',
        semanticStore=dict(path='/tmp/native-section', project='project-p', generation='g'), selection=selection))
    assert worker.handle_request(raw)['result']['records'] == []
    assert calls == [('project-p', 'g', selection)]
    raw['params']['projectId'] = 'foreign'
    with pytest.raises(ValueError):
        worker.handle_request(raw)
    assert len(calls) == 1
