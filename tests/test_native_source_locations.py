"""Build context uses exact native location addresses, never stored body copies."""
import json
import sqlite3

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import TableCell, TableData, RichTableCell, ProvenanceItem

from semantica.parse.document_reader import _docling_locations, native_text_projection
from semantica.semantic_document_reader import (write_reader_artifact, read_source_locations,
    locate_source_range, read_source_native_ranges, DocumentReaderBudgetError, DocumentReaderIndexError)
from semantica.semantic_source_artifact import _native_grounding_ranges
from semantica.semantic_worker_context import query_cancellation
from semantica.utils.exceptions import ProcessingError
from threading import Event
from tests.test_native_document_reader import payload, request


def original_context_oracle(locations, start, end):
    """Frozen pre-cutover context semantics, independent of the indexed consumer."""
    overlapping = [item for item in locations if item['start'] is not None
        and item['start'] < end and item['end'] > start]
    pages = {item['page'] for item in overlapping if item.get('page') is not None}
    selected = {item['ref'] for item in locations if item in overlapping or item.get('page') in pages}
    tables = {item['table_id'] for item in locations if item['ref'] in selected and item.get('table_id')}
    selected.update(item['ref'] for item in locations if item.get('table_id') in tables)
    by_ref = {item['ref']: item for item in locations}
    pending = list(selected)
    while pending:
        item = by_ref[pending.pop()]
        for key in ('captions', 'footnotes', 'references'):
            for reference in item.get('structure', {}).get(key, []):
                ref = reference.get('$ref') if isinstance(reference, dict) else reference
                if isinstance(ref, str) and ref in by_ref and ref not in selected:
                    selected.add(ref)
                    pending.append(ref)
    return [dict(item) for item in locations if item['ref'] in selected
        and not (item.get('table_id') and not item.get('cell'))]


def fixture(tmp_path):
    native = DoclingDocument(name='source-locations')
    for number in (1, 2):
        native.add_page(page_no=number, size=Size(width=600, height=800))
    def prov(page, length):
        return ProvenanceItem(page_no=page, charspan=(0, length), bbox=BoundingBox(
            l=1, t=10, r=100, b=1, coord_origin=CoordOrigin.BOTTOMLEFT))
    native.add_text(label='section_header', text=' Unique heading 😀 ', prov=prov(1, 18))
    caption = native.add_text(label='caption', text='Unique caption body', prov=prov(1, 19))
    note = native.add_text(label='footnote', text='Unique note body', prov=prov(2, 16))
    cells = [TableCell(text=value, start_row_offset_idx=row, end_row_offset_idx=row+1,
        start_col_offset_idx=0, end_col_offset_idx=1, column_header=row == 0)
        for row, value in enumerate(('Unique header body', 'rich fallback'))]
    table = native.add_table(data=TableData(num_rows=2, num_cols=1, table_cells=cells), caption=caption)
    table.prov.extend([prov(1, 0), prov(2, 0)])
    table.footnotes.append(note.get_ref())
    rich = native.add_text(label='text', text='Unique rich body 漢', parent=table, prov=prov(2, 18))
    table.data.table_cells[1] = RichTableCell(**cells[1].model_dump(), ref=rich.get_ref())
    formula = native.add_text(label='formula', text='Unique formula text', prov=prov(2, 19))
    formula.orig = 'UNIQUE ORIGINAL FORMULA 😀'
    split = native.add_text(label='text', text='Multipage Unicode 😀 content')
    split.prov.extend([prov(1, 10), prov(2, len(split.text))])
    split.prov[1].charspan = (10, len(split.text))
    tail = native.add_text(label='text', text='Unrelated page one', prov=prov(1, 18))
    document = {'format': 'docling', 'document': native.export_to_dict(), 'pages': []}
    text = native_text_projection(document)[0]
    expected = _docling_locations(document, text)
    path = tmp_path / 'source.json'
    digests = write_reader_artifact(path, payload(document))
    return path, digests, text, expected


