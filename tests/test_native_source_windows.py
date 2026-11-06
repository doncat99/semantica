"""Reader windows must preserve the builder's exact native text/window contract."""
from threading import Event
import sqlite3

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size

from semantica.semantic_document_reader import (write_reader_artifact, read_document_reader,
    DocumentReaderBudgetError, read_source_window_ranges)
from semantica.semantic_source_artifact import (_native_text, _native_grounding_ranges,
    _window_native_ranges, _NativeSourceRanges, _NativeWindowRanges)
from semantica.split.structural_chunker import StructuralChunker
from semantica.split.sliding_window_chunker import SlidingWindowChunker
from semantica.semantic_worker_context import query_cancellation
from semantica.parse.document_reader import SCALAR_SEGMENT
from semantica.utils.exceptions import ProcessingError
from tests.test_native_document_reader import request, payload


BODY = ('# Heading 😀\n\nA Unicode paragraph e\u0301 漢.\n'
    + ('- list item 日本語\n- second item\n\n' * 500)
    + '```python\nprint("end")\n```\n\n' + ('Tail content. ' * 900))


def _text_windows(text):
    """Frozen pre-cutover scheduling oracle, independent of the native index."""
    cursor = 0
    for chunk in StructuralChunker(respect_headers=True, respect_sections=True, max_chunk_size=12288).chunk(text):
        start, end = cursor, min(len(text), chunk.end_index)
        if end > start and text[start:end].strip():
            if end-start <= 12288:
                yield start, end, text[start:end]
            else:
                part_cursor = start
                for part in SlidingWindowChunker(chunk_size=12288, overlap=0).chunk(text[start:end]):
                    part_start, part_end = part_cursor, start+min(end-start, part.end_index)
                    if part_end > part_start and text[part_start:part_end].strip():
                        yield part_start, part_end, text[part_start:part_end]
                        part_cursor = part_end
                if part_cursor < end and text[part_cursor:end].strip():
                    yield part_cursor, end, text[part_cursor:end]
            cursor = end
    if cursor < len(text) and text[cursor:].strip():
        yield cursor, len(text), text[cursor:]


def make_document(format):
    if format == 'docling':
        native = DoclingDocument(name='windows')
        native.add_page(page_no=1, size=Size(width=600, height=800))
        native.add_text(label='section_header', text='# Heading 😀')
        native.add_text(label='text', text='')
        native.add_text(label='text', text='A Unicode paragraph e\u0301 漢.')
        native.add_text(label='text', text='- list item 日本語\n- second item')
        native.add_text(label='code', text='```python\nprint("end")\n```')
        native.add_text(label='text', text='Tail content. ' * 20000)
        return {'format':'docling', 'document':native.export_to_dict(), 'pages':[]}
    if format == 'pdf-text':
        return {'format':'pdf-text', 'pages':[
            {'page_number':1, 'text':'# Heading 😀\n\nA Unicode paragraph e\u0301 漢.'},
            {'page_number':2, 'text':''},
            {'page_number':3, 'text':'- list item 日本語\n- second item\n\n```python\nprint("end")\n```'},
            {'page_number':4, 'text':'Tail content. ' * 20000}]}
    sections = [
        {'text':'# Heading 😀\n\nA Unicode paragraph e\u0301 漢.'},
        {'text':''},
        {'text':'- list item 日本語\n- second item\n\n```python\nprint("end")\n```'},
        {'text':'Tail content. ' * 20000},
    ]
    if format == 'epub':
        sections = [dict(item, id=f'chapter-{i}', href=f'chapter-{i}.xhtml', media_type='application/xhtml+xml')
            for i, item in enumerate(sections)]
    else:
        sections = [dict(item, locator={'kind':'paragraph','paragraph':i}) for i,item in enumerate(sections)]
    return {'format':format, 'sections':sections}


