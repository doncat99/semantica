"""Exact topology oracle and allocation evidence; not a total build budget."""
import gc
import itertools
import json
import tracemalloc

from semantica.kg import _graph_view
from semantica.kg.community_detector import CommunityDetector


def test_conversion_does_not_materialize_intermediate_graph_view(monkeypatch):
    import semantica.kg.community_detector as owner

    def forbidden(*args, **kwargs):
        raise AssertionError("conversion retained a complete intermediate GraphView")

    monkeypatch.setattr(owner, "build_graph_view", forbidden)
    graph = CommunityDetector()._to_networkx({
        "entities": [{"id": "isolate"}],
        "relationships": [("a", "b"), ("b", "a"), ("b", "b")],
    })
    assert list(graph.nodes) == ["isolate", "a", "b"]
    assert list(graph.edges) == [("a", "b"), ("b", "b")]


def _previous_graph_view_topology(detector, graph):
    view = _graph_view.build_graph_view(graph)
    result = detector.nx.Graph()
    result.add_nodes_from(view.nodes)
    result.add_edges_from(view.edges)
    return result


def _assert_topology_and_result_equal(detector, graph):
    current = detector._to_networkx(graph)
    proposed = _previous_graph_view_topology(detector, graph)
    assert list(current.nodes) == list(proposed.nodes)
    assert list(current.edges) == list(proposed.edges)
    assert detector.detect_communities(current, algorithm="greedy_modularity") == (
        detector.detect_communities(proposed, algorithm="greedy_modularity")
    )


def test_all_four_node_simple_graphs_preserve_full_greedy_result():
    detector = CommunityDetector()
    pairs = list(itertools.combinations(range(4), 2))
    for included in itertools.product((False, True), repeat=len(pairs)):
        graph = {
            "entities": [{"id": str(index)} for index in range(4)],
            "relationships": [
                {"source": str(source), "target": str(target)}
                for (source, target), keep in zip(pairs, included) if keep
            ],
        }
        _assert_topology_and_result_equal(detector, graph)


def test_topology_characterization_includes_normalization_and_edge_order():
    detector = CommunityDetector()
    graph = {
        "entities": [{"id": "isolated"}, {"id": "a"}, {"id": ""}, {"id": None}],
        "nodes": ["b", "a"],
        "relationships": [
            {"source": "a", "target": "b", "metadata": {"body": "ignored"}},
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
            {"source": "b", "target": "b"},
            {"source": "implicit", "target": "a"},
            {"source": "", "target": "not-admitted"},
            ({"id": ""}, {"id": "admitted-isolate"}),
            {"invalid": "record"},
            ("x", "y"),
        ],
    }
    _assert_topology_and_result_equal(detector, graph)
    existing = detector._to_networkx(graph)
    assert detector._to_networkx(existing) is existing


def _peak(operation):
    gc.collect()
    tracemalloc.start()
    try:
        result = operation()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, {"current_bytes": current, "peak_bytes": peak}


def test_report_conversion_allocation_without_production_budget(record_property):
    detector = CommunityDetector()
    report = {"networkx": detector.nx.__version__, "conversion": []}
    for count in (4096, 16384):
        graph = {
            "entities": [{"id": str(index)} for index in range(count + 1)],
            "relationships": [
                {"source": str(index), "target": str(index + 1)}
                for index in range(count)
            ],
        }
        current, baseline = _peak(lambda: detector._to_networkx(graph))
        proposed, previous = _peak(lambda: _previous_graph_view_topology(detector, graph))
        assert list(current.nodes) == list(proposed.nodes)
        assert list(current.edges) == list(proposed.edges)
        report["conversion"].append({
            "nodes": count + 1, "edges": count,
            "direct": baseline, "previous_graph_view": previous,
        })
    encoded = json.dumps(report, sort_keys=True)
    record_property("topology_conversion_allocation", encoded)
    print(encoded)