def test_location_pages_restore_exact_oracle_without_index_body(tmp_path):
    path, digests, text, expected = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    items, after = [], -1
    while True:
        result = read_source_locations(selected, after=after, limit=2)
        items.extend(result['items'])
        after = result['nextCursor']
        if after is None:
            break
    assert items == expected
    index = path.with_suffix('.reader.sqlite')
    raw = index.read_bytes()
    for value in ('Unique heading', 'Unique caption body', 'Unique rich body', 'UNIQUE ORIGINAL FORMULA'):
        assert value.encode() not in raw
    with sqlite3.connect(index) as db:
        assert db.execute('SELECT count(*) FROM source_locations').fetchone()[0] == len(expected)
        assert all('quote' not in json.loads(row[0]) for row in db.execute('SELECT descriptor FROM source_locations'))


def test_context_and_locator_equal_existing_shortest_stable_oracle(tmp_path):
    path, digests, text, expected = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    for item in expected:
        if item['start'] is None:
            continue
        start, end = item['start'], min(item['end'], item['start'] + 3)
        wanted = original_context_oracle(expected, start, end)
        rows, after = [], -1
        while True:
            result = read_source_locations(selected, start=start, end=end, context=True, after=after, limit=2)
            rows.extend(result['items'])
            after = result['nextCursor']
            if after is None:
                break
        assert rows == wanted
        containing = [row for row in expected if row['start'] is not None
            and row['start'] <= start and end <= row['end']]
        assert locate_source_range(selected, start=start, end=end)['item'] == min(
            containing, key=lambda row: row['end'] - row['start'])


def test_builder_locator_does_not_hydrate_unconsumed_oversized_quote(tmp_path, monkeypatch):
    from semantica import semantic_document_reader as reader
    from semantica.semantic_source_artifact import _NativeSourceLocations
    from semantica.semantic_publication_builder import _located_document_fields
    native = DoclingDocument(name='long-paragraph')
    native.add_text(label='text', text=('ordinary descriptive context. ' * 550)[:15_950])
    path = tmp_path / 'long.json'
    digests = write_reader_artifact(path, payload({'format': 'docling',
        'document': native.export_to_dict(), 'pages': []}))
    selected = request(path, digests, 'source_windows')
    reads = []
    locate = reader.locate_source_range

    def observe(*args, **kwargs):
        result = locate(*args, **kwargs)
        reads.append(result['readBytes'])
        assert 'quote' not in result['item'] and 'quoteAddress' not in result['item']
        return result

    monkeypatch.setattr(reader, 'locate_source_range', observe)
    fields, metadata = _located_document_fields(_NativeSourceLocations(selected), 0, 20)
    assert fields == {}
    assert metadata['structural_ref'] == '#/texts/0'
    assert reads == [0], 'location metadata must not read the unused 15,950-character quote'


def test_builder_locator_preserves_hydrated_structure_and_section_fields(tmp_path):
    from semantica.semantic_source_artifact import _NativeSourceLocations
    from semantica.semantic_publication_builder import _located_document_fields
    path, digests, _, expected = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    for item in expected:
        if item['start'] is None:
            continue
        start, end = item['start'], min(item['end'], item['start'] + 3)
        containing = min((row for row in expected if row['start'] is not None
            and row['start'] <= start and end <= row['end']), key=lambda row: row['end'] - row['start'])
        fields, metadata = _located_document_fields(_NativeSourceLocations(selected), start, end)
        wanted = {key: containing[key] for key in ('page', 'bbox', 'table_id', 'cell')
            if containing.get(key) is not None}
        if containing['section_path']:
            wanted['section_path'] = containing['section_path']
        assert fields == wanted
        assert metadata['structural_ref'] == containing['ref']
        if containing.get('structure'):
            assert metadata['structure'] == containing['structure']


def test_locations_fail_closed_on_bounds_and_mutation(tmp_path):
    path, digests, _, _ = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    selected.selection.max_bytes = 1
    with pytest.raises(DocumentReaderBudgetError):
        read_source_locations(selected, limit=1)
    path.touch()
    with pytest.raises(ValueError, match='installation changed'):
        read_source_locations(selected, limit=1)


