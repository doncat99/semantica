"""Builder's real paid-embedding handoff across a process boundary."""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
from types import SimpleNamespace

import pytest


def test_embedding_identity_ignores_publication_recipe_and_unrelated_producers(tmp_path, monkeypatch):
    from semantica import semantic_publication_builder as builder
    relay = SimpleNamespace(model_id='model', binding_id='binding')
    source = dict(project='project', source='source', material='material',
                  representation='representation', recipe='publication-a', parser='parser')
    tokens = [
        (builder._native_build, builder._native_build.set((SimpleNamespace(native_store_dir=tmp_path/'facts'), None, None))),
        (builder._native_source_binding, builder._native_source_binding.set(source)),
        (builder._native_embedding_ranges, builder._native_embedding_ranges.set([[0, 6]])),
    ]
    try:
        first = builder._embedding_owner_binding(['source'], relay)
        source['recipe'] = 'publication-b'
        monkeypatch.setattr(builder, 'PROJECT_PROCESSING_DIGEST', 'unrelated-query-change', raising=False)
        monkeypatch.setattr(builder, '_product_json', lambda *args: 'different-generation')
        second = builder._embedding_owner_binding(['source'], relay)
        assert first[2:] == second[2:]
        from semantica.semantic_embedding_recipe import embedding_recipe
        assert first[2]['recipe'] == embedding_recipe(relay)
        assert first[3]['recipe'] == embedding_recipe(relay)
        # Text identity remains per operation; space is shared by one producer/model.
        changed_text = builder._embedding_owner_binding(['SOURCE'], relay)
        assert first[2] != changed_text[2]
        assert first[3:] == changed_text[3:]
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def test_embedding_recipe_tracks_actual_model_binding_not_producer_code(monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_embedding_recipe import embedding_recipe
    relay = SimpleNamespace(model_id='model', binding_id='binding')
    original = embedding_recipe(relay)
    assert embedding_recipe(SimpleNamespace(model_id='other', binding_id='binding')) != original
    assert embedding_recipe(SimpleNamespace(model_id='model', binding_id='other')) != original

    def changed_embedding_request(texts, relay):
        return [[2.0]], None

    monkeypatch.setattr(builder, '_request_embedding', changed_embedding_request)
    # Transport/usage-receipt orchestration is outside the paid vector producer.
    assert embedding_recipe(relay) == original
    monkeypatch.setattr(builder, '_embedding_payload', lambda texts, model: {'input': texts, 'model': model, 'dimensions': 1024}, raising=False)
    assert embedding_recipe(relay) == original


def child(root, fault='none', dimension='3'):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_artifact_schema import ModelReceipt
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    root = Path(root)
    cache = ExtractionCache(backend=SqliteCacheBackend(str(root/'accepted.db')))
    request = SimpleNamespace(native_store_dir=str(root/'facts'))
    builder._native_build.set((request, None, cache))
    # Restart after a publication-only change must retain the same physical space.
    builder._native_source_binding.set(dict(project='project',source='source',material='material',
        representation='representation',recipe='publication-changed' if fault == 'reused' else 'recipe',parser='parser'))
    def relay(*args, **kwargs):
        with (root/'calls').open('a') as stream:
            stream.write('model\n')
            stream.flush()
            os.fsync(stream.fileno())
        scalar = {'overflow': 1e100, 'zero': 0.}.get(fault, 1.)
        response = {'model':'model', 'data':[{'index':0,'embedding':[scalar] * int(dimension)}],
                    'usage': {'input_tokens': 7}}
        if fault == 'model':
            response['model'] = 'wrong-model'
        elif fault == 'data':
            response['data'] = []
        elif fault == 'index':
            response['data'][0]['index'] = 1
        elif fault == 'scalar':
            response['data'][0]['embedding'] = [True]
        elif fault == 'nonfinite':
            response['data'][0]['embedding'] = [float('inf')]
        return response, ModelReceipt(
            id='receipt',operation='embedding',provider='fixture',model='model',
            input_digest='sha256:'+'1'*64,output_digest='sha256:'+'2'*64)
    builder._relay_json = relay
    accept = cache.accept
    def accepted(*args, **kwargs):
        result = accept(*args, **kwargs)
        if fault == 'accepted':
            os._exit(73)
        return result
    cache.accept = accepted
    adopt = SQLiteVecStore.adopt_embedding
    def adopted(self, *args, **kwargs):
        result = adopt(self, *args, **kwargs)
        if fault == 'adopted':
            os._exit(73)
        return result
    SQLiteVecStore.adopt_embedding = adopted
    def embed(_item):
        token = builder._native_source_ranges.set([dict(nativeRef='#/document/text', start=0, end=6, windowStart=0, windowEnd=6)])
        try:
            return builder._embed_windows([(0,6,'source')], SimpleNamespace(model_id='model',binding_id='binding'))
        finally:
            builder._native_source_ranges.reset(token)
    if fault in {'overflow', 'zero', 'dimension', 'model', 'data', 'index', 'scalar', 'nonfinite'}:
        # Production dispatch permits transport retries, but invalid paid
        # responses must fail permanently. A later user retry is a new decision.
        try:
            builder._native_parallel_map([None], embed, 1, max_attempts=2)
        except Exception as exc:
            cause = exc.__cause__
            assert cause.code == 'INVALID_EMBEDDING_RESULT' and cause.retryable is False
            assert cause.diagnostic['upstreamRequestSent'] and not cause.diagnostic['accepted']
            assert cause.diagnostic['modelReceiptId'] == 'receipt'
            assert cause.diagnostic['usage'] == {'input_tokens': 7}
            raise
    vectors, receipt = embed(None)
    assert vectors == [None]
    assert receipt._native_vector_ids and Path(receipt._native_vector_path).is_file()
    if fault == 'reused':
        assert receipt._native_reused


def run(root, fault='none', dimension=3):
    return subprocess.run([sys.executable,'-c',
        "import runpy,sys;runpy.run_path(sys.argv[1])['child'](*sys.argv[2:])",
        str(Path(__file__).resolve()),str(root),fault,str(dimension)],capture_output=True,text=True,timeout=30)


@pytest.mark.parametrize('fault',['accepted','adopted'])
def test_real_builder_embedding_restart_does_not_repay(tmp_path,fault):
    first = run(tmp_path,fault)
    assert first.returncode == 73, first.stderr
    for _ in range(2):
        resumed = run(tmp_path,'reused')
        assert resumed.returncode == 0,resumed.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']


def test_maximum_native_dimension_uses_existing_acceptance_owner(tmp_path):
    first = run(tmp_path,dimension=8192)
    assert first.returncode == 0,first.stderr
    resumed = run(tmp_path,'reused',dimension=8192)
    assert resumed.returncode == 0,resumed.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']


def test_invalid_provider_dimension_is_rejected_without_space(tmp_path):
    first = run(tmp_path,dimension=8193)
    assert first.returncode != 0 and 'dimension exceeds' in first.stderr
    assert not list(tmp_path.glob('embedding-*.sqlite'))
    assert (tmp_path/'calls').read_text().splitlines() == ['model']


@pytest.mark.parametrize('fault', ['overflow', 'zero'])
def test_invalid_native_vectors_never_become_accepted_results(tmp_path, fault):
    first = run(tmp_path, fault)
    assert first.returncode != 0 and 'invalid for its native space' in first.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']
    with sqlite3.connect(tmp_path/'accepted.db') as conn:
        assert conn.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM accepted_receipts').fetchone()[0] == 0
    assert not list(tmp_path.glob('embedding-*.sqlite'))


@pytest.mark.parametrize('fault', ['dimension', 'model', 'data', 'index', 'scalar', 'nonfinite'])
def test_invalid_paid_provider_response_fails_once_with_cost_evidence(tmp_path, fault):
    first = run(tmp_path, fault, dimension=8193 if fault == 'dimension' else 3)
    assert first.returncode != 0
    # child assertions check the permanent error and receipt/usage diagnostics.
    assert 'AssertionError' not in first.stderr, first.stderr
    assert (tmp_path/'calls').read_text().splitlines() == ['model']
    with sqlite3.connect(tmp_path/'accepted.db') as conn:
        assert conn.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM accepted_receipts').fetchone()[0] == 0
    assert not list(tmp_path.glob('embedding-*.sqlite'))
