import pytest

from semantica.explorer.native_scope import NativeScope


def node(identity='urn:canonical:one'):
    return dict(id=identity, name='Acme', entityType='ORG')


def scope():
    return NativeScope('http://127.0.0.1:1234/scene','secret','project','generation')


def test_native_scope_complete_filter_and_existing_native_graph(monkeypatch):
    owner=scope()
    calls=[]
    def page(selection):
        calls.append(selection)
        if selection['kind']=='nodes':
            return dict(nodes=[node()],links=[],next_cursor=None)
        return dict(nodes=[],links=[],next_cursor=None)
    monkeypatch.setattr(owner,'page',page)
    session,selected=owner.select(dict(sourceId='source'))
    assert session.read_only and session._source_path is None
    assert session.get_node('urn:canonical:one')['content']=='Acme'
    assert session.get_node('urn:canonical:one')['type']=='Concept'
    assert session.get_node('urn:canonical:one')['properties']['entityType']=='ORG'
    assert 'next_cursor' not in selected
    assert selected['selection']==dict(sourceId='source')
    assert calls==[dict(kind='nodes',sourceIds=['source'],fields=['id','name','entityType']),dict(kind='links',visibleIds=['urn:canonical:one'],fields=['id','source','target','predicate','status'])]


@pytest.mark.parametrize('selection', [{}, {'sourceId': 'source'}])
def test_complete_multi_page_graph_preserves_cross_page_relations_and_status(monkeypatch, selection):
    owner = scope()
    calls = []
    def page(selection):
        calls.append(selection)
        if selection['kind'] == 'nodes':
            start = 128 if selection.get('after') else 0
            return dict(nodes=[node(f'urn:node:{i:03}') for i in range(start, 130 if start else 128)],
                links=[], next_cursor=None if start else 'urn:node:127')
        assert selection['kind'] in {'topology', 'incident'}
        assert selection['fields'][-1] == 'status'
        if selection['kind'] == 'incident' and selection['nodeId'] not in {'urn:node:000', 'urn:node:129'}:
            return dict(nodes=[], links=[], next_cursor=None)
        limit = 32 if selection['kind'] == 'incident' else 128
        start = int(selection['after'].rsplit(':', 1)[1]) + 1 if selection.get('after') else 0
        stop = min(start + limit, 130)
        return dict(nodes=[], links=[dict(id=f'urn:fact:{i:03}', source='urn:node:000', target='urn:node:129',
            predicate='owns', status='disputed') for i in range(start, stop)],
            next_cursor=f'urn:fact:{stop-1:03}' if stop < 130 else None)
    monkeypatch.setattr(owner, 'page', page)
    session, selected = owner.select(selection)
    assert selected['nodeCount'] == 130 and selected['linkCount'] == 130
    edges, total = session.get_edges(limit=200)
    assert total == 130 and all(edge['properties']['status'] == 'disputed' for edge in edges)
    assert {edge['id'] for edge in edges} == {f'urn:fact:{i:03}' for i in range(130)}
    assert calls[1]['after'] == 'urn:node:127'


def test_high_connection_source_is_read_to_completion(monkeypatch):
    owner = scope()
    def page(selection):
        if selection['kind'] == 'nodes':
            return dict(nodes=[node('urn:a'), node('urn:b')], links=[], next_cursor=None)
        assert selection['kind'] == 'links'
        start = 128 if selection.get('after') else 0
        return dict(nodes=[], links=[dict(id=f'urn:fact:{i:03}', source='urn:a', target='urn:b',
            predicate='owns', status='disputed') for i in range(start, 130 if start else 128)],
            next_cursor=None if start else 'urn:fact:127')
    monkeypatch.setattr(owner, 'page', page)
    session, selected = owner.select(dict(sourceId='source'))
    assert selected['linkCount'] == 130 and session.get_edges()[1] == 130


def test_scope_rejects_invalid_selection(monkeypatch):
    owner=scope()
    with pytest.raises(ValueError,match='at most one'):
        owner.select(dict(sourceId='source', topicId='topic'))
    with pytest.raises(ValueError,match='1-128'):
        owner.select(dict(nodeIds=['urn:one']*129))
    with pytest.raises(ValueError,match='at most one'):
        owner.select(dict(sourceId='source', linksAfter=42))