def test_window_overlap_and_cell_filters_apply_before_hydration(tmp_path):
    path, digests, _, expected = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    for cell in (item for item in expected if item.get('cell') and item['start'] is not None):
        start, end = cell['start'], min(cell['end'], cell['start'] + 3)
        wanted = [item for item in expected if item.get('cell') and item['start'] is not None
            and item['start'] < end and item['end'] > start]
        rows, after = [], -1
        while True:
            page = read_source_locations(selected, start=start, end=end,
                cells_only=True, after=after, limit=1)
            rows.extend(page['items'])
            after = page['nextCursor']
            if after is None:
                break
        assert rows == wanted
        addresses = read_source_locations(selected, start=start, end=end,
            cells_only=True, hydrate=False, limit=1)
        assert addresses['readBytes'] == 0


def test_missing_location_index_requires_explicit_rebuild(tmp_path):
    path, digests, _, _ = fixture(tmp_path)
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        db.execute('DROP TABLE source_location_dependencies')
    with pytest.raises(DocumentReaderIndexError, match='rebuild'):
        read_source_locations(request(path, digests, 'source_windows'), limit=1)


@pytest.mark.parametrize('format', ['docling', 'pdf-text', 'epub', 'flat-odf'])
def test_original_scalar_ranges_page_without_body_hydration(tmp_path, format):
    from tests.test_native_source_windows import make_document
    document = make_document(format)
    text = native_text_projection(document)[0]
    path = tmp_path / 'source.json'
    digests = write_reader_artifact(path, payload(document))
    selected = request(path, digests, 'source_windows')
    rows, after = [], -1
    while True:
        result = read_source_native_ranges(selected, after=after, limit=2)
        assert result['readBytes'] == 0
        rows.extend(result['items'])
        after = result['nextCursor']
        if after is None:
            break
    assert rows == _native_grounding_ranges(document, text)


def test_address_pages_and_selected_hydration_do_not_read_unselected_body(tmp_path):
    native = DoclingDocument(name='large')
    for index in range(2000):
        native.add_text(label='text', text=f'Body number {index} ' + 'unselected '*30)
    path = tmp_path / 'large.json'
    digests = write_reader_artifact(path, payload({'format': 'docling',
        'document': native.export_to_dict(), 'pages': []}))
    selected = request(path, digests, 'source_windows')
    addresses = read_source_locations(selected, after=1997, limit=1, hydrate=False)
    assert addresses['readBytes'] == 0
    assert not any(key in addresses['items'][0] for key in ('quote', 'section_path', 'original_text'))
    hydrated = read_source_locations(selected, after=1997, limit=1)
    assert hydrated['items'][0]['quote'].startswith('Body number 1998 ')
    assert hydrated['readBytes'] < 1000 < path.stat().st_size//100
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        plan = ' '.join(str(row) for row in db.execute('EXPLAIN QUERY PLAN SELECT ordinal FROM '
            'source_location_bounds WHERE start_min<=? AND start_max>=?', (100, 102)))
        assert 'VIRTUAL TABLE INDEX' in plan
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        for call in (lambda: read_source_locations(selected, limit=1),
            lambda: read_source_native_ranges(selected, limit=1)):
            with pytest.raises(ProcessingError, match='canceled'):
                call()
    finally:
        query_cancellation.reset(token)


def test_indivisible_oversized_location_rejected_without_truncation(tmp_path):
    native = DoclingDocument(name='large-location')
    native.add_text(label='code', text='oversized '*2000)
    path = tmp_path / 'large.json'
    digests = write_reader_artifact(path, payload({'format': 'docling',
        'document': native.export_to_dict(), 'pages': []}))
    selected = request(path, digests, 'source_windows')
    assert read_source_locations(selected, limit=1, hydrate=False)['items']
    with pytest.raises(DocumentReaderBudgetError, match='scalar extent'):
        read_source_locations(selected, limit=1)


