"""A completed or failed build releases the native writer for query handoff."""
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as builder
from semantica.triplet_store.oxigraph_store import OxigraphStore


@pytest.mark.parametrize('failure', [False, True])
def test_build_releases_native_writer_and_context(tmp_path, monkeypatch, failure):
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir()
    request = SimpleNamespace(native_cache_dir=str(cache_dir), native_store_dir=str(tmp_path / 'facts'))
    previous = builder._native_build.get()
    owners = []

    def build(request, progress=None):
        owner = builder._native_build.get()[1]
        owners.append(owner)
        owner.begin_publication('project', expected_generation=None, source_count=0, canonical_count=0)
        if failure:
            raise RuntimeError('fixture build failure')
        return {'project': 'project'}

    monkeypatch.setattr(builder, '_build_semantic_artifacts', build)
    if failure:
        with pytest.raises(RuntimeError, match='fixture build failure'):
            builder.build_semantic_artifacts(request)
    else:
        assert builder.build_semantic_artifacts(request) == {'project': 'project'}
    assert builder._native_build.get() is previous
    assert not hasattr(owners[0], 'store')
    reader = OxigraphStore(request.native_store_dir)
    try:
        assert reader.publication_status('project')['state'] == 'pending'
    finally:
        reader.close()


def test_rebuild_invalidates_ready_generation_before_reading_source(tmp_path, monkeypatch):
    from tests.test_native_extraction_handoff import build_child
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    from tests.test_semantic_artifact import _request
    from semantica.utils.exceptions import ProcessingError

    first = build_child(tmp_path, stop_before_publication=False)
    old_generation = first['publication']['generation']
    observed = []

    def fail_read(*args, **kwargs):
        store = builder._native_build.get()[1]
        status = store.publication_status('project-1')
        observed.append(status)
        assert status['state'] == 'pending'
        assert status['generation'] != old_generation
        with pytest.raises(ProcessingError, match='not ready'):
            store.read_publication_scene('project-1', old_generation, {'kind': 'nodes'})
        raise RuntimeError('source read failed')

    monkeypatch.setattr(builder, '_load_parsed_source', fail_read)
    request = SemanticArtifactBuildRequest.model_validate(
        _request(tmp_path / 'source.txt', tmp_path / 'published')['params'])
    with pytest.raises(RuntimeError, match='source read failed'):
        builder.build_semantic_artifacts(request)
    assert len(observed) == 1
    store = OxigraphStore(request.native_store_dir)
    try:
        assert store.publication_status('project-1')['state'] == 'pending'
        with pytest.raises(ProcessingError, match='not ready'):
            store.read_publication_scene('project-1', old_generation, {'kind': 'nodes'})
    finally:
        store.close()


def test_ready_build_publishes_canonical_fact_with_native_support(tmp_path):
    from tests.test_native_extraction_handoff import build_child
    from tests.test_semantic_artifact import _request
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    built = build_child(tmp_path, stop_before_publication=False)
    request = SemanticArtifactBuildRequest.model_validate(
        _request(tmp_path / 'source.txt', tmp_path / 'published')['params'])
    store = OxigraphStore(request.native_store_dir)
    try:
        generation = built['publication']['generation']
        nodes = store.read_publication_scene('project-1', generation, {'kind': 'nodes'})['nodes']
        scene = store.read_publication_scene('project-1', generation,
            {'kind': 'links', 'visibleIds': [node['id'] for node in nodes]})
        assert len(scene['links']) == 1
        fact = scene['links'][0]
        assert fact['id'].startswith('relation:')
        supports = store.read_publication_fact_members('project-1', generation, fact['id'])
        assert supports['member_count'] == len(supports['members']) == 1
        support = store.read_native_records('project-1', generation, supports['members'])[0]
        assert support['id'] != fact['id']
        assert support['fields']['urn:semantica:field:predicateName'][0]['value'] == fact['predicate']
        assert fact['sourceIds'] == ['source-1']
        assert fact['evidenceIds']
    finally:
        store.close()