@pytest.mark.parametrize('format', ['docling', 'pdf-text', 'epub', 'flat-odf'])
def test_reader_windows_match_exact_builder_windows_and_native_ranges(tmp_path, format):
    document = make_document(format)
    expected_text = _native_text(document)
    expected = list(_text_windows(expected_text))
    path = tmp_path / f'{format}.json'
    digests = write_reader_artifact(path, payload(document))
    addresses, after = [], -1
    while True:
        page = read_source_window_ranges(request(path, digests, 'source_windows'), after=after, limit=2)
        assert page['readBytes'] == 0
        addresses.extend(page['items'])
        after = page['nextCursor']
        if after is None:
            break
    assert addresses == [{'start': start, 'end': end} for start, end, _ in expected]
    rows, cursor = [], None
    while True:
        result = read_document_reader(request(path, digests, 'source_windows',
            after=-1 if cursor is None else cursor, limit=2, maxBytes=256*1024))
        rows.extend(result['items'])
        assert result['readBytes'] <= 256*1024
        cursor = result['nextCursor']
        if cursor is None:
            break
    assert [(item['start'], item['end'], item['text']) for item in rows] == expected
    ranges = _native_grounding_ranges(document, expected_text)
    lazy_windows = _NativeWindowRanges(request(path, digests, 'source_windows'), len(expected))
    assert list(lazy_windows) == [(start, end) for start, end, _ in expected]
    lazy_ranges = _NativeSourceRanges(request(path, digests, 'source_windows'))
    assert [_window_native_ranges(lazy_ranges, start, end) for start, end, _ in expected] == [
        _window_native_ranges(ranges, start, end) for start, end, _ in expected]
    assert [item['nativeRanges'] for item in rows] == [
        _window_native_ranges(ranges, start, end) for start, end, _ in expected]
    assert path.stat().st_size > 200_000
    assert max(item['readBytes'] for item in rows) <= 2*SCALAR_SEGMENT
    assert max(item['readBytes'] for item in rows) < path.stat().st_size // 8
    index = path.with_suffix('.reader.sqlite')
    assert b'Tail content.' not in index.read_bytes()
    with sqlite3.connect(index) as db:
        plan = ' '.join(str(row) for row in db.execute(
            'EXPLAIN QUERY PLAN SELECT start,end,kind,native_ref,native_start,join_before_length '
            'FROM source_map WHERE start>=(SELECT start FROM source_map WHERE start<=? '
            'ORDER BY start DESC LIMIT 1) AND start<? AND end>? ORDER BY start',
            (expected[0][0], expected[0][1], expected[0][0])))
    assert 'SEARCH source_map USING PRIMARY KEY' in plan and 'SCAN source_map' not in plan
    assert 'start>? AND start<?' in plan


def test_source_window_rejects_adversarial_map_fanout_and_missing_join_extent(tmp_path):
    document = {'format':'text', 'text':'x'*2000}
    path = tmp_path / 'fanout.json'
    digests = write_reader_artifact(path, payload(document))
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        db.execute('DELETE FROM source_map')
        for index in range(300):
            db.execute('INSERT INTO source_map VALUES (?,?,?,?,?,?)',
                (index, index+1, 'newline', None, None, 0))
    with pytest.raises(DocumentReaderBudgetError, match='mapping count exceeds budget'):
        read_document_reader(request(path, digests, 'source_windows', limit=1))

    document = {'format':'pdf-text', 'pages':[{'page_number':1, 'text':'bounded'}]}
    path = tmp_path / 'bad-map.json'
    digests = write_reader_artifact(path, payload(document))
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        db.execute('UPDATE source_map SET end=end-1 WHERE kind="native"')
    with pytest.raises(ValueError, match='incomplete'):
        read_document_reader(request(path, digests, 'source_windows', limit=1))


def test_source_window_query_observes_cancellation(tmp_path):
    from semantica.semantic_publication_builder import _read_source_projection_text as read_source_text_range
    document = make_document('pdf-text')
    path = tmp_path / 'cancel.json'
    digests = write_reader_artifact(path, payload(document))
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            read_document_reader(request(path, digests, 'source_windows', limit=1))
        with pytest.raises(ProcessingError, match='canceled'):
            read_source_text_range(request(path, digests, 'source_windows'), start=1, end=3)
    finally:
        query_cancellation.reset(token)


