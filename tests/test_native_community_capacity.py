"""Measure the unchanged native graph operation, including both process RSSes."""
import json
from pathlib import Path
import threading
import time

import psutil
import pytest

from semantica.pipeline.parallelism_manager import ParallelismManager, Task
from semantica.semantic_publication_builder import _native_community_operation
from semantica.utils.exceptions import ProcessingError


def _topology(count, shape):
    entities = [{"id": f"n{i}"} for i in range(count)]
    if shape == "hub":
        pairs = ((0, i) for i in range(1, count))
    else:
        pairs = ((i, j) for i in range(count)
                 for j in range(i + 1, min((i // 8 + 1) * 8, count)))
    relations = [{"id": f"e{i}-{j}", "source": f"n{i}", "target": f"n{j}"} for i, j in pairs]
    if shape != "hub":
        relations.extend({"id": f"bridge{i}", "source": f"n{i-1}", "target": f"n{i}"}
                         for i in range(8, count, 8))
    return {"entities": entities, "relationships": relations}


def _marked_community(topology, marker):
    Path(marker).touch()
    return _native_community_operation(topology)


@pytest.mark.parametrize("count,shape", [(2048, "clustered"), (10000, "clustered"), (2048, "hub")])
def test_native_community_capacity_records_complete_operation(tmp_path, count, shape):
    process = psutil.Process()
    baseline = {child.pid for child in process.children(recursive=True)}
    stop = threading.Event()
    samples = []

    def monitor():
        while not stop.is_set():
            child_rss = 0
            for child in process.children(recursive=True):
                if child.pid not in baseline:
                    try:
                        child_rss += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
            samples.append((process.memory_info().rss, child_rss))
            stop.wait(.01)

    thread = threading.Thread(target=monitor)
    thread.start()
    started = time.monotonic()
    try:
        topology = _topology(count, shape)
        result = ParallelismManager().execute_isolated_task(
            Task("capacity", _native_community_operation, (topology,)),
            timeout_seconds=120, max_rss_bytes=1024**3)
        members = [member for community in result["communities"] for member in community]
        assert len(members) == count
        assert set(members) == {row["id"] for row in topology["entities"]}
    finally:
        stop.set()
        thread.join()
    assert samples and any(child for _, child in samples)
    assert {child.pid for child in process.children(recursive=True)} <= baseline
    receipt = dict(nodes=count, edges=len(topology["relationships"]), shape=shape,
        seconds=time.monotonic() - started, parent_peak_rss=max(v[0] for v in samples),
        child_peak_rss=max(v[1] for v in samples), combined_peak_rss=max(sum(v) for v in samples),
        sample_interval_seconds=.01)
    (tmp_path / "capacity.json").write_text(json.dumps(receipt))
    print(json.dumps(receipt))


def test_native_community_cancels_after_handler_starts_and_reaps(tmp_path):
    marker = tmp_path / "started"
    cancellation = threading.Event()
    stop = threading.Event()
    baseline = {child.pid for child in psutil.Process().children(recursive=True)}
    observed = []

    def cancel_started():
        while not stop.wait(.01):
            if marker.exists():
                observed.append(time.monotonic())
                cancellation.set()
                return

    thread = threading.Thread(target=cancel_started)
    thread.start()
    try:
        with pytest.raises(ProcessingError) as caught:
            ParallelismManager().execute_isolated_task(Task("native-cancel", _marked_community,
                (_topology(4096, "hub"), str(marker))), timeout_seconds=120,
                max_rss_bytes=1024**3, cancellation=cancellation)
        assert caught.value.processing_context["reason"] == "cancelled"
        assert observed
        assert time.monotonic() - observed[0] < 1
    finally:
        stop.set()
        thread.join()
    assert {child.pid for child in psutil.Process().children(recursive=True)} <= baseline
