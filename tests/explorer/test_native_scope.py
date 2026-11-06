import pytest

from semantica.explorer.native_scope import NativeScope, F


def node(identity='urn:canonical:one'):
    return dict(id=identity,type=F+'Entity',fields={F+'name':[dict(value='Acme')],
        F+'entityType':[dict(value='ORG')]},sourceIds=['source'],evidenceIds=['urn:evidence'])


def scope():
    return NativeScope('http://127.0.0.1:1234/scene','secret','project','generation')


def test_native_scope_explicit_page_and_existing_native_graph(monkeypatch):
    owner=scope()
    calls=[]
    def page(selection):
        calls.append(selection)
        if selection['kind']=='nodes':
            return dict(nodes=[node()],links=[],next_cursor='urn:canonical:one')
        return dict(nodes=[],links=[],next_cursor=None)
    monkeypatch.setattr(owner,'page',page)
    session,selected=owner.select(dict(sourceId='source'))
    assert session.read_only and session._source_path is None
    assert session.get_node('urn:canonical:one')['content']=='Acme'
    assert selected['next_cursor']=='urn:canonical:one'
    assert selected['selection']==dict(sourceId='source')
    assert calls==[dict(kind='nodes',sourceIds=['source']),dict(kind='links',visibleIds=['urn:canonical:one'])]
    owner.select(dict(sourceId='source',after=selected['next_cursor']))
    assert calls[-2]['after']=='urn:canonical:one'


def test_scope_overflow_is_an_error_not_a_silent_sample(monkeypatch):
    owner=scope()
    monkeypatch.setattr(owner,'page',lambda selection: dict(nodes=[node()],links=[],next_cursor='more'))
    with pytest.raises(ValueError,match='more than 128 links'):
        owner.select(dict(communityId='community:one'))
    assert owner.selection is None
    with pytest.raises(ValueError,match='exactly one'):
        owner.select({})
    with pytest.raises(ValueError,match='1-128'):
        owner.select(dict(nodeIds=['urn:one']*129))


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


def test_native_scope_api_does_not_load_project_until_selected(monkeypatch):
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
        assert client.get('/api/native-scope').json()['active'] is None
        assert calls==[]
        selected=client.post('/api/native-scope/select',json=dict(nodeIds=['urn:canonical:one']))
        assert selected.status_code==200,selected.text
        result=client.get('/api/graph/nodes').json()
        assert result['nodes'][0]['id']=='urn:canonical:one'
        assert client.post('/api/graph/nodes',json={}).status_code==403


@pytest.mark.parametrize('endpoint',['https://127.0.0.1/scene','http://example.com/scene','http://127.0.0.1/other'])
def test_native_scope_requires_loopback(endpoint):
    with pytest.raises(ValueError,match='loopback'):
        NativeScope(endpoint,'token','p','g')