@pytest.mark.parametrize('format', ['docling', 'pdf-text', 'epub', 'flat-odf'])
def test_source_range_hydrates_exact_arbitrary_unicode_span(tmp_path, format):
    from semantica.semantic_document_reader import read_source_text_range
    document = make_document(format)
    text = _native_text(document)
    ranges = _native_grounding_ranges(document, text)
    path = tmp_path / f'range-{format}.json'
    digests = write_reader_artifact(path, payload(document))
    reader = request(path, digests, 'source_windows', limit=1)
    for start, end in ((3, 67), (16001, 18017), (len(text)-97, len(text))):
        result = read_source_text_range(reader, start=start, end=end)
        assert result['item']['text'] == text[start:end]
        assert result['item']['nativeRanges'] == _window_native_ranges(ranges, start, end)
        assert result['readBytes'] <= 256*1024
        assert result['readBytes'] < path.stat().st_size // 4
    for start, end in ((-1, 2), (1, 1), (0, 12289), (len(text)-1, len(text)+1)):
        with pytest.raises(ValueError):
            read_source_text_range(reader, start=start, end=end)
    reader.selection.max_bytes = 1
    with pytest.raises(DocumentReaderBudgetError, match='physical byte budget'):
        read_source_text_range(reader, start=1, end=3)
    path.touch()
    with pytest.raises(ValueError, match='installation changed'):
        read_source_text_range(reader, start=1, end=3)


