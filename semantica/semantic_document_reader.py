"""Range reads from one native JSON; indexes contain addresses, never text."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from hashlib import sha256, file_digest
from pathlib import Path
from time import monotonic

from .parse.document_reader import (SCALAR_SEGMENT, project_document_reader,
    native_text_projection, source_text_windows, _docling_locations)
from .semantic_worker_context import check_query_cancellation

INDEX_FORMAT = 'semantica.document-reader-index.v3'
PHYSICAL_READ_LIMIT = 256 * 1024
METADATA_LIMIT = 4096
SAFE_QUALITY_CODES = frozenset((
    'formula_transcription_missing', 'fragmented_cjk_encoding', 'unmapped_characters'))


class DocumentReaderBudgetError(ValueError):
    """A requested native range cannot fit its physical/transport budget."""


class DocumentReaderIndexError(ValueError):
    """The installed index requires an explicit rebuild, never a fallback read."""


def _identity(path):
    stat = path.stat()
    return ':'.join(map(str, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))


def write_reader_artifact(path: Path, payload: dict) -> tuple[str, str, dict]:
    """Stream canonical native content once, recording only scalar byte addresses."""
    if payload.get('protocol') != 'semantica.parsed-source.v3':
        raise ValueError('native reader requires current parsed-source protocol')
    document = payload['document']
    if 'reader' in document:
        raise ValueError('canonical native content must not contain a reader projection')
    if document.get('format') == 'docling' and any(key in document for key in ('text', 'plain_text', 'doctags')):
        raise ValueError('canonical Docling content must not contain serialized body mirrors')
    if document.get('format') in {'epub', 'flat-odf'} and any(
            key in document for key in ('text', 'plain_text', 'doctags', 'flat_odf')):
        raise ValueError('canonical section content must not contain serialized body mirrors')
    index_path = path.with_suffix('.reader.sqlite')
    if index_path.exists():
        index_path.unlink()
    digest, offset = sha256(), 0
    with path.open('wb') as stream, closing(sqlite3.connect(index_path)) as db, db:
        db.execute('PRAGMA cache_size=-2048')
        db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE items(field TEXT,ordinal INTEGER,page INTEGER,descriptor TEXT NOT NULL,
                PRIMARY KEY(field,ordinal)) WITHOUT ROWID;
            CREATE INDEX items_page ON items(field,page);
            CREATE INDEX items_page_part ON items(field,page,json_extract(descriptor,'$.pagePart'));
            CREATE INDEX items_native_range ON items(field,json_extract(descriptor,'$.ref'),json_extract(descriptor,'$.start'));
            CREATE TABLE page_counts(page INTEGER PRIMARY KEY,parts INTEGER NOT NULL) WITHOUT ROWID;
            CREATE TABLE source_windows(ordinal INTEGER PRIMARY KEY,start INTEGER NOT NULL,end INTEGER NOT NULL) WITHOUT ROWID;
            CREATE TABLE source_map(start INTEGER NOT NULL,end INTEGER NOT NULL,kind TEXT NOT NULL,
                native_ref TEXT,native_start INTEGER,join_before_length INTEGER NOT NULL,
                PRIMARY KEY(start)) WITHOUT ROWID;
            CREATE INDEX source_map_end ON source_map(end);
            CREATE INDEX source_map_kind_start ON source_map(kind,start);
            CREATE TABLE source_locations(ordinal INTEGER PRIMARY KEY,start INTEGER,end INTEGER,
                page INTEGER,table_id TEXT,ref TEXT NOT NULL,descriptor TEXT NOT NULL);
            CREATE INDEX source_locations_range ON source_locations(start,end);
            CREATE INDEX source_locations_page ON source_locations(page);
            CREATE INDEX source_locations_table ON source_locations(table_id);
            CREATE INDEX source_locations_ref ON source_locations(ref);
            CREATE VIRTUAL TABLE source_location_bounds USING rtree_i32(ordinal,start_min,start_max);
            CREATE TABLE source_location_dependencies(ordinal INTEGER,ref TEXT,
                PRIMARY KEY(ordinal,ref)) WITHOUT ROWID;
            CREATE TABLE segments(ref TEXT,start INTEGER,end INTEGER,offset INTEGER,length INTEGER,digest BLOB,
                PRIMARY KEY(ref,start)) WITHOUT ROWID;
            CREATE TABLE native_addresses(ref TEXT PRIMARY KEY,offset INTEGER,length INTEGER,digest BLOB) WITHOUT ROWID;
            CREATE TABLE native_nodes(ref TEXT PRIMARY KEY,fields TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE native_headers(id INTEGER PRIMARY KEY,ref TEXT NOT NULL);
            CREATE VIRTUAL TABLE native_header_bounds USING rtree_i32(id,
                table_min,table_max,role_min,role_max,row_min,row_max,col_min,col_max);''')
        active_digests = []
        def emit(raw):
            nonlocal offset
            stream.write(raw)
            digest.update(raw)
            for selected_digest in active_digests:
                selected_digest.update(raw)
            offset += len(raw)
        def write(value, path_parts=()):
            check_query_cancellation()
            native_path = path_parts[2:] if path_parts[:2] == ('document', 'document') else ()
            selected = (len(native_path) == 2 and native_path[0] == 'texts') or (
                len(native_path) == 3 and native_path[0] in ('texts','groups','tables','pictures') and
                native_path[2] in ('self_ref','label','parent','prov','captions','footnotes','children')) or (
                len(native_path) == 4 and native_path[0] == 'tables' and native_path[2] == 'data' and
                native_path[3] in ('num_rows','num_cols')) or (
                len(native_path) == 5 and native_path[0] == 'tables' and native_path[2:4] == ('data','table_cells'))
            start_offset = offset
            if len(native_path) == 2 and native_path[0] in ('texts','groups','tables','pictures'):
                fields = [key for key in ('self_ref','label','parent','prov','captions','footnotes','children') if key in value]
                db.execute('INSERT INTO native_nodes VALUES (?,?)', ('#/' + '/'.join(native_path), json.dumps(fields)))
            if selected:
                active_digests.append(sha256())
            if len(native_path) == 5 and native_path[0] == 'tables' and native_path[2:4] == ('data','table_cells'):
                from docling_core.types.doc.document import TableCell, RichTableCell
                cell = (RichTableCell if 'ref' in value else TableCell).model_validate(value)
                coords = [cell.start_row_offset_idx, cell.end_row_offset_idx,
                    cell.start_col_offset_idx, cell.end_col_offset_idx]
                if not (0 <= coords[0] < coords[1] <= 2147483647 and 0 <= coords[2] < coords[3] <= 2147483647):
                    raise ValueError('native table cell coordinates are invalid')
                table = int(native_path[1])
                if not 0 <= table <= 2147483647:
                    raise ValueError('native table identity exceeds index bounds')
                for role, enabled in enumerate((cell.column_header, cell.row_header), start=1):
                    if enabled:
                        row = db.execute('INSERT INTO native_headers(ref) VALUES (?)',
                            ('#/' + '/'.join(native_path),))
                        db.execute('INSERT INTO native_header_bounds VALUES (?,?,?,?,?,?,?,?,?)',
                            (row.lastrowid, table, table, role, role, coords[0], coords[1], coords[2], coords[3]))
            if isinstance(value, dict):
                emit(b'{')
                for index, (key, child) in enumerate(value.items()):
                    if index:
                        emit(b',')
                    emit(json.dumps(str(key), ensure_ascii=False).encode() + b':')
                    write(child, (*path_parts, str(key)))
                emit(b'}')
            elif isinstance(value, (list, tuple)):
                emit(b'[')
                for index, child in enumerate(value):
                    if index:
                        emit(b',')
                    write(child, (*path_parts, str(index)))
                emit(b']')
            elif isinstance(value, str):
                ref = '#/' + '/'.join(path_parts)
                emit(b'"')
                for start in range(0, len(value), SCALAR_SEGMENT):
                    check_query_cancellation()
                    raw = json.dumps(value[start:start + SCALAR_SEGMENT], ensure_ascii=False).encode('utf-8')[1:-1]
                    content_scalar = (path_parts == ('document', 'text') or
                        (len(path_parts) == 4 and path_parts[:2] == ('document', 'sections') and path_parts[-1] == 'text') or
                        (len(path_parts) == 4 and path_parts[:2] == ('document', 'pages') and path_parts[-1] == 'text') or
                        (len(path_parts) == 5 and path_parts[:3] == ('document','document','texts') and path_parts[-1] in ('text','orig')) or
                        (len(path_parts) == 8 and path_parts[:3] == ('document','document','tables') and
                         path_parts[4:6] == ('data','table_cells') and path_parts[-1] == 'text'))
                    if content_scalar:
                        db.execute('INSERT INTO segments VALUES (?,?,?,?,?,?)',
                            (ref, start, min(start + SCALAR_SEGMENT, len(value)), offset, len(raw), sha256(raw).digest()))
                    emit(raw)
                emit(b'"')
            else:
                emit(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            if selected:
                db.execute('INSERT INTO native_addresses VALUES (?,?,?,?)',
                    ('#/' + '/'.join(native_path), start_offset, offset-start_offset, active_digests.pop().digest()))
        counts = {'chunks': 0, 'pages': 0}
        text_char_count = 0
        def index_record(field, record):
            nonlocal text_char_count
            encoded = json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            if len(encoded.encode('utf-8')) > 16 * 1024:
                raise DocumentReaderBudgetError('native reader address metadata exceeds budget')
            db.execute('INSERT INTO items VALUES (?,?,?,?)', (field, counts[field], record.get('pageNumber'), encoded))
            counts[field] += 1
            if field == 'chunks':
                text_char_count += record['end'] - record['start']
        projection = project_document_reader(document, sink=index_record)
        source_text, mappings = native_text_projection(document)
        db.executemany('INSERT INTO source_map VALUES (?,?,?,?,?,?)', (
            (item['start'], item['end'], item['kind'], item.get('nativeRef'),
             item.get('nativeStart'), item.get('joinBeforeLength', 0)) for item in mappings))
        window_count = 0
        for start, end in source_text_windows(source_text):
            db.execute('INSERT INTO source_windows VALUES (?,?,?)', (window_count, start, end))
            window_count += 1
        location_count = 0
        def index_location(record):
            nonlocal location_count
            check_query_cancellation()
            encoded = json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            if len(encoded.encode()) > 16*1024:
                raise DocumentReaderBudgetError('native location address metadata exceeds budget')
            db.execute('INSERT INTO source_locations VALUES (?,?,?,?,?,?,?)',
                (location_count, record['start'], record['end'], record['page'], record['table_id'], record['ref'], encoded))
            if record['start'] is not None:
                if not 0 <= record['start'] < record['end'] <= 2147483647:
                    raise DocumentReaderBudgetError('native location coordinate exceeds index bounds')
                db.execute('INSERT INTO source_location_bounds VALUES (?,?,?)',
                    (location_count, record['start'], record['end']))
            for key in ('captions', 'footnotes', 'references'):
                for dependency in record['structure'].get(key, []):
                    ref = dependency.get('$ref') if isinstance(dependency, dict) else dependency
                    if isinstance(ref, str):
                        db.execute('INSERT OR IGNORE INTO source_location_dependencies VALUES (?,?)', (location_count, ref))
            location_count += 1
        _docling_locations(document, source_text, sink=index_location, address_only=True)
        for number, summary in projection.get('pageSummaries', {}).items():
            db.execute('INSERT INTO page_counts VALUES (?,?)', (number, summary['partCount']))
            db.execute('''UPDATE items SET descriptor=json_set(descriptor,'$.state',?,
                '$.hasMoreParts',json(CASE WHEN json_extract(descriptor,'$.pagePart')<? THEN 'true' ELSE 'false' END))
                WHERE field='pages' AND page=?''', (summary['state'], summary['partCount'] - 1, number))
        write(payload)
        artifact_digest = 'sha256:' + digest.hexdigest()
        header = {'protocol': payload['protocol'], 'materialRevision': payload['materialRevision'],
            'representationRevision': document['representation_revision'], 'format': document['format']}
        if 'mime_type' in document:
            header['documentMimeType'] = document['mime_type']
        header['sourceCharCount'] = len(source_text)
        header['sourceWindowCount'] = window_count
        header['sourceLocationCount'] = location_count
        header['documentPageCount'] = len(projection.get('pageSummaries', {}))
        for key in ('mimeType', 'forceOcr', 'processingRevision', 'documentProcessing',
                    'parser', 'parserVersion', 'origin'):
            if key in payload:
                header[key] = payload[key]
        if 'content_hash' in document:
            header['contentHash'] = document['content_hash']
        if isinstance(document.get('quality'), dict):
            quality = document['quality']
            header['quality'] = {key: quality[key] for key in ('version', 'status') if key in quality}
            header['quality']['issueCount'] = len(quality.get('issues', []))
            if quality.get('status') == 'needs_review':
                codes = set()
                for issue in quality.get('issues', []):
                    if (isinstance(issue, dict) and isinstance(issue.get('code'), str)
                            and issue['code'] in SAFE_QUALITY_CODES):
                        codes.add(issue['code'])
                        if codes == SAFE_QUALITY_CODES:
                            break
                header['quality']['issueCodes'] = sorted(codes)
        reader_header = {'chunkCount': counts['chunks'], 'pagePartCount': counts['pages'],
            'pageCount': len(projection.get('pageSummaries', {})),
            'format': document['format'], 'indexFormat': INDEX_FORMAT}
        states = dict.fromkeys(('document_text','mixed_text','native_text','no_text_content',
            'blank','ocr_text','invalid_layout'), 0)
        for summary in projection.get('pageSummaries', {}).values():
            states[summary['state']] += 1
        reader_header.update(textCharCount=text_char_count, pageStateCounts=states,
            processingProfile='semantica:' + document['format'],
            status='partial' if states['invalid_layout'] else 'ready')
        encoded_header = json.dumps(header, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(encoded_header.encode('utf-8')) > METADATA_LIMIT:
            raise DocumentReaderBudgetError('native reader binding metadata exceeds budget')
        db.executemany('INSERT INTO metadata VALUES (?,?)', (
            ('format', INDEX_FORMAT), ('artifactDigest', artifact_digest),
            ('header', encoded_header),
            ('readerHeader', json.dumps(reader_header, separators=(',', ':'))),
            ('chunks', str(counts['chunks'])), ('pages', str(counts['pages'])),
            ('source_windows', str(window_count))))
    with index_path.open('rb') as stream:
        index_digest = 'sha256:' + file_digest(stream, 'sha256').hexdigest()
    return artifact_digest, index_digest, reader_header


def _read_structure(db, stream, selection, check):
    """Resolve native dependency closure; only addresses/geometry live in SQLite."""
    import re
    from pydantic import TypeAdapter
    from docling_core.types.doc.document import DoclingDocument, TextItem, TableItem, PictureItem, GroupItem, TableCell, RichTableCell

    loaded, nodes, containers, cells = {}, {}, {}, {}
    active, done, metadata_done = set(), set(), set()
    pending_nodes = []
    read_bytes = 0
    limit = min(selection.max_bytes, PHYSICAL_READ_LIMIT)
    # Bounds native/SQLite work as well as returned objects; spatial queries do
    # not scan every preceding cell to find an intersecting header span.
    steps = 0
    def progress():
        nonlocal steps
        check()
        steps += 1000
        if steps > 100000:
            raise DocumentReaderBudgetError('native structure query work budget exceeded')
        return 0
    db.set_progress_handler(progress, 1000)
    text_adapter = TypeAdapter(DoclingDocument.model_fields['texts'].annotation.__args__[0])

    def depth_check(depth):
        check()
        if depth > selection.max_depth:
            raise DocumentReaderBudgetError('native structure depth budget exceeded')

    def read(ref):
        nonlocal read_bytes
        check()
        if ref in loaded:
            return loaded[ref]
        if len(loaded) >= selection.max_objects:
            raise DocumentReaderBudgetError('native structure object budget exceeded')
        row = db.execute('SELECT offset,length,digest FROM native_addresses WHERE ref=?', (ref,)).fetchone()
        if row is None:
            raise ValueError('native structure reference is missing: ' + ref)
        offset, length, digest = row
        if offset < 0 or length <= 0:
            raise ValueError('native structure address is invalid')
        if read_bytes + length > limit:
            raise DocumentReaderBudgetError('native structure physical byte budget exceeded; use scalar ranges for oversized text')
        stream.seek(offset)
        raw = stream.read(length)
        read_bytes += len(raw)
        if len(raw) != length or sha256(raw).digest() != digest:
            raise ValueError('native structure digest does not match')
        loaded[ref] = json.loads(raw)
        return loaded[ref]

    def model_for(ref):
        if not re.fullmatch(r'#/(texts|tables|pictures|groups)/\d+', ref):
            raise ValueError('unsupported native structure reference: ' + str(ref))
        return {'texts':TextItem,'tables':TableItem,'pictures':PictureItem,'groups':GroupItem}[ref.split('/')[1]]

    def metadata(ref, depth, ancestors=()):
        depth_check(depth)
        if ref == '#/body':
            return
        if ref in ancestors:
            raise ValueError('native structure parent cycle')
        if ref in metadata_done:
            return
        model = model_for(ref)
        row = db.execute('SELECT fields FROM native_nodes WHERE ref=? AND length(fields)<=4096', (ref,)).fetchone()
        if row is None:
            raise ValueError('native structure node metadata is missing: ' + ref)
        fields = json.loads(row[0])
        value = {}
        for field in ('self_ref','label','parent','prov','captions','footnotes'):
            if field in fields:
                raw = read(ref + '/' + field)
                parsed = TypeAdapter(model.model_fields[field].annotation).validate_python(raw)
                value[field] = parsed.model_dump(mode='json', by_alias=True, exclude_none=True) if hasattr(parsed, 'model_dump') else [
                    item.model_dump(mode='json', by_alias=True, exclude_none=True) if hasattr(item, 'model_dump') else item
                    for item in parsed] if isinstance(parsed, list) else parsed
        if value.get('self_ref') != ref or 'label' not in value:
            raise ValueError('native structure identity does not match')
        if model is TableItem:
            value['data'] = {key:read(ref + '/data/' + key) for key in ('num_rows','num_cols')}
        containers[ref] = value
        parent = value.get('parent')
        if parent:
            metadata(parent['$ref'], depth + 1, (*ancestors, ref))
        # Mark only after checking parent edges; normal caption -> table parent
        # edges must not be mistaken for a dependency cycle.
        metadata_done.add(ref)
        for field in ('captions','footnotes'):
            for dependency in value.get(field, []):
                pending_nodes.append((dependency['$ref'], depth + 1))

    def node(ref, depth):
        depth_check(depth)
        if ref in active:
            raise ValueError('native structure dependency cycle')
        if ref in done:
            return
        model = model_for(ref)
        active.add(ref)
        if model is TextItem:
            raw = read(ref)
            text_adapter.validate_python(raw)
            if raw.get('self_ref') != ref:
                raise ValueError('native structure identity does not match')
            nodes[ref] = raw
            value = text_adapter.validate_python(raw)
            if value.parent:
                metadata(value.parent.cref, depth + 1)
            children = [child.cref for child in value.children]
        elif model in (PictureItem, GroupItem):
            metadata(ref, depth)
            children = [child['$ref'] for child in read(ref + '/children')]
        else:
            raise ValueError('native structure requires explicit table cell roots, not a whole table')
        for child in children:
            node(child, depth + 1)
        active.remove(ref)
        done.add(ref)

    def cell(ref, depth, include_headers):
        depth_check(depth)
        if ref in cells:
            return
        if not re.fullmatch(r'#/tables/\d+/data/table_cells/\d+', ref):
            raise ValueError('unsupported native table cell reference')
        raw = read(ref)
        value = (RichTableCell if 'ref' in raw else TableCell).model_validate(raw)
        cells[ref] = raw
        table_ref = ref.split('/data/')[0]
        metadata(table_ref, depth + 1)
        if isinstance(value, RichTableCell):
            node(value.ref.cref, depth + 1)
        if include_headers:
            table_id = int(table_ref.rsplit('/', 1)[1])
            for role in (1, 2):
                extent = ('b.col_min<? AND b.col_max>? AND b.row_max<=?' if role == 1 else
                    'b.row_min<? AND b.row_max>? AND b.col_max<=?')
                coords = ((value.end_col_offset_idx, value.start_col_offset_idx, value.start_row_offset_idx)
                    if role == 1 else (value.end_row_offset_idx, value.start_row_offset_idx, value.start_col_offset_idx))
                rows = db.execute('''SELECT h.ref FROM native_header_bounds b CROSS JOIN native_headers h ON h.id=b.id
                    WHERE b.table_min<=? AND b.table_max>=? AND b.role_min<=? AND b.role_max>=? AND ''' + extent +
                    ' LIMIT ?', (table_id, table_id, role, role, *coords, selection.max_objects + 1))
                for count, (header_ref,) in enumerate(rows):
                    if count >= selection.max_objects:
                        raise DocumentReaderBudgetError('native structure header object budget exceeded')
                    cell(header_ref, depth + 1, False)

    for root in selection.roots:
        if '/data/table_cells/' in root:
            cell(root, 0, True)
        else:
            node(root, 0)
        while pending_nodes:
            dependency, depth = pending_nodes.pop()
            node(dependency, depth)
    result = dict(roots=selection.roots, nodes=nodes, containers=containers, cells=cells)
    if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > selection.max_bytes:
        raise DocumentReaderBudgetError('native structure transport byte budget exceeded')
    return result, read_bytes, len(loaded)


def _read_source_windows(db, stream, selection, check, source_range=None):
    if source_range is None:
        rows = db.execute('SELECT ordinal,start,end FROM source_windows WHERE ordinal>? ORDER BY ordinal LIMIT ?',
            (selection.after, selection.limit))
        total = int(db.execute("SELECT value FROM metadata WHERE key='source_windows'").fetchone()[0])
        last = selection.after
    else:
        rows, total, last = [(0, *source_range)], 1, -1
    items, read_bytes, transport_bytes = [], 0, 0
    for ordinal, start, end in rows:
        check()
        if ordinal != last + 1 or not 0 <= start < end or end-start > 12_288:
            raise ValueError('native source window index continuation or extent is invalid')
        text_parts, ranges, cursor, pending_join = [], [], start, 0
        window_read_bytes = 0
        mapped = db.execute('''SELECT start,end,kind,native_ref,native_start,join_before_length
            FROM source_map WHERE start>=(SELECT start FROM source_map WHERE start<=?
                ORDER BY start DESC LIMIT 1) AND start<? AND end>? ORDER BY start''',
            (start, end, start))
        mapping_count = 0
        for map_start, map_end, kind, native_ref, native_start, join_len in mapped:
            check()
            mapping_count += 1
            if mapping_count > 258:
                raise DocumentReaderBudgetError('native source window mapping count exceeds budget')
            lo, hi = max(start, map_start), min(end, map_end)
            if lo >= hi or lo != cursor:
                if lo >= hi:
                    continue
                raise ValueError('native source window map has a gap or overlap')
            if kind == 'newline':
                value = '\n' * (hi-lo)
                pending_join += hi-lo
            elif kind == 'native' and native_ref:
                scalar_start = native_start + lo-map_start
                scalar_end = native_start + hi-map_start
                first_segment = scalar_start // SCALAR_SEGMENT * SCALAR_SEGMENT
                segments = db.execute('''SELECT start,end,offset,length,digest FROM segments
                    WHERE ref=? AND start>=? AND start<? ORDER BY start LIMIT 5''',
                    (native_ref, first_segment, scalar_end))
                parts, covered = [], scalar_start
                for cp_start, cp_end, offset, length, digest in segments:
                    check()
                    if cp_start > covered or cp_end <= covered:
                        raise ValueError('native source window scalar map is incomplete')
                    if read_bytes + length > min(selection.max_bytes, PHYSICAL_READ_LIMIT):
                        raise DocumentReaderBudgetError('native source window physical byte budget exceeded')
                    stream.seek(offset)
                    raw = stream.read(length)
                    read_bytes += len(raw)
                    window_read_bytes += len(raw)
                    if len(raw) != length or sha256(raw).digest() != digest:
                        raise ValueError('native source window scalar digest does not match')
                    scalar = json.loads(b'"' + raw + b'"')
                    if len(scalar) != cp_end-cp_start:
                        raise ValueError('native source window scalar length does not match')
                    parts.append(scalar[max(0,scalar_start-cp_start):min(cp_end,scalar_end)-cp_start])
                    covered = min(scalar_end, cp_end)
                if covered != scalar_end:
                    raise ValueError('native source window scalar extent is incomplete')
                value = ''.join(parts)
                descriptor = dict(nativeRef=native_ref, start=scalar_start, end=scalar_end,
                    windowStart=lo-start, windowEnd=hi-start)
                if (ranges and join_len and pending_join == join_len and
                        ranges[-1]['windowEnd'] + join_len == lo-start):
                    descriptor['joinBefore'] = '\n' * join_len
                ranges.append(descriptor)
                pending_join = 0
            else:
                raise ValueError('native source window map record is invalid')
            text_parts.append(value)
            cursor = hi
        if cursor != end:
            raise ValueError('native source window map is incomplete')
        text = ''.join(text_parts)
        item = dict(start=start, end=end, text=text, nativeRanges=ranges, readBytes=window_read_bytes)
        encoded_size = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode())
        if transport_bytes + encoded_size > selection.max_bytes:
            if items:
                break
            raise DocumentReaderBudgetError('native source window transport byte budget exceeded')
        items.append(item)
        transport_bytes += encoded_size
        last = ordinal
    return dict(items=items, total=total, nextCursor=last if last+1 < total else None,
        readBytes=read_bytes)


def read_source_text_range(request, *, start: int, end: int):
    """Hydrate one exact source-offset range from the canonical native artifact."""
    if request.selection.field != 'source_windows':
        raise ValueError('source text range requires a source_windows selection')
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError('native source range is invalid')
    if end-start > 12_288:
        raise DocumentReaderBudgetError('native source range exceeds character budget')
    result = _read_document_reader(request, source_range=(start, end))
    return {'header': result['header'], 'item': result['items'][0], 'readBytes': result['readBytes']}


def read_document_reader(request):
    return _read_document_reader(request)


def read_source_header(request):
    """Admit installed source identity without reading any native body bytes."""
    return _read_document_reader(request, header_only=True)


def read_source_locations(request, *, after=-1, limit=128, start=None, end=None, context=False, hydrate=True, ref=None, cells_only=False):
    """Page exact producer locations, optionally selecting native grounding closure."""
    if type(after) is not int or after < -1 or type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('native location cursor or limit is invalid')
    if (context or start is not None or end is not None) and (type(start) is not int or type(end) is not int or not 0 <= start < end or end-start > 12_288):
        raise ValueError('native location context range is invalid')
    if ref is not None and (not isinstance(ref, str) or len(ref) > 1024):
        raise ValueError('native location reference is invalid')
    return _read_document_reader(request, location_query=dict(after=after, limit=limit,
        start=start, end=end, context=context, hydrate=hydrate, ref=ref, locate=False, cells_only=cells_only))


def locate_source_range(request, *, start, end, hydrate=True, include_quote=True):
    """Choose the shortest containing location, preserving producer order on ties."""
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError('native location range is invalid')
    result = _read_document_reader(request, location_query=dict(after=-1, limit=1,
        start=start, end=end, context=False, hydrate=hydrate, ref=None, locate=True,
        include_quote=include_quote))
    return {'header': result['header'], 'item': result['items'][0] if result['items'] else None,
        'readBytes': result['readBytes']}


def read_source_native_ranges(request, *, after=-1, limit=128, start=None, end=None):
    """Page original native scalar extents without hydrating text or clipping windows."""
    if type(after) is not int or after < -1 or type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('native source-map cursor or limit is invalid')
    if (start is not None or end is not None) and (type(start) is not int or type(end) is not int or not 0 <= start < end or end-start > 12_288):
        raise ValueError('native source-map window range is invalid')
    return _read_document_reader(request, source_map_query=(after, limit, start, end))


def read_source_window_ranges(request, *, after=-1, limit=128):
    """Page existing extraction-window addresses without reading source text."""
    if type(after) is not int or after < -1 or type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('native source-window cursor or limit is invalid')
    return _read_document_reader(request, window_map_query=(after, limit))


def _read_source_window_ranges(db, selection, after, limit, check):
    rows = db.execute('SELECT ordinal,start,end FROM source_windows WHERE ordinal>? ORDER BY ordinal LIMIT ?',
        (after, limit+1))
    items, last, size, more = [], after, 0, False
    for ordinal, start, end in rows:
        check()
        if len(items) == limit:
            more = True
            break
        if type(start) is not int or type(end) is not int or not 0 <= start < end or end-start > 12_288:
            raise DocumentReaderIndexError('native source-window extent is invalid; rebuild the representation')
        item = dict(start=start, end=end)
        size += len(json.dumps(item, separators=(',', ':')).encode())
        if size > selection.max_bytes:
            raise DocumentReaderBudgetError('native source-window transport byte budget exceeded')
        items.append(item)
        last = ordinal
    return dict(items=items, nextCursor=last if more else None, readBytes=0)


def _read_source_native_ranges(db, selection, after, limit, start, end, check):
    items, last, size = [], after, 0
    where, params = 'm.start>?', [after]
    if start is not None:
        where += " AND m.start>=(SELECT start FROM source_map WHERE kind='native' AND start<=? ORDER BY start DESC LIMIT 1) AND m.start<? AND m.end>?"
        params.extend((start, end, start))
    rows = db.execute('''SELECT start,end,native_ref,native_start,join_before_length,
        (SELECT p.end FROM source_map p WHERE p.kind='native' AND p.start<m.start ORDER BY p.start DESC LIMIT 1)
        FROM source_map m WHERE kind='native' AND ''' + where + ' ORDER BY start LIMIT ?', (*params, limit+1))
    more = False
    for start, end, ref, native_start, join_len, previous_end in rows:
        check()
        if len(items) == limit:
            more = True
            break
        if not ref or not 0 <= start < end or native_start < 0 or join_len not in (0, 1, 2):
            raise ValueError('native source-map extent is invalid')
        item = dict(nativeRef=ref, start=native_start, end=native_start+end-start,
            windowStart=start, windowEnd=end)
        if join_len and previous_end is not None and previous_end+join_len == start:
            item['joinBefore'] = '\n'*join_len
        size += len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode())
        if size > selection.max_bytes:
            raise DocumentReaderBudgetError('native source-map transport byte budget exceeded')
        items.append(item)
        last = start
    return dict(items=items, nextCursor=last if more else None, readBytes=0)


def _read_source_locations(db, stream, selection, query, check):
    from types import SimpleNamespace
    steps = 0
    def progress():
        nonlocal steps
        check()
        steps += 1000
        if steps > 200_000:
            raise DocumentReaderBudgetError('native location query work budget exceeded')
        return 0
    db.set_progress_handler(progress, 1000)
    prefix, where, params = '', 'l.ordinal>?', [query['after']]
    order = 'l.ordinal'
    if query['context']:
        prefix = '''WITH RECURSIVE overlap AS (
            SELECT l.ordinal,l.page FROM source_location_bounds b CROSS JOIN source_locations l ON l.ordinal=b.ordinal
                WHERE b.start_min<? AND b.start_max>?),
            admitted AS (SELECT ref FROM source_locations WHERE
                ordinal IN (SELECT ordinal FROM overlap) OR page IN (SELECT page FROM overlap WHERE page IS NOT NULL)),
            initial AS (SELECT table_id,ref FROM source_locations WHERE ref IN (SELECT ref FROM admitted)),
            selected(ref) AS (SELECT ref FROM initial UNION
                SELECT ref FROM source_locations WHERE table_id IN (SELECT table_id FROM initial WHERE table_id IS NOT NULL)
                UNION SELECT d.ref FROM selected s JOIN source_locations x ON x.ordinal=
                    (SELECT MAX(ordinal) FROM source_locations WHERE ref=s.ref)
                    JOIN source_location_dependencies d ON d.ordinal=x.ordinal)
            '''
        params = [query['end'], query['start'], *params]
        where += " AND l.ref IN (SELECT ref FROM selected) AND NOT (l.table_id IS NOT NULL AND json_extract(l.descriptor,'$.cell') IS NULL)"
    elif query['locate']:
        where += ' AND l.ordinal IN (SELECT ordinal FROM source_location_bounds WHERE start_min<=? AND start_max>=?)'
        params.extend((query['start'], query['end']))
        order = '(l.end-l.start),l.ordinal'
    elif query['start'] is not None:
        where += ' AND l.ordinal IN (SELECT ordinal FROM source_location_bounds WHERE start_min<? AND start_max>?)'
        params.extend((query['end'], query['start']))
    if query.get('cells_only'):
        where += " AND json_extract(l.descriptor,'$.cell') IS NOT NULL"
    if query['ref'] is not None:
        where += ' AND l.ref=?'
        params.append(query['ref'])
    rows = db.execute(prefix + 'SELECT l.ordinal,l.descriptor FROM source_locations l WHERE ' + where +
        ' ORDER BY ' + order + ' LIMIT ?', (*params, query['limit']+1))
    items, read_bytes, transport, last, more = [], 0, 0, query['after'], False
    physical_limit = min(selection.max_bytes, PHYSICAL_READ_LIMIT)
    def hydrate_address(address):
        nonlocal read_bytes
        check()
        lo, hi = address['start'], address['end']
        if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi or hi-lo > 12_288:
            raise DocumentReaderBudgetError('native location scalar extent exceeds budget')
        if lo == hi:
            return ''
        if address['kind'] == 'source':
            value = _read_source_windows(db, stream, SimpleNamespace(max_bytes=physical_limit-read_bytes), check, (lo, hi))
            read_bytes += value['readBytes']
            return value['items'][0]['text']
        if address['kind'] != 'native':
            raise ValueError('native location scalar address is invalid')
        parts, covered = [], lo
        for start, end, offset, length, digest in db.execute('''SELECT start,end,offset,length,digest
            FROM segments WHERE ref=? AND start>=? AND start<? ORDER BY start LIMIT 5''',
            (address['ref'], lo//SCALAR_SEGMENT*SCALAR_SEGMENT, hi)):
            check()
            if start > covered or end <= covered or length < 0 or offset < 0:
                raise ValueError('native location scalar map is invalid')
            if read_bytes+length > physical_limit:
                raise DocumentReaderBudgetError('native location physical byte budget exceeded')
            stream.seek(offset)
            raw = stream.read(length)
            read_bytes += len(raw)
            if len(raw) != length or sha256(raw).digest() != digest:
                raise ValueError('native location scalar digest does not match')
            scalar = json.loads(b'"' + raw + b'"')
            if len(scalar) != end-start:
                raise ValueError('native location scalar length does not match')
            parts.append(scalar[max(lo-start,0):min(hi,end)-start])
            covered = min(hi, end)
        if covered != hi:
            raise ValueError('native location scalar extent is incomplete')
        return ''.join(parts)
    for ordinal, encoded in rows:
        check()
        if len(items) == query['limit']:
            more = True
            break
        if len(encoded.encode()) > 16*1024:
            raise DocumentReaderBudgetError('native location descriptor exceeds budget')
        item = json.loads(encoded)
        if not query['hydrate']:
            item['sourceLocationOrdinal'] = ordinal
        if query['hydrate']:
            quote_address = item.pop('quoteAddress')
            if query.get('include_quote', True):
                item['quote'] = hydrate_address(quote_address)
            item['section_path'] = [hydrate_address(address) for address in item.pop('sectionPathAddresses', [])]
            if 'originalTextAddress' in item:
                item['structure']['original_text'] = hydrate_address(item.pop('originalTextAddress'))
        size = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode())
        if transport+size > selection.max_bytes:
            raise DocumentReaderBudgetError('native location transport byte budget exceeded')
        items.append(item)
        transport += size
        last = ordinal
    return dict(items=items, nextCursor=last if more else None, readBytes=read_bytes)


def _read_document_reader(request, *, source_range=None, header_only=False, location_query=None, source_map_query=None, window_map_query=None):
    try:
        return _read_installed_document_reader(request, source_range=source_range, header_only=header_only,
            location_query=location_query, source_map_query=source_map_query, window_map_query=window_map_query)
    except sqlite3.DatabaseError as exc:
        if str(exc) == 'interrupted':
            check_query_cancellation()
            raise DocumentReaderBudgetError('native document reader query work or deadline budget exceeded') from exc
        raise DocumentReaderIndexError('native document reader index is invalid; rebuild the representation') from exc


def _read_installed_document_reader(request, *, source_range=None, header_only=False, location_query=None, source_map_query=None, window_map_query=None):
    deadline = monotonic() + 30
    def check():
        check_query_cancellation()
        if monotonic() > deadline:
            raise TimeoutError('document reader exceeded its execution budget')
    source, index = Path(request.artifact.path), Path(request.reader_index.path)
    for path, ref in ((source, request.artifact), (index, request.reader_index)):
        if ref.installation.identity != _identity(path):
            raise ValueError('document reader installation changed; publish before querying')
    selection = request.selection
    physical_limit = min(selection.max_bytes, PHYSICAL_READ_LIMIT)
    read_bytes, transport_bytes, items, last = 0, 0, [], selection.after
    with closing(sqlite3.connect(index.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db, source.open('rb') as stream:
        db.execute('PRAGMA cache_size=-2048')
        db.set_progress_handler(lambda: (check() or 0), 1000)
        metadata = dict(db.execute("SELECT key,value FROM metadata WHERE key IN ('format','artifactDigest','header','chunks','pages','source_windows') AND length(CAST(value AS BLOB))<=? LIMIT 6", (METADATA_LIMIT,)))
        if set(metadata) != {'format', 'artifactDigest', 'header', 'chunks', 'pages', 'source_windows'}:
            raise DocumentReaderIndexError('document reader index metadata is missing or exceeds budget; rebuild the representation')
        try:
            header = json.loads(metadata['header'])
        except (ValueError, TypeError) as exc:
            raise DocumentReaderIndexError('native reader header is invalid; rebuild the representation') from exc
        if not isinstance(header, dict) or not all(key in header for key in
                ('materialRevision', 'representationRevision', 'format', 'sourceCharCount',
                 'sourceWindowCount', 'sourceLocationCount', 'documentPageCount')):
            raise DocumentReaderIndexError('native reader admission metadata is incomplete; rebuild the representation')
        if (metadata.get('format') != INDEX_FORMAT or metadata.get('artifactDigest') != request.artifact.digest
                or header.get('protocol') != 'semantica.parsed-source.v3'
                or header['materialRevision'] != request.material_revision
                or header['representationRevision'] != request.representation_revision):
            raise ValueError('document reader index does not match requested representation')
        header['sourceId'] = request.source_id
        if location_query is not None or source_map_query is not None or window_map_query is not None:
            required = ({'source_locations', 'source_location_bounds', 'source_location_dependencies', 'segments', 'source_map'}
                if location_query is not None else {'source_map'} if source_map_query is not None else {'source_windows'})
            found = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('source_locations','source_location_bounds','source_location_dependencies','segments','source_map','source_windows')")}
            if not required <= found:
                raise DocumentReaderIndexError('native source address index is missing; rebuild the representation')
        if window_map_query is not None:
            result = _read_source_window_ranges(db, selection, *window_map_query, check)
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header': header, **result}
        if source_map_query is not None:
            result = _read_source_native_ranges(db, selection, *source_map_query, check)
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header': header, **result}
        if location_query is not None:
            result = _read_source_locations(db, stream, selection, location_query, check)
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header': header, **result}
        if header_only:
            check()
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header': header, 'readBytes': 0}
        if selection.field == 'source_windows':
            result = _read_source_windows(db, stream, selection, check, source_range)
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header':header, **result}
        if selection.field == 'structure':
            if header.get('format') != 'docling':
                raise ValueError('native structure requires a Docling representation')
            structure, read_bytes, object_count = _read_structure(db, stream, selection, check)
            for path, ref in ((source, request.artifact), (index, request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
            return {'header':header, 'structure':structure, 'readBytes':read_bytes,
                'objectsRead':object_count, 'nextCursor':None}
        elif selection.field == 'ranges':
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='items_native_range'").fetchone():
                raise ValueError('native reader location index is missing; rebuild the representation')
            total = len(selection.ranges)
            def range_rows():
                metadata_bytes = 0
                for ordinal, item in enumerate(selection.ranges):
                    locator, page_numbers = {}, set()
                    for field in ('chunks', 'pages'):
                        candidates = db.execute('''SELECT descriptor FROM items
                            WHERE field=? AND json_extract(descriptor,'$.ref')=?
                            AND json_extract(descriptor,'$.start')>=? AND json_extract(descriptor,'$.start')<=?
                            ORDER BY json_extract(descriptor,'$.start') DESC LIMIT 129''',
                            (field, item.native_ref, item.start // SCALAR_SEGMENT * SCALAR_SEGMENT, item.start))
                        for position, (encoded,) in enumerate(candidates):
                            check()
                            metadata_bytes += len(encoded.encode('utf-8'))
                            if position >= 128 or metadata_bytes > PHYSICAL_READ_LIMIT:
                                raise DocumentReaderBudgetError('native reader location metadata exceeds budget')
                            descriptor = json.loads(encoded)
                            if descriptor['end'] <= item.start:
                                continue
                            if field == 'chunks':
                                locator = descriptor['locator']
                            else:
                                page_numbers.add(descriptor['pageNumber'])
                    # A cross-page scalar opens at the page containing the range start.
                    if len(page_numbers) == 1:
                        locator = {**locator, 'page': next(iter(page_numbers))}
                    yield ordinal, json.dumps({'ref': item.native_ref, 'start': item.start,
                        'end': item.end, 'locator': {**locator, 'nativeRef': item.native_ref,
                            'startChar': item.start, 'endChar': item.end}})
            rows = range_rows()
        elif selection.page_number is None:
            total = int(metadata[selection.field])
            rows = db.execute('''SELECT ordinal,descriptor FROM items
                WHERE field=? AND ordinal>? ORDER BY ordinal LIMIT ?''',
                (selection.field, selection.after, selection.limit))
        else:
            count = db.execute('SELECT parts FROM page_counts WHERE page=?', (selection.page_number,)).fetchone()
            total = count[0] if count else 0
            rows = db.execute('''SELECT json_extract(descriptor,'$.pagePart'),descriptor FROM items
                WHERE field='pages' AND page=? AND json_extract(descriptor,'$.pagePart')>?
                ORDER BY json_extract(descriptor,'$.pagePart') LIMIT ?''',
                (selection.page_number, selection.after, selection.limit))
        if total < 0:
            raise ValueError('document reader index count is invalid')
        for ordinal, descriptor in rows:
            check()
            if ordinal != last + 1 or ordinal >= total:
                raise ValueError('document reader index continuation is invalid')
            if len(descriptor.encode('utf-8')) > 16 * 1024:
                raise DocumentReaderBudgetError('native reader address metadata exceeds budget')
            record = json.loads(descriptor)
            value = ''
            if 'ref' in record:
                start, end = record['start'], record['end']
                if not 0 <= start <= end or end - start > 64 * 1024:
                    raise ValueError('native reader scalar range is invalid')
                rows = list(db.execute('''SELECT start,end,offset,length,digest FROM segments
                    WHERE ref=? AND start>=? AND start<? ORDER BY start LIMIT 5''',
                    (record['ref'], start // SCALAR_SEGMENT * SCALAR_SEGMENT, end)))
                needed = sum(row[3] for row in rows)
                if read_bytes + needed > physical_limit:
                    if items and selection.field != 'ranges':
                        break
                    raise DocumentReaderBudgetError('native reader physical byte budget exceeded')
                parts, covered = [], start
                for cp_start, cp_end, offset, length, digest in rows:
                    check()
                    if (offset < 0 or length < 0 or offset + length > source.stat().st_size
                            or cp_start > covered or cp_end <= covered):
                        raise ValueError('native reader scalar address is invalid')
                    stream.seek(offset)
                    raw = stream.read(length)
                    read_bytes += len(raw)
                    if len(raw) != length or sha256(raw).digest() != digest:
                        raise ValueError('native reader scalar digest does not match')
                    scalar = json.loads(b'"' + raw + b'"')
                    if len(scalar) != cp_end - cp_start:
                        raise ValueError('native reader scalar length does not match')
                    parts.append(scalar[max(0, start - cp_start):min(len(scalar), end - cp_start)])
                    covered = min(end, cp_end)
                if covered != end:
                    raise ValueError('native reader scalar range is incomplete')
                value = ''.join(parts)
            if selection.field in ('chunks', 'ranges'):
                item = {'text': value, 'locator': record['locator']}
            else:
                item = {key: val for key, val in record.items() if key not in ('ref','start','end','locator','box')}
                item['text'] = value
                item['textStartChar'] = record.get('start', 0)
                item['textEndChar'] = record.get('end', 0)
                item['blocks'] = ([{'text': value, **record['box'], 'blockOrdinal': record['blockStart'],
                    'startChar': record['start'], 'endChar': record['end'], 'locator': record['locator']}]
                    if 'box' in record else [])
            item_bytes = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            if transport_bytes + item_bytes > selection.max_bytes:
                if items and selection.field != 'ranges':
                    break
                raise DocumentReaderBudgetError('native reader item exceeds transport byte budget')
            items.append(item)
            transport_bytes += item_bytes
            last = ordinal
        for path, ref in ((source, request.artifact), (index, request.reader_index)):
            if ref.installation.identity != _identity(path):
                raise ValueError('document reader installation changed during reading')
    return {'header': header, 'items': items, 'total': total, 'readBytes': read_bytes,
        'nextCursor': last if last + 1 < total else None}
