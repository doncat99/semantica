"""The native pipeline owns real build stages, failure and ordering."""
import pytest

from semantica import semantic_artifact_builder as builder
from semantica.pipeline import ExecutionEngine, StepStatus
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


STAGES = ['prepare', 'parsed_inputs', 'extraction', 'source_projection',
          'source_classification', 'entity_resolution', 'fact_reconciliation',
          'semantic_organization', 'artifact_writing']


def test_build_executes_real_native_dependency_stages(tmp_path, monkeypatch):
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    captured = []
    execute = ExecutionEngine.execute_pipeline
    def observe(self, pipeline, *args, **kwargs):
        captured.append(pipeline)
        assert [step.name for step in pipeline.steps] == STAGES
        assert [step.dependencies for step in pipeline.steps] == [[], *[[name] for name in STAGES[:-1]]]
        assert len({step.handler for step in pipeline.steps}) == len(STAGES)
        assert self.failure_handler.default_max_retries == 0
        return execute(self, pipeline, *args, **kwargs)
    monkeypatch.setattr(ExecutionEngine, 'execute_pipeline', observe)
    result = builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / 'out')['params']))
    assert result['graph_path'] == tmp_path / 'out' / 'semantic-graph.json'
    assert result['graph_path'].is_file()
    assert not (tmp_path / 'out' / 'snapshot.json').exists()
    assert len(captured) == 1
    assert all(step.status == StepStatus.COMPLETED for step in captured[0].steps)


def test_stage_failure_preserves_cause_and_never_publishes_or_retries(tmp_path, monkeypatch):
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    captured, calls = [], []
    execute = ExecutionEngine.execute_pipeline
    def observe(self, pipeline, *args, **kwargs):
        captured.append(pipeline)
        return execute(self, pipeline, *args, **kwargs)
    failure = ValueError('organization rejected')
    def reject(*args):
        calls.append('organization')
        raise failure
    monkeypatch.setattr(ExecutionEngine, 'execute_pipeline', observe)
    monkeypatch.setattr(builder, '_semantic_organization', reject)
    with pytest.raises(ValueError) as error:
        builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
            _request(source, tmp_path / 'out')['params']))
    assert error.value is failure
    assert calls == ['organization']
    assert len(captured) == 1
    assert captured[0].steps[-2].status == StepStatus.FAILED
    assert captured[0].steps[-1].status == StepStatus.PENDING
    assert not (tmp_path / 'out' / 'semantic-graph.json').exists()
    assert not (tmp_path / 'out' / 'snapshot.json').exists()
