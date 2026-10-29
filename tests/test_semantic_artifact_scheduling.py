import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from semantica import semantic_artifact_builder as builder
from semantica.pipeline.parallelism_manager import ParallelismManager, Task


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


def test_global_queue_interleaves_sources_preserves_order_and_budget(monkeypatch):
    monkeypatch.setattr(builder, '_text_windows', lambda text: [(i, i+1, c) for i, c in enumerate(text)])
    monkeypatch.setattr(builder, '_docling_locations', lambda *args: [])
    lock = threading.Lock()
    active = peak = 0
    calls = []
    def extract(text, relay, spec, locations, item, formula_semantics):
        assert formula_semantics is False
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(text)
        time.sleep(.01)
        with lock:
            active -= 1
        return ({'entities': [], 'relations': []}, [], False)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    request = SimpleNamespace(parallelism=2, relays={'model': None, 'embedding': None}, recipe=SimpleNamespace(extraction_spec=None))
    events = []
    result = builder._extract_project_sources([(SimpleNamespace(source_id='a', material_revision='immutable-a'), False, ('abc', {})), (SimpleNamespace(source_id='b', material_revision='immutable-b'), False, ('xy', {}))], request, events.append)
    assert peak == 2
    assert calls[:2] == ['abc', 'xy']
    assert [len(value[1]) for value in result] == [3, 2]
    assert [[chunk['start_char'] for chunk in value[1]] for value in result] == [[0, 1, 2], [0, 1]]
    counts = [event['metadata']['completedChunks'] for event in events if event['stage'] == 'extracting']
    assert counts[0] == 0 and counts[-1] == 5
    assert counts == sorted(counts)
    initial = events[0]['metadata']['sourceProgress']
    assert [(s['sourceId'], s['completedChunks'], s['totalChunks'], s['state']) for s in initial] == [('a', 0, 3, 'queued'), ('b', 0, 2, 'queued')]
    extracting = [event for event in events if event['stage'] == 'extracting']
    assert any(row['inFlightChunks'] > 0 for event in extracting for row in event['metadata']['sourceProgress'])
    final = extracting[-1]['metadata']['sourceProgress']
    assert [(s['sourceId'], s['completedChunks'], s['totalChunks'], s['state']) for s in final] == [('a', 3, 3, 'completed'), ('b', 2, 2, 'completed')]
    assert all(sum(s['completedChunks'] for s in event['metadata']['sourceProgress']) == event['metadata']['completedChunks'] for event in events)


def test_restore_coalesces_warnings_without_blocking_worker_lock(monkeypatch):
    monkeypatch.setattr(builder, '_text_windows', lambda text: [(i, i + 1, c) for i, c in enumerate(text)])
    monkeypatch.setattr(builder, '_docling_locations', lambda *args: [])
    calls, events = [], []
    receipt = SimpleNamespace(metadata={'rejected_candidates': [
        {'action': 'discarded_candidate', 'diagnostic': {'reason': 'ungrounded'}} for _ in range(100)]})
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
    source = SimpleNamespace(source_id='a', material_revision='a')
    request = SimpleNamespace(parallelism=4, relays={'model': None, 'embedding': None}, recipe=SimpleNamespace(extraction_spec=None))
    builder._extract_project_sources([(source, False, ('a' * 20, {}))], request, progress)
    extraction = [e for e in events if e['stage'] == 'extracting']
    assert len(extraction) < 10
    assert extraction[-1]['metadata']['warningCount'] == 2000
    assert extraction[-1]['metadata']['restoredChunks'] == 20
    assert len(receipt.metadata['rejected_candidates']) == 100


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
