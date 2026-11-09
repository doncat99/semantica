"""Paid vectors survive process loss in the existing native owners."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import struct

import pytest

from semantica.utils.exceptions import ProcessingError, ValidationError
from semantica.vector_store.sqlite_vec_store import SQLiteVecStore


SPACE = dict(binding='embedding-space-1', model='model-1', recipe='recipe-1')
BINDING = dict(project='project-1', source='source-1', material='material-1',
    representation='representation-1', recipe='recipe-1', model='model-1',
    space='embedding-space-1', parser='parser-1', ranges=[[0, 8], [9, 16]],
    input_digest='sha256:'+'1'*64)
RECEIPT = dict(id='receipt-1', operation='embedding', provider='fixture', model='model-1',
    input_digest='sha256:'+'2'*64, output_digest='sha256:'+'3'*64,
    metadata={'usage': {'input_tokens': 7}}, parameters={})


def test_completed_space_opens_read_only_without_schema_writes(tmp_path, monkeypatch):
    path = str(tmp_path/'vectors.db')
    assert SQLiteVecStore.open_embedding_space(path, SPACE, 3, read_only=True) is None
    assert not (tmp_path/'vectors.db').exists()
    owner = SQLiteVecStore.open_embedding_space(path, SPACE, 3)
    original = owner.adopt_embedding(BINDING, [[1.,0.,0.],[0.,1.,0.]], RECEIPT, accepted_digest='paid')
    owner.close()
    def reject_schema(*args, **kwargs):
        raise AssertionError('Completed read attempted schema creation')
    monkeypatch.setattr(SQLiteVecStore, '_ensure_table_exists', reject_schema)
    owner = SQLiteVecStore.open_embedding_space(path, SPACE, read_only=True)
    try:
        assert owner.read_embedding(BINDING) == original
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            owner._conn.execute('DELETE FROM embeddings_embedding_operations')
    finally:
        owner.close()


def test_missing_scope_index_requires_offline_upgrade_without_copying_vectors(tmp_path):
    path = str(tmp_path/'vectors.db')
    owner = SQLiteVecStore.open_embedding_space(path, SPACE, 3)
    original = owner.adopt_embedding(BINDING, [[1.,0.,0.],[0.,1.,0.]], RECEIPT, accepted_digest='paid')
    rowids = owner._conn.execute('SELECT * FROM embeddings_rowids ORDER BY rowid').fetchall()
    owner._conn.execute('DROP INDEX embeddings_embedding_scope')
    owner._conn.commit()
    owner.close()
    with pytest.raises(ProcessingError, match='explicit offline migration'):
        SQLiteVecStore.open_embedding_space(path, SPACE)
    assert SQLiteVecStore.migrate_embedding_scope_index(path) == dict(indexed=False, changed=False, vectors_copied=0)
    assert SQLiteVecStore.migrate_embedding_scope_index(path, execute=True)['changed']
    assert not SQLiteVecStore.migrate_embedding_scope_index(path, execute=True)['changed']
    owner = SQLiteVecStore.open_embedding_space(path, SPACE)
    try:
        assert owner.read_embedding(BINDING) == original
        assert owner._conn.execute('SELECT * FROM embeddings_rowids ORDER BY rowid').fetchall() == rowids
    finally:
        owner.close()


def test_range_lookup_is_indexed_survives_restart_and_checks_scope(tmp_path):
    path = str(tmp_path/'vectors.db')
    owner = SQLiteVecStore.open_embedding_space(path, SPACE, 3)
    owner.adopt_embedding(BINDING, [[1.,0.,0.],[0.,1.,0.]], RECEIPT, accepted_digest='paid')
    owner.close()
    owner = SQLiteVecStore.open_embedding_space(path, SPACE)
    try:
        scope = {key: value for key, value in BINDING.items() if key != 'input_digest'}
        queries = []
        owner._conn.set_trace_callback(queries.append)
        assert owner.read_embedding_range_binding(scope) == BINDING
        owner._conn.set_trace_callback(None)
        query = next(query for query in queries if query.startswith('SELECT logical_id,binding_json'))
        plan = owner._conn.execute('EXPLAIN QUERY PLAN '+query).fetchall()
        assert any('USING INDEX embeddings_embedding_scope' in row[-1] for row in plan), plan
        assert owner.read_embedding_range_binding({**scope, 'source': 'other'}) is None
        assert owner.read_embedding_range_binding({**scope, 'ranges': [[0, 7], [9, 16]]}) is None
        with pytest.raises(ValidationError, match='exact immutable scope'):
            owner.read_embedding_range_binding({**scope, 'filePath': '/irrelevant'})
    finally:
        owner.close()


def test_offline_identity_migration_keeps_physical_vectors_receipts_and_rowids(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'), SPACE, 3)
    before = owner.adopt_embedding(BINDING, [[1.,0.,0.],[0.,1.,0.]], RECEIPT, accepted_digest='paid')
    physical = owner._conn.execute('SELECT id,embedding,metadata FROM embeddings ORDER BY id').fetchall()
    rowids = owner._conn.execute('SELECT * FROM embeddings_rowids ORDER BY rowid').fetchall()
    receipts = owner._conn.execute('SELECT * FROM embeddings_embedding_operations').fetchall()
    # Emulate the pre-index layout. Ordinary reads must not try the old key.
    owner._conn.execute('DELETE FROM embeddings_embedding_bindings')
    owner._conn.commit()
    assert owner.read_embedding(BINDING) is None
    space = {**SPACE,'binding':'logical-space','recipe':'logical-recipe'}
    binding = {**BINDING,'space':space['binding'],'recipe':space['recipe']}
    mutations = []
    def authorize(action, table, column, database, trigger):
        if action in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE):
            mutations.append(table)
            if table.startswith('embeddings') and table != 'embeddings_embedding_bindings':
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    owner._conn.set_authorizer(authorize)
    result = owner.migrate_embedding_identity(space, [dict(previous=BINDING,current=binding)])
    owner._conn.set_authorizer(None)
    assert result == dict(operations=1,vectors_copied=0,receipts_copied=0,publications='require-rebuild')
    assert owner.read_embedding(binding) == before
    assert owner._conn.execute('SELECT id,embedding,metadata FROM embeddings ORDER BY id').fetchall() == physical
    assert owner._conn.execute('SELECT * FROM embeddings_rowids ORDER BY rowid').fetchall() == rowids
    assert owner._conn.execute('SELECT * FROM embeddings_embedding_operations').fetchall() == receipts
    assert 'embeddings' not in mutations and 'embeddings_embedding_operations' not in mutations
    assert owner._conn.execute('SELECT binding_json FROM embeddings_embedding_bindings').fetchone()[0] == json.dumps(binding,sort_keys=True,separators=(',',':'))
    with pytest.raises(ValidationError,match='differs'):
        owner.read_embedding(BINDING)
    owner.close()
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'),space)
    assert owner.read_embedding(binding) == before
    owner.close()


def test_parser_rebind_requires_explicit_equivalence_and_preserves_paid_result(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'), SPACE, 3)
    before = owner.adopt_embedding(BINDING, [[1.,0.,0.],[0.,1.,0.]], RECEIPT, accepted_digest='paid')
    current = {**BINDING, 'parser': 'semantic-parser'}
    items = [dict(previous=BINDING, current=current)]
    with pytest.raises(ValidationError, match='changed a paid input'):
        owner.migrate_embedding_identity(SPACE, items)
    assert owner.read_embedding(BINDING) == before
    owner.migrate_embedding_identity(SPACE, items, parser_rebindings={(BINDING['parser'], current['parser'])})
    assert owner.read_embedding(current) == before
    assert owner._conn.execute('SELECT count(*) FROM embeddings_embedding_operations').fetchone()[0] == 1
    owner.close()


def test_logical_mapping_to_missing_physical_operation_fails_closed(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'),SPACE,3)
    owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='paid')
    owner._conn.execute('DELETE FROM embeddings_embedding_operations')
    owner._conn.commit()
    with pytest.raises(ProcessingError,match='missing paid operation'):
        owner.read_embedding(BINDING)
    with pytest.raises(ProcessingError,match='missing paid operation'):
        owner.embedding_physical_operation_id(BINDING)
    owner.close()


@pytest.mark.parametrize('failure', ['incomplete','changed-input','duplicate','injected'])
def test_identity_migration_rolls_back_every_binding_and_space(tmp_path, failure):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'),SPACE,3)
    owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='paid')
    before = owner._conn.execute('SELECT * FROM embeddings_embedding_bindings').fetchall()
    metadata = owner._conn.execute('SELECT * FROM embedding_space').fetchall()
    space = {**SPACE,'binding':'new-space','recipe':'new-recipe'}
    current = {**BINDING,'space':space['binding'],'recipe':space['recipe']}
    items = [dict(previous=BINDING,current=current)]
    if failure == 'incomplete': items = []
    if failure == 'changed-input': current['source'] = 'foreign'
    if failure == 'duplicate': items *= 2
    if failure == 'injected':
        owner._conn.execute("CREATE TRIGGER reject_space BEFORE UPDATE ON embedding_space BEGIN SELECT RAISE(ABORT,'injected'); END")
    owner._conn.commit()
    with pytest.raises((ValidationError,ProcessingError,sqlite3.IntegrityError)):
        owner.migrate_embedding_identity(space,items)
    assert owner.embedding_space_identity == SPACE
    assert owner._conn.execute('SELECT * FROM embedding_space').fetchall() == metadata
    assert owner._conn.execute('SELECT * FROM embeddings_embedding_bindings').fetchall() == before
    assert owner.read_embedding(BINDING)['accepted_digest'] == 'paid'
    assert not owner._conn.execute("SELECT name FROM sqlite_temp_master WHERE name='embedding_migration'").fetchall()
    owner.close()


def child(root, fault='none'):
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    root = Path(root)
    cache = ExtractionCache(backend=SqliteCacheBackend(str(root/'accepted.db')))
    key = SQLiteVecStore.embedding_operation_id(BINDING)
    native = SQLiteVecStore.open_embedding_space(str(root/'vectors.db'), SPACE)
    accepted = cache.accepted_digest('embedding', key)
    adopted = native.read_embedding(BINDING) if native is not None else None
    if adopted is None:
        if accepted is None:
            with (root/'calls').open('a') as stream:
                stream.write('model\n')
                stream.flush()
                os.fsync(stream.fileno())
            payload = dict(vectors=[[1., 0., 0.], [0., 1., 0.]], receipt=RECEIPT)
            accepted = cache.accept('embedding', key, payload)
            if fault == 'accepted':
                os._exit(73)
        else:
            payload = cache.get_accepted('embedding', key)
        native = native or SQLiteVecStore.open_embedding_space(str(root/'vectors.db'), SPACE, 3)
        if fault == 'commit':
            native._conn.execute("CREATE TRIGGER reject_op BEFORE INSERT ON embeddings_embedding_operations BEGIN SELECT RAISE(ABORT,'injected commit failure'); END")
            native._conn.commit()
        adopted = native.adopt_embedding(BINDING, payload['vectors'], payload['receipt'], accepted_digest=accepted)
        if fault == 'adopted':
            os._exit(73)
    if accepted is None or accepted != adopted['accepted_digest']:
        raise ProcessingError('Native acceptance identity differs')
    if cache.has_accepted_body('embedding', key, accepted):
        cache.release_accepted('embedding', key, accepted)
    assert adopted['vectors'] == [[1., 0., 0.], [0., 1., 0.]]
    assert adopted['receipt'] == RECEIPT
    native.close()


def run(root, fault='none'):
    return subprocess.run([sys.executable, '-c',
        "import runpy,sys; runpy.run_path(sys.argv[1])['child'](*sys.argv[2:])",
        str(Path(__file__).resolve()), str(root), fault], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize('fault', ['accepted', 'adopted'])
def test_restart_does_not_repay_and_releases_pending_matrix(tmp_path, fault):
    first = run(tmp_path, fault)
    assert first.returncode == 73, first.stderr
    for _ in range(2):
        restarted = run(tmp_path)
        assert restarted.returncode == 0, restarted.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']
    with sqlite3.connect(tmp_path/'accepted.db') as conn:
        assert conn.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 0


def test_atomic_adoption_rolls_back_both_vectors_and_receipt(tmp_path):
    failed = run(tmp_path, 'commit')
    assert failed.returncode != 0 and 'injected commit failure' in failed.stderr
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'), SPACE)
    assert native._conn.execute('SELECT count(*) FROM embeddings').fetchone()[0] == 0
    assert native.read_embedding(BINDING) is None
    native._conn.execute('DROP TRIGGER reject_op')
    native._conn.commit()
    native.close()
    restarted = run(tmp_path)
    assert restarted.returncode == 0, restarted.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']


def test_missing_adopted_vector_fails_closed(tmp_path):
    assert run(tmp_path).returncode == 0
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'), SPACE)
    identity = native.embedding_operation_id(BINDING)
    native._conn.execute('DELETE FROM embeddings WHERE id=?', (identity+':0',))
    native._conn.commit()
    native.close()
    restarted = run(tmp_path)
    assert restarted.returncode != 0 and 'missing' in restarted.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']


def test_space_dimension_discovery_and_identity_fail_closed(tmp_path):
    path = str(tmp_path/'vectors.db')
    assert SQLiteVecStore.open_embedding_space(path, SPACE) is None
    native = SQLiteVecStore.open_embedding_space(path, SPACE, 3)
    assert native._conn.execute('PRAGMA synchronous').fetchone()[0] == 2
    native._conn.execute('PRAGMA synchronous=NORMAL')
    native.close()
    reopened = SQLiteVecStore.open_embedding_space(path, SPACE)
    assert reopened.dimension == 3
    assert reopened._conn.execute('PRAGMA synchronous').fetchone()[0] == 2
    reopened.close()
    with pytest.raises(ProcessingError):
        SQLiteVecStore.open_embedding_space(path, {**SPACE, 'model': 'other'})
    with pytest.raises(ProcessingError):
        SQLiteVecStore.open_embedding_space(path, SPACE, 4)


def test_binding_ranges_and_vector_allocation_are_bounded(tmp_path):
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.db'), SPACE, 3)
    with pytest.raises(ValidationError):
        native.read_embedding({**BINDING, 'ranges': [[0, 1]]*257})
    with pytest.raises(ValidationError):
        native.adopt_embedding(BINDING, [[1., 0.]], RECEIPT, accepted_digest='accepted')
    native.close()


def test_repeated_adoption_without_vectors_does_not_return_float_arrays(tmp_path):
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'no-vectors.sqlite'), SPACE, 3)
    first = native.adopt_embedding(BINDING, [[1., 0., 0.], [0., 1., 0.]], RECEIPT,
        accepted_digest='accepted', include_vectors=False)
    repeated = native.adopt_embedding(BINDING, [[1., 0., 0.], [0., 1., 0.]], RECEIPT,
        accepted_digest='accepted', include_vectors=False)
    assert 'vectors' not in first
    assert 'vectors' not in repeated
    assert repeated['ids'] == first['ids']
    assert repeated['accepted_digest'] == 'accepted'
    native.close()


def test_embedding_receipt_keeps_provider_zero_completion_usage(tmp_path):
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'provider-usage.sqlite'), SPACE, 3)
    receipt = {**RECEIPT, 'metadata': {'usage': {
        'prompt_tokens': 7, 'completion_tokens': 0, 'total_tokens': 7}}}
    adopted = native.adopt_embedding(BINDING, [[1., 0., 0.], [0., 1., 0.]],
        receipt, accepted_digest='accepted')
    assert adopted['receipt'] == receipt
    assert native.read_embedding(BINDING)['receipt'] == receipt
    native.close()


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': 7, 'completion_tokens': 1, 'total_tokens': 8},
    {'prompt_tokens': 7, 'completion_tokens': 0, 'total_tokens': 8},
    {'prompt_tokens': 7, 'completion_tokens': -1, 'total_tokens': 6},
])
def test_embedding_receipt_rejects_generation_or_inconsistent_usage(tmp_path, usage):
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'invalid-usage.sqlite'), SPACE, 3)
    receipt = {**RECEIPT, 'metadata': {'usage': usage}}
    with pytest.raises(ValidationError):
        native.adopt_embedding(BINDING, [[1., 0., 0.], [0., 1., 0.]],
            receipt, accepted_digest='accepted')
    assert native.read_embedding(BINDING) is None
    native.close()


def test_metadata_only_read_still_checks_vector_digest_and_finiteness(tmp_path):
    native = SQLiteVecStore.open_embedding_space(str(tmp_path/'validated.sqlite'), SPACE, 3)
    native.adopt_embedding(BINDING, [[1., 0., 0.], [0., 1., 0.]], RECEIPT,
        accepted_digest='accepted', include_vectors=False)
    identity = SQLiteVecStore.embedding_operation_id(BINDING)
    second = struct.pack('<fff', 0.5, 0.0, 0.0)
    native._conn.execute('UPDATE embeddings SET embedding=? WHERE id=?', (second, identity+':0'))
    native._conn.commit()
    with pytest.raises(ProcessingError, match='digest'):
        native.read_embedding(BINDING, include_vectors=False)

    first = struct.pack('<fff', float('nan'), 0.0, 0.0)
    native._conn.execute('UPDATE embeddings SET embedding=? WHERE id=?', (first, identity+':0'))
    rows = [first, native._conn.execute('SELECT embedding FROM embeddings WHERE id=?', (identity+':1',)).fetchone()[0]]
    native._conn.execute('UPDATE embeddings_embedding_operations SET digest=? WHERE id=?',
        (hashlib.sha256(b''.join(rows)).hexdigest(), identity))
    native._conn.commit()
    with pytest.raises(ProcessingError, match='corrupt'):
        native.read_embedding(BINDING, include_vectors=False)
    native.close()


@pytest.mark.parametrize('field', ['project', 'source', 'material', 'representation', 'parser', 'input_digest'])
def test_operation_identity_isolates_exact_input_tuple(field):
    assert SQLiteVecStore.embedding_operation_id(BINDING) != SQLiteVecStore.embedding_operation_id({**BINDING, field:'other'})
