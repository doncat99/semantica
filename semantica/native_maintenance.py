"""Offline integrity admission for native stores, including restored installations.

Verification never repairs data. Explicit source address indexing only adds lookup edges.
The caller stops the owning process,
verifies its archive byte manifest and supplies the exact publication receipt.
Opening Oxigraph takes its exclusive writer lock; a live owner is rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
                publication.verify_operation(operation.value,source).audit()
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


def upgrade_saved_source(request):
    """Explicit v2 -> current artifact migration; never an ordinary reader path.

    Preserve the historical representation identity and immutable original. Only
    redundant serialized mirrors are removed from the new native carrier.
    """
    from types import SimpleNamespace
    from .semantic_document_reader import _identity
    from .semantic_source_artifact import _write_parsed_source_artifact, _has_representation_identity, _safe_id
    from .source import normalized_processing_profile
    from .parse.document_contract import document_suffix
    if not isinstance(request, dict) or set(request) != {'artifactPath', 'artifactDigest', 'targetPath'}:
        raise ValueError('Invalid saved source upgrade request')
    source, target = Path(request['artifactPath']), Path(request['targetPath'])
    if (not source.is_absolute() or source.is_symlink() or not source.is_file()
            or not target.is_absolute() or target.is_symlink() or source.resolve() == target.resolve()):
        raise ValueError('Saved source upgrade requires distinct installed and staging paths')
    before = _identity(source)
    with source.open('rb') as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Saved source upgrade exceeds 64MiB budget')
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != request['artifactDigest']:
        raise ValueError('Saved source upgrade artifact digest differs')
    payload = json.loads(raw)
    del raw
    document = payload.get('document')
    if (payload.get('protocol') != 'semantica.parsed-source.v2'
            or not isinstance(document, dict) or not _has_representation_identity(document)
            or not isinstance(payload.get('sourceId'), str) or not payload['sourceId']
            or document.get('content_hash') != payload.get('materialRevision')
            or not isinstance(payload.get('materialRevision'), str)
            or not isinstance(payload.get('mimeType'), str)
            or type(payload.get('forceOcr')) is not bool
            or not isinstance(payload.get('name'), str)
            or not isinstance(payload.get('parser'), str) or not payload['parser']
            or not isinstance(payload.get('parserVersion'), str) or not payload['parserVersion']
            or payload.get('origin') not in {'native', 'ocr', 'mixed', 'external', 'adapter'}
            or payload.get('processingRevision') != 'semantica-document-processing-v1'):
        raise ValueError('Unsupported or invalid historical saved source')
    previous_profile = payload.get('documentProcessing')
    if (not isinstance(previous_profile, dict) or previous_profile.get('pdfTextOrder') != 'coordinates'
            or previous_profile.get('processingRevision') != payload['processingRevision']):
        raise ValueError('Unsupported historical processing profile')
    profile = normalized_processing_profile({k: previous_profile[k] for k in
        ('mode', 'endpoint', 'bindingId', 'remoteCancellation') if previous_profile.get(k) is not None})
    suffix = document_suffix(source, payload['name'], payload['mimeType'], False)
    # Record the actual historical recipe, not today's implementation provenance.
    provenance = dict(protocol=payload['protocol'], processingRevision=payload['processingRevision'],
        profile=previous_profile, parser=payload['parser'], parserVersion=payload['parserVersion'],
        mimeType=payload['mimeType'], suffix=suffix, forceOcr=payload['forceOcr'])
    processing = 'sha256:' + hashlib.sha256(json.dumps(provenance, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    if document.get('format') == 'docling':
        if not isinstance(document.get('document'), dict):
            raise ValueError('Historical Docling native document is missing')
        for key in ('text', 'plain_text', 'doctags', 'reader', 'source'):
            document.pop(key, None)
    elif document.get('format') == 'plain-text':
        if not isinstance(document.get('text'), str):
            raise ValueError('Historical text scalar is missing')
        document.pop('source', None)
        document['format'] = 'text'
    else:
        raise ValueError('Unsupported historical native document format')
    current = {k: payload[k] for k in ('materialRevision', 'mimeType', 'forceOcr',
        'parser', 'parserVersion', 'origin')}
    current.update(protocol='semantica.parsed-source.v3', documentProcessing=profile,
        processingRevision=processing, document=document)
    source_id = payload['sourceId']
    output = target.parent / f'parsed-{_safe_id(source_id)}.json'
    if output.is_symlink() or output.resolve() == source.resolve():
        raise ValueError('Saved source upgrade output aliases its original')
    # Delegate serialization and indexing to the sole current native writer.
    operation = SimpleNamespace(output_dir=str(target.parent), source=SimpleNamespace(source_id=source_id))
    result = _write_parsed_source_artifact(operation, current)
    if _identity(source) != before:
        raise ValueError('Saved source changed during offline upgrade')
    result.update(sourceExtension=suffix, documentParserDigest=processing, forceOcr=payload['forceOcr'])
    return result


def rebuild_reader_index(request):
    """Offline projection upgrade, one bounded saved representation at a time.

    Never invokes a parser or model; only the canonical address writer is used.
    Originals stay immutable, and the caller adopts the new index atomically.
    """
    from .semantic_document_reader import write_reader_artifact, _identity
    from .semantic_query_schema import DocumentReaderRequest
    if not isinstance(request, dict) or set(request) != {'reader', 'targetPath'}:
        raise ValueError('Invalid reader index rebuild request')
    reader = DocumentReaderRequest.model_validate(request['reader'])
    source = Path(reader.artifact.path)
    target = Path(request['targetPath'])
    if (not source.is_absolute() or source.is_symlink() or not source.is_file()
            or not target.is_absolute() or target.is_symlink()
            or source.resolve() == target.resolve()):
        raise ValueError('Reader upgrade requires distinct installed and staging paths')
    before = _identity(source)
    if before != reader.artifact.installation.identity:
        raise ValueError('Reader installation identity differs')
    # Explicit offline maintenance may traverse one complete document, never a project.
    with source.open('rb') as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Reader upgrade exceeds 64MiB per-document budget')
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != reader.artifact.digest:
        raise ValueError('Reader artifact digest differs')
    payload = json.loads(raw)
    del raw
    if (payload.get('materialRevision') != reader.material_revision
            or payload.get('document', {}).get('representation_revision') != reader.representation_revision):
        raise ValueError('Reader representation identity differs')
    artifact_digest, index_digest, header = write_reader_artifact(target, payload)
    if artifact_digest != reader.artifact.digest or _identity(source) != before:
        raise ValueError('Reader upgrade changed representation digest or installation identity')
    return dict(artifactDigest=artifact_digest, readerIndexDigest=index_digest,
        readerIndexPath=str(target.with_suffix('.reader.sqlite')), readerHeader=header)


def rebuild_keyword_index(request, *, cancelled=lambda: False, progress=lambda counts: None):
    """Rebuild only the native lexical projection from installed readers."""
    from .explorer.search_index import GraphSearchIndex, _file_identity
    from .semantic_query_schema import DocumentReaderRequest
    from .triplet_store.oxigraph_store import OxigraphStore
    from .triplet_store.publication_records import PublicationRecords

    fields = {'semanticStorePath', 'publicationReference', 'readers', 'targetPath', 'deadlineSeconds'}
    if (not isinstance(request, dict) or set(request) != fields
            or len(json.dumps(request, ensure_ascii=False).encode()) > 65536
            or not isinstance(request['readers'], list) or len(request['readers']) > 512):
        raise ProcessingError('Invalid keyword index rebuild request')
    seconds = request['deadlineSeconds']
    if type(seconds) is not int or not 1 <= seconds <= 600:
        raise ProcessingError('Keyword index rebuild deadline must be 1..600 seconds')
    deadline = time.monotonic() + seconds

    def check():
        if cancelled() or time.monotonic() >= deadline:
            raise ProcessingError('Keyword index rebuild cancelled or deadline exceeded')

    store_path = Path(request['semanticStorePath'])
    if store_path.is_symlink() or not store_path.is_dir():
        raise ProcessingError('Keyword index rebuild requires an installed semantic store')
    store_path = store_path.resolve()
    reference = request['publicationReference']
    if (not isinstance(reference, dict) or set(reference) != {'project', 'generation', 'state', 'source_count', 'canonical_count', 'indexes'}
            or reference['state'] != 'ready' or type(reference['source_count']) is not int
            or not isinstance(reference['generation'], str)
            or len(reference['generation']) != 64
            or any(character not in '0123456789abcdef' for character in reference['generation'])):
        raise ProcessingError('Keyword index rebuild requires a complete ready publication')
    recipe = GraphSearchIndex.native_positions_recipe_digest()
    target = Path(request['targetPath'])
    expected_name = f"keyword-{reference['generation']}-{recipe.removeprefix('sha256:')[:16]}.sqlite"
    if (not target.is_absolute() or target.parent.resolve() != store_path.parent
            or target.name != expected_name or target.parent.is_symlink() or target.is_symlink()):
        raise ProcessingError('Keyword index rebuild target is outside its canonical project store')

    owner = OxigraphStore(store_path)
    try:
        publication = PublicationRecords(owner, reference['project'])
        active_generation = publication._pointer(publication.registry_head, 'active', publication.registry)
        if active_generation is None or active_generation.value != reference['generation']:
            raise ProcessingError('Native active publication differs from the host receipt')
        # The latest pointer may name an interrupted pending build. Startup
        # migration repairs only the active ready generation named by the host.
        publication.generation = active_generation
        actual = publication.status()
        expected_identity = {key: reference[key] for key in ('project', 'generation', 'state', 'source_count', 'canonical_count')}
        if (actual is None or any(actual.get(key) != value for key, value in expected_identity.items())
                or actual['indexes']['semantic'] != reference['indexes']['semantic']):
            raise ProcessingError('Native publication identity changed before keyword rebuild')
        if actual['indexes']['keyword'].get('kind') != 'native-scalar-positions':
            raise ProcessingError('Native keyword publication kind changed before keyword rebuild')

        readers = []
        seen = set()
        for raw in request['readers']:
            check()
            reader = DocumentReaderRequest.model_validate(raw)
            if reader.source_id in seen:
                raise ProcessingError('Keyword index rebuild contains duplicate source readers')
            seen.add(reader.source_id)
            binding = publication.source_binding(reference['generation'], reader.source_id)
            if (binding['material'] != reader.material_revision
                    or binding['representation'] != reader.representation_revision):
                raise ProcessingError('Keyword reader differs from published source identity')
            readers.append(reader)
        if len(readers) != reference['source_count']:
            raise ProcessingError('Keyword readers do not cover the complete publication')

        def installed_receipt(index_path):
            before = _file_identity(index_path)
            digest = hashlib.sha256()
            with index_path.open('rb') as stream:
                while block := stream.read(262144):
                    check()
                    digest.update(block)
            receipt = dict(kind='native-scalar-positions', store_id='sha256:' + digest.hexdigest(), recipe_digest=recipe)
            lexical_owner = GraphSearchIndex.open_native_positions(index_path, project=reference['project'],
                generation=reference['generation'], receipt=receipt, installation_identity=before)
            count = 0
            try:
                for source, material, representation in lexical_owner._native_db.execute(
                        'SELECT source,material,representation FROM sources'):
                    check()
                    binding = publication.source_binding(reference['generation'], source)
                    if binding['material'] != material or binding['representation'] != representation:
                        raise ProcessingError('Keyword index source binding differs')
                    count += 1
            finally:
                lexical_owner.close_native_positions()
            if count != reference['source_count'] or _file_identity(index_path) != before:
                raise ProcessingError('Keyword index source coverage or installation changed')
            return receipt, before

        if target.exists():
            receipt, identity = installed_receipt(target)
        else:
            staging = target.with_name(f'.{target.name}.upgrade')
            if staging.is_symlink():
                raise ProcessingError('Stale keyword rebuild stage is a symbolic link')
            staging.unlink(missing_ok=True)
            try:
                check()
                receipt = GraphSearchIndex.publish_native_positions(staging, project=reference['project'],
                    generation=reference['generation'], readers=readers)
                check()
                os.replace(staging, target)
                receipt, identity = installed_receipt(target)
            finally:
                staging.unlink(missing_ok=True)

        address = dict(path=str(target), receipt=receipt, installation=dict(digest=receipt['store_id'],
            identity=':'.join(map(str, identity))))
        if actual['indexes']['keyword'] != receipt:
            if (actual['generation'] != reference['generation']
                    or actual['indexes']['semantic'] != reference['indexes']['semantic']):
                raise ProcessingError('Native keyword publication changed during recovery')
            updated = publication.replace_keyword_index(reference['generation'], receipt, address)
        else:
            updated = actual
        if (updated['generation'] != reference['generation'] or updated['indexes']['keyword'] != receipt
                or updated['indexes']['semantic'] != reference['indexes']['semantic']):
            raise ProcessingError('Native keyword index adoption did not preserve publication identity')
        return dict(state='rebuilt', project=reference['project'], generation=reference['generation'],
            publicationReference=updated, keyword=dict(path=str(target), receipt=receipt,
                installation=dict(digest=receipt['store_id'], identity=':'.join(map(str, identity)))))
    finally:
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


def index_native_source_projection(request, *, rebind=False, execute=False):
    """Explicit offline migration of one completed projection's lookup edges."""
    from .triplet_store.oxigraph_store import OxigraphStore
    from .triplet_store.publication_records import PublicationRecords
    from .triplet_store.extraction_records import ExtractionRecords

    fields = ({'semanticStorePath','publicationReference','previous','extraction','formulaSemantics'}
        if rebind else {'semanticStorePath','publicationReference','inputKey'})
    if (not isinstance(request,dict) or set(request)!=fields
            or len(json.dumps(request).encode())>65536):
        raise ProcessingError('Invalid source projection indexing request')
    path=request['semanticStorePath']
    if not isinstance(path,str) or not Path(path).is_absolute() or Path(path).is_symlink() or not Path(path).is_dir():
        raise ProcessingError('Source indexing requires an absolute existing store path')
    reference=request['publicationReference']
    if not isinstance(reference,dict) or not isinstance(reference.get('project'),str):
        raise ProcessingError('Source indexing requires the exact publication reference')
    owner=OxigraphStore(path)
    try:
        if PublicationRecords(owner,reference['project']).status()!=reference:
            raise ProcessingError('Native publication reference differs from installed owner')
        if rebind:
            return ExtractionRecords.rebind_source_projection(owner, reference['project'], request['previous'],
                extraction=request['extraction'], formula_semantics=request['formulaSemantics'], execute=execute)
        ExtractionRecords.index_source_projection(owner,reference['project'],request['inputKey'])
        return dict(indexed=True,publicationReference=reference,inputKey=request['inputKey'])
    finally:
        owner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-file', required=True)
    parser.add_argument('--index-source-projection',action='store_true',
        help='Explicit offline address indexing; never invoked during ordinary verification')
    parser.add_argument('--rebind-source-projection', action='store_true',
        help='Offline semantic rebind of a reviewed historical projection; dry-run unless --execute')
    parser.add_argument('--index-embedding-scope', action='store_true',
        help='Explicit offline upgrade of the accepted embedding range lookup index')
    parser.add_argument('--rebuild-keyword-index', action='store_true',
        help='Rebuild a stale derived keyword index from installed document readers')
    parser.add_argument('--rebuild-reader-index', action='store_true')
    parser.add_argument('--upgrade-saved-source', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if sum((args.index_source_projection, args.rebind_source_projection, args.index_embedding_scope, args.rebuild_keyword_index, args.rebuild_reader_index, args.upgrade_saved_source)) > 1:
        parser.error('Choose exactly one maintenance operation')
    with open(args.request_file, 'rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ProcessingError('Native maintenance request exceeds 64KiB')
    request=json.loads(raw)
    if args.upgrade_saved_source:
        result = upgrade_saved_source(request)
    elif args.rebuild_reader_index:
        result = rebuild_reader_index(request)
    elif args.rebuild_keyword_index:
        result = rebuild_keyword_index(request)
    elif args.index_embedding_scope:
        from .vector_store.sqlite_vec_store import SQLiteVecStore
        from .triplet_store.oxigraph_store import OxigraphStore
        if set(request) != {'semanticStorePath', 'vectorStorePath'}:
            raise ProcessingError('Embedding index migration requires exact native store paths')
        owner = OxigraphStore(request['semanticStorePath'])
        try:
            result = SQLiteVecStore.migrate_embedding_scope_index(request['vectorStorePath'], execute=args.execute)
        finally:
            owner.close()
    else:
        result = (index_native_source_projection(request, rebind=args.rebind_source_projection, execute=args.execute)
            if args.index_source_projection or args.rebind_source_projection else verify_native_installation(request))
    sys.stdout.write(json.dumps(result, separators=(',', ':'))+'\n')


if __name__ == '__main__':
    main()
