"""Host service startup is separate from authorized Project scene lifetime."""
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession

CONTROL = {'X-Explorer-Control-Key': 'control-secret'}
BIND = dict(path='/native/store', projectId='project', generation='generation',
            apiKey='session-secret', origin='ontoscience://app')


@pytest.fixture
def native(monkeypatch):
    calls = []
    class Scope:
        def __init__(self, path, project, generation):
            calls.append(('open', path, project, generation))
            self.project, self.generation = project, generation
            self.selection = None
            self._cancelled = threading.Event()
        def select(self, selection, install=None, *, cancel_event=None):
            calls.append(('select', selection))
            graph = ContextGraph(advanced_analytics=False)
            graph.add_nodes([dict(id=self.project, type='test', content=self.project)])
            session = GraphSession(graph)
            session._read_only = True
            self.selection = dict(project=self.project, generation=self.generation)
            if install: install(session)
            return session, self.selection
        def close(self): calls.append(('close', self.project))
    monkeypatch.setattr('semantica.explorer.native_scope.NativeScope', Scope)
    monkeypatch.setenv('SEMANTICA_EXPLORER_CONTROL_KEY', 'control-secret')
    return calls


def test_service_boot_does_not_open_project_and_unbind_keeps_health(native):
    app = create_app(native_service=True)
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        assert native == []
        unbound = client.get('/api/graph/stats', headers={'Origin': 'http://127.0.0.1:55666'})
        assert unbound.status_code == 503
        assert unbound.json()['detail'] == 'No Project session is bound'
        assert unbound.headers['access-control-allow-origin'] == '*'
        assert client.post('/api/native-service/session', json=BIND).status_code == 401
        assert client.post('/api/native-service/session', json=BIND, headers=CONTROL).status_code == 200
        key = {'X-API-Key': BIND['apiKey'], 'Origin': BIND['origin']}
        assert client.get('/api/graph/stats', headers=key).json()['node_count'] == 1
        assert client.get('/api/native-scope', headers=key).json()['project'] == 'project'
        wrong_origin = client.get('/api/graph/stats', headers={**key, 'Origin': 'http://127.0.0.1:55666'})
        assert wrong_origin.status_code == 403
        assert wrong_origin.json()['detail'] == 'Project session origin does not match'
        assert wrong_origin.headers['access-control-allow-origin'] == '*'
        invalid_key = client.get('/api/graph/stats', headers={**key, 'X-API-Key': 'invalid'})
        assert invalid_key.status_code == 401
        assert invalid_key.json()['detail'] == 'Invalid Project session key'
        assert invalid_key.headers['access-control-allow-origin'] == '*'
        assert client.delete('/api/native-service/session', headers=CONTROL).status_code == 200
        assert client.get('/api/health').status_code == 200
        unbound_again = client.get('/api/graph/stats', headers=key)
        assert unbound_again.status_code == 503
        assert unbound_again.headers['access-control-allow-origin'] == '*'
        assert native[-1] == ('close', 'project')


def test_native_read_only_reasoning_and_patch_preflight(native):
    app = create_app(native_service=True)
    with TestClient(app) as client:
        client.post('/api/native-service/session', json=BIND, headers=CONTROL).raise_for_status()
        headers = {'X-API-Key': BIND['apiKey'], 'Origin': BIND['origin']}

        preview = client.post('/api/reason', headers=headers, json={
            'facts': ['inhibits(Metformin, mTOR)', 'causes(mTOR, Neurodegeneration)'],
            'rules': ['IF inhibits(Metformin, mTOR) AND causes(mTOR, Neurodegeneration) THEN candidate(Metformin, Alzheimer)'],
            'apply_to_graph': False,
        })
        assert preview.status_code == 200, preview.text
        assert preview.json()['mutated'] is False

        write = client.post('/api/reason', headers=headers, json={
            'facts': ['inhibits(Metformin, mTOR)'],
            'rules': ['IF inhibits(Metformin, mTOR) THEN candidate(Metformin, Alzheimer)'],
            'apply_to_graph': True,
        })
        assert write.status_code == 403
        assert write.json()['detail'] == 'Published graph is read-only'

        preflight = client.options('/api/ontology/example/toggle', headers={
            'Origin': BIND['origin'],
            'Access-Control-Request-Method': 'PATCH',
            'Access-Control-Request-Headers': 'content-type,x-api-key',
        })
        assert preflight.status_code == 200, preflight.text
        # Native HTTP routes apply the exact bound-origin check after the
        # preflight; CORS stays wildcard so the dynamic session origin works.
        assert preflight.headers['access-control-allow-origin'] == '*'
        assert 'PATCH' in preflight.headers['access-control-allow-methods']
        assert 'x-api-key' in preflight.headers['access-control-allow-headers'].lower()

        # Native HTTP access is protected by the exact session origin and API
        # key. CORS stays non-credentialed because the browser sends X-API-Key.
        assert 'access-control-allow-credentials' not in preflight.headers


def test_native_read_only_allows_calculation_posts_but_rejects_mutations(native):
    app = create_app(native_service=True)
    with TestClient(app) as client:
        client.post('/api/native-service/session', json=BIND, headers=CONTROL).raise_for_status()
        headers = {'X-API-Key': BIND['apiKey'], 'Origin': BIND['origin']}

        # Invalid/empty payloads must reach each endpoint's own request or
        # domain validation. A generic 403 here means the read-only fence has
        # silently disconnected a browser calculation.
        read_only_posts = [
            '/api/enrich/extract',
            '/api/enrich/links',
            '/api/enrich/dedup',
            '/api/ontology/suggest-alignments',
            '/api/ontology/shacl/generate',
            '/api/ontology/shacl/validate',
            '/api/ontology/versions/example/compare',
        ]
        for path in read_only_posts:
            response = client.post(path, headers=headers, json={})
            assert response.status_code != 403, (path, response.text)
            assert response.headers.get('access-control-allow-origin') == '*'

        for path in ['/api/import', '/api/enrich/merge', '/api/ontology/create']:
            response = client.post(path, headers=headers, json={})
            assert response.status_code == 403, (path, response.text)
            assert response.json()['detail'] == 'Published graph is read-only'
            assert response.headers.get('access-control-allow-origin') == '*'


