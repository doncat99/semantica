"""Native scheduler must retain only its active dispatch window."""
import gc
import weakref

from semantica.pipeline.parallelism_manager import ParallelismManager, Task


def test_lazy_dispatch_and_result_release():
    generated = 0
    refs = []

    class Payload:
        pass

    def work():
        value = Payload()
        refs.append(weakref.ref(value))
        return value

    def tasks():
        nonlocal generated
        for index in range(40):
            generated += 1
            yield Task(str(index), work)

    completed = 0
    for result in ParallelismManager(max_workers=2).iter_results(tasks(), fail_fast=True):
        completed += 1
        gc.collect()
        assert generated <= completed + 2
        assert sum(ref() is not None for ref in refs) <= 3
        assert result.success
        del result
    assert completed == generated == 40
    gc.collect()
    assert not any(ref() is not None for ref in refs)


def test_stream_stops_dispatch_on_failure():
    called = []

    def fail(index):
        called.append(index)
        raise ValueError('invalid')

    results = list(ParallelismManager(max_workers=1).iter_results(
        (Task(str(i), fail, (i,)) for i in range(20)), fail_fast=True))
    assert called == [0]
    assert len(results) == 1 and not results[0].success


def test_builder_callback_releases_completed_values():
    from semantica.semantic_publication_builder import _native_parallel_map

    refs = []
    completed = []

    class Payload:
        pass

    def work(index):
        gc.collect()
        assert sum(ref() is not None for ref in refs) <= 1
        value = Payload()
        refs.append(weakref.ref(value))
        return value

    def consume(index, value):
        completed.append(index)
        assert isinstance(value, Payload)

    assert _native_parallel_map(list(range(20)), work, 1, consume) == []
    gc.collect()
    assert completed == list(range(20))
    assert not any(ref() is not None for ref in refs)
