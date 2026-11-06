"""Retired source projections must not survive native canonical reduction."""
import gc
import weakref

from semantica import semantic_publication_builder as builder
from semantica.triplet_store.oxigraph_store import OxigraphStore
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


def test_model_build_releases_raw_source_entities_and_facts_after_native_reduction(tmp_path, monkeypatch):
    import urllib.request
    # The fixture installs a no-network transport; register restoration with the
    # test owner even though the existing helper assigns that global directly.
    monkeypatch.setattr(urllib.request, 'urlopen', urllib.request.urlopen)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-only')
    baseline = build_child(tmp_path, stop_before_publication=False)
    expected = publication_semantics(baseline)
    paid_calls = (tmp_path / 'build-calls.jsonl').read_bytes()
    references = dict(entities=[], assertions=[], relations=[])
    boundaries = []
    build_source = builder._build_source
    remap_facts = builder._remap_identity_facts
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

    def remap(*args, **kwargs):
        assert_released('entities')
        boundaries.append('entity-resolution')
        return remap_facts(*args, **kwargs)

    def organization(*args, **kwargs):
        assert_released('entities', 'assertions', 'relations')
        boundaries.append('fact-reconciliation')
        return organize(*args, **kwargs)

    monkeypatch.setattr(builder, '_build_source', source)
    monkeypatch.setattr(builder, '_remap_identity_facts', remap)
    monkeypatch.setattr(builder, '_semantic_organization', organization)
    result = build_child(tmp_path, stop_before_publication=False)
    assert boundaries == ['entity-resolution', 'fact-reconciliation']
    assert result['publication']['state'] == 'ready'
    assert result['publication']['canonical_count'] == 2
    assert result['publication']['generation'] != baseline['publication']['generation']
    assert (tmp_path / 'build-calls.jsonl').read_bytes() == paid_calls
    assert publication_semantics(result) == expected
