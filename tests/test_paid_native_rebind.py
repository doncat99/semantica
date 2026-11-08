"""Offline migration preserves physical paid identities and accepted receipts."""
import importlib.util
import hashlib
from pathlib import Path
import runpy
import sqlite3
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/rebind_paid_native_results.py'
spec = importlib.util.spec_from_file_location('paid_rebind', SCRIPT)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)
OLD = 'sha256:' + '1' * 64
NEW = 'sha256:' + '2' * 64


def fixture(tmp_path, monkeypatch):
    import semantica.semantic_publication_builder as builder
    import semantica.semantic_source_artifact as sources
    helper = runpy.run_path(str(Path(__file__).with_name('test_native_extraction_handoff.py')))
    child = helper['run_child'](tmp_path, recipe=OLD)
    assert child.returncode == 0, child.stderr
    source = SimpleNamespace(source_id='source-1', file_path='source.txt', name='source.txt', mime_type='text/plain', material_revision='material-1')
    request = SimpleNamespace(project_id='project-1', sources=[source],
        parsed_sources=[SimpleNamespace(source_id='source-1', representation_revision='representation-1')], recipe=SimpleNamespace(force_ocr_source_ids=[]),
        document_processing=SimpleNamespace(model_dump=lambda **_: {}),
        relays={'embedding': SimpleNamespace(binding_id='embedding', model_id='embedding')},
        native_store_dir=str(tmp_path/'facts'), native_cache_dir=str(tmp_path),
        model_dump=lambda **_: {'project': 'project-1'})
    monkeypatch.setattr(builder, '_extraction_recipe', lambda _: NEW)
    monkeypatch.setattr(maintenance, 'parser_identity', lambda *a: 'parser')
    import semantica.semantic_document_reader as reader
    monkeypatch.setattr(reader, 'read_source_header', lambda *a: {'header': {'processingRevision': 'parser'}})
    monkeypatch.setattr(sources, '_load_parsed_source', lambda *a: SimpleNamespace(reader='reader'))
    monkeypatch.setattr(builder, '_read_source_projection_text', lambda reader, start, end: helper['TEXT'][start:end])
    return request


def ledger(tmp_path):
    with sqlite3.connect(tmp_path/'accepted.sqlite') as db:
        return list(db.execute('SELECT * FROM accepted_receipts ORDER BY namespace,key'))


@pytest.mark.parametrize('preindex', [False, True])
def test_migration_is_in_place_reentrant_and_keeps_paid_ledger(tmp_path, monkeypatch, preindex):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.extraction_records import F
    request = fixture(tmp_path, monkeypatch)
    before = ledger(tmp_path)
    owner = OxigraphStore(request.native_store_dir)
    if preindex:
        graph = owner._oxigraph.NamedNode('urn:semantica:project:' + hashlib.sha256(b'project-1').hexdigest() + ':extraction-index')
        owner.store.clear_graph(graph)
    facts = {str(q) for q in owner.store if q.predicate.value not in {F+'bindingParser', F+'bindingRecipe', F+'extractionStage', F+'operationDigest', F+'physicalOperation'}}
    owner.close()
    dry = maintenance.migrate(request, OLD)
    assert dry['extractions'] == 2 and ledger(tmp_path) == before
    first = maintenance.migrate(request, OLD, apply=True)
    second = maintenance.migrate(request, OLD, apply=True)
    assert first['extractions'] == second['extractions'] == 2
    assert first['factsCopied'] == first['vectorsCopied'] == first['receiptsCopied'] == 0
    owner = OxigraphStore(request.native_store_dir)
    after = {str(q) for q in owner.store if q.predicate.value not in {F+'bindingParser', F+'bindingRecipe', F+'extractionStage', F+'operationDigest', F+'physicalOperation'}}
    assert after == facts
    owner.close()
    assert ledger(tmp_path) == before
    assert len((tmp_path/'calls.jsonl').read_text().splitlines()) == 2


def test_interrupted_extraction_migration_resumes_without_copy(tmp_path, monkeypatch):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    request = fixture(tmp_path, monkeypatch)
    original = OxigraphStore.rebind_extraction
    calls = []
    def interrupted(owner, *args):
        result = original(owner, *args)
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('interruption after durable operation')
        return result
    monkeypatch.setattr(OxigraphStore, 'rebind_extraction', interrupted)
    with pytest.raises(RuntimeError, match='interruption'):
        maintenance.migrate(request, OLD, apply=True)
    monkeypatch.setattr(OxigraphStore, 'rebind_extraction', original)
    assert maintenance.migrate(request, OLD, apply=True)['extractions'] == 2
    assert len((tmp_path/'calls.jsonl').read_text().splitlines()) == 2


def test_missing_acceptance_fails_closed(tmp_path, monkeypatch):
    request = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path/'accepted.sqlite') as db:
        db.execute('DELETE FROM accepted_receipts')
    with pytest.raises(ValueError, match='matching paid acceptance'):
        maintenance.migrate(request, OLD, apply=True)


