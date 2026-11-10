"""Demand-driven native RDF, lexical and vector owner queries."""
from __future__ import annotations
import json
import sqlite3
import time
from hashlib import sha256
from pathlib import Path
from .semantic_query_schema import SemanticQueryRequest, SemanticQueryResult, QueryHit
from .utils.exceptions import ValidationError, ProcessingError


class QueryError(RuntimeError):
    """Native identity, scope or resource admission failed."""


def admit_native_store(reference, project, owner):
    from .semantic_worker_context import check_query_cancellation
    check_query_cancellation()
    if reference.project != project:
        raise QueryError('native store project differs from request project')
    status = owner.publication_status(project)
    if status is None or status['generation'] != reference.generation or status['state'] != 'ready':
        raise QueryError('native publication stale or not ready')
    check_query_cancellation()
    return owner


class NativeQueryStore:
    """One exclusive native handle in the existing serial query worker."""
    def __init__(self):
        self.owner = self.reference = None

    def acquire(self, reference):
        from .triplet_store.oxigraph_store import OxigraphStore
        from .semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        path = Path(reference.path)
        if not path.is_dir() or not (path / 'CURRENT').is_file():
            raise QueryError('native store does not exist')
        if self.owner is not None:
            if (reference.path, reference.project) != (self.reference.path, self.reference.project):
                raise QueryError('release the acquired native store before switching identity')
            admit_native_store(reference, reference.project, self.owner)
        else:
            try:
                candidate = OxigraphStore(path)
            except (ProcessingError, OSError) as exc:
                raise QueryError(str(exc)) from exc
            try:
                admit_native_store(reference, reference.project, candidate)
            except BaseException:
                candidate.close()
                raise
            self.owner = candidate
        self.reference = reference
        return dict(project=reference.project, generation=reference.generation, state='ready')

    def borrow(self, reference, project):
        if self.owner is None or (reference.path, project) != (self.reference.path, self.reference.project):
            raise QueryError('native store must be acquired for this identity')
        return admit_native_store(reference, project, self.owner)

    def release(self, reference):
        if self.owner is not None and (reference.path, reference.project) != (self.reference.path, self.reference.project):
            raise QueryError('native store release identity does not match')
        self.close()
        return dict(project=reference.project, released=True)

    def close(self):
        if self.owner is not None:
            self.owner.close()
            self.owner, self.reference = None, None


def read_canonical_records(request, session):
    try:
        from .semantic_worker_context import check_query_cancellation
        reference, selection = request.semantic_store, request.selection
        owner = session.borrow(reference, request.project_id)
        if selection.ids is not None:
            result = dict(records=owner.read_native_records(request.project_id, reference.generation,
                selection.ids, max_bytes=selection.max_bytes, source_ids=selection.source_ids), next_cursor=None)
        else:
            result = owner.read_publication_records(request.project_id, reference.generation,
                source=selection.source_id, after=selection.after, limit=selection.limit, max_bytes=selection.max_bytes)
        check_query_cancellation()
        return dict(project=request.project_id, generation=reference.generation, **result)
    except (ValueError, TypeError, OSError, ValidationError, ProcessingError) as exc:
        raise QueryError(str(exc)) from exc


def _receipt(value):
    return value.model_dump(exclude_none=True)


