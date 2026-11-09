"""Retired source projections must not survive native canonical reduction."""
import gc
import weakref
import pytest

from semantica import semantic_publication_builder as builder
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from tests.test_native_extraction_handoff import build_child


def publication_semantics(result):
    store = OxigraphStore(result['semantic_store']['path'])
    try:
        generation = result['publication']['generation']
        nodes = store.read_publication_scene('project-1', generation, dict(kind='nodes'))
        links = store.read_publication_scene('project-1', generation,
            dict(kind='links', visibleIds=[item['id'] for item in nodes['nodes']]))
        # The tiny fixture's complete accepted native graph is the integrity
        # oracle; no semantic bodies are retained by lifecycle probes themselves.
        accepted = sorted(str(quad) for quad in store.store
                          if quad.graph_name.value.startswith('urn:semantica:project:'))
        return nodes['nodes'], links['links'], accepted
    finally:
        store.close()


@pytest.mark.parametrize('change', ['path', 'name', 'both'])
def test_path_and_display_name_do_not_rebuild_completed_projection(tmp_path, monkeypatch, change):
    import urllib.request
    from tests import test_semantic_artifact as fixtures
    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    baseline = build_child(tmp_path, stop_before_publication=False)
    expected = publication_semantics(baseline)
    paid = (tmp_path / 'build-calls.jsonl').read_bytes()
    moved = tmp_path / 'relocated' / 'source.txt'
    moved.parent.mkdir()
    moved.write_bytes((tmp_path / 'source.txt').read_bytes())
    request = fixtures._request
    admitted_request = request(tmp_path / 'source.txt', tmp_path / 'published', recipe='model')
    def relocated(*args, **kwargs):
        from copy import deepcopy
        result = deepcopy(admitted_request)
        if change in {'path', 'both'}:
            result['params']['sources'][0]['filePath'] = str(moved)
        if change in {'name', 'both'}:
            result['params']['sources'][0]['name'] = 'Display name changed.txt'
        return result
    def forbidden(*args, **kwargs):
        raise AssertionError('completed projection must not rebuild source entities or facts')
    monkeypatch.setattr(fixtures, '_request', relocated)
    monkeypatch.setattr(builder, '_build_source', forbidden)
    from semantica import semantic_document_reader as reader
    from semantica import semantic_source_artifact as source_artifact
    monkeypatch.setattr(reader, 'read_source_text_range', forbidden)
    digest_file = source_artifact._digest_file
    def metadata_digest(path):
        assert path.name.endswith('.reader.sqlite'), 'completion must not hash source bodies'
        return digest_file(path)
    monkeypatch.setattr(source_artifact, '_digest_file', metadata_digest)
    monkeypatch.setattr(source_artifact, 'source_content_revision', forbidden)
    monkeypatch.setattr(builder, '_request_embedding', forbidden)
    result = build_child(tmp_path, stop_before_publication=False)
    assert publication_semantics(result) == expected
    assert (tmp_path / 'build-calls.jsonl').read_bytes() == paid


def test_model_build_releases_raw_source_entities_and_facts_after_native_reduction(tmp_path, monkeypatch):
    import urllib.request
    # The fixture installs a no-network transport; register restoration with the
    # test owner even though the existing helper assigns that global directly.
    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-only')
    references = dict(entities=[], facts=[])
    boundaries = []
    build_source = builder._build_source
    reconcile_facts = QualifiedFactIndex.reconcile_and_stage
    organize = builder._semantic_organization

    def source(*args, **kwargs):
        built = build_source(*args, **kwargs)
        for kind, values in references.items():
            values.extend(weakref.ref(item) for item in built[kind])
        return built

    def assert_released(*kinds):
        gc.collect()
        for kind in kinds:
            assert references[kind], f'fixture must exercise raw {kind}'
            assert all(ref() is None for ref in references[kind]), (
                f'raw source {kind} still retained after canonical replacement')

    def reconcile(*args, **kwargs):
        assert_released('entities')
        boundaries.append('entity-resolution')
        return reconcile_facts(*args, **kwargs)

    def organization(*args, **kwargs):
        assert_released('entities', 'facts')
        boundaries.append('fact-reconciliation')
        return organize(*args, **kwargs)

    monkeypatch.setattr(builder, '_build_source', source)
    monkeypatch.setattr(QualifiedFactIndex, 'reconcile_and_stage', reconcile)
    monkeypatch.setattr(builder, '_semantic_organization', organization)
    baseline = build_child(tmp_path, stop_before_publication=False)
    assert boundaries == ['entity-resolution', 'fact-reconciliation']
    expected = publication_semantics(baseline)
    paid_calls = (tmp_path / 'build-calls.jsonl').read_bytes()

    def forbidden_source(*args, **kwargs):
        raise AssertionError('completed source projection must be reused')

    monkeypatch.setattr(builder, '_build_source', forbidden_source)
    monkeypatch.setattr(QualifiedFactIndex, 'reconcile_and_stage', reconcile_facts)
    monkeypatch.setattr(builder, '_semantic_organization', organize)
    result = build_child(tmp_path, stop_before_publication=False)
    assert result['publication']['state'] == 'ready'
    assert result['publication']['canonical_count'] == 2
    assert result['publication']['generation'] == baseline['publication']['generation']
    assert (tmp_path / 'build-calls.jsonl').read_bytes() == paid_calls
    assert publication_semantics(result) == expected


def test_embedding_model_change_reuses_source_classification_identity_and_facts(tmp_path, monkeypatch):
    import urllib.request
    from tests import test_semantic_artifact as fixtures
    from semantica.triplet_store.identity_candidate_index import IdentityCandidateIndex
    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    baseline = build_child(tmp_path, stop_before_publication=False)
    expected = publication_semantics(baseline)[:2]
    paid = (tmp_path / 'build-calls.jsonl').read_text().splitlines()
    original_request = fixtures._request
    def changed(*args, **kwargs):
        result = original_request(*args, **kwargs)
        result['params']['relays']['embedding']['modelId'] = 'embedding-new'
        return result
    def forbidden(*args, **kwargs):
        raise AssertionError('embedding-only change recomputed a completed knowledge stage')
    monkeypatch.setattr(fixtures, '_request', changed)
    monkeypatch.setattr(builder, '_build_source', forbidden)
    monkeypatch.setattr(builder, '_context_batches', forbidden)
    monkeypatch.setattr(QualifiedFactIndex, '_reduce_partition', forbidden)
    monkeypatch.setattr(IdentityCandidateIndex, 'build', forbidden)
    result = build_child(tmp_path, stop_before_publication=False)
    assert result['publication']['state'] == 'ready'
    assert publication_semantics(result)[:2] == expected
    assert (tmp_path / 'build-calls.jsonl').read_text().splitlines()[len(paid):] == ['"embedding"']