@pytest.mark.parametrize('preindex', [False, True])
@pytest.mark.parametrize('rebind_parser', [False, True])
def test_vector_path_move_preserves_blob_receipt_and_ledger(tmp_path, monkeypatch, preindex, rebind_parser):
    from semantica.semantic_artifact_schema import stable_digest
    from semantica.semantic_embedding_recipe import embedding_recipe
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    request = fixture(tmp_path, monkeypatch)
    relay = request.relays['embedding']
    def space(recipe):
        return dict(binding=stable_digest(dict(binding=relay.binding_id, model=relay.model_id, recipe=recipe)), model=relay.model_id, recipe=recipe)
    old, current = space(OLD), space(embedding_recipe(relay))
    def path(identity):
        return tmp_path / ('embedding-' + identity['binding'].removeprefix('sha256:') + '.sqlite')
    binding = dict(project='project-1', source='source-1', material='material-1', representation='representation-1',
        recipe=OLD, model=relay.model_id, space=old['binding'], parser='parser', ranges=[[0, 1]], input_digest=stable_digest(['a']))
    receipt = dict(id='receipt-embedding', operation='embedding', provider='fixture', model=relay.model_id,
        input_digest=stable_digest('input'), output_digest=stable_digest('output'))
    cache = ExtractionCache(backend=SqliteCacheBackend(str(tmp_path/'accepted.sqlite')))
    physical = SQLiteVecStore.embedding_operation_id(binding)
    digest = cache.accept('embedding', physical, dict(vectors=[[1., 0., 0.]], receipt=receipt))
    owner = SQLiteVecStore.open_embedding_space(str(path(old)), old, 3)
    adopted = owner.adopt_embedding(binding, [[1., 0., 0.]], receipt, accepted_digest=digest)
    before_vectors = list(owner._conn.execute('SELECT id,embedding,metadata FROM embeddings ORDER BY id'))
    before_ops = list(owner._conn.execute('SELECT * FROM embeddings_embedding_operations'))
    if preindex:
        import semantica.semantic_publication_builder as builder
        import semantica.source as sources
        source = request.sources[0]
        source.material_revision, source.file_path, source.name, source.mime_type = 'material-1', 'original.pdf', 'original.pdf', 'application/pdf'
        request.parsed_sources[0].representation_revision = 'representation-1'
        monkeypatch.setattr(builder, '_source_windows', lambda parsed: iter([(0, 1, 'a')]))
        monkeypatch.setattr(sources, 'source_processing_revision', lambda *a, **k: 'parser')
        owner._conn.execute('DROP TABLE embeddings_embedding_bindings')
        owner._conn.commit()
    owner.close()
    cache.release_accepted('embedding', physical, digest)
    cache._backend.close()
    before_ledger = ledger(tmp_path)
    if rebind_parser:
        monkeypatch.setattr(maintenance, 'parser_identity', lambda *a: 'semantic-parser')
    assert maintenance.migrate(request, OLD)['embeddings'] == 1
    assert path(old).exists() and not path(current).exists()
    assert maintenance.migrate(request, OLD, apply=True)['embeddings'] == 1
    assert not path(old).exists() and path(current).exists()
    assert maintenance.migrate(request, OLD, apply=True)['embeddings'] == 1
    owner = SQLiteVecStore.open_embedding_space(str(path(current)), current)
    updated = {**binding, 'recipe': current['recipe'], 'space': current['binding'],
        'parser': 'semantic-parser' if rebind_parser else binding['parser']}
    assert owner.read_embedding(updated) == adopted
    assert owner.embedding_physical_operation_id(updated) == physical
    assert list(owner._conn.execute('SELECT id,embedding,metadata FROM embeddings ORDER BY id')) == before_vectors
    assert list(owner._conn.execute('SELECT * FROM embeddings_embedding_operations')) == before_ops
    owner.close()
    assert ledger(tmp_path) == before_ledger
    # The production caller must use the stable physical acceptance key after reindexing.
    from semantica import semantic_publication_builder as builder
    cache = ExtractionCache(backend=SqliteCacheBackend(str(tmp_path/'accepted.sqlite')))
    monkeypatch.setattr(builder, '_relay_json', lambda *a, **k: pytest.fail('migrated vector was requested again'))
    tokens = [
        (builder._native_build, builder._native_build.set((request, None, cache))),
        (builder._native_source_binding, builder._native_source_binding.set({key: updated[key] for key in ('project', 'source', 'material', 'representation', 'parser')})),
        (builder._native_embedding_ranges, builder._native_embedding_ranges.set([[0, 1]])),
        (builder._native_source_ranges, builder._native_source_ranges.set([dict(nativeRef='#/document/text', start=0, end=1, windowStart=0, windowEnd=1)])),
        (builder._native_embedding_vectors_required, builder._native_embedding_vectors_required.set(False)),
    ]
    try:
        vectors, reused = builder._embed_texts(['a'], relay)
        assert vectors == [None] and reused._native_reused
        assert reused._native_vector_ids == adopted['ids']
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
        cache._backend.close()


