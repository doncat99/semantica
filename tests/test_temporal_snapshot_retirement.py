"""Aggregate temporal graph copies have no remaining public entry point."""
from pathlib import Path

from click.testing import CliRunner


def test_graph_builder_has_no_snapshot_or_fake_query():
    from semantica.kg.graph_builder import GraphBuilder
    assert not hasattr(GraphBuilder, 'create_temporal_snapshot')
    assert not hasattr(GraphBuilder, 'query_temporal')


def test_cli_has_no_temporal_snapshot_command():
    from semantica.cli import main
    result = CliRunner().invoke(main, ['temporal', 'snapshot', '--at', '2026-01-01'])
    assert result.exit_code != 0
    assert "No such command 'snapshot'" in result.output


def test_retired_temporal_graph_schema_is_absent():
    import semantica.kg
    assert not (Path(semantica.kg.__file__).parent / 'schemas' / 'temporal_snapshot_v1.json').exists()


def test_rdf_exporter_has_no_retired_graph_snapshot_term():
    from semantica.export.rdf_exporter import DEFAULT_METADATA_TERMS
    assert 'snapshot_time' not in DEFAULT_METADATA_TERMS


def test_temporal_reasoning_exposes_only_live_closure():
    from semantica import reasoning
    from semantica.reasoning.temporal_truth_maintenance import TemporalTruthMaintenanceAdapter

    assert not hasattr(reasoning, 'TemporalFactSnapshot')
    assert not hasattr(TemporalTruthMaintenanceAdapter, 'query_at')


def test_temporal_visualization_does_not_consume_full_graph_snapshots():
    from semantica.visualization.temporal_visualizer import TemporalVisualizer

    assert not hasattr(TemporalVisualizer, 'visualize_snapshot_comparison')


def test_graph_builder_has_no_snapshot_config():
    import inspect
    from semantica.kg.graph_builder import GraphBuilder
    assert 'version_snapshots' not in inspect.signature(GraphBuilder).parameters
    assert not hasattr(GraphBuilder(resolve_conflicts=False), 'version_snapshots')


def test_temporal_query_has_no_full_graph_point_in_time_apis():
    from semantica.kg.temporal_query import TemporalGraphQuery
    assert not hasattr(TemporalGraphQuery, 'reconstruct_at_time')
    assert not hasattr(TemporalGraphQuery, 'query_at_time')


def test_cli_has_no_full_graph_temporal_query():
    from semantica.cli import main
    result = CliRunner().invoke(main, ['temporal', 'query', 'ignored'])
    assert result.exit_code != 0
    assert "No such command 'query'" in result.output


def test_temporal_wrapper_rejects_retired_time_point_dispatch():
    import pytest
    from semantica.kg.methods import query_temporal
    from semantica.utils.exceptions import ProcessingError
    with pytest.raises(ProcessingError, match='Unknown temporal query method: time_point'):
        query_temporal({}, method='time_point', at_time='2024-01-01')


def test_temporal_wrapper_keeps_native_range_semantics():
    from semantica.kg.methods import query_temporal
    relationship = {'id': 'r', 'valid_from': '2024-01-01', 'valid_until': '2025-01-01'}
    result = query_temporal({'relationships': [relationship]}, start_time='2024-02-01', end_time='2024-03-01')
    assert result['relationships'] == [relationship]


def test_temporal_registered_method_failure_has_no_fallback(monkeypatch):
    import pytest
    from semantica.kg import methods
    error = RuntimeError('native owner unavailable')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(methods.method_registry, 'get', lambda *args: fail)
    with pytest.raises(RuntimeError) as caught:
        methods.query_temporal({}, method='custom')
    assert caught.value is error
