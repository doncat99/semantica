"""JSONL worker for bounded native Semantica queries."""

from __future__ import annotations

import json
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any, Dict, Optional, TextIO

from pydantic import ValidationError

from .semantic_query import QueryError, NativeQueryStore, query_semantic_artifact
from .semantic_query_schema import (
    CanonicalRecordRequest,
    SemanticQueryRequest,
    QueryWorkerRequest,
    QueryWorkerResponse,
    NativeStoreControlRequest,
    NativeStoreReleaseRequest,
    NativeBindingRequest,
    NativeEvidenceRequest,
    NativeSceneRequest,
    NativePathRequest,
    NativeFactMembersRequest,
    NativeClassificationRequest,
    NativeClassificationBatchRequest,
)
from .semantic_worker_context import query_cancellation, query_phase
from .utils.exceptions import ProcessingError

MAX_FRAME_BYTES = 8 * 1024 * 1024
_native_store = NativeQueryStore()


def _encode_frame(payload: Dict[str, Any]) -> str:
    # Reject a giant scalar before JSONEncoder allocates its escaped copy.
    nodes = 0
    def check(value, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000:
            raise ValueError('query response object budget exceeded')
        if depth > 64:
            raise ValueError('query response depth budget exceeded')
        if isinstance(value, str) and len(value) >= MAX_FRAME_BYTES:
            raise ValueError('query response byte budget exceeded')
        if isinstance(value, dict):
            for key, item in value.items():
                check(key, depth + 1)
                check(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check(item, depth + 1)
    check(payload)
    output, size = io.StringIO(), 1  # Include the JSONL newline in the wire budget.
    for chunk in json.JSONEncoder(ensure_ascii=False, sort_keys=True).iterencode(payload):
        size += len(chunk.encode('utf-8'))
        if size > MAX_FRAME_BYTES:
            raise ValueError('query response byte budget exceeded')
        output.write(chunk)
    return output.getvalue() + '\n'


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None, metrics=None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
        if metrics is not None:
            payload['metrics'] = metrics
    else:
        payload["error"] = {"type": error.__class__.__name__ if error else "Error", "message": str(error)[:2048] if error else "unknown error"}
    return QueryWorkerResponse.model_validate(payload).model_dump(exclude_none=True, by_alias=True)


def handle_request(raw: Dict[str, Any]) -> Dict[str, Any]:
    request = QueryWorkerRequest.model_validate(raw)
    if request.method == "schema":
        return _response(request.id, True, result={"query": SemanticQueryRequest.model_json_schema()})
    if request.method in {'acquire_store', 'release_store'}:
        model = NativeStoreControlRequest if request.method == 'acquire_store' else NativeStoreReleaseRequest
        reference = model.model_validate(request.params).semantic_store
        with query_phase('openStore' if request.method == 'acquire_store' else 'releaseStore'):
            result = (_native_store.acquire if request.method == 'acquire_store' else _native_store.release)(reference)
        return _response(request.id, True, result=result)
    if request.method == "records":
        records_request = CanonicalRecordRequest.model_validate({
            **request.params,
            "protocol": request.protocol,
            "id": request.id,
            "method": request.method,
        })
        from .semantic_query import read_canonical_records
        result = read_canonical_records(records_request, _native_store)
        return _response(request.id, True, result=result)
    if request.method == 'fact_members':
        from .semantic_worker_context import check_query_cancellation
        selected = NativeFactMembersRequest.model_validate(request.params)
        check_query_cancellation()
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        result = owner.read_publication_fact_members(selected.project_id, selected.semantic_store.generation,
            selected.identity, after=selected.after, limit=selected.limit, max_bytes=selected.max_bytes)
        check_query_cancellation()
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=dict(project=selected.project_id,
            generation=selected.semantic_store.generation, **result))
    if request.method == 'section':
        selected = NativeSceneRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        result = owner.read_native_section_records(selected.project_id,
            selected.semantic_store.generation, selected.selection)
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=result)
    if request.method == 'bindings':
        from .semantic_worker_context import check_query_cancellation
        selected = NativeBindingRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        bindings = []
        for identity in selected.ids:
            check_query_cancellation()
            bindings.append(dict(id=identity, **owner.read_record_binding(
                selected.project_id, selected.semantic_store.generation, identity)))
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=dict(project=selected.project_id,
            generation=selected.semantic_store.generation, bindings=bindings))
    if request.method == 'classification_batch':
        from .semantic_worker_context import check_query_cancellation
        selected = NativeClassificationBatchRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        pages = []
        for selection in selected.selections:
            check_query_cancellation()
            pages.append(owner.read_native_classification_dimension(selected.project_id,
                selected.semantic_store.generation, selection.source_id, selection.dimension_id,
                after=selection.after, limit=selection.limit, max_bytes=selection.max_bytes))
            if len(json.dumps(pages, ensure_ascii=False).encode()) > selected.max_bytes:
                raise ProcessingError('Classification batch exceeds byte budget')
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=dict(project=selected.project_id,
            generation=selected.semantic_store.generation, pages=pages))
    if request.method == 'classification':
        selected = NativeClassificationRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        selection = selected.selection
        result = owner.read_native_classification_dimension(selected.project_id,
            selected.semantic_store.generation, selection.source_id, selection.dimension_id,
            after=selection.after, limit=selection.limit, max_bytes=selection.max_bytes)
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=result)
    if request.method in {'open_stream', 'next_stream', 'close_stream'}:
        from .semantic_query_schema import NativeStreamOpen, NativeStreamNext, NativeStreamClose
        schema = {'open_stream': NativeStreamOpen, 'next_stream': NativeStreamNext, 'close_stream': NativeStreamClose}[request.method]
        return _response(request.id, True, result=_native_store.stream(request.method, schema.model_validate(request.params)))
    if request.method == 'scene':
        selected = NativeSceneRequest.model_validate(request.params)
        with query_phase('openStore'):
            owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        result = owner.read_publication_scene(selected.project_id,
            selected.semantic_store.generation, selected.selection)
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=result)
    if request.method == 'analyze':
        from .semantic_query_schema import NativeAnalysisRequest
        from .kg.publication_analysis import analyze_publication
        selected = NativeAnalysisRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        result = analyze_publication(owner, selected.project_id, selected.semantic_store.generation)
        _native_store.borrow(selected.semantic_store, selected.project_id)
        return _response(request.id, True, result=result)
    if request.method == 'path':
        from collections import deque
        from .semantic_worker_context import check_query_cancellation, count_query_work
        selected = NativePathRequest.model_validate(request.params)
        check_query_cancellation()
        owner = _native_store.borrow(selected.semantic_store, selected.project_id)
        generation = selected.semantic_store.generation
        endpoints = list(dict.fromkeys((selected.source, selected.target)))
        admitted = owner.read_publication_scene(selected.project_id, generation, dict(
            kind='nodes', fields=['id'], nodeIds=endpoints, limit=len(endpoints), maxBytes=min(262144, selected.max_bytes)))
        pages = 1
        read_bytes = len(json.dumps(admitted, ensure_ascii=False).encode())
        count_query_work('pathEndpointRows', len(admitted.get('nodes', [])))
        count_query_work('pathPages')
        count_query_work('pathReadBytes', read_bytes)
        check_query_cancellation()
        _native_store.borrow(selected.semantic_store, selected.project_id)
        if admitted.get('next_cursor') is not None or {row.get('id') for row in admitted.get('nodes', [])} != set(endpoints):
            return _response(request.id, True, result=dict(project=selected.project_id, generation=generation,
                status='unavailable', nodeIds=[], relations=[], pages=1, inspectedEdges=0, visitedNodes=0,
                readBytes=read_bytes, detail='A path endpoint is unavailable in this publication.'))
        if selected.source == selected.target:
            return _response(request.id, True, result=dict(project=selected.project_id, generation=generation,
                status='found', nodeIds=[selected.source], relations=[], pages=1, inspectedEdges=0, visitedNodes=1, readBytes=read_bytes))

        started = time.monotonic()
        deadline = started + selected.max_millis / 1000
        queue = deque([(selected.source, 0)])
        visited = {selected.source}
        parents = {}
        inspected = 0
        depth_limited = False

        def response(status, *, detail=None, path=None):
            result = dict(project=selected.project_id, generation=generation, status=status,
                nodeIds=path[0] if path else [], relations=path[1] if path else [], pages=pages,
                inspectedEdges=inspected, visitedNodes=len(visited), readBytes=read_bytes)
            if detail:
                result['detail'] = detail
            check_query_cancellation()
            _native_store.borrow(selected.semantic_store, selected.project_id)
            return _response(request.id, True, result=result)

        while queue:
            check_query_cancellation()
            node, depth = queue.popleft()
            if depth >= selected.max_depth:
                depth_limited = True
                continue
            after = None
            while True:
                check_query_cancellation()
                if pages >= selected.max_pages or inspected >= selected.max_edges or time.monotonic() >= deadline:
                    return response('incomplete', detail='Path search reached its bounded traversal budget.')
                remaining_bytes = selected.max_bytes - read_bytes
                if remaining_bytes <= 0:
                    return response('incomplete', detail='Path search reached its total read-byte budget.')
                page = owner.read_publication_scene(selected.project_id, generation, dict(
                    kind='incident', fields=['id', 'source', 'target', 'predicate'], nodeId=node,
                    limit=32, maxBytes=min(262144, remaining_bytes), **({'after': after} if after else {})))
                pages += 1
                page_bytes = len(json.dumps(page, ensure_ascii=False).encode())
                read_bytes += page_bytes
                count_query_work('pathPages')
                count_query_work('pathReadBytes', page_bytes)
                count_query_work('pathIncidentPages')
                count_query_work('pathIncidentEdges', len(page.get('links', [])))
                if read_bytes > selected.max_bytes:
                    return response('incomplete', detail='Path search reached its total read-byte budget.')
                for link in page.get('links', []):
                    check_query_cancellation()
                    inspected += 1
                    next_node = link['target'] if link['source'] == node else link['source']
                    if next_node in visited:
                        continue
                    if len(visited) >= selected.max_nodes:
                        return response('incomplete', detail='Path search reached its visited-node budget.')
                    parents[next_node] = (node, dict(id=link['id'], source=link['source'], target=link['target'], type=link['predicate']))
                    visited.add(next_node)
                    if next_node == selected.target:
                        node_ids, relations, cursor = [next_node], [], next_node
                        while cursor != selected.source:
                            previous, relation = parents[cursor]
                            relations.append(relation)
                            node_ids.append(previous)
                            cursor = previous
                        return response('found', path=(list(reversed(node_ids)), list(reversed(relations))))
                    queue.append((next_node, depth + 1))
                after = page.get('next_cursor')
                if not after:
                    break
        return response('incomplete' if depth_limited else 'not_found', detail=(
            'Search reached the maximum path length.' if depth_limited else
            'No connection exists between the selected nodes in this publication.'))
    if request.method == 'evidence':
        from .vector_store.sqlite_vec_store import SQLiteVecStore
        selected = NativeEvidenceRequest.model_validate(request.params)
        owner = _native_store.borrow(selected.semantic_store,selected.project_id)
        descriptor=selected.native_indexes.semantic
        receipt=descriptor.receipt.model_dump(exclude_none=True)
        if owner.publication_status(selected.project_id)['indexes']['semantic'] != receipt:
            raise ProcessingError('Evidence index differs from current native publication')
        # Exact native ownership is checked before consulting derived associations.
        owner.read_record_binding(selected.project_id,selected.semantic_store.generation,selected.record_id)
        space=descriptor.space
        vectors=SQLiteVecStore.open_embedding_space(descriptor.path,
            dict(binding=space.space_id,model=space.model_id,recipe=space.recipe))
        if vectors is None:
            raise ProcessingError('Native evidence vector owner is missing')
        try:
            page=vectors.read_native_evidence(project=selected.project_id,
                generation=selected.semantic_store.generation,receipt=receipt,identity=selected.record_id,
                source_ids=selected.source_ids,after=selected.after,limit=selected.limit)
        finally:
            vectors.close()
        _native_store.borrow(selected.semantic_store,selected.project_id)
        return _response(request.id,True,result=dict(project=selected.project_id,
            generation=selected.semantic_store.generation,recordId=selected.record_id,**page))
    if request.method == 'reader':
        from .semantic_document_reader import read_document_reader
        from .semantic_query_schema import DocumentReaderRequest
        result = read_document_reader(DocumentReaderRequest.model_validate({**request.params, 'id': request.id}))
        return _response(request.id, True, result=result)
    query = SemanticQueryRequest.model_validate({
        **request.params,
        "protocol": request.protocol,
        "id": request.id,
        "method": request.method,
    })
    metrics = {}
    result = query_semantic_artifact(query, session=_native_store, metrics=metrics)
    return _response(request.id, True, result=result.model_dump(mode="json", by_alias=True), metrics=metrics)


