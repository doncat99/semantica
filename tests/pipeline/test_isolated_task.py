import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from semantica.pipeline.parallelism_manager import ParallelismManager, Task
from semantica.utils.exceptions import ProcessingError


def _mark_and_wait(path):
    Path(path).write_text(str(os.getpid()))
    time.sleep(30)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGKILL/ps lifetime probe")
def test_parent_sigkill_leaves_no_running_operation(tmp_path):
    marker = tmp_path / "operation.pid"
    program = (
        "from semantica.pipeline.parallelism_manager import ParallelismManager, Task\n"
        "from tests.pipeline.test_isolated_task import _mark_and_wait\n"
        "if __name__ == '__main__':\n"
        f"    ParallelismManager().execute_isolated_task(Task('wait', _mark_and_wait, ({str(marker)!r},)), "
        "timeout_seconds=60, max_rss_bytes=1024**3)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", program], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            assert parent.poll() is None
            time.sleep(.05)
        assert marker.exists(), "operation must actually be running before parent termination"
        child_pid = int(marker.read_text())
        parent.kill()
        parent.communicate(timeout=10)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)],
                                    capture_output=True, text=True).stdout.strip()
            if not status or status.startswith("Z"):
                return
            time.sleep(.05)
        pytest.fail("operation survived its killed parent")
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=10)
        if child_pid is not None:
            try:
                os.kill(child_pid, 9)
            except ProcessLookupError:
                pass


def test_isolated_task_returns_complete_result():
    assert ParallelismManager().execute_isolated_task(
        Task("sum", sum, ([1, 2, 3],)), timeout_seconds=10,
        max_rss_bytes=1024**3) == 6


def test_isolated_task_keeps_installed_runtime_immutable():
    assert ParallelismManager().execute_isolated_task(
        Task("immutable-runtime", eval, ("__import__('sys').dont_write_bytecode",)),
        timeout_seconds=10, max_rss_bytes=1024**3) is True


def _grow_memory():
    retained = bytearray(256 * 1024**2)
    time.sleep(30)
    return len(retained)


def test_live_memory_growth_terminates_operation():
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("growth", _grow_memory), timeout_seconds=10,
            max_rss_bytes=128 * 1024**2)
    assert caught.value.processing_context["reason"] == "memory"


@pytest.mark.parametrize("handler, reason", [
    (lambda: None, "startup"),
    (int, "ValueError: invalid literal for int() with base 10: 'invalid'"),
    (os._exit, "child_exit"),
])
def test_isolated_startup_handler_and_exit_failures_are_typed(handler, reason):
    baseline = {child.pid for child in multiprocessing.active_children()}
    args = ("invalid",) if handler is int else (71,) if handler is os._exit else ()
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("failure", handler, args), timeout_seconds=10,
            max_rss_bytes=1024**3)
    assert caught.value.processing_context == {"task_id": "failure", "reason": reason}
    assert {child.pid for child in multiprocessing.active_children()} == baseline


@pytest.mark.parametrize("reason", ["deadline", "cancelled", "memory"])
def test_isolated_failure_reaps_child_and_next_task_runs(reason):
    baseline = {child.pid for child in multiprocessing.active_children()}
    cancellation = threading.Event()
    timer = threading.Timer(.3, cancellation.set) if reason == "cancelled" else None
    if timer:
        timer.start()
    try:
        with pytest.raises(ProcessingError) as caught:
            ParallelismManager().execute_isolated_task(
                Task("blocked", time.sleep, (30,)),
                timeout_seconds=.3 if reason == "deadline" else 10,
                max_rss_bytes=1 if reason == "memory" else 1024**3,
                cancellation=cancellation)
        assert caught.value.processing_context["reason"] == reason
    finally:
        if timer:
            timer.join()
    assert {child.pid for child in multiprocessing.active_children()} == baseline
    assert ParallelismManager().execute_isolated_task(
        Task("sum", sum, ([4, 5],)), timeout_seconds=10,
        max_rss_bytes=1024**3) == 9