def test_failed_continuation_preserves_installed_graph(monkeypatch):
    import semantica.explorer.native_scope as module
    owner = scope()
    installed = []
    monkeypatch.setattr(owner, 'page', lambda selection: dict(
        nodes=[node()] if selection['kind'] == 'nodes' else [], links=[], next_cursor=None))
    owner.select({}, installed.append)
    previous = owner.selection
    monkeypatch.setattr(module, 'MAX_GRAPH_BYTES', 1)
    with pytest.raises(ValueError, match='byte budget'):
        owner.select({}, installed.append)
    assert owner.selection is previous and len(installed) == 1


def test_cancelled_selection_does_not_install_and_next_request_runs(monkeypatch):
    owner=scope()
    installed=[]
    def cancelled_page(selection):
        owner._cancelled.set()
        return dict(nodes=[node()],links=[],next_cursor=None)
    monkeypatch.setattr(owner,'page',cancelled_page)
    with pytest.raises(ValueError,match='cancelled'):
        owner.select(dict(sourceId='source'),installed.append)
    assert owner.selection is None and installed==[]
    monkeypatch.setattr(owner,'page',lambda selection:dict(
        nodes=[node()] if selection['kind']=='nodes' else [],links=[],next_cursor=None))
    owner.select(dict(sourceId='source'),installed.append)
    assert len(installed)==1 and owner.selection['nodeCount']==1


def test_native_scope_api_loads_bound_project_without_an_extra_selection(monkeypatch):
    from fastapi.testclient import TestClient
    from semantica.explorer.app import create_app
    monkeypatch.setenv('SEMANTICA_ALLOW_ANONYMOUS','true')
    owner=scope()
    calls=[]
    def page(selection):
        calls.append(selection)
        return dict(nodes=[node()] if selection['kind']=='nodes' else [],links=[],next_cursor=None)
    monkeypatch.setattr(owner,'page',page)
    with TestClient(create_app(native_scope=owner)) as client:
        active = client.get('/api/native-scope').json()['active']
        assert active['selection'] == {} and active['nodeCount'] == 1
        assert calls[0] == dict(kind='nodes', fields=['id','name','entityType'])
        assert len(calls) == 2
        assert client.get('/api/graph/nodes').json()['nodes'][0]['id']=='urn:canonical:one'
        selected=client.post('/api/native-scope/select',json=dict(nodeIds=['urn:canonical:one']))
        assert selected.status_code==200,selected.text
        result=client.get('/api/graph/nodes').json()
        assert result['nodes'][0]['id']=='urn:canonical:one'
        assert client.post('/api/graph/nodes',json={}).status_code==403


@pytest.mark.parametrize('endpoint',['https://127.0.0.1/scene','http://example.com/scene','http://127.0.0.1/other'])
def test_native_scope_requires_loopback(endpoint):
    with pytest.raises(ValueError,match='loopback'):
        NativeScope(endpoint,'token','p','g')


def test_project_startup_failure_is_not_an_empty_success(monkeypatch):
    from semantica.explorer.app import create_app
    owner = scope()
    def unavailable(selection):
        raise ValueError('Native scene publication changed')
    monkeypatch.setattr(owner, 'page', unavailable)
    with pytest.raises(ValueError, match='publication changed'):
        create_app(native_scope=owner)
    assert owner.selection is None


def test_completed_topic_scope_uses_same_concepts_and_fact_edges(monkeypatch):
    owner = scope()
    calls = []
    def page(selection):
        calls.append(selection)
        if selection['kind'] == 'nodes':
            return dict(nodes=[node('urn:a'), node('urn:b')], links=[], next_cursor=None)
        return dict(nodes=[], links=[dict(id='urn:fact', source='urn:a', target='urn:b',
            predicate='owns', status='disputed')], next_cursor=None)
    monkeypatch.setattr(owner, 'page', page)
    session, selected = owner.select(dict(topicId='topic:completed'))
    assert calls[0]['topicId'] == 'topic:completed'
    assert selected['nodeCount'] == 2 and selected['linkCount'] == 1
    assert session.get_node('urn:a')['type'] == 'Concept'
    edges, total = session.get_edges()
    assert total == 1
    assert edges[0]['properties']['status'] == 'disputed'
