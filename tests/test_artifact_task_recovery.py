from collections import Counter
from types import SimpleNamespace

import pytest

from semantica import semantic_artifact_builder as builder
from semantica.pipeline import parallelism_manager as parallel


def test_retry_only_failed_task_without_restarting_siblings(monkeypatch):
    monkeypatch.setattr(parallel.time, 'sleep', lambda _: None)
    calls = Counter()
    retries = []

    def work(index):
        calls[index] += 1
        if index == 1 and calls[index] == 1:
            raise builder.SemanticArtifactError('timeout', retryable=True, retry_after_ms=3000)
        return index

    assert builder._native_parallel_map(list(range(5)), work, 2, max_attempts=2,
                                       on_retry=lambda *args: retries.append(args)) == list(range(5))
    assert calls == {0: 1, 1: 2, 2: 1, 3: 1, 4: 1}
    assert [(row[0], row[1], row[2]) for row in retries] == [(1, 2, 3000)]


def test_exhausted_transient_task_keeps_dispatching_other_work(monkeypatch):
    monkeypatch.setattr(parallel.time, 'sleep', lambda _: None)
    calls = Counter()
    completed = []

    def work(index):
        calls[index] += 1
        if index == 0:
            raise builder.SemanticArtifactError('timeout', retryable=True)
        return index

    with pytest.raises(Exception) as failure:
        builder._native_parallel_map(list(range(4)), work, 1,
                                     lambda index, value: completed.append(value), max_attempts=2)
    assert completed == [1, 2, 3]
    assert calls == {0: 2, 1: 1, 2: 1, 3: 1}
    typed = builder._typed_extraction_error(failure.value)
    assert typed.retryable is False  # No automatic whole-build replay after the task budget.
    assert typed.diagnostic['parallelTask']['attempts'] == 2


def test_permanent_failure_is_not_retried_or_followed_by_more_tasks():
    calls = []

    def work(index):
        calls.append(index)
        raise builder.SemanticArtifactError('auth', retryable=False, status=401)

    with pytest.raises(Exception):
        builder._native_parallel_map(list(range(4)), work, 1, max_attempts=2)
    assert calls == [0]


def test_phase_recovery_retains_counts_and_emits_retry_timing(monkeypatch):
    monkeypatch.setattr(parallel.time, 'sleep', lambda _: None)
    monkeypatch.setattr(builder, '_source_windows', lambda *args, **kwargs: [(0, 1, 'a'), (1, 2, 'b')])
    monkeypatch.setattr(builder, '_docling_locations', lambda *args: [])
    calls = Counter()

    def extract(text, relay, spec, locations, item, formula_semantics):
        calls[item[0]] += 1
        if item[0] == 1 and calls[1] == 1:
            raise builder.SemanticArtifactError('timeout', retryable=True)
        return {'entities': [], 'relations': []}, [], False

    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    request = SimpleNamespace(parallelism=1, relays={'model': None, 'embedding': None},
                              recipe=SimpleNamespace(extraction_spec=None))
    events = []
    builder._extract_project_sources([(SimpleNamespace(source_id='a'), False, ('ab', {}))], request, events.append)
    extracting = [event['metadata'] for event in events if event['stage'] == 'extracting']
    assert max(row['retryCount'] for row in extracting) == 1
    assert extracting[-1]['lastRetry'] == {'taskId': '1', 'attempt': 2, 'delayMs': 1000}
    assert [row['completedChunks'] for row in extracting] == sorted(row['completedChunks'] for row in extracting)
    assert extracting[-1]['sourceProgress'][0]['state'] == 'completed'
    assert extracting[-1]['sourceProgress'][0]['failedChunks'] == 0
    assert all(row['elapsedMs'] >= 0 and row['startedAtMs'] > 0 for row in extracting)


@pytest.mark.parametrize('workers', [8, 16])
def test_native_tasks_reach_but_do_not_exceed_requested_parallelism(workers):
    import threading
    gate = threading.Barrier(workers)
    lock = threading.Lock()
    active = peak = 0

    def work(index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            gate.wait(timeout=10)
            return index
        finally:
            with lock:
                active -= 1

    assert builder._native_parallel_map(list(range(workers * 2)), work, workers,
                                       max_attempts=2) == list(range(workers * 2))
    assert peak == workers


@pytest.mark.parametrize('fail', [False, True])
def test_long_task_emits_heartbeat_and_joins_reporter_on_settlement(monkeypatch, fail):
    import threading
    heartbeat = threading.Event()
    events = []
    monkeypatch.setattr(builder, '_source_windows', lambda *args, **kwargs: [(0, 1, 'a')])
    monkeypatch.setattr(builder, '_docling_locations', lambda *args: [])

    def progress(event):
        events.append(event)
        if event['stage'] == 'extracting' and event['metadata']['elapsedMs'] >= 4000:
            heartbeat.set()

    def extract(*args):
        assert heartbeat.wait(10), 'long-running task must produce a progress heartbeat'
        if fail:
            raise builder.SemanticArtifactError('terminal', retryable=False)
        return {'entities': [], 'relations': []}, [], False

    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.]], SimpleNamespace()))
    request = SimpleNamespace(parallelism=1, relays={'model': None, 'embedding': None},
                              recipe=SimpleNamespace(extraction_spec=None))
    sources = [(SimpleNamespace(source_id='a'), False, ('a', {}))]
    if fail:
        with pytest.raises(builder.SemanticArtifactError, match='terminal'):
            builder._extract_project_sources(sources, request, progress)
    else:
        builder._extract_project_sources(sources, request, progress)
    assert any(event['metadata']['elapsedMs'] >= 4000 and event['metadata']['completedChunks'] == 0
               for event in events if event['stage'] == 'extracting')
    assert not any(t.name in {'extracting-progress', 'embedding-progress'}
                   for t in threading.enumerate())