def query_semantic_artifact(request: SemanticQueryRequest, *, session, metrics=None) -> SemanticQueryResult:
    """Retrieve native addresses first; hydrate only the selected native ranges."""
    from .explorer.search_index import GraphSearchIndex
    from .semantic_worker_context import check_query_cancellation
    started = time.perf_counter()
    metrics = metrics if metrics is not None else {}
    metrics.update(retrievalMs=0., hydrationMs=0., canonicalBytes=0, recordBytes=0, sqliteVmStepsLowerBound=0)
    lexical = vector = None
    try:
        if request.method != 'query':
            raise QueryError('native query requires method=query')
        owner = session.borrow(request.semantic_store, request.project_id)
        status = owner.publication_status(request.project_id)
        for name in ('keyword', 'semantic'):
            descriptor = getattr(request.native_indexes, name)
            if descriptor is not None and _receipt(descriptor.receipt) != status['indexes'].get(name):
                raise QueryError('query index differs from the current native publication')
        before = time.perf_counter()
        if request.mode == 'keyword':
            descriptor = request.native_indexes.keyword
            lexical = GraphSearchIndex.open_native_positions(descriptor.path, project=request.project_id,
                generation=request.generation, receipt=_receipt(descriptor.receipt),
                installation_identity=tuple(map(int, descriptor.installation.identity.split(':'))))
            page = lexical.search_native_positions(request.query, source_ids=request.source_ids,
                limit=request.limit, after=request.position, navigation=request.navigation)
            rows = page['items']
        else:
            from .vector_store.sqlite_vec_store import SQLiteVecStore
            descriptor = request.native_indexes.semantic
            space = descriptor.space
            if (request.embedding.binding_id,request.embedding.model_id) != (space.binding_id,space.model_id):
                raise QueryError('query embedding differs from native space')
            vector = SQLiteVecStore.open_embedding_space(descriptor.path,
                dict(binding=space.space_id,model=space.model_id,recipe=space.recipe))
            if vector is None or vector.dimension != space.dimensions:
                raise QueryError('native vector owner missing or incompatible')
            search = vector.search_native_records if request.target == 'knowledge' else vector.search_native_ranges
            rows = search(request.embedding.vector, project=request.project_id,
                generation=request.generation,receipt=_receipt(descriptor.receipt),top_k=request.top_k or request.limit,
                source_ids=request.source_ids,page_limit=request.limit,offset=request.offset)
            page = dict(total=None,nextCursor=None,previousCursor=None,startOffset=request.offset)
        metrics['retrievalMs'] = (time.perf_counter()-before)*1000
        common = dict(project_id=request.project_id,generation=request.generation,query=request.query,
            total=page['total'],next_position=page['nextCursor'],previous_position=page['previousCursor'],
            start_offset=page['startOffset'],next_offset=page['startOffset']+len(rows) if page['nextCursor'] else None)
        if request.mode == 'semantic':
            following = request.offset + len(rows)
            common['next_offset'] = following if len(rows) == request.limit and following < (request.top_k or request.limit) else None
        required = sorted({source for row in rows for source in row.get('sourceIds',[row.get('sourceId')])})
        if request.source_artifacts is None:
            return SemanticQueryResult(**common,contexts=[],required_source_ids=required)
        if any(source not in request.source_artifacts for source in required):
            raise QueryError('hydration requires selected native reader references')
        before = time.perf_counter()
        for source in required:
            reader = request.source_artifacts[source]
            binding = owner.read_source_binding(request.project_id,request.generation,source)
            if (reader.material_revision,reader.representation_revision) != (binding['material'],binding['representation']):
                raise QueryError('selected reader differs from native source membership')
        if request.target == 'knowledge':
            if request.mode == 'semantic':
                records = owner.read_native_records(request.project_id,request.generation,
                    [row['id'] for row in rows],max_bytes=262144) if rows else []
                for record,row in zip(records,rows,strict=True):
                    record.update(evidenceIds=row['evidenceIds'],sourceIds=row['sourceIds'],score=row['score'],
                        evidenceNextCursor=row['evidenceNextCursor'])
            else:
                positions = [dict(source=row['sourceId'],**address) for row in rows
                    for address in row.get('ranges',[dict(nativeRef=row.get('nativeRef'),start=row.get('start'),end=row.get('end'))])]
                records = owner.read_grounded_candidates(request.project_id,request.generation,positions,
                    limit=request.limit,max_bytes=262144) if positions else []
            hits = _knowledge_hits(records)
        else:
            hits = [_document_hit(request,row,metrics,page['startOffset']+n) for n,row in enumerate(rows)]
        check_query_cancellation()
        admit_native_store(request.semantic_store,request.project_id,owner)
        metrics['hydrationMs'] = (time.perf_counter()-before)*1000
        result = SemanticQueryResult(**common,contexts=hits)
        if len(result.model_dump_json().encode())>262144:
            raise QueryError('native query response exceeds 256 KiB')
        return result
    except (ValueError,TypeError,sqlite3.Error,OSError,ValidationError,ProcessingError) as exc:
        raise QueryError(str(exc)) from exc
    finally:
        if lexical is not None:
            lexical.close_native_positions()
        if vector is not None:
            vector.close()
        metrics['durationMs'] = (time.perf_counter()-started)*1000


def _document_hit(request,row,metrics,match_index):
    from .semantic_document_reader import read_document_reader
    from .semantic_query_schema import DocumentReaderSelection
    from .semantic_artifact_schema import DocumentLocator
    source = row['sourceId']
    reader = request.source_artifacts[source]
    if 'materialRevision' in row and (row['materialRevision'],row['representationRevision']) != (reader.material_revision,reader.representation_revision):
        raise QueryError('native vector range differs from selected source')
    ranges = row.get('ranges') or [dict(nativeRef=row['nativeRef'],start=row['start'],end=row['end'])]
    selected = [dict(nativeRef=item['nativeRef'],start=item['start'],end=item['end']) for item in ranges]
    page = read_document_reader(reader.model_copy(update={'selection':DocumentReaderSelection.model_validate(
        dict(field='ranges',ranges=selected,maxBytes=262144))}))
    metrics['canonicalBytes'] += page['readBytes']
    text = ''.join(item.get('joinBefore','')+value['text']+item.get('joinAfter','')
                   for item,value in zip(ranges,page['items'],strict=True))
    first = ranges[0]
    location = row.get('locator',page['items'][0]['locator'])
    locator = DocumentLocator(representation_id=reader.representation_revision,nativeRef=first['nativeRef'],
        origin='native',quote=page['items'][0]['text'],start_char=first['start'],end_char=first['end'],quality='precise',
        **{key:location[key] for key in ('page','bbox','table_id','cell','slide','section_path') if location.get(key) is not None})
    identity = json.dumps([reader.representation_revision,selected],separators=(',',':'))
    return QueryHit(id='text:'+sha256(identity.encode()).hexdigest(),kind='source_text',title=source,text=text,
        score=row.get('score',1.),source_ids=[source],locator=locator,
        match_index=match_index if request.mode=='keyword' else None,position=row.get('position'))


def _knowledge_hits(records):
    from .triplet_store.extraction_records import F,RDF_TYPE
    kinds={'Entity':'entity','Relation':'relation','Assertion':'assertion','Evidence':'evidence','EntityMention':'evidence'}
    hits=[]
    for item in records:
        fields=item['fields']
        types=[value['value'].removeprefix(F) for value in fields.get(RDF_TYPE,[])]
        kind=next((kinds[value] for value in types if value in kinds),None)
        if kind is None:
            raise QueryError('unsupported native candidate type')
        words=[value['value'] for key,values in fields.items() if key in {F+'name',F+'label',F+'text',F+'predicateName',F+'description'}
            for value in values if value['type']=='literal']
        text=' '.join(words)
        hits.append(QueryHit(id=item['id'],kind=kind,title=text[:160] or item['id'],text=text,score=item.get('score',1.),
            evidence_ids=item['evidenceIds'],source_ids=item['sourceIds'],evidence_next_cursor=item.get('evidenceNextCursor')))
    return hits
