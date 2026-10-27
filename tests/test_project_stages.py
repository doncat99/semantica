import json
import os
import subprocess
import sys
import threading

import pytest

from semantica import semantic_artifact_builder as builder
from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError, active_checkpoint
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


@pytest.mark.parametrize('interrupted_owner,completed', [
    ('reconcile_qualified_facts', ['entity_resolution']),
    ('_semantic_organization', ['entity_resolution', 'fact_reconciliation']),
    ('_write_json', ['entity_resolution', 'fact_reconciliation', 'semantic_organization']),
])
def test_restart_after_identity_reuses_completed_project_work(tmp_path, monkeypatch, interrupted_owner, completed):
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    params = _request(source, tmp_path / 'first', recipe='model')['params']
    # Model/embedding transport is covered by the existing checkpoint tests.
    monkeypatch.setattr(builder, '_extract_project_sources', lambda *args: [(None, [], [])])
    original = builder._resolve_native_entities
    calls = []
    def resolve(*args, **kwargs):
        calls.append('identity')
        return original(*args, **kwargs)
    monkeypatch.setattr(builder, '_resolve_native_entities', resolve)
    interrupted = getattr(builder, interrupted_owner)
    def interrupt(*args):
        if interrupted_owner == '_write_json' and args[0].name != 'retrieval.json':
            return interrupted(*args)
        raise RuntimeError('interrupted after identity')
    monkeypatch.setattr(builder, interrupted_owner, interrupt)
    events = []
    with pytest.raises(RuntimeError, match='interrupted'):
        builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(params), events.append)
    assert calls == ['identity']
    assert [e['stage'] for e in events if e.get('metadata', {}).get('state') == 'completed'
            and e['stage'] in ('entity_resolution', 'fact_reconciliation', 'semantic_organization')] == completed
    # A different process must use the saved identity result, even after a model/release switch.
    params['resumeCheckpointDirs'] = [str(tmp_path / 'first' / 'checkpoint')]
    params['outputDir'] = str(tmp_path / 'second')
    params['relays']['model']['modelId'] = 'model-2'
    params['release']['artifactDigest'] = 'sha256:' + 'f' * 64
    script = '''
import json, sys
from semantica import semantic_artifact_builder as b
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
b._extract_project_sources = lambda *args: [(None, [], [])]
def forbidden(*args, **kwargs):
    raise AssertionError('completed identity was recomputed')
for stage in json.loads(sys.argv[1]):
    setattr(b, {'entity_resolution': '_resolve_native_entities', 'fact_reconciliation': 'reconcile_qualified_facts',
                'semantic_organization': '_semantic_organization'}[stage], forbidden)
events = []
result = b.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(json.load(sys.stdin)), events.append)
assert result['snapshot'].entities
print(json.dumps(events))
'''
    run = subprocess.run([sys.executable, '-c', script, json.dumps(completed)], input=json.dumps(params), text=True,
                         capture_output=True, timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    assert run.returncode == 0, run.stderr
    resumed = json.loads(run.stdout.splitlines()[-1])
    restored = [e for e in resumed if e.get('metadata', {}).get('restored')]
    assert [e['stage'] for e in restored] == completed
    assert [e['stage'] for e in resumed if e.get('metadata', {}).get('state') == 'completed'
            and e['stage'] != 'source_projection'] == [
        'entity_resolution', 'fact_reconciliation', 'semantic_organization', 'artifact_writing']
    assert not any('sourceProgress' in e.get('metadata', {}) for e in restored)
    assert all(e['percent'] < 100 for e in resumed if e['stage'] == 'artifact_writing')


def test_project_stage_reuse_is_content_scoped_and_corruption_fails_closed(tmp_path):
    from pydantic import TypeAdapter
    source = tmp_path / 'source.txt'
    source.write_text('A source')
    params = _request(source, tmp_path / 'output')['params']
    request = SemanticArtifactBuildRequest.model_validate(params)
    token = active_checkpoint.set(SnapshotCheckpoint(request))
    calls = []
    def compute():
        calls.append(1)
        return ['result']
    adapter = TypeAdapter(list[str])
    try:
        for inputs in ({'mentions': ['a'], 'schema': {}}, {'mentions': ['a'], 'schema': {}},
                       {'mentions': ['b'], 'schema': {}}, {'mentions': ['a'], 'schema': {'key': True}}):
            assert builder._project_stage('entity_resolution', inputs, adapter, compute, None, 90) == ['result']
        assert len(calls) == 3
    finally:
        active_checkpoint.reset(token)
    # Business input changes must retain self-scoped completed units, not reject the dataset.
    source.write_text('Changed source')
    changed = _request(source, tmp_path / 'output')['params']
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(changed))
    assert len(list(checkpoint.root.glob('project-stage-*.json'))) == 3
    entry = next(checkpoint.root.glob('project-stage-*.json'))
    data = json.loads(entry.read_bytes())
    data['payload'] = ['tampered']
    entry.write_text(json.dumps(data))
    with pytest.raises(SnapshotCheckpointError):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(changed))


def test_project_stage_heartbeat_and_failure_do_not_claim_completion():
    entered = threading.Event()
    heartbeat = threading.Event()
    events = []
    def progress(event):
        events.append(event)
        if entered.is_set() and event['metadata']['state'] == 'running':
            heartbeat.set()
    with pytest.raises(RuntimeError, match='failed'):
        with builder._project_progress(progress, 'entity_resolution', 90):
            entered.set()
            assert heartbeat.wait(5), 'long native work must remain observable'
            raise RuntimeError('failed')
    assert events[-1]['metadata']['state'] == 'failed'
    assert not any(e['metadata']['state'] == 'completed' for e in events)
    assert events[-1]['metadata']['elapsedMs'] > 0
    assert all(e['percent'] == 90 for e in events)


def test_invalid_completed_stage_is_rejected_without_recomputation(tmp_path):
    from pydantic import TypeAdapter
    from semantica.semantic_artifact_schema import stable_digest
    source = tmp_path / 'source.txt'
    source.write_text('A source')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'output')['params'])
    checkpoint = SnapshotCheckpoint(request)
    inputs = {'mentions': ['a']}
    checkpoint.write('project-stage', {'stage': 'entity_resolution', 'inputsDigest': stable_digest(inputs)},
                     {'invalid': 'result with a valid content digest'})
    token = active_checkpoint.set(checkpoint)
    def forbidden():
        raise AssertionError('invalid data must not silently trigger recomputation')
    events = []
    try:
        with pytest.raises(SnapshotCheckpointError, match='invalid completed project stage'):
            builder._project_stage('entity_resolution', inputs, TypeAdapter(list[str]), forbidden, events.append, 90)
    finally:
        active_checkpoint.reset(token)
    assert events[-1]['metadata']['state'] == 'failed'
