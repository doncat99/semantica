"""Load a read-only Explorer scene from its admitted native publication."""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(self, path, project, generation):
        from ..semantic_query import admit_native_store
        from ..triplet_store.oxigraph_store import OxigraphStore
        location = Path(path)
        if not location.is_dir() or not (location / 'CURRENT').is_file() or not project or not generation:
            raise ValueError('Native Explorer requires an existing scoped publication store')
        self.reference = SimpleNamespace(path=str(location), project=project, generation=generation)
        self.owner = OxigraphStore(location)
        try:
            admit_native_store(self.reference, project, self.owner)
        except BaseException:
            self.owner.close()
            raise
        self.project, self.generation = project, generation
        self.selection = None
        self._lock = threading.Lock()
        self._cancelled = threading.Event()

    def page(self, selection, *, traversal=None):
        from ..semantic_query import admit_native_store
        from ..triplet_store.publication_records import PublicationRecords
        admit_native_store(self.reference, self.project, self.owner)
        query = dict(selection, limit=32 if selection['kind'] == 'incident' else 128, maxBytes=MAX_BYTES)
        page = (traversal.read(self.owner) if traversal is not None else
                PublicationRecords(self.owner, self.project).scene(self.generation, query))
        for field in ('nodes', 'links'):
            if not isinstance(page.get(field), list) or len(page[field]) > 128:
                raise ValueError('Native scene exceeds row budget')
        result = dict(page)
        result['project'] = self.project
        result['generation'] = self.generation
        return result

    def select(self, selection, install=None, *, cancel_event=None):
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
                traversal = None
                if not selection and query['kind'] in {'nodes', 'topology'}:
                    from ..semantic_query import NativeTraversal
                    traversal = NativeTraversal(SimpleNamespace(semantic_store=self.reference,
                        build_id=None, selection=dict(query, limit=128, maxBytes=MAX_BYTES)))
                while True:
                    if self._cancelled.is_set() or cancel_event is not None and cancel_event.is_set():
                        raise ValueError('Native scene selection cancelled')
                    if time.monotonic() > deadline:
                        raise ValueError('Native graph loading exceeded time budget')
                    page_query = dict(query, **({'after': after} if after else {}))
                    page = self.page(page_query, traversal=traversal) if traversal is not None else self.page(page_query)
                    size += len(json.dumps(page, ensure_ascii=False).encode())
                    if size > MAX_GRAPH_BYTES:
                        raise ValueError('Native graph exceeds in-memory Explorer byte budget')
                    if self._cancelled.is_set() or cancel_event is not None and cancel_event.is_set():
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
            if self._cancelled.is_set() or cancel_event is not None and cancel_event.is_set():
                raise ValueError('Native scene selection cancelled')
            if install is not None:
                install(session)
            self.selection = selected
            return session, self.selection
        finally:
            self._lock.release()

    def close(self):
        self.owner.close()


def install_native_scope(app, scope):
    resolve_scope = scope if callable(scope) else lambda: scope
    @app.get('/api/native-scope', dependencies=[Depends(require_auth)])
    def status():
        scope = resolve_scope()
        return dict(available=True,project=scope.project,generation=scope.generation,active=scope.selection)

    @app.get('/api/native-scope/catalog', dependencies=[Depends(require_auth)])
    def catalog(kind: str, after: str = None):
        scope = resolve_scope()
        if kind not in {'sources','communities','topics'}:
            raise HTTPException(422, 'Invalid native catalog')
        try:
            return scope.page(dict(kind=kind,**({'after':after} if after is not None else {})))
        except (ValueError, TimeoutError) as error:
            raise HTTPException(422,str(error)) from error

    @app.post('/api/native-scope/cancel', dependencies=[Depends(require_auth)])
    def cancel():
        scope = resolve_scope()
        scope._cancelled.set()
        return dict(state='cancellation_requested')

    @app.post('/api/native-scope/select', dependencies=[Depends(require_auth)])
    async def select(request: WebRequest):
        scope = resolve_scope()
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
