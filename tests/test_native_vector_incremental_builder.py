"""Current builder generations reuse unchanged native bodies and paid operations."""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re

from semantica.explorer.search_index import _file_identity
from semantica.source import source_content_revision
from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
from tests.test_native_extraction_handoff import build_child


def test_current_builder_two_changes_withdrawals_preserve_unchanged_vector_body(tmp_path, monkeypatch):
    import urllib.request
    import semantica.semantic_publication_builder as builder
    import tests.test_semantic_artifact as fixtures

    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    sentence = 'Ada Lovelace designed the Analytical Engine.'
    source = tmp_path / 'source.txt'
    source.write_text(sentence)
    original_request = fixtures._request
    current_sources = [('source-1', source)]
    requests, statements, embedding_calls, adopted = [], [], [], []
    parsed_refs = {}

    def request(*args, **kwargs):
        kwargs['prepare'] = False
        raw = original_request(*args, **kwargs)
        params = raw['params']
        params['sources'] = [dict(filePath=str(path), materialRevision=source_content_revision(path),
            mimeType='text/plain', name=path.name, sourceId=identity) for identity, path in current_sources]
        # Parsing is a separate producer. Supply its already accepted reference
        # for unchanged inputs, as the host does, rather than reparsing it in
        # test setup and mistaking that fixture write for a builder write.
        params['parsedSources'] = []
        for item in params['sources']:
            key = (item['sourceId'], item['materialRevision'])
            if key not in parsed_refs:
                parsed_refs[key] = fixtures._parsed_ref(params, item)
            params['parsedSources'].append(parsed_refs[key])
        params['inputRevision'] = 'sha256:' + sha256(json.dumps(params['sources'], sort_keys=True).encode()).hexdigest()
        requests.append(params)
        return raw
    monkeypatch.setattr(fixtures, '_request', request)
    original_connection = SQLiteVecStore._get_connection
    @contextmanager
    def traced_connection(owner):
        with original_connection(owner) as connection:
            connection.set_trace_callback(lambda statement: statements.append((owner.db_path, statement)))
            yield connection
    monkeypatch.setattr(SQLiteVecStore, '_get_connection', traced_connection)
    original_embedding = builder._request_embedding
    def embedding(texts, relay):
        identity = builder._native_source_binding.get()['source']
        embedding_calls.append(identity)
        if len(requests) > 1:
            assert identity != 'source-1', 'unchanged source must not call embedding relay'
        return original_embedding(texts, relay)
    monkeypatch.setattr(builder, '_request_embedding', embedding)
    original_adopt = SQLiteVecStore.adopt_embedding
    def adopt(owner, binding, *args, **kwargs):
        adopted.append((binding['source'], owner.embedding_operation_id(binding)))
        return original_adopt(owner, binding, *args, **kwargs)
    monkeypatch.setattr(SQLiteVecStore, 'adopt_embedding', adopt)

    results, baseline, reader_before, unchanged_id, unchanged_operation = [], None, None, None, None
    transitions = []
    for generation in range(3):
        if generation:
            # Both rounds add a source, replace a source's material, and withdraw
            # the previously added source. The original source remains unchanged.
            changed = tmp_path / f'changed-{generation}.txt'
            changed.write_text(sentence + f' New material revision {generation}.')
            added = tmp_path / f'added-{generation}.txt'
            added.write_text(sentence + f' Added source revision {generation}.')
            current_sources[:] = [('source-1', source), ('changed', changed), (f'added-{generation}', added)]
        else:
            changed = tmp_path / 'changed-0.txt'
            changed.write_text(sentence + ' Original changing material.')
            added = tmp_path / 'added-0.txt'
            added.write_text(sentence + ' Original withdrawn source.')
            current_sources[:] = [('source-1', source), ('changed', changed), ('added-0', added)]
        start_sql, start_calls, start_adopt = len(statements), len(embedding_calls), len(adopted)
        # The reused single-product fixture has no identity-keyed history. Each
        # changed input gets an empty product slot, never the prior report body.
        (tmp_path / 'host-product.json').unlink(missing_ok=True)
        result = build_child(tmp_path, stop_before_publication=False)
        results.append(result)
        assert result['publication']['state'] == 'ready' and result['publication']['source_count'] == 3
        descriptor = result['native_indexes']['semantic']
        space = descriptor['space']
        owner = SQLiteVecStore.open_embedding_space(descriptor['path'],
            dict(binding=space['space_id'], model=space['modelId'], recipe=space['recipe']))
        try:
            connection = owner._conn
            if generation == 0:
                unchanged_id = connection.execute('SELECT vector_id FROM embeddings_native_ranges WHERE source=?',
                    ('source-1',)).fetchone()[0]
                unchanged_operation = unchanged_id.rsplit(':', 1)[0]
            vector = connection.execute('SELECT embedding,metadata FROM embeddings WHERE id=?', (unchanged_id,)).fetchone()
            operation = connection.execute('SELECT * FROM embeddings_embedding_operations WHERE id=?',
                (unchanged_operation,)).fetchone()
            assert vector and operation
            state = (vector, operation)
            native_sources = {row[0] for row in connection.execute('SELECT DISTINCT source FROM embeddings_native_ranges')}
            assert native_sources == {identity for identity, _ in current_sources}
            assert connection.execute('SELECT DISTINCT generation FROM embeddings_native_ranges').fetchall() == [
                (result['publication']['generation'],)]
        finally:
            owner.close()
        parsed = Path(next(item['artifactPath'] for item in requests[-1]['parsedSources'] if item['sourceId'] == 'source-1'))
        readers = [parsed, parsed.with_suffix('.reader.sqlite')]
        reader_state = [(str(path), _file_identity(path), sha256(path.read_bytes()).hexdigest()) for path in readers]
        if generation == 0:
            baseline, reader_before = state, reader_state
        else:
            assert state == baseline, 'unchanged vector bytes and accepted operation must remain exact'
            assert reader_state == reader_before, 'unchanged canonical body and reader must not be rewritten'
            writes = [sql for path, sql in statements[start_sql:] if path == descriptor['path']
                and re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE)\b', sql, re.I)]
            body_writes = [sql for sql in writes if re.match(
                r'\s*(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM|REPLACE INTO)\s+embeddings\s*[( ]', sql, re.I)]
            operation_writes = [sql for sql in writes if 'embeddings_embedding_operations' in sql]
            assert len(body_writes) == len(operation_writes) == 2
            assert all(re.match(r'\s*INSERT INTO\b', sql, re.I)
                for sql in body_writes + operation_writes), 'incremental publication must only insert new bodies/operations'
            assert not any(unchanged_id in sql for sql in body_writes), 'unchanged vector body was rewritten'
            assert not any(unchanged_operation in sql for sql in operation_writes), 'unchanged accepted operation was rewritten'
            assert 'source-1' not in embedding_calls[start_calls:]
            assert 'source-1' not in [source for source, _ in adopted[start_adopt:]]
            transitions.append(dict(generation=generation, unchanged_vector_body_writes=0,
                unchanged_operation_writes=0, unchanged_reader_rewrites=0,
                body_writes=len(body_writes), operation_writes=len(operation_writes),
                address_writes=len(writes)-len(body_writes)-len(operation_writes),
                embedding_relay_sources=embedding_calls[start_calls:]))
    assert len({item['publication']['generation'] for item in results}) == 3
    print('current-builder-vector-incremental=' + json.dumps(transitions))
