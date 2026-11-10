"""Explicit bounded scenes for the native Explorer, without another store handle.

The owner relay runs in the host's existing worker queue. This client neither
opens RocksDB nor writes graph files. Native algorithms see only the selected
page, whose continuation is always exposed to the caller.
"""
import json
import threading
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from fastapi import Depends, HTTPException, Request as WebRequest
from starlette.concurrency import run_in_threadpool

from ..context.context_graph import ContextGraph
from .dependencies import require_auth
from .markdown_resources import MarkdownResourceRegistry
from .session import GraphSession

MAX_BYTES = 262144


class NativeScope:
    def __init__(self, endpoint, token, project, generation):
        address = urlsplit(endpoint)
        if (address.scheme != 'http' or address.hostname != '127.0.0.1'
                or address.path != '/scene' or address.query or address.fragment
                or address.username or not token or not project or not generation):
            raise ValueError('Native Explorer requires a scoped loopback relay')
        self.endpoint, self.token = endpoint, token
        self.project, self.generation = project, generation
        self.selection = None
        self._lock = threading.Lock()
        self._cancelled = threading.Event()

    def page(self, selection):
        body = json.dumps(dict(selection, limit=128, maxBytes=MAX_BYTES)).encode()
        if len(body) > MAX_BYTES:
            raise ValueError('Native scene selection exceeds byte budget')
        request = Request(self.endpoint, data=body, method='POST', headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=16) as response:
                data = response.read(MAX_BYTES + 1)
        except HTTPError as error:
            raise ValueError('Native scene owner rejected the scoped request ('+str(error.code)+')') from error
        if len(data) > MAX_BYTES:
            raise ValueError('Native scene exceeds byte budget')
        page = json.loads(data)
        if page.get('project') != self.project or page.get('generation') != self.generation:
            raise ValueError('Native scene publication changed')
        for field in ('nodes', 'links'):
            if not isinstance(page.get(field), list) or len(page[field]) > 128:
                raise ValueError('Native scene exceeds row budget')
        return page

    def select(self, selection, install=None):
        if not self._lock.acquire(blocking=False):
            raise ValueError('Another Explorer selection is in progress')
        try:
            self._cancelled.clear()
            if (not isinstance(selection, dict)
                    or set(selection)-{'sourceId','communityId','topicId','nodeIds','after'}
                    or sum(key in selection for key in ('sourceId','communityId','topicId','nodeIds')) != 1):
                raise ValueError('Choose exactly one source, community, topic, or explicit node set')
            native = dict(kind='nodes', fields=['id','name','entityType'])
            if 'sourceId' in selection:
                native['sourceIds'] = [selection['sourceId']]
            if 'communityId' in selection:
                native['communityId'] = selection['communityId']
            if 'topicId' in selection:
                native['topicId'] = selection['topicId']
            if 'nodeIds' in selection:
                nodes = selection['nodeIds']
                if (not isinstance(nodes,list) or not 1 <= len(nodes) <= 128
                        or 'after' in selection):
                    raise ValueError('Explicit scene requires 1-128 node identities')
                native['nodeIds'] = nodes
            if 'after' in selection:
                native['after'] = selection['after']
            page = self.page(native)
            if self._cancelled.is_set():
                raise ValueError('Native scene selection cancelled')
            identities = [node['id'] for node in page['nodes']]
            edges = self.page(dict(kind='links',visibleIds=identities,fields=['id','source','target','predicate','status'])) if identities else dict(links=[],next_cursor=None)
            if self._cancelled.is_set():
                raise ValueError('Native scene selection cancelled')
            if edges.get('next_cursor') is not None:
                raise ValueError('Selected page has more than 128 links; select fewer explicit nodes')
            # Keep both transport responses and the transient graph bounded.
            if len(json.dumps([page,edges],ensure_ascii=False).encode()) > MAX_BYTES:
                raise ValueError('Selected graph exceeds byte budget; select fewer explicit nodes')
            graph = ContextGraph(advanced_analytics=False)
            graph.add_nodes([dict(id=node['id'], type='Concept', content=node['name'],
                properties=node) for node in page['nodes']])
            graph.add_edges([dict(id=edge['id'],source_id=edge['source'],target_id=edge['target'],
                type=edge['predicate'],properties=edge) for edge in edges['links']])
            session = GraphSession(graph)
            session._read_only = True
            selected = dict(selection=selection,next_cursor=page.get('next_cursor'),
                nodeCount=len(identities),linkCount=len(edges['links']),project=self.project,generation=self.generation)
            if self._cancelled.is_set():
                raise ValueError('Native scene selection cancelled')
            if install is not None:
                install(session)
            self.selection = selected
            return session, self.selection
        finally:
            self._lock.release()


def install_native_scope(app, scope):
    @app.get('/api/native-scope', dependencies=[Depends(require_auth)])
    def status():
        return dict(available=True,project=scope.project,generation=scope.generation,active=scope.selection)

    @app.get('/api/native-scope/catalog', dependencies=[Depends(require_auth)])
    def catalog(kind: str, after: str = None):
        if kind not in {'sources','communities','topics'}:
            raise HTTPException(422, 'Invalid native catalog')
        try:
            return scope.page(dict(kind=kind,**({'after':after} if after is not None else {})))
        except (ValueError, TimeoutError) as error:
            raise HTTPException(422,str(error)) from error

    @app.post('/api/native-scope/cancel', dependencies=[Depends(require_auth)])
    def cancel():
        scope._cancelled.set()
        return dict(state='cancellation_requested')

    @app.post('/api/native-scope/select', dependencies=[Depends(require_auth)])
    async def select(request: WebRequest):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BYTES:
                raise HTTPException(413,'Native scene selection exceeds byte budget')
        def install(session):
            app.state.session = session
            app.state.markdown_resources = MarkdownResourceRegistry(session.graph, app.state.agent_memory)
        try:
            _, selection = await run_in_threadpool(scope.select,json.loads(raw),install)
            return selection
        except (ValueError, TimeoutError) as error:
            raise HTTPException(422,str(error)) from error
