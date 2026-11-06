"""Source-lifetime resource contracts for the actual native producer.

They instrument object lifetimes and the real scheduler boundary, not source text.
No transport/model call is made. Single-source size is a separate unresolved gap.
"""
import gc
import weakref

import pytest

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.source import source_content_revision
from tests.test_semantic_artifact import _parsed_ref, _request


def project_request(root, *, recipe="deterministic", count=4, repeats=8):
    first = root / "source-0.txt"
    first.write_text("Ada Lovelace designed the Analytical Engine.\n" * repeats)
    body = first.read_text()
    raw = _request(first, root / "published", recipe=recipe, prepare=False)["params"]
    template = raw["sources"][0]
    raw["sources"], raw["parsedSources"] = [], []
    for index in range(count):
        path = root / f"source-{index}.txt"
        path.write_text(f"Source {index}.\n" + body)
        source = dict(template, filePath=str(path), name=path.name,
                      sourceId=f"source-{index}", materialRevision=source_content_revision(path))
        raw["sources"].append(source)
        raw["parsedSources"].append(_parsed_ref(raw, source))
    return SemanticArtifactBuildRequest.model_validate(raw)


def track_documents(monkeypatch):
    references = []
    load = builder._load_parsed_source

    def observe(*args, **kwargs):
        gc.collect()
        assert not any(ref() is not None for ref in references), (
            "release the previous source document before loading the next"
        )
        parsed = load(*args, **kwargs)
        references.append(weakref.ref(parsed))
        return parsed

    monkeypatch.setattr(builder, "_load_parsed_source", observe)
    return references


def test_project_organization_does_not_retain_loaded_source_documents(tmp_path, monkeypatch):
    request = project_request(tmp_path)
    references = track_documents(monkeypatch)
    organize = builder._semantic_organization
    publish = builder._publish_native_indexes
    alive_at_organization = []

    def inspect_publication(request, generation, sources):
        assert len(sources) == 4
        for source in sources:
            assert not {"document", "text", "source_locations"}.intersection(source)
            addresses = list(source["native_scalar_ranges"].window(0, 128))
            assert addresses
            assert all(set(address) <= {"nativeRef", "start", "end", "windowStart", "windowEnd", "joinBefore"}
                       for address in addresses)
        return publish(request, generation, sources)

    def observe(*args, **kwargs):
        gc.collect()
        alive_at_organization.append(sum(ref() is not None for ref in references))
        return organize(*args, **kwargs)

    monkeypatch.setattr(builder, "_semantic_organization", observe)
    monkeypatch.setattr(builder, "_publish_native_indexes", inspect_publication)
    result = builder.build_semantic_artifacts(request)
    assert result["publication"]["source_count"] == 4
    assert len(references) == 4, "probe must observe every real parsed source"
    assert alive_at_organization == [0], (
        "global topology must consume native references, not retain every source document; "
        f"live parsed documents: {alive_at_organization}"
    )


def test_model_scheduler_does_not_materialize_every_source_window_list(tmp_path, monkeypatch):
    request = project_request(tmp_path, recipe="model", repeats=512)
    references, samples = [], []
    windows = builder._source_windows
    from semantica import semantic_document_reader as reader
    read = reader.read_source_text_range
    hydrated_bytes = []

    def observe_read(*args, **kwargs):
        result = read(*args, **kwargs)
        hydrated_bytes.append(len(result['item']['text'].encode()))
        return result

    def observe(parsed):
        value = windows(parsed)
        references.append(weakref.ref(value))
        return value

    class ProbeComplete(Exception):
        pass

    def inspect_scheduler(jobs, *_args, **_kwargs):
        assert all(len(job[2]) == 2 and all(type(value) is int for value in job[2]) for job in jobs), (
            "queued extraction jobs must contain source addresses, never window text"
        )
        gc.collect()
        live = [ref() for ref in references if ref() is not None]
        samples.append(dict(sources=len(live), jobs=len(jobs),
                            address_count=sum(len(values.ranges) for values in live),
                            body_bytes=sum(hydrated_bytes)))
        raise ProbeComplete("stop before extraction transport")

    monkeypatch.setattr(builder, "_source_windows", observe)
    monkeypatch.setattr(reader, 'read_source_text_range', observe_read)
    monkeypatch.setattr(builder, "_native_parallel_map", inspect_scheduler)
    with pytest.raises(ProbeComplete, match="before extraction transport"):
        builder.build_semantic_artifacts(request)
    assert samples and samples[0]["jobs"] > 0 and samples[0]['address_count'] > 0
    assert samples[0]['body_bytes'] == 0, 'address-only scheduling must not hydrate source window bodies'
    assert samples[0]["sources"] <= 1, (
        "producer must schedule a bounded source/window batch, not all project body windows; "
        f"observed {samples[0]}"
    )


def test_single_source_still_uses_the_requested_parallel_window_budget(tmp_path, monkeypatch):
    from threading import Barrier
    from types import SimpleNamespace
    from tests.test_semantic_artifact_scheduling import scheduling_request

    barrier = Barrier(2)
    calls = []

    def extract(text, relay, spec, locations, item, formula_semantics):
        calls.append(item[0])
        barrier.wait(timeout=2)
        return ({"entities": [], "relations": []}, [], False)

    monkeypatch.setattr(builder, "_extract_window", extract)
    monkeypatch.setattr(builder, "_embed_texts", lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    sources, request = scheduling_request(tmp_path, [("one", "abcd")], 2)
    results = builder._extract_project_sources(sources, request, None)
    assert sorted(calls) == [0, 1, 2, 3]
    assert [chunk["start_char"] for chunk in results[0][1]] == [0, 1, 2, 3]


def test_scheduler_retains_addresses_and_only_active_window_bodies(tmp_path, monkeypatch):
    from threading import Lock
    from types import SimpleNamespace
    from tests.test_semantic_artifact_scheduling import scheduling_request

    references, samples = [], []
    lock = Lock()

    class Window(str):
        pass

    text = ''.join(chr(65 + index % 26) * 100 for index in range(80))
    from semantica import semantic_document_reader as reader
    read = reader.read_source_text_range

    def observe_read(*args, **kwargs):
        result = read(*args, **kwargs)
        body = Window(result['item']['text'])
        with lock:
            references.append(weakref.ref(body))
        return {**result, 'item': {**result['item'], 'text': body}}
    parallel_map = builder._native_parallel_map

    def inspect(jobs, *args, **kwargs):
        assert not any(ref() is not None for ref in references), 'queued jobs retain source window bodies'
        assert all(not isinstance(value, str) for job in jobs for value in job[2])
        return parallel_map(jobs, *args, **kwargs)

    def extract(*args):
        with lock:
            samples.append(sum(ref() is not None for ref in references))
        return {'entities': [], 'relations': []}, [], False

    monkeypatch.setattr(builder, '_native_parallel_map', inspect)
    monkeypatch.setattr(reader, 'read_source_text_range', observe_read)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda values, relay: ([[1.] for _ in values], SimpleNamespace()))
    sources, request = scheduling_request(tmp_path, [('one', text)], 3, window_chars=100)
    result = builder._extract_project_sources(sources, request, None)
    assert len(result[0][1]) == 80
    assert references and samples and 0 < max(samples) <= 3
    assert not any(ref() is not None for ref in references)