def serve(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    # Keep stdin responsive to cancellation while executing one serial query.
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            return _serve(stdin, stdout, executor)
    finally:
        _native_store.close()


def _serve(stdin, stdout, executor) -> int:
    pending = None
    active_id = None
    canceled = Event()

    def execute(line, event):
        token = query_cancellation.set(event)
        try:
            _serve_line(line, stdout)
        finally:
            query_cancellation.reset(token)

    while True:
        line = stdin.readline(MAX_FRAME_BYTES + 1)
        if not line:
            break
        if len(line.encode('utf-8')) > MAX_FRAME_BYTES:
            # Do not drain an unbounded frame or interpret its remainder as another request.
            if pending is not None:
                pending.result()
            stdout.write(_encode_frame(_response(None, False, error=ValueError('query input byte budget exceeded'))))
            stdout.flush()
            return 1
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            raw = None
        if isinstance(raw, dict) and raw.get('method') == 'cancel':
            if (set(raw) != {'id', 'method', 'protocol'}
                    or raw['protocol'] != 'semantica.semantic-query.v1'):
                raise ValueError('invalid query cancellation frame')
            if raw['id'] == active_id:
                canceled.set()
            continue
        if pending is not None:
            pending.result()
        if (isinstance(raw, dict) and raw.get('method') == 'query'
                and isinstance(raw.get('params'), dict) and raw['params'].get('mode') in ('semantic', 'hybrid')):
            # Windows NumPy/BLAS DLL initialization can block on first import
            # inside an executor thread. Load the existing vector owner on the
            # serving thread before dispatch, only when a vector query needs it.
            from .vector_store.sqlite_vec_store import SQLiteVecStore
        active_id = raw.get('id') if isinstance(raw, dict) else None
        canceled = Event()
        pending = executor.submit(execute, line, canceled)
    if pending is not None:
        pending.result()
    return 0


def _serve_line(line, stdout):
    from .semantic_worker_context import query_diagnostics, query_phase
    metrics = {}
    token = query_diagnostics.set(metrics)
    request_id: Optional[str] = None
    try:
        raw = json.loads(line)
        if isinstance(raw, dict):
            candidate_id = raw.get("id")
            if isinstance(candidate_id, str) and len(candidate_id.encode('utf-8')) <= 256:
                request_id = candidate_id
        with query_phase('execution'):
            response = handle_request(raw)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError, QueryError, ProcessingError, OSError) as exc:
        response = _response(request_id, False, error=exc)
    finally:
        query_diagnostics.reset(token)
    response.setdefault('metrics', {}).update(metrics)
    try:
        from time import perf_counter
        encoding = perf_counter()
        frame = _encode_frame(response)
        response['metrics']['serializationMs'] = round((perf_counter() - encoding) * 1000, 3)
        response['metrics']['responseBytes'] = len(frame.encode())
        frame = _encode_frame(response)
    except (ValueError, TypeError) as exc:
        frame = _encode_frame(_response(request_id, False, error=exc))
    stdout.write(frame)
    stdout.flush()


def main() -> None:
    raise SystemExit(serve())


if __name__ == "__main__":
    main()
