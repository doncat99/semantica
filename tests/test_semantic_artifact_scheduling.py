import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from semantica import semantic_publication_builder as builder
from semantica.pipeline.parallelism_manager import ParallelismManager, Task
from semantica.semantic_artifact_schema import DocumentProcessingProfile, RecipeRef
from semantica.semantic_artifact_schema import SourceBuildInput
from semantica.source import source_content_revision
from tests.artifact_helpers import native_parsed_fixture


def scheduling_request(tmp_path, materials, parallelism, *, window_chars=1):
    sources, refs = [], []
    for source_id, text in materials:
        path = tmp_path / f'{source_id}.txt'
        path.write_text(text)
        source = SourceBuildInput(sourceId=source_id, materialRevision=source_content_revision(path),
            filePath=str(path), name=path.name, mimeType='text/plain')
        # Control the producer address seam, so scheduling still consumes the
        # canonical installed index and its real bounded native text reader.
        from semantica import semantic_document_reader as reader
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(reader, 'source_text_windows', lambda value: (
                (start, min(len(value), start+window_chars))
                for start in range(0, len(value), window_chars)))
            parsed = native_parsed_fixture(source)
        sources.append((source, False, parsed))
        refs.append(SimpleNamespace(source_id=source_id,
                                    representation_revision=parsed.document['representation_revision']))
    relay = SimpleNamespace(binding_id='test', model_id='test-model', context_window_tokens=500000, max_output_tokens=32768)
    request = SimpleNamespace(parallelism=parallelism, project_id='fixture-project',
        parsed_sources=refs, relays={'model': relay, 'embedding': None},
        recipe=RecipeRef(id='model', version='1'),
        document_processing=DocumentProcessingProfile(mode='local'))
    return sources, request


def test_healthy_relay_is_parallel_and_recovery_is_single_probe():
    gate = builder._RelayCooldown()
    barrier = threading.Barrier(4)
    def healthy():
        with gate.admit():
            barrier.wait(timeout=2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: healthy(), range(4)))
    with pytest.raises(builder.SemanticArtifactError):
        with gate.admit():
            raise builder.SemanticArtifactError('cooldown', retryable=True, retry_after_ms=80)
    started = time.monotonic()
    probe_entered, release = threading.Event(), threading.Event()
    entries = []
    def probe(index):
        with gate.admit():
            entries.append(index)
            if len(entries) == 1:
                probe_entered.set()
                assert release.wait(2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(probe, i) for i in range(4)]
        assert probe_entered.wait(2)
        assert time.monotonic() - started >= .07
        assert len(entries) == 1
        release.set()
        for future in futures:
            future.result(timeout=2)
    assert len(entries) == 4


def test_global_queue_interleaves_sources_preserves_order_and_budget(tmp_path, monkeypatch):
    lock = threading.Lock()
    active = peak = 0
    calls = []
    def extract(text, relay, spec, locations, item, formula_semantics):
        assert formula_semantics is False
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(item[2])
        time.sleep(.01)
        with lock:
            active -= 1
        return ({'entities': [], 'relations': []}, [], False)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    sources, request = scheduling_request(tmp_path, [('source-a', 'abc'), ('source-b', 'xy')], 2)
    events = []
    result = builder._extract_project_sources(sources, request, events.append)
    assert peak == 2
    # Submission interleaves sources; worker start order is not deterministic.
    assert sorted(calls[:2]) == ['a', 'x']
    assert [len(value[1]) for value in result] == [3, 2]
    assert [[chunk['start_char'] for chunk in value[1]] for value in result] == [[0, 1, 2], [0, 1]]
    counts = [event['metadata']['completedChunks'] for event in events if event['stage'] == 'extracting']
    assert counts[0] == 0 and counts[-1] == 5
    assert counts == sorted(counts)
    initial = events[0]['metadata']['sourceProgress']
    assert [(s['sourceId'], s['completedChunks'], s['totalChunks'], s['state']) for s in initial] == [('source-a', 0, 3, 'queued'), ('source-b', 0, 2, 'queued')]
    extracting = [event for event in events if event['stage'] == 'extracting']
    assert any(row['inFlightChunks'] > 0 for event in extracting for row in event['metadata']['sourceProgress'])
    final = extracting[-1]['metadata']['sourceProgress']
    assert [(s['sourceId'], s['completedChunks'], s['totalChunks'], s['state']) for s in final] == [('source-a', 3, 3, 'completed'), ('source-b', 2, 2, 'completed')]
    assert all(sum(s['completedChunks'] for s in event['metadata']['sourceProgress']) == event['metadata']['completedChunks'] for event in events)