def test_context_address_hydration_preserves_each_native_record(tmp_path):
    from semantica.semantic_source_artifact import _NativeSourceLocations
    path, digests, text, expected = fixture(tmp_path)
    locations = _NativeSourceLocations(request(path, digests, 'source_windows'))
    addresses = list(locations.context_addresses(0, 6))
    assert addresses
    assert all('quote' not in item and 'sourceLocationOrdinal' in item for item in addresses)
    assert [locations.hydrate(item) for item in addresses] == original_context_oracle(expected, 0, 6)


@pytest.mark.parametrize("table_rows", [180, 360])
def test_large_native_table_context_streams_complete_units_with_original_batch_identity(tmp_path, table_rows):
    from semantica.semantic_source_artifact import _NativeSourceLocations
    from semantica import semantic_publication_builder as builder
    native = DoclingDocument(name='large-context')
    native.add_page(page_no=1, size=Size(width=600, height=800))
    prov = ProvenanceItem(page_no=1, charspan=(0, 6), bbox=BoundingBox(
        l=1, t=10, r=100, b=1, coord_origin=CoordOrigin.BOTTOMLEFT))
    native.add_text(label='text', text='Report', prov=prov)
    caption = native.add_text(label='caption', text='USD millions')
    note = native.add_text(label='footnote', text='Restated figures')
    cells = [TableCell(text=f'value {row} {col}', start_row_offset_idx=row, end_row_offset_idx=row+1,
        start_col_offset_idx=col, end_col_offset_idx=col+1, column_header=row == 0)
        for row in range(table_rows) for col in range(3)]
    table = native.add_table(data=TableData(num_rows=table_rows, num_cols=3, table_cells=cells), caption=caption)
    table.prov.append(prov)
    table.footnotes.append(note.get_ref())
    document = dict(format='docling', document=native.export_to_dict(), pages=[])
    path = tmp_path/'large-context.json'
    digests = write_reader_artifact(path, payload(document))
    locations = _NativeSourceLocations(request(path, digests, 'source_windows'))
    metadata_bytes = sum(len(json.dumps(item, ensure_ascii=False).encode())
        for item in locations.context_addresses(0, 6))
    assert metadata_bytes > 262144
    expected = list(builder._extraction_context_batches('Report', list(locations.context(0, 6)), 6000))
    actual = list(builder._extraction_context_batches('Report', builder._window_grounding_context(locations, 0, 6), 6000))
    assert actual == expected
    assert len(actual) > 1
    assert {record['ref'] for batch in actual for record in batch} == {
        record['ref'] for record in locations.context_addresses(0, 6)}
    from semantica.semantic_document_context import iter_source_context_units
    audit = {}
    units = [list(unit) for unit in iter_source_context_units(locations.reader, start=0, end=6, audit=audit)]
    assert len(units) == table_rows+2
    assert audit['closureExecutions'] == 1
    print(json.dumps(dict(tableRows=table_rows, **audit)))
    assert audit['vmSteps'] < table_rows*1600
    plan = str(audit['rowQueryPlan'])
    assert 'context_table_shared (table_id=? AND shared=?)' in plan
    assert 'VIRTUAL TABLE INDEX' in plan
    assert 'SEARCH l USING INTEGER PRIMARY KEY' in plan
    assert audit['temporaryPages'] * audit['pageBytes'] < 1024*1024



def test_context_session_excludes_consumer_waits_and_closes_on_cancel(tmp_path, monkeypatch):
    from semantica import semantic_document_context as query
    path, digests, _, _ = fixture(tmp_path)
    selected = request(path, digests, 'source_windows')
    clock = [100.0]
    monkeypatch.setattr(query, 'monotonic', lambda: clock[0])
    audit = {}
    session = query.iter_source_context_units(selected, start=0, end=6, audit=audit)
    first = next(session)
    assert list(first)
    # A model call can take minutes while the native cursor is suspended.
    clock[0] += 3600
    assert [list(unit) for unit in session]
    assert audit['closureExecutions'] == 1
    assert audit['temporaryPages'] * audit['pageBytes'] <= 32*1024*1024
    session = query.iter_source_context_units(selected, start=0, end=6)
    assert list(next(session))
    event = Event(); event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            list(session)
    finally:
        query_cancellation.reset(token)
        session.close()
