"""Completed source projection must release superseded DTO owners."""
import gc
import weakref

import pytest

from semantica import semantic_publication_builder as builder
from tests.test_native_build_body_budget import project_request


def test_global_resolution_releases_source_mentions_and_unused_registry(tmp_path, monkeypatch):
    request = project_request(tmp_path, recipe='model', count=3, repeats=2)
    originals, registries = [], []
    build_source = builder._build_source
    resolve = builder._resolve_native_entities

    def extract(sources, *_args):
        # Exercise the real deterministic native extraction owner; mocked DTOs
        # without persisted membership cannot enter the current build contract.
        return [(None, [], []) for _ in sources]

    def source(*args, **kwargs):
        result = build_source(*args, **kwargs)
        originals.extend(weakref.ref(item) for item in result['entities'])
        return result

    def resolution(*args, **kwargs):
        result = resolve(*args, **kwargs)
        registries.extend(weakref.ref(item) for item in result[2])
        return result

    class Observed(Exception):
        pass

    def inspect(topology, *_args, **_kwargs):
        gc.collect()
        assert originals
        assert registries
        assert all(ref() is None for ref in originals), 'source and projection owners retain superseded mentions'
        assert all(ref() is None for ref in registries), 'unused identity registry survives into organization'
        assert topology['entities']
        assert set(topology['entities'][0]) == {'id', 'name'}
        assert all(set(row) == {'id', 'source', 'target', 'type'} for row in topology['relationships'])
        raise Observed()

    monkeypatch.setattr(builder, '_extract_project_sources', extract)
    monkeypatch.setattr(builder, '_build_source', source)
    monkeypatch.setattr(builder, '_resolve_native_entities', resolution)
    monkeypatch.setattr(builder, '_semantic_organization', inspect)
    with pytest.raises(Observed):
        builder.build_semantic_artifacts(request)
