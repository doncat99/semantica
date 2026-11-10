"""Keyword positions belong to native scalar addresses, never a second body."""
import json
import sqlite3
import re
import time
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from semantica.explorer.search_index import GraphSearchIndex, _file_identity
from semantica.semantic_document_reader import write_reader_artifact, read_document_reader
from semantica.semantic_query_schema import DocumentReaderSelection
from tests.test_native_document_reader import payload, request


def publish(tmp_path, text):
    source = tmp_path / 'source.json'
    digests = write_reader_artifact(source, payload({'format': 'text', 'text': text}))
    reader = request(source, digests)
    target = tmp_path / 'keyword.sqlite'
    receipt = GraphSearchIndex.publish_native_positions(target, project='p', generation='g', readers=[reader])
    return target, receipt, reader


def test_repeated_positions_do_not_repeat_term_queries_or_maintain_inverted_index(tmp_path, monkeypatch):
    connect, statements = sqlite3.connect, []
    def traced(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(sqlite3, 'connect', traced)
    path, _, _ = publish(tmp_path, 'Acme report ' * 2000)
    lookups = [sql for sql in statements if sql.startswith('SELECT id FROM terms WHERE term=')]
    assert len(lookups) == 3  # Two words and the literal space, regardless of support count.
    insertions = [n for n, sql in enumerate(statements) if sql.startswith('INSERT INTO positions VALUES')]
    index = next(n for n, sql in enumerate(statements) if sql.startswith('CREATE INDEX positions_term'))
    assert len(insertions) == 8000 and index > max(insertions)
    with connect(path) as db:
        assert db.execute('SELECT count(*) FROM positions').fetchone()[0] == 8000


def test_native_keyword_has_every_position_across_reader_segments_and_restart(tmp_path):
    text = 'before ' + 'x ' * 8185 + 'ESG ESG/esg ESG\nESG end'
    path, receipt, reader = publish(tmp_path, text)
    owner = GraphSearchIndex.open_native_positions(path, project='p', generation='g',
        receipt=receipt, installation_identity=_file_identity(path))
    page = owner.search_native_positions('ESG', source_ids=[reader.source_id], limit=2)
    assert page['total'] == text.lower().count('esg') == 5
    assert len(page['items']) == 2
    owner.close_native_positions()
    owner = GraphSearchIndex.open_native_positions(path, project='p', generation='g',
        receipt=receipt, installation_identity=_file_identity(path))
    other = owner.search_native_positions('ESG', source_ids=[reader.source_id], limit=128, after=page['nextCursor'])
    hits = page['items'] + other['items']
    assert [text[item['start']:item['end']] for item in hits] == ['ESG', 'ESG', 'esg', 'ESG', 'ESG']
    assert all(item['nativeRef'] == '#/document/text' for item in hits)
    assert owner.search_native_positions('ESG', source_ids=['other'])['total'] == 0
    owner.close_native_positions()
    with sqlite3.connect(path) as db:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert set(tables) == {'metadata', 'sources', 'terms', 'grams', 'positions'}
        assert all('text' not in row[1] for name in tables for row in db.execute('PRAGMA table_info(' + name + ')'))


def test_native_keyword_phrase_unicode_and_identity_admission(tmp_path):
    path, receipt, reader = publish(tmp_path, 'a İ ESG report ESG reportz')
    owner = GraphSearchIndex.open_native_positions(path, project='p', generation='g',
        receipt=receipt, installation_identity=_file_identity(path))
    page = owner.search_native_positions('esg report', source_ids=[reader.source_id])
    assert page['total'] == 2  # literal substring contract, not whole-word semantics
    unicode = owner.search_native_positions('i', source_ids=[reader.source_id])
    assert unicode['items'][0]['start'] == 2 and unicode['items'][0]['end'] == 3
    owner.close_native_positions()
    with pytest.raises(ValueError, match='identity'):
        GraphSearchIndex.open_native_positions(path, project='other', generation='g',
            receipt=receipt, installation_identity=_file_identity(path))


def test_native_keyword_large_page_oracle_bidirectional_navigation_and_restart(tmp_path):
    texts = ['😀漢 ' + 'padding ' * 2300 + ('ESG/esg ESG\n' * 160) for _ in range(3)]
    artifact = tmp_path / 'pages.json'
    digests = write_reader_artifact(artifact, payload({'format': 'pdf-text', 'pages': [
        {'page_number': n + 1, 'text': text} for n, text in enumerate(texts)]}))
    reader = request(artifact, digests)
    foreign = tmp_path / 'foreign.json'
    foreign_reader = request(foreign, write_reader_artifact(foreign,
        payload({'format': 'text', 'text': 'ESG ' * 2000}))).model_copy(update={'source_id': 'foreign'})
    index = tmp_path / 'large.sqlite'
    receipt = GraphSearchIndex.publish_native_positions(index, project='p', generation='g',
        readers=[reader, foreign_reader])
    expected = [(f'#/document/pages/{n}/text', match.start(), match.end(), n + 1)
        for n, text in enumerate(texts) for match in re.finditer('esg', text.lower())]
    assert len(expected) == 1440
    timings, read_bytes, pages = [], 0, []
    def search(owner, **kwargs):
        started = time.perf_counter()
        result = owner.search_native_positions('ESG', source_ids=[reader.source_id], limit=37, **kwargs)
        timings.append((time.perf_counter() - started) * 1000)
        assert result['total'] == len(expected)
        addresses = [(item['nativeRef'], item['start'], item['end'], item['locator']['page'])
            for item in result['items']]
        assert addresses == expected[result['startOffset']:result['startOffset'] + len(addresses)]
        return result
    for restart in range(2):
        owner = GraphSearchIndex.open_native_positions(index, project='p', generation='g',
            receipt=receipt, installation_identity=_file_identity(index))
        page = search(owner)
        if restart == 0:
            while True:
                pages.append(page)
                selection = DocumentReaderSelection.model_validate({'field': 'ranges', 'maxBytes': 262144, 'ranges': [
                    {'nativeRef': item['nativeRef'], 'start': item['start'], 'end': item['end']}
                    for item in page['items']]})
                hydrated = read_document_reader(reader.model_copy(update={'selection': selection}))
                read_bytes += hydrated['readBytes']
                assert [item['text'] for item in hydrated['items']] == [
                    texts[int(item['nativeRef'].split('/')[3])][item['start']:item['end']]
                    for item in page['items']]
                assert all(item['text'].lower() == 'esg' for item in hydrated['items'])
                if page['nextCursor'] is None:
                    break
                page = search(owner, after=page['nextCursor'])
            assert sum(len(page['items']) for page in pages) == 1440
            while page['previousCursor'] is not None:
                page = search(owner, after=page['previousCursor'], navigation='previous')
            assert page['startOffset'] == 0
        else:
            # Reopen and resume in a deep page without replaying preceding pages.
            deep = search(owner, after=pages[29]['nextCursor'])
            assert deep['items'] == pages[30]['items'] and deep['startOffset'] == 1110
            following = search(owner, after=page['items'][0]['position'], navigation='next_page')
            assert following['items'][0]['locator']['page'] == 2
            preceding = search(owner, after=following['items'][0]['position'], navigation='previous_page')
            assert preceding['items'][-1]['locator']['page'] == 1
        owner.close_native_positions()
    assert max(timings) < 3000
    print('native-keyword-oracle=' + json.dumps(dict(hits=1440, pages=len(pages),
        queries=len(timings), max_query_ms=max(timings), range_read_bytes=read_bytes,
        scope='one authorized source, three native pages, restart; no cold-IO claim')))
    child_code = r'''
import json, os, resource, sys, time
from pathlib import Path
boot = time.perf_counter()
from semantica.explorer.search_index import GraphSearchIndex, _file_identity
from semantica.semantic_document_reader import read_document_reader
from semantica.semantic_query_schema import DocumentReaderRequest, DocumentReaderSelection
data = json.loads(sys.argv[1])
reader = DocumentReaderRequest.model_validate(data['reader'])
imports_ms = (time.perf_counter() - boot) * 1000
started = time.perf_counter()
owner = GraphSearchIndex.open_native_positions(Path(data['index']), project='p', generation='g',
    receipt=data['receipt'], installation_identity=_file_identity(Path(data['index'])))
open_ms = (time.perf_counter() - started) * 1000
# Instrument only this reader's native-content fd; SQLite C reads are outside this probe.
original_open = Path.open
reads = []
class TracedFile:
    def __init__(self, stream): self.stream = stream
    def __enter__(self): return self
    def __exit__(self, *args): return self.stream.__exit__(*args)
    def __getattr__(self, name): return getattr(self.stream, name)
    def read(self, size=-1):
        offset = self.stream.tell()
        raw = self.stream.read(size)
        reads.append([offset, size, len(raw)])
        return raw
def traced_open(path, *args, **kwargs):
    stream = original_open(path, *args, **kwargs)
    return TracedFile(stream) if str(path) == reader.artifact.path else stream
Path.open = traced_open
results = []
for position in (None, data['deep']):
    before = resource.getrusage(resource.RUSAGE_SELF)
    begin = len(reads)
    started = time.perf_counter()
    page = owner.search_native_positions('ESG', source_ids=[reader.source_id], limit=37, after=position)
    retrieval_ms = (time.perf_counter() - started) * 1000
    selection = DocumentReaderSelection.model_validate(dict(field='ranges', maxBytes=262144,
        ranges=[dict(nativeRef=item['nativeRef'], start=item['start'], end=item['end']) for item in page['items']]))
    hydrated = read_document_reader(reader.model_copy(update={'selection': selection}))
    total_ms = (time.perf_counter() - started) * 1000
    after = resource.getrusage(resource.RUSAGE_SELF)
    assert all(item['text'].lower() == 'esg' for item in hydrated['items'])
    assert total_ms < 3000 and page['total'] == 1440
    physical = reads[begin:]
    assert sum(row[2] for row in physical) == hydrated['readBytes']
    assert all(0 < row[1] <= 65536 and row[1] == row[2] for row in physical)
    results.append(dict(offset=page['startOffset'], items=page['items'], retrieval_ms=retrieval_ms,
        request_ms=total_ms, native_content_read_bytes=hydrated['readBytes'], native_content_read_calls=len(physical),
        read_ranges=[dict(offset=offset, requested=size, returned=actual, calls=physical.count([offset,size,actual]))
            for offset,size,actual in sorted(set(map(tuple, physical)))],
        maxrss_raw=after.ru_maxrss, rss_growth_raw=after.ru_maxrss-before.ru_maxrss,
        input_blocks=after.ru_inblock-before.ru_inblock))
owner.close_native_positions()
print(json.dumps(dict(pid=os.getpid(), owner_file=sys.modules['semantica.explorer.search_index'].__file__,
    imports_ms=imports_ms, open_ms=open_ms, results=results,
    rss_unit='bytes' if sys.platform == 'darwin' else 'KiB')))
'''
    restarted = []
    for _ in range(2):
        started = time.perf_counter()
        child = subprocess.run([sys.executable, '-I', '-B', '-c', child_code,
            json.dumps(dict(index=str(index), receipt=receipt, deep=pages[29]['nextCursor'],
                reader=reader.model_dump(by_alias=True)))], capture_output=True, text=True, timeout=30, check=True)
        result = json.loads(child.stdout)
        result['process_wall_ms'] = (time.perf_counter() - started) * 1000
        assert result['results'][0]['items'] == pages[0]['items']
        assert result['results'][1]['items'] == pages[30]['items']
        for query in result['results']:
            query['item_count'] = len(query.pop('items'))
        restarted.append(result)
    assert restarted[0]['pid'] != restarted[1]['pid']
    print('native-keyword-process-restarts=' + json.dumps(restarted))


def test_native_keyword_two_publication_changes_withdrawals_and_stale_admission(tmp_path):
    def source(name, text):
        path = tmp_path / (name + '.json')
        return request(path, write_reader_artifact(path, payload({'format': 'text', 'text': text}))).model_copy(
            update={'source_id': name.split('-')[0]})
    unchanged = source('a', 'ESG unchanged ESG')
    original_paths = [unchanged.artifact.path, unchanged.reader_index.path]
    before = {path: (_file_identity(Path(path)), sha256(Path(path).read_bytes()).hexdigest())
        for path in original_paths}
    previous, previous_text = None, None
    for generation, changed, added in [('g0', 'old', 'd'), ('g1', 'new', 'c'), ('g2', 'latest', 'e')]:
        readers = [unchanged, source('b-' + generation, 'ESG ' + changed), source(added, 'ESG added')]
        index = tmp_path / (generation + '.sqlite')
        receipt = GraphSearchIndex.publish_native_positions(index, project='p', generation=generation, readers=readers)
        if previous:
            old_path, old_receipt, old_cursor, withdrawn = previous
            with pytest.raises(ValueError, match='publication identity differs'):
                GraphSearchIndex.open_native_positions(old_path, project='p', generation=generation,
                    receipt=old_receipt, installation_identity=_file_identity(old_path))
        owner = GraphSearchIndex.open_native_positions(index, project='p', generation=generation,
            receipt=receipt, installation_identity=_file_identity(index))
        result = owner.search_native_positions('ESG', limit=2)
        assert result['total'] == 4
        assert [item['sourceId'] for item in result['items']] == ['a', 'a']
        assert owner.search_native_positions(changed)['total'] == 1
        if previous:
            assert owner.search_native_positions(previous_text)['total'] == 0
            assert owner.search_native_positions('ESG', source_ids=[withdrawn])['total'] == 0
            with pytest.raises(ValueError, match='not an installed position'):
                owner.search_native_positions('ESG', after=old_cursor)
        withdrawn_cursor = owner.search_native_positions('ESG', source_ids=[added])['items'][0]['position']
        previous = index, receipt, withdrawn_cursor, added
        previous_text = changed
        owner.close_native_positions()
        assert {path: (_file_identity(Path(path)), sha256(Path(path).read_bytes()).hexdigest())
            for path in original_paths} == before
    print('native-keyword-publications=' + json.dumps(dict(generations=3, changes=2,
        withdrawals=2, unchanged_reader_files=2, unchanged_reader_rewrites=0,
        scope='reader identity+bytes and lexical results; excludes vector publication')))


@pytest.mark.parametrize('failure', ['cancel', 'timeout'])
def test_native_keyword_interrupted_candidate_fill_cleans_scratch_and_connection(tmp_path, monkeypatch, failure):
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    from semantica.utils.exceptions import ProcessingError
    import semantica.explorer.search_index as search_index

    path, receipt, reader = publish(tmp_path, 'ESG evidence ESG')
    owner = GraphSearchIndex.open_native_positions(path, project='p', generation='g',
        receipt=receipt, installation_identity=_file_identity(path))
    event = Event()
    token = query_cancellation.set(event)
    try:
        with monkeypatch.context() as patch:
            if failure == 'cancel':
                event.set()
                expected, message = ProcessingError, 'query canceled'
            else:
                clock = iter([0., 4.])
                patch.setattr(search_index.time, 'monotonic', lambda: next(clock, 4.))
                expected, message = TimeoutError, '3 second budget'
            with pytest.raises(expected, match=message):
                owner.search_native_positions('ESG')
            # Keep cancellation/deadline active: a leaked progress handler would
            # interrupt this unrelated statement on the shared connection.
            assert owner._native_db.execute('''WITH RECURSIVE n(x) AS
                (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000)
                SELECT sum(x) FROM n''').fetchone() == (50005000,)
            assert owner._native_db.execute("SELECT name FROM sqlite_temp_master WHERE name='native_candidates'").fetchall() == []
        event.clear()
        assert owner.search_native_positions('ESG')['total'] == 2
        assert owner._native_db.execute("SELECT name FROM sqlite_temp_master WHERE name='native_candidates'").fetchall() == []
        with pytest.raises(ValueError, match='not an installed position'):
            owner.search_native_positions('ESG', after=['missing', '#/document/text', 0, 0])
        assert owner._native_db.execute("SELECT name FROM sqlite_temp_master WHERE name='native_candidates'").fetchall() == []
    finally:
        query_cancellation.reset(token)
        owner.close_native_positions()


def test_native_keyword_cleanup_failure_preserves_original_cancellation(tmp_path, monkeypatch, caplog):
    import semantica.semantic_worker_context as context
    from semantica.utils.exceptions import ProcessingError

    path, receipt, reader = publish(tmp_path, 'ESG evidence')
    owner = GraphSearchIndex.open_native_positions(path, project='p', generation='g',
        receipt=receipt, installation_identity=_file_identity(path))
    connection = owner._native_db
    canceled = ProcessingError('injected cancellation during candidate fill')
    def cancel():
        raise canceled
    class CleanupFailure:
        drops = 0
        def __getattr__(self, name):
            return getattr(connection, name)
        def execute(self, sql, *args):
            if sql == 'DROP TABLE IF EXISTS temp.native_candidates':
                self.drops += 1
                if self.drops == 2:
                    raise sqlite3.OperationalError('injected cleanup failure')
            return connection.execute(sql, *args)
    owner._native_db = CleanupFailure()
    monkeypatch.setattr(context, 'check_query_cancellation', cancel)
    try:
        with pytest.raises(ProcessingError) as raised:
            owner.search_native_positions('ESG')
        assert raised.value is canceled
        assert 'Native keyword scratch cleanup failed' in caplog.text
        assert 'injected cleanup failure' in caplog.text
        assert connection.execute('''WITH RECURSIVE n(x) AS
            (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000)
            SELECT sum(x) FROM n''').fetchone() == (50005000,)
    finally:
        owner._native_db = connection
        owner.close_native_positions()