def test_scope_switch_revokes_http_websocket_and_old_origin(native):
    app = create_app(native_service=True)
    with TestClient(app) as client:
        client.post('/api/native-service/session', json=BIND, headers=CONTROL).raise_for_status()
        with client.websocket_connect('/ws/graph-updates?api_key=session-secret', headers={'Origin': 'ontoscience://app'}) as ws:
            assert ws.receive_json()['event'] == 'connection_ack'
            next_bind = dict(BIND, projectId='other', apiKey='new-secret', origin='http://localhost:7777')
            client.post('/api/native-service/session', json=next_bind, headers=CONTROL).raise_for_status()
            assert ws.receive()['type'] == 'websocket.close'
        assert client.get('/api/graph/stats', headers={'X-API-Key': 'session-secret'}).status_code == 401
        assert client.get('/api/graph/stats', headers={'X-API-Key': 'new-secret'}).status_code == 200
        response = client.get('/api/graph/stats', headers={'X-API-Key': 'new-secret', 'Origin': 'ontoscience://app'})
        assert response.status_code == 403
        assert native.count(('close', 'project')) == 1


def test_cancel_in_progress_bind_does_not_publish_partial_scene(native, monkeypatch):
    from semantica.explorer.native_scope import NativeScope
    entered = threading.Event()
    def wait_for_cancel(scope, selection, install=None, *, cancel_event=None):
        entered.set()
        assert scope._cancelled.wait(5)
        raise ValueError('Native scene selection cancelled')
    monkeypatch.setattr(NativeScope, 'select', wait_for_cancel)
    with TestClient(create_app(native_service=True)) as client:
        result = []
        worker = threading.Thread(target=lambda: result.append(client.post('/api/native-service/session', json=BIND, headers=CONTROL)))
        worker.start()
        assert entered.wait(5)
        assert client.post('/api/native-service/cancel', headers=CONTROL).status_code == 200
        worker.join(5)
        assert not worker.is_alive()
        assert result[0].status_code == 422
        assert client.get('/api/graph/stats', headers={'X-API-Key': 'session-secret'}).status_code == 503
        assert native[-1] == ('close', 'project')


def test_native_service_cli_boot_and_host_pipe_shutdown_without_project(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    env = {**os.environ, 'SEMANTICA_EXPLORER_CONTROL_KEY': 'host-key',
           'SEMANTICA_API_KEY': 'initial-key', 'PYTHONDONTWRITEBYTECODE': '1'}
    with (tmp_path / 'service.log').open('wb') as output:
        child = subprocess.Popen([sys.executable, '-B', '-m', 'semantica.explorer',
            '--native-service', '--port', str(port), '--no-browser', '--read-only'],
            stdin=subprocess.PIPE, stdout=output, stderr=output,
            cwd=Path(__file__).resolve().parents[2], env=env)
        try:
            child.stdin.write(b'SEMANTICA_NATIVE_EXPLORER_ADMIT\n')
            child.stdin.flush()
            deadline = time.monotonic() + 20
            while True:
                assert child.poll() is None, (tmp_path / 'service.log').read_text()
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=.2) as response:
                        assert response.status == 200
                    break
                except OSError:
                    assert time.monotonic() < deadline, (tmp_path / 'service.log').read_text()
                    time.sleep(.05)
            child.stdin.close()
            assert child.wait(10) == 0
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(5)


def test_bind_waits_for_admitted_request_before_swapping_session(native):
    from fastapi import Request
    app = create_app(native_service=True)
    entered, finish = threading.Event(), threading.Event()
    @app.get('/api/testing/read')
    def slow_read(request: Request):
        entered.set()
        assert finish.wait(5)
        return {'project': request.app.state.session.get_nodes(limit=1)[0][0]['id']}
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as client:
        client.post('/api/native-service/session', json=BIND, headers=CONTROL).raise_for_status()
        reads, binds = [], []
        reader = threading.Thread(target=lambda: reads.append(client.get('/api/testing/read', headers={'X-API-Key': 'session-secret'})))
        reader.start()
        assert entered.wait(5)
        binder = threading.Thread(target=lambda: binds.append(client.post('/api/native-service/session', json=dict(BIND, projectId='other', apiKey='new-key'), headers=CONTROL)))
        binder.start()
        finish.set()
        reader.join(5)
        binder.join(5)
        assert not reader.is_alive() and not binder.is_alive()
        assert reads[0].json() == {'project': 'project'}
        assert binds[0].status_code == 200


@pytest.mark.parametrize('body,status', [
    (dict(BIND, origin='https://untrusted.example'), 422),
    (dict(BIND, unexpected=True), 422),
    (dict(BIND, path='x' * 262145), 413),
])
def test_native_control_rejects_unadmitted_or_oversized_binding(native, body, status):
    with TestClient(create_app(native_service=True)) as client:
        assert client.post('/api/native-service/session', json=body, headers=CONTROL).status_code == status
        assert native == []
        assert client.post('/api/native-service/session', json=BIND,
            headers={**CONTROL, 'Origin': 'ontoscience://app'}).status_code == 403