@pytest.mark.parametrize('preindex', [False, True])
def test_classification_batch_and_reduction_migrate_without_copies(tmp_path, monkeypatch, preindex):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.classification_records import ClassificationRecords
    request = fixture(tmp_path, monkeypatch)
    request.relays['model'] = SimpleNamespace(binding_id='model', model_id='model')
    monkeypatch.setattr(builder, '_classification_recipe', lambda _: 'current-classification')
    helpers = runpy.run_path(str(Path(__file__).parent/'triplet_store/test_classification_records.py'))
    profile, binding, receipt, value = helpers['inputs']()
    binding.update(project='project-1', source='source-1', recipe='old-classification')
    value = value.model_copy(update={'source_id': 'source-1'})
    owner = OxigraphStore(request.native_store_dir)
    cache = ExtractionCache(backend=SqliteCacheBackend(str(tmp_path/'accepted.sqlite')))
    physical = owner.classification_operation_id(binding)
    digest = cache.accept('classification', binding['context_digest'], dict(value=value.model_dump(mode='json'), receipts=[receipt]), native_operation=physical)
    owner.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'], accepted_digest=digest, receipts=[receipt])
    reduced = {**binding, 'target': 'reduction', 'context_digest': 'reduction'}
    reduction = ClassificationRecords(owner, reduced)
    reduction.adopt_reduction([physical], profile=profile)
    expected = reduction.read_reduced_dimension('sector')
    if preindex:
        owner.store.clear_graph(reduction.index_graph)
    owner.close()
    cache._backend.close()
    before = ledger(tmp_path)
    result = maintenance.migrate(request, OLD, apply=True, old_classification_recipe='old-classification')
    assert result['classifications'] == 2
    assert maintenance.migrate(request, OLD, apply=True, old_classification_recipe='old-classification')['classifications'] == 2
    owner = OxigraphStore(request.native_store_dir)
    current = {**binding, 'recipe': 'current-classification'}
    assert owner.classification_operation_id(current) == physical
    assert owner.read_classification(current, profile=profile, allowed_evidence_ids=['evidence-1']) == value
    reduction = ClassificationRecords(owner, {**reduced, 'recipe': 'current-classification'})
    assert reduction.read_reduced_dimension('sector') == expected
    owner.close()
    assert ledger(tmp_path) == before


def test_parser_metadata_rebind_preserves_physical_results(tmp_path, monkeypatch):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    request = fixture(tmp_path, monkeypatch)
    before = ledger(tmp_path)
    owner = OxigraphStore(request.native_store_dir)
    original = list(maintenance.source_bindings(owner, request.project_id, 'source-1', OLD))
    owner.close()
    monkeypatch.setattr(maintenance, 'parser_identity', lambda *a: 'semantic-parser')
    maintenance.migrate(request, OLD, apply=True)
    owner = OxigraphStore(request.native_store_dir)
    for previous, stage, physical in original:
        current = {**previous, 'recipe': NEW, 'parser': 'semantic-parser'}
        assert owner.extraction_operation_id(current, stage) == physical
        from semantica.triplet_store.extraction_records import ExtractionRecords
        assert ExtractionRecords(owner, current, stage).receipt() is not None
    owner.close()
    assert ledger(tmp_path) == before


def test_rebind_moves_completed_window_reference_without_recomputing(tmp_path, monkeypatch):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.extraction_records import ExtractionRecords
    request = fixture(tmp_path, monkeypatch)
    owner = OxigraphStore(request.native_store_dir)
    binding = next(b for b, stage, _ in maintenance.source_bindings(owner, request.project_id, 'source-1', OLD) if stage == 'entities')
    window = {k: v for k, v in binding.items() if k != 'grounding'}
    ExtractionRecords.window_completion(owner, window, False, [binding['grounding']])
    owner.close()
    maintenance.migrate(request, OLD, apply=True)
    owner = OxigraphStore(request.native_store_dir)
    assert ExtractionRecords.window_completion(owner, window, False) is None
    current = {**window, 'recipe': NEW, 'parser': 'parser'}
    assert ExtractionRecords.window_completion(owner, current, False) == [{**binding, 'recipe': NEW, 'parser': 'parser'}]
    owner.close()
    assert len((tmp_path/'calls.jsonl').read_text().splitlines()) == 2


def test_migration_rejects_different_material_before_rebinding(tmp_path, monkeypatch):
    request = fixture(tmp_path, monkeypatch)
    request.sources[0].material_revision = 'different-material'
    with pytest.raises(ValueError, match='admitted material'):
        maintenance.migrate(request, OLD, apply=True)