def test_projection_reads_fragmented_source_by_native_windows(tmp_path, monkeypatch):
    from semantica import semantic_document_reader as reader
    from semantica.semantic_publication_builder import _read_source_projection_text
    from semantica.semantic_publication_builder import _source_passage_ranges, _source_occurrence_ordinals

    native = DoclingDocument(name='fragmented')
    for section in range(12):
        native.add_text(label='section_header', text=f'Heading {section}')
        for index in range(30):
            native.add_text(label='text', text=f'Alpha Beta 😀 {section}-{index} value.')
    document = {'format': 'docling', 'document': native.export_to_dict(), 'pages': []}
    expected = _native_text(document)
    path = tmp_path / 'fragmented.json'
    digests = write_reader_artifact(path, payload(document))
    selected = request(path, digests, 'source_windows')
    with pytest.raises(DocumentReaderBudgetError, match='mapping count'):
        reader.read_source_text_range(selected, start=0, end=min(12288, len(expected)))
    original = reader._read_source_windows
    reads = []

    def observe(db, stream, selection, check, source_range=None):
        start, end = source_range
        assert 0 < end-start <= 12288
        result = original(db, stream, selection, check, source_range)
        from tests.test_native_scalar_grounding import scalar
        for address in result['items'][0]['nativeRanges']:
            assert scalar(document, address['nativeRef'])[address['start']:address['end']] == (
                expected[start+address['windowStart']:start+address['windowEnd']])
        reads.append((start, end))
        return result

    monkeypatch.setattr(reader, '_read_source_windows', observe)
    class Text:
        def __len__(self):
            return len(expected)
        def __getitem__(self, key):
            return _read_source_projection_text(selected, key.start, key.stop)
    text = Text()
    for start, end in ((0, min(12288, len(expected))), (13, 9000), (len(expected)-97, len(expected))):
        assert text[start:end] == expected[start:end]
    actual = list(_source_passage_ranges(lambda start, end: text[start:end], len(text)))
    oracle = list(_source_passage_ranges(lambda start, end: expected[start:end], len(expected)))
    assert actual == oracle
    targets = [('Alpha Beta', len(expected)), ('Beta 😀', len(expected)//2)]
    assert _source_occurrence_ordinals(lambda start, end: text[start:end], len(text), targets) == (
        _source_occurrence_ordinals(lambda start, end: expected[start:end], len(expected), targets))
    from semantica.semantic_publication_builder import _EvidenceReference
    from semantica.semantic_artifact_schema import EvidenceSpan, DocumentLocator
    start, end = 13, 9000
    span = EvidenceSpan(id='evidence:dense', representation_id='representation:r',
        quote=expected[start:end], confidence=1,
        locator=DocumentLocator(representation_id='representation:r', origin='native',
            quote=expected[start:end], start_char=start, end_char=end, quality='precise'))
    assert _EvidenceReference.from_span(span, selected).model_dump(mode='json') == span.model_dump(mode='json')
    assert len(reads) > 3


def test_segmented_text_preserves_range_byte_and_cancellation_budgets(tmp_path):
    from semantica.semantic_publication_builder import _read_source_projection_text as read_source_text
    path = tmp_path / 'segmented-bounds.json'
    digests = write_reader_artifact(path, payload(make_document('pdf-text')))
    selected = request(path, digests, 'source_windows')
    with pytest.raises(DocumentReaderBudgetError, match='character budget'):
        read_source_text(selected, start=0, end=12289)
    selected.selection.max_bytes = 1
    with pytest.raises(DocumentReaderBudgetError, match='byte budget'):
        read_source_text(selected, start=0, end=20)
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            read_source_text(selected, start=0, end=20)
    finally:
        query_cancellation.reset(token)


@pytest.mark.parametrize('format', ['pdf-text', 'epub', 'flat-odf'])
def test_projection_preserves_dense_empty_native_sections(tmp_path, format):
    from semantica.semantic_publication_builder import _read_source_projection_text
    parts = ['', 'Alpha 😀', *([''] * 300), 'Beta 漢', '']
    document = ({'format': format, 'pages': [dict(page_number=i+1, text=value)
        for i, value in enumerate(parts)]} if format == 'pdf-text' else
        {'format': format, 'sections': [dict(text=value,
            **(dict(id=f'section-{i}', href=f'{i}.xhtml', media_type='application/xhtml+xml')
               if format == 'epub' else dict(locator={'kind': 'paragraph', 'paragraph': i})))
            for i, value in enumerate(parts)]})
    expected = _native_text(document)
    path = tmp_path / f'dense-empty-{format}.json'
    digests = write_reader_artifact(path, payload(document))
    selected = request(path, digests, 'source_windows')
    assert _read_source_projection_text(selected, 0, len(expected)) == expected


def test_projection_shares_physical_budget_across_native_reads(tmp_path, monkeypatch):
    from semantica import semantic_document_reader as reader
    from semantica.semantic_publication_builder import _read_source_projection_text
    native = DoclingDocument(name='budget')
    for index in range(160):
        native.add_text(label='section_header', text=f'Heading {index}')
        native.add_text(label='text', text='😀漢 value.')
    document = {'format': 'docling', 'document': native.export_to_dict(), 'pages': []}
    expected = _native_text(document)
    path = tmp_path / 'shared-budget.json'
    digests = write_reader_artifact(path, payload(document))
    selected = request(path, digests, 'source_windows')
    original, sizes = reader.read_source_text_range, []

    def observe(request, *, start, end):
        assert request.selection.max_bytes == min(selected.selection.max_bytes, reader.PHYSICAL_READ_LIMIT)-sum(sizes)
        result = original(request, start=start, end=end)
        sizes.append(result['readBytes'])
        return result

    monkeypatch.setattr(reader, 'read_source_text_range', observe)
    assert _read_source_projection_text(selected, 0, len(expected)) == expected
    assert len(sizes) > 1 and sum(sizes) > 0


def test_projection_deadline_includes_header_lookup(tmp_path, monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica import semantic_document_reader as reader
    path = tmp_path / 'deadline.json'
    digests = write_reader_artifact(path, payload(make_document('pdf-text')))
    selected = request(path, digests, 'source_windows')
    original, elapsed = reader.read_source_header, [0]
    monkeypatch.setattr(builder.time, 'monotonic', lambda: elapsed[0])

    def delayed(request):
        result = original(request)
        elapsed[0] = 31
        return result

    monkeypatch.setattr(reader, 'read_source_header', delayed)
    with pytest.raises(DocumentReaderBudgetError, match='execution budget'):
        builder._read_source_projection_text(selected, 0, 20)


@pytest.mark.parametrize('empty_sections', [False, True])
def test_builder_splits_only_unreadable_producer_windows(tmp_path, monkeypatch, empty_sections):
    from types import SimpleNamespace
    from semantica import semantic_document_reader as reader_module
    from semantica.semantic_publication_builder import _source_windows
    from semantica.semantic_source_artifact import _NativeSourceText, _NativeSourceWindows

    document = {'format': 'pdf-text', 'pages': [
        {'page_number': 1, 'text': '# Valid heading\nvalid body'},
        *[{'page_number': index+2, 'text': '' if empty_sections else f'item {index}'}
          for index in range(320)],
        {'page_number': 322, 'text': '# Final heading\nlast body'},
    ]}
    text = _native_text(document)
    path = tmp_path / 'producer-split.json'
    digests = write_reader_artifact(path, payload(document))
    selected = request(path, digests, 'source_windows')
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        originals = list(db.execute('SELECT start,end FROM source_windows ORDER BY ordinal'))
    from semantica.semantic_artifact_errors import SemanticArtifactError
    original_read = reader_module.read_source_text_range
    reads = []
    def observe(*args, **kwargs):
        reads.append((kwargs['start'], kwargs['end']))
        return original_read(*args, **kwargs)
    monkeypatch.setattr(reader_module, 'read_source_text_range', observe)
    parsed = SimpleNamespace(reader=selected, text=_NativeSourceText(selected, len(text)),
        windows=_NativeSourceWindows(_NativeSourceText(selected, len(text)),
            _NativeWindowRanges(selected, len(originals))))
    windows = _source_windows(parsed)
    assert not reads, 'planning must never hydrate source text'
    addresses = list(windows.ranges)
    assert len(addresses) > len(originals)
    for start, end in originals:
        parts = [(lo, hi) for lo, hi in addresses if start <= lo < hi <= end]
        assert parts[0][0] == start and parts[-1][1] == end
        assert all(left[1] == right[0] for left, right in zip(parts, parts[1:]))
        try:
            result = original_read(selected, start=start, end=end)
            _window_native_ranges(_NativeSourceRanges(selected), start, end)
        except DocumentReaderBudgetError:
            pass
        except SemanticArtifactError as exc:
            assert exc.code == "NATIVE_GROUNDING_UNSUPPORTED"
        else:
            assert parts == [(start, end)], 'valid paid operation identity must remain unchanged'
    actual = list(windows)
    assert [(lo, hi) for lo, hi, _ in actual] == addresses
    for lo, hi, body in actual:
        assert hi-lo <= 12288
        assert body == text[lo:hi]
        assert len(_window_native_ranges(_NativeSourceRanges(selected), lo, hi)) <= 128


def test_builder_preserves_readable_dense_windows_and_splits_oversized_addresses(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_publication_builder import _source_windows, _read_source_projection_text
    from semantica.semantic_source_artifact import _NativeSourceText, _NativeSourceWindows
    native = DoclingDocument(name='valid-dense')
    for index in range(110):
        native.add_text(label='text', text=f'Row {index}')
    for oversized, document in [(False, {'format': 'docling', 'document': native.export_to_dict(), 'pages': []}),
            (True, {'format': 'text', 'text': 'word ' * 3000})]:
        text = _native_text(document)
        path = tmp_path / f'address-{oversized}.json'
        digests = write_reader_artifact(path, payload(document))
        if oversized:
            with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
                db.execute('DELETE FROM source_windows')
                db.execute('INSERT INTO source_windows VALUES (0,0,?)', (len(text),))
                import json
                row = json.loads(db.execute("SELECT value FROM metadata WHERE key='header'").fetchone()[0])
                row['sourceWindowCount'] = 1
                db.execute("UPDATE metadata SET value=? WHERE key='header'", (json.dumps(row),))
                db.execute("UPDATE metadata SET value='1' WHERE key='source_windows'")
        with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
            originals = list(db.execute('SELECT start,end FROM source_windows ORDER BY ordinal'))
        selected = request(path, digests, 'source_windows')
        body = _NativeSourceText(selected, len(text))
        parsed = SimpleNamespace(reader=selected, text=body,
            windows=_NativeSourceWindows(body, _NativeWindowRanges(selected, len(originals))))
        windows = _source_windows(parsed)
        if oversized:
            assert list(windows.ranges) == [(0, 12288), (12288, len(text))]
            assert _read_source_projection_text(selected, 11000, 14000) == text[11000:14000]
        else:
            assert list(windows.ranges) == originals
        assert ''.join(item[2] for item in windows) == text


def test_builder_window_planning_rejects_changed_installed_index(tmp_path):
    from semantica.semantic_publication_builder import _source_window_addresses
    path = tmp_path / 'changed-addresses.json'
    digests = write_reader_artifact(path, payload(make_document('pdf-text')))
    selected = request(path, digests, 'source_windows')
    iterator = _source_window_addresses(selected)
    next(iterator)
    path.with_suffix('.reader.sqlite').touch()
    with pytest.raises(ValueError, match='installation changed'):
        list(iterator)