def test_restore_coalesces_warnings_without_blocking_worker_lock(tmp_path, monkeypatch):
    calls, events = [], []
    receipt = SimpleNamespace(metadata={'rejected_count': 100})
    def extract(*args):
        calls.append(args)
        return ({'entities': [], 'relations': []}, [receipt], True)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    def progress(event):
        if event['stage'] == 'extracting' and any(r['inFlightChunks'] for r in event['metadata']['sourceProgress']):
            # A slow stdout consumer cannot hold the source-state lock.
            deadline = time.monotonic() + 2
            while len(calls) < 20 and time.monotonic() < deadline:
                time.sleep(.001)
            assert len(calls) == 20
        events.append(event)
    sources, request = scheduling_request(tmp_path, [('source-a', 'a' * 20)], 4)
    builder._extract_project_sources(sources, request, progress)
    extraction = [e for e in events if e['stage'] == 'extracting']
    assert len(extraction) < 10
    assert extraction[-1]['metadata']['warningCount'] == 2000
    assert extraction[-1]['metadata']['restoredChunks'] == 20
    assert receipt.metadata == {'rejected_count': 100}
    assert extraction[-1]['metadata']['warning']['diagnostic'] == {'rejectedCount': 100}


def test_exhausted_transient_failure_stops_dispatching_new_chunks():
    calls = []
    def fail(index):
        calls.append(index)
        raise builder.SemanticArtifactError('offline', retryable=True)
    results = ParallelismManager(max_workers=1).execute_parallel([Task(str(i), fail, (i,)) for i in range(10)], fail_fast=True)
    assert calls == [0]
    assert len(results) == 1 and not results[0].success


def test_typed_retry_respects_gateway_delay_and_permanent_failure(monkeypatch):
    from pydantic import BaseModel
    from semantica.semantic_extract.providers import BaseProvider
    from semantica.semantic_extract import providers
    from semantica.utils.exceptions import ProcessingError
    class Result(BaseModel):
        value: int
    class Provider(BaseProvider):
        def generate(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise builder.SemanticArtifactError('cooldown', retryable=self.retryable, retry_after_ms=29845)
            return '{"value":7}'
        def generate_structured(self, prompt, **kwargs):
            raise AssertionError('typed generation must not add another structured retry loop')
    delays = []
    monkeypatch.setattr(providers.time, 'sleep', delays.append)
    provider = Provider()
    provider.calls, provider.retryable = 0, True
    assert provider.generate_typed('test', Result, max_retries=2).value == 7
    assert delays == [29.845]
    provider.calls, provider.retryable = 0, False
    delays.clear()
    with pytest.raises(ProcessingError):
        provider.generate_typed('test', Result, max_retries=2)
    assert provider.calls == 1
    assert delays == []


@pytest.mark.parametrize("window", [(500, 900, 'text'), [500, 900, 'text']])
def test_flattened_failure_reports_actual_window_offsets(window):
    def fail(item):
        raise builder.SemanticArtifactError('offline', retryable=True)
    with pytest.raises(Exception) as failure:
        builder._native_parallel_map([(2, 4, window)], fail, 1)
    assert failure.value.parallel_context['sourceIndex'] == 2
    assert failure.value.parallel_context['windowStart'] == 500
    assert failure.value.parallel_context['windowEnd'] == 900
