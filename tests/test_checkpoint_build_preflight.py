import json
from pathlib import Path

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, _bytes
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


@pytest.mark.parametrize('paid', [False, True])
@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('entrypoint', ['worker', 'builder'])
def test_worker_upgrades_legacy_imports_before_build_without_network(tmp_path, monkeypatch, paid, nested, entrypoint):
    from semantica import semantic_artifact_builder as builder
    from semantica.semantic_worker import handle_request
    source = tmp_path / 'source.txt'
    source.write_text('Saved material')
    raw = _request(source, tmp_path / 'work')
    request = SemanticArtifactBuildRequest.model_validate(raw['params'])
    original = SnapshotCheckpoint(request)
    if paid:
        original.write('completed', 'paid', {'result': 'preserved'})
    target = tmp_path / 'dataset' / 'imports' / 'old'
    if nested:
        target = target / 'imports' / 'previous'
    target.parent.mkdir(parents=True)
    original.root.rename(target)
    manifest = json.loads((target / 'manifest.json').read_bytes())
    manifest.pop('entryIdentity')
    (target / 'manifest.json').write_bytes(_bytes(manifest))
    raw['params']['checkpointDir'] = str(tmp_path / 'dataset' / 'checkpoint')
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('preflight used network'))
    class StopAfterCheckpoint(Exception):
        pass
    def build(request, **kwargs):
        restored = SnapshotCheckpoint(request)
        if paid:
            assert restored.read('completed', 'paid') == {'result': 'preserved'}
        assert not target.exists()
        raise StopAfterCheckpoint
    monkeypatch.setattr(builder, '_build_semantic_artifacts', build)
    for _ in range(2):
        with pytest.raises(StopAfterCheckpoint):
            if entrypoint == 'worker':
                handle_request(raw)
            else:
                builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(raw['params']))


def test_checkpoint_failure_is_a_typed_recovery_error():
    from semantica.project_checkpoint import SnapshotCheckpointError
    from semantica.semantic_worker import _response
    error = _response('build', False, error=SnapshotCheckpointError('saved payload digest mismatch'))['error']
    assert error['code'] == 'COMPLETED_WORK_RECOVERY_GAP'
    assert error['diagnostic']['code'] == 'COMPLETED_WORK_RECOVERY_GAP'
    assert 'saved payload digest mismatch' in error['message']


@pytest.mark.parametrize('legacy', [False, True])
def test_preflight_ignores_unpublished_atomic_writes(tmp_path, legacy):
    from semantica.project_checkpoint_upgrade import prepare_project_checkpoints
    source = tmp_path / 'source.txt'
    source.write_text('Saved material')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'work')['params'])
    original = SnapshotCheckpoint(request)
    original.write('completed', 'paid', {'result': 'preserved'})
    if legacy:
        manifest_path = original.root / 'manifest.json'
        manifest = json.loads(manifest_path.read_bytes())
        manifest.pop('entryIdentity')
        manifest_path.write_bytes(_bytes(manifest))
    (original.root / '.pending-interrupted').write_bytes(b'incomplete JSON')
    restored = prepare_project_checkpoints(request)
    assert restored.read('completed', 'paid') == {'result': 'preserved'}


@pytest.mark.parametrize('defect', [None, 'digest', 'foreign-project', 'conflict'])
def test_preflight_converts_original_document_locators_atomically(tmp_path, defect):
    from copy import deepcopy
    from semantica.project_checkpoint import _digest, SnapshotCheckpointError
    from semantica.project_checkpoint_upgrade import prepare_project_checkpoints, _locator
    source = tmp_path / 'source.txt'
    source.write_text('Already parsed content')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'work')['params'])
    request.checkpoint_dir = str(tmp_path / 'dataset' / 'checkpoint')
    original = SnapshotCheckpoint(request)
    manifest = json.loads((original.root / 'manifest.json').read_bytes())
    inputs = deepcopy(manifest['provenance'])
    inputs.update(inputs.pop('provenance'))
    if defect == 'foreign-project':
        inputs['projectId'] = 'foreign'
    manifest.update(inputs=inputs, fence=_digest(_bytes(inputs)))
    manifest.pop('entryIdentity')
    key = {'sourceId': request.sources[0].source_id, 'contentHash': request.sources[0].material_revision,
           'forceOcr': False, 'documentProcessing': inputs['documentProcessing']}
    payload = ['Already parsed content', {'text': 'Already parsed content',
        'content_hash': request.sources[0].material_revision, 'mime_type': 'text/plain'},
        'original', request.sources[0].material_revision, 'text', '1']
    entry = {'fence': manifest['fence'], 'payload': payload, 'digest': _digest(_bytes(payload))}
    if defect == 'digest':
        entry['payload'][2] = 'tampered'
    carrier = original.root.parent / 'imports' / 'old'
    carrier.mkdir(parents=True)
    (carrier / 'manifest.json').write_bytes(_bytes(manifest))
    (carrier / _locator('document', key)).write_bytes(_bytes(entry))
    canonical = {k:v for k,v in key.items() if k != 'documentProcessing'}
    if defect == 'conflict':
        original.write('document', canonical, [*payload[:2], 'different', *payload[3:]])
    before = {str(p):p.read_bytes() for p in original.root.parent.rglob('*.json')}
    if defect:
        with pytest.raises(SnapshotCheckpointError, match='digest|different project|conflicting'):
            prepare_project_checkpoints(request)
        assert {str(p):p.read_bytes() for p in original.root.parent.rglob('*.json')} == before
    else:
        prepare_project_checkpoints(request)
        restored = SnapshotCheckpoint(request)
        assert restored.read('document', canonical) == payload
        assert not carrier.exists()
        before = {str(p):p.read_bytes() for p in restored.root.iterdir()}
        prepare_project_checkpoints(request)
        assert {str(p):p.read_bytes() for p in restored.root.iterdir()} == before
