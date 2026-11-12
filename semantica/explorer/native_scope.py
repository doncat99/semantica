"""Load the native Explorer graph through bounded owner reads.

The owner relay runs in the host's existing worker queue. This client neither
opens RocksDB nor writes graph files. Transport cursors are consumed internally;
native graph algorithms receive the complete Project or optional filtered graph.
"""
import json
import threading
import time
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
MAX_GRAPH_BYTES = 128 * 1024 * 1024
MAX_LOAD_SECONDS = 300


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
        body = json.dumps(dict(selection, limit=32 if selection['kind'] == 'incident' else 128, maxBytes=MAX_BYTES)).encode()
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
                    or set(selection)-{'sourceId','communityId','topicId','nodeIds'}
                    or sum(key in selection for key in ('sourceId','communityId','topicId','nodeIds')) > 1):
                raise ValueError('Choose at most one source, community, topic, or explicit node set; no filter selects the Project')
            native = dict(kind='nodes', fields=['id','name','entityType'])
            if 'sourceId' in selection:
                native['sourceIds'] = [selection['sourceId']]
            if 'communityId' in selection:
                native['communityId'] = selection['communityId']
            if 'topicId' in selection:
                native['topicId'] = selection['topicId']
            if 'nodeIds' in selection:
                nodes = selection['nodeIds']
                if not isinstance(nodes,list) or not 1 <= len(nodes) <= 128:
                    raise ValueError('Explicit scene requires 1-128 node identities')
                native['nodeIds'] = nodes
            deadline = time.monotonic() + MAX_LOAD_SECONDS
            size = 0
            def pages(query, field):
                nonlocal size
                after = None
                while True:
                    if self._cancelled.is_set():
                        raise ValueError('Native scene selection cancelled')
                    if time.monotonic() > deadline:
                        raise ValueError('Native graph loading exceeded time budget')
                    page = self.page(dict(query, **({'after': after} if after else {})))
                    size += len(json.dumps(page, ensure_ascii=False).encode())
                    if size > MAX_GRAPH_BYTES:
                        raise ValueError('Native graph exceeds in-memory Explorer byte budget')
                    if self._cancelled.is_set():
                        raise ValueError('Native scene selection cancelled')
                    yield page[field]
                    cursor = page.get('next_cursor')
                    if cursor is None:
                        return
                    if not isinstance(cursor, str) or not cursor or after is not None and cursor <= after:
                        raise ValueError('Native graph cursor did not advance')
                    after = cursor
            graph = ContextGraph(advanced_analytics=False)
            identities = set()
            for batch in pages(native, 'nodes'):
                graph.add_nodes([dict(id=node['id'], type=node['entityType'], content=node['name'],
                    properties=node) for node in batch])
                identities.update(node['id'] for node in batch)
            fields = ['id','source','target','predicate','status']
            if not selection:
                queries = [dict(kind='topology', fields=fields)]
            elif len(identities) <= 128:
                queries = [dict(kind='links', visibleIds=sorted(identities), fields=fields)] if identities else []
            else:
                queries = (dict(kind='incident', nodeId=identity, fields=fields) for identity in sorted(identities))
            edge_ids = set()
            for query in queries:
                for batch in pages(query, 'links'):
                    edges = []
                    for edge in batch:
                        if edge['source'] not in identities or edge['target'] not in identities:
                            if not selection:
                                raise ValueError('Native Project relation has an unknown endpoint')
                            continue
                        if edge['id'] in edge_ids:
                            continue
                        edge_ids.add(edge['id'])
                        edges.append(dict(id=edge['id'], source_id=edge['source'], target_id=edge['target'],
                            type=edge['predicate'], properties=edge))
                    graph.add_edges(edges)
            session = GraphSession(graph)
            session._read_only = True
            selected = dict(selection=selection, nodeCount=len(identities),linkCount=len(edge_ids),
                project=self.project,generation=self.generation)
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
