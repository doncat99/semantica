"""Offline integrity admission for native stores, including restored installations.

No data conversion or repair is performed. The caller stops the owning process,
verifies its archive byte manifest and supplies the exact publication receipt.
Opening Oxigraph takes its exclusive writer lock; a live owner is rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from .utils.exceptions import ProcessingError


def verify_native_installation(request, *, cancelled=lambda: False, progress=lambda counts: None):
    """Traverse native receipts incrementally; never build an aggregate graph.

    Input and output are <=64KiB. SQLite page cache is 2MiB, hash reads 256KiB,
    RDF pages <=128 rows and existing typed receipt budgets remain enforced.
    The caller must also impose a subprocess deadline: Oxigraph's native query
    engine does not offer a cooperative interrupt inside one query call.
    """
    from .triplet_store.oxigraph_store import OxigraphStore
    from .triplet_store.publication_records import PublicationRecords, P, F, RDF_TYPE
    from .explorer.search_index import GraphSearchIndex, _file_identity

    fields = {'semanticStorePath', 'project', 'generation', 'publicationReference', 'keyword', 'semantic', 'deadlineSeconds'}
    if (not isinstance(request, dict) or set(request) - fields
            or not {'semanticStorePath', 'publicationReference'} <= set(request)
            or len(json.dumps(request).encode()) > 65536):
        raise ProcessingError('Invalid native maintenance request')
    seconds = request.get('deadlineSeconds', 600)
    if type(seconds) is not int or not 1 <= seconds <= 600:
        raise ProcessingError('Native maintenance deadline must be 1..600 seconds')
    deadline = time.monotonic() + seconds
    counts = dict(sources=0, operations=0, acceptedOperations=0, nativeFields=0,
        canonicalRecords=0, records=0, vectors=0, embeddingOperations=0, associations=0)

    def check():
        if cancelled() or time.monotonic() >= deadline:
            raise ProcessingError('Native maintenance cancelled or deadline exceeded')

    def path(value, directory=False):
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ProcessingError('Native maintenance requires absolute installed paths')
        result = Path(value)
        if result.is_symlink() or (not result.is_dir() if directory else not result.is_file()):
            raise ProcessingError('Native maintenance carrier missing or symlinked')
        return result

    def sqlite_integrity(db):
        db.execute('PRAGMA cache_size=-2048')
        db.set_progress_handler(lambda: (check(), 0)[1], 1000)
        rows = db.execute('PRAGMA integrity_check')
        if rows.fetchone() != ('ok',) or rows.fetchone() is not None:
            raise ProcessingError('Native SQLite integrity check failed')

    reference = request['publicationReference']
    if (not isinstance(reference, dict) or set(reference) != {'project','generation','state','source_count','canonical_count','indexes'}
            or reference['state'] not in {'pending','ready','withdrawn'}
            or request.get('project', reference['project']) != reference['project']
            or request.get('generation', reference['generation']) != reference['generation']):
        raise ProcessingError('Native maintenance requires the complete publication reference')
    check()
    owner = OxigraphStore(path(request['semanticStorePath'], True))
    keyword_owner = vector_owner = None
    try:
        publication = PublicationRecords(owner, reference['project'])
        if publication.status() != reference:
            raise ProcessingError('Native publication reference differs from installed owner')
        generation = reference['generation']
        # Pending builds can contain accepted paid work not yet referenced by
        # publication membership. Verify those canonical owner operations too.
        for graph in (publication.facts, publication.graph):
            for quad in owner.store.quads_for_pattern(None,None,None,graph):
                check()
                if len(str(quad).encode()) > 262144:
                    raise ProcessingError('Native stored field exceeds verification budget')
                counts['nativeFields'] += 1
        operation_after = ''
        while True:
            check()
            operations = list(owner.store.query(f'''SELECT DISTINCT ?operation WHERE {{ GRAPH {publication.facts} {{
                {{ ?operation <{F}operationIdentity> ?identity }} UNION
                {{ ?operation <{RDF_TYPE}> <{F}ExtractionOperation> }} }}
                FILTER(STR(?operation) > {publication.ox.Literal(operation_after)}) }} ORDER BY ?operation LIMIT 128'''))
            if not operations:
                break
            for row in operations:
                check()
                operation = row['operation']
                source = {}
                for field in ('source','material','representation'):
                    predicate = publication.ox.NamedNode(F+'binding'+field[0].upper()+field[1:])
                    values = []
                    for quad in owner.store.quads_for_pattern(operation,predicate,None,publication.facts):
                        values.append(quad.object.value)
                        if len(values) > 1:
                            break
                    if len(values) != 1:
                        raise ProcessingError('Native accepted operation binding incomplete')
                    source[field] = values[0]
                publication.verify_operation(operation.value,source)
                counts['acceptedOperations'] += 1
            operation_after = operations[-1]['operation'].value
            progress(dict(counts))
        # Stream each source and its operation references. Operation receipts
        # validate typed facts, native grounding and paid-result digests.
        after = ''
        while True:
            check()
            query = f'''SELECT ?node ?source WHERE {{ GRAPH {publication.graph} {{
                {publication.head} <{P}source> ?node . ?node <{P}source> ?source . }}
                FILTER(STR(?source) > {publication.ox.Literal(after)}) }} ORDER BY ?source LIMIT 128'''
            batch = list(owner.store.query(query))
            if not batch:
                break
            for row in batch:
                check()
                source = {field: publication.one(row['node'], field) for field in ('source','material','representation','recipe')}
                operation_after, operation_count = '', 0
                while True:
                    check()
                    operations = list(owner.store.query(f'''SELECT ?operation WHERE {{ GRAPH {publication.graph} {{
                        {row['node']} <{P}operation> ?operation . }}
                        FILTER(STR(?operation) > {publication.ox.Literal(operation_after)}) }} ORDER BY ?operation LIMIT 128'''))
                    if not operations:
                        break
                    for operation in operations:
                        check()
                        publication.verify_operation(operation['operation'].value, source)
                        operation_count += 1
                        counts['operations'] += 1
                    operation_after = operations[-1]['operation'].value
                if reference['state'] == 'ready' and operation_count != int(publication.one(row['node'], 'operationCount')):
                    raise ProcessingError('Native publication source operation count differs')
                counts['sources'] += 1
            after = batch[-1]['source'].value
            progress(dict(counts))
        if reference['state'] == 'ready':
            if counts['sources'] != reference['source_count']:
                raise ProcessingError('Native publication source count differs')
            for canonical in (False, True):
                cursor = None
                while True:
                    check()
                    page = publication.page(generation, after=cursor, canonical=canonical)
                    counts['canonicalRecords' if canonical else 'records'] += len(page['records'])
                    cursor = page['next_cursor']
                    progress(dict(counts))
                    if cursor is None:
                        break
            if counts['canonicalRecords'] != reference['canonical_count']:
                raise ProcessingError('Native canonical publication count differs')
            keyword, semantic = request.get('keyword'), request.get('semantic')
            if (not isinstance(keyword, dict) or set(keyword) != {'path','receipt'}
                    or keyword['receipt'] != reference['indexes']['keyword']
                    or not isinstance(semantic, dict) or set(semantic) != {'path','receipt','space','dimensions'}
                    or semantic['receipt'] != reference['indexes']['semantic']):
                raise ProcessingError('Ready native publication requires exact index installations')
            keyword_path = path(keyword['path'])
            before = _file_identity(keyword_path)
            digest = hashlib.sha256()
            with keyword_path.open('rb') as stream:
                while block := stream.read(262144):
                    check()
                    digest.update(block)
            if keyword['receipt']['store_id'] != 'sha256:' + digest.hexdigest() or _file_identity(keyword_path) != before:
                raise ProcessingError('Native keyword carrier digest differs or changed during verification')
            keyword_owner = GraphSearchIndex.open_native_positions(keyword_path, project=reference['project'], generation=generation,
                receipt=keyword['receipt'], installation_identity=before)
            sqlite_integrity(keyword_owner._native_db)
            keyword_sources = 0
            for source, material, representation in keyword_owner._native_db.execute('SELECT source,material,representation FROM sources'):
                check()
                binding = publication.source_binding(generation, source)
                if binding['material'] != material or binding['representation'] != representation:
                    raise ProcessingError('Native keyword source binding differs')
                keyword_sources += 1
            if keyword_sources != counts['sources'] or _file_identity(keyword_path) != before:
                raise ProcessingError('Native keyword source coverage or installation changed')
            vector_owner = _verify_vectors(path(semantic['path']), semantic, reference, publication, counts, check, sqlite_integrity)
            installation = [str(value) for value in before]
        else:
            if request.get('keyword') is not None or request.get('semantic') is not None or reference['indexes']:
                raise ProcessingError('Non-ready publication cannot admit query indexes')
            installation = None
        check()
        if publication.status() != reference:
            raise ProcessingError('Native publication changed during verification')
        result = dict(state='verified', project=reference['project'], generation=generation,
            publicationReference=reference, keywordInstallation=installation, counts=counts)
        if len(json.dumps(result).encode()) > 65536:
            raise ProcessingError('Native maintenance response exceeds budget')
        return result
    finally:
        if keyword_owner is not None:
            keyword_owner.close_native_positions()
        if vector_owner is not None:
            vector_owner.close()
        owner.close()


def _verify_vectors(path, semantic, reference, publication, counts, check, sqlite_integrity):
    from .vector_store.sqlite_vec_store import SQLiteVecStore
    from .vector_store import sqlite_vec_store as module
    dimensions, space = semantic['dimensions'], semantic['space']
    if (type(dimensions) is not int or not 1 <= dimensions <= 8192 or not isinstance(space, dict)
            or set(space) != {'binding','model','recipe'} or semantic['receipt']['space_id'] != space['binding']):
        raise ProcessingError('Native embedding installation space differs')
    owner = SQLiteVecStore(str(path), 'embeddings', dimensions, 'cosine', read_only=True)
    try:
        conn = owner._conn
        sqlite_integrity(conn)
        expected = json.dumps(space, sort_keys=True, separators=(',', ':'))
        if conn.execute('SELECT identity,dimension FROM embedding_space WHERE id=1').fetchone() != (expected, dimensions):
            raise ProcessingError('Native embedding space identity differs')
        project, generation, receipt = reference['project'], reference['generation'], semantic['receipt']
        row = conn.execute('SELECT generation,count,digest,recipe FROM embeddings_native_publications WHERE project=?', (project,)).fetchone()
        if row is None or (row[0],row[2],row[3]) != (generation,receipt['store_id'],receipt['recipe_digest']):
            raise ProcessingError('Native vector publication receipt differs')
        digest, count = owner.native_publication_digest(conn,project,generation,check=check)
        if digest != receipt['store_id'] or count != row[1]:
            raise ProcessingError('Native vector publication reference digest differs')
        # Revalidate accepted vectors one vector (<=32KiB) at a time; no matrix.
        for identity, count, digest, encoded, receipt_digest, accepted in conn.execute(
                'SELECT id,count,digest,receipt,receipt_digest,accepted_digest FROM embeddings_embedding_operations'):
            check()
            if (type(count) is not int or not 1 <= count <= 256 or len(encoded.encode()) > 65536
                    or not accepted or hashlib.sha256(encoded.encode()).hexdigest() != receipt_digest):
                raise ProcessingError('Native embedding operation receipt corrupt')
            hasher = hashlib.sha256()
            for index in range(count):
                check()
                vector = conn.execute('SELECT embedding FROM embeddings WHERE id=?', (identity+':'+str(index),)).fetchone()
                if vector is None or len(vector[0]) != dimensions*4 or not module.np.all(module.np.isfinite(module.np.frombuffer(vector[0], dtype=module.np.float32))):
                    raise ProcessingError('Native accepted embedding vector missing or corrupt')
                hasher.update(vector[0])
            if hasher.hexdigest() != digest:
                raise ProcessingError('Native accepted embedding operation digest differs')
            counts['embeddingOperations'] += 1
        for identity, source, material, representation, ranges in conn.execute(
                'SELECT vector_id,source,material,representation,ranges FROM embeddings_native_ranges WHERE project=? AND generation=?', (project,generation)):
            check()
            if len(ranges.encode()) > 65536 or not 1 <= len(json.loads(ranges)) <= 128:
                raise ProcessingError('Native vector range exceeds budget')
            binding = publication.source_binding(generation, source)
            if binding['material'] != material or binding['representation'] != representation:
                raise ProcessingError('Native vector source binding differs')
            operation, separator, offset = identity.rpartition(':')
            adopted = conn.execute('SELECT count FROM embeddings_embedding_operations WHERE id=?', (operation,)).fetchone()
            if not separator or not offset.isdecimal() or adopted is None or not 0 <= int(offset) < adopted[0]:
                raise ProcessingError('Native vector reference lacks accepted operation')
            counts['vectors'] += 1
        if counts['vectors'] != row[1]:
            raise ProcessingError('Native vector publication count differs')
        for vector, record, evidence, source in conn.execute(
                'SELECT vector_id,record_id,evidence_id,source FROM embeddings_native_ranges_records WHERE project=? AND generation=?', (project,generation)):
            check()
            if not conn.execute('SELECT 1 FROM embeddings_native_ranges WHERE project=? AND generation=? AND vector_id=? AND source=?', (project,generation,vector,source)).fetchone():
                raise ProcessingError('Native vector association has no scoped range')
            records = publication.read(generation, [record,evidence], source_ids=[source])
            if len(records) != 2:
                raise ProcessingError('Native vector association has missing native records')
            counts['associations'] += 1
        conn.set_progress_handler(None,0)
        return owner
    except BaseException:
        owner.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-file', required=True)
    args = parser.parse_args()
    with open(args.request_file, 'rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ProcessingError('Native maintenance request exceeds 64KiB')
    result = verify_native_installation(json.loads(raw))
    sys.stdout.write(json.dumps(result, separators=(',', ':'))+'\n')


if __name__ == '__main__':
    main()
