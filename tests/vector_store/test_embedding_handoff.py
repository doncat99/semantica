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
