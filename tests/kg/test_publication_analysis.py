"""Publication analytics delegates only complete, bounded graphs to KG owners."""
import pytest

from tests.triplet_store.test_publication_records import topology_fixture


def test_persisted_publication_metrics_match_native_owners(tmp_path):
    from semantica.kg.publication_analysis import analyze_publication
    from semantica.kg.centrality_calculator import CentralityCalculator
    from semantica.kg.connectivity_analyzer import ConnectivityAnalyzer
    store, generation, _ = topology_fixture(tmp_path)
    try:
        result = analyze_publication(store, 'p', generation)
        nodes = store.read_publication_scene('p', generation, dict(kind='nodes', fields=['id'], limit=128))['nodes']
        links = store.read_publication_scene('p', generation, dict(kind='topology', fields=['id','source','target','predicate'], limit=128))['links']
        graph = dict(entities=nodes, relationships=[dict(link, type=link['predicate']) for link in links])
        assert result['status'] == 'ready'
        assert result['nodeCount'] == len(nodes)
        assert result['relationCount'] == len(links)
        assert result['metrics']['centrality'] == CentralityCalculator().calculate_degree_centrality(graph)
        assert result['metrics']['connectivity'] == ConnectivityAnalyzer().analyze_connectivity(graph)
        assert set(result['metrics']) == {'centrality','pagerank','community','connectivity','validation'}
    finally:
        store.close()


def test_budget_exhaustion_never_reports_partial_graph_metrics(tmp_path, monkeypatch):
    from semantica.kg.publication_analysis import analyze_publication
    from semantica.kg.centrality_calculator import CentralityCalculator
    store, generation, _ = topology_fixture(tmp_path)
    try:
        monkeypatch.setattr(CentralityCalculator, 'calculate_degree_centrality',
            lambda *a, **k: pytest.fail('partial graph reached analytics owner'))
        result = analyze_publication(store, 'p', generation, max_nodes=1)
        assert result['status'] == 'incomplete'
        assert result['metrics'] == {}
        assert result['nodeCount'] <= 1
        assert result['detail']
    finally:
        store.close()


def test_persisted_analysis_cancellation_stops_before_next_page(tmp_path, monkeypatch):
    from threading import Event
    from semantica.kg.publication_analysis import analyze_publication
    from semantica.semantic_worker_context import query_cancellation
    from semantica.utils.exceptions import ProcessingError
    store, generation, _ = topology_fixture(tmp_path)
    canceled = Event()
    token = query_cancellation.set(canceled)
    original = store.read_publication_scene
    calls = []
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(args)
        canceled.set()
        return result
    monkeypatch.setattr(store, 'read_publication_scene', read)
    try:
        with pytest.raises(ProcessingError, match='query canceled'):
            analyze_publication(store, 'p', generation)
        assert len(calls) == 1
    finally:
        query_cancellation.reset(token)
        store.close()


def test_page_envelope_cannot_overrun_analysis_byte_budget():
    from semantica.kg.publication_analysis import analyze_publication
    class Owner:
        def read_publication_scene(self, *args):
            return dict(nodes=[], links=[], next_cursor=None, project='p', generation='g')
    result = analyze_publication(Owner(), 'p', 'g', max_bytes=1)
    assert result['status'] == 'incomplete'
    assert result['projectionBytes'] <= 1
    assert result['metrics'] == {}