class _SlowPickle:
    def __reduce__(self):
        time.sleep(1)
        return (str, ("slow",))


def _restore_slow():
    time.sleep(1)
    return "slow"


class _SlowRestore:
    def __reduce__(self):
        return (_restore_slow, ())


def _return_slow_pickle():
    return _SlowRestore()


@pytest.mark.parametrize("cancel", [False, True])
def test_input_transport_never_executes_arbitrary_pickle(cancel):
    """Arbitrary reducer execution previously blocked spawn past the deadline."""
    cancellation = threading.Event()
    timer = threading.Timer(.1, cancellation.set) if cancel else None
    if timer:
        timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ProcessingError) as caught:
            ParallelismManager().execute_isolated_task(
                Task("input", str, (_SlowPickle(),)), timeout_seconds=.2,
                max_rss_bytes=1024**3, cancellation=cancellation)
        assert caught.value.processing_context["reason"] == "input_contract"
        assert time.monotonic() - started < .8
    finally:
        if timer:
            timer.join()


def test_output_transport_never_executes_arbitrary_pickle():
    started = time.monotonic()
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("output", _return_slow_pickle), timeout_seconds=10,
            max_rss_bytes=1024**3)
    assert caught.value.processing_context["reason"] == "output_contract"
    assert time.monotonic() - started < .8


def _return_text(size):
    return "x" * size


def _identity(value):
    return value


@pytest.mark.parametrize("location", ["input", "output"])
def test_transport_byte_limit_fails_without_partial_result(location):
    args = ("x" * 4096,) if location == "input" else (4096,)
    handler = _identity if location == "input" else _return_text
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("limit", handler, args), timeout_seconds=10,
            max_rss_bytes=1024**3, max_transport_bytes=512)
    assert caught.value.processing_context["reason"] == location + "_limit"


def test_json_transport_preserves_exact_supported_values():
    value = {"unicode": "雪\n\"\\", "nested": [None, True, False, -42, 1.25, {}]}
    assert ParallelismManager().execute_isolated_task(
        Task("identity", _identity, (value,)), timeout_seconds=10,
        max_rss_bytes=1024**3) == value


def test_nested_tuple_is_rejected_instead_of_changing_handler_semantics():
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("tuple", _identity, ((1, 2),)), timeout_seconds=10,
            max_rss_bytes=1024**3)
    assert caught.value.processing_context["reason"] == "input_contract"


def test_cycle_is_bounded_without_recursion_or_pickle():
    value = []
    value.append(value)
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task("cycle", _identity, (value,)), timeout_seconds=10,
            max_rss_bytes=1024**3)
    assert caught.value.processing_context["reason"] == "input_limit"


def test_parent_memory_is_checked_before_serialization(monkeypatch):
    """An over-budget builder must not serialize/spawn another full graph."""
    import psutil
    from types import SimpleNamespace
    parent_type = psutil.Process
    monkeypatch.setattr(parent_type, 'memory_info', lambda self: SimpleNamespace(rss=256 * 1024**2))
    spawned = []
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: spawned.append(args))
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task('parent-budget', sum, ([1, 2, 3],)), timeout_seconds=10,
            max_rss_bytes=128 * 1024**2)
    assert caught.value.processing_context['reason'] == 'memory'
    assert spawned == []


def test_parent_and_child_share_the_operation_budget(monkeypatch):
    import psutil
    from types import SimpleNamespace
    # Neither process individually exceeds the budget; their sum does.
    monkeypatch.setattr(psutil.Process, 'memory_info', lambda self: SimpleNamespace(rss=80 * 1024**2))
    with pytest.raises(ProcessingError) as caught:
        ParallelismManager().execute_isolated_task(
            Task('combined-budget', time.sleep, (1,)), timeout_seconds=10,
            max_rss_bytes=128 * 1024**2)
    assert caught.value.processing_context['reason'] == 'memory'
