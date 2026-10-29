"""Durable task transitions must preserve accepted-result immutability."""
from copy import deepcopy

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, _bytes, _digest
from semantica.project_checkpoint_upgrade import canonicalize_checkpoint, _locator


@pytest.mark.parametrize('phase', ['submitting', 'running', 'complete'])
def test_legacy_remote_task_requires_offline_conversion(phase, tmp_path):
    inputs = {'projectId': 'p', 'sources': []}
    manifest = {'inputs': inputs, 'fence': _digest(_bytes(inputs)),
                'createdAt': '2026-10-29T00:00:00', 'entryIdentity': 'business-content-v1'}
    key = {'contentHash': 'a' * 64, 'name': 'source.pdf', 'forceOcr': False,
           'profile': {'endpoint': 'https://docling.test'}}
    payload = {'phase': phase, 'remoteCancellation': 'unsupported'}
    if phase != 'submitting':
        payload['taskId'] = 'task-1'
    if phase == 'complete':
        payload['result'] = {'status': 'success', 'document': {
            'json_content': {}, 'text_content': 'evidence', 'doctags_content': '<text>evidence</text>'}}
    entry = {'key': key, 'fence': manifest['fence'], 'payload': payload, 'digest': _digest(_bytes(payload))}
    name = _locator('remote-docling', key)
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    owner.fence = manifest['fence']
    with pytest.raises(ValueError, match='offline.*migration'):
        owner._import_entry(name, entry, manifest['fence'])
    original = deepcopy((manifest, entry))
    converted, entries = canonicalize_checkpoint(manifest, {name: entry})
    assert (manifest, entry) == original
    kinds = ['remote-docling-submission']
    if phase != 'submitting':
        kinds.append('remote-docling-task')
    if phase == 'complete':
        kinds.append('remote-docling-result')
    assert set(entries) == {_locator(kind, key) for kind in kinds}
    for name, value in entries.items():
        owner.fence = converted['fence']
        owner._import_entry(name, value, converted['fence'])
    owner._initialize(tmp_path, [], converted['inputs'])
    owner._install(converted, entries)
    owner._initialize(tmp_path, [], converted['inputs'])
    assert owner.read('remote-docling-submission', key)['phase'] == 'submitting'
    if phase != 'submitting':
        assert owner.read('remote-docling-task', key)['taskId'] == 'task-1'
    if phase == 'complete':
        assert owner.read('remote-docling-result', key)['result'] == payload['result']


def test_invalid_legacy_remote_result_is_not_admitted():
    inputs = {'projectId': 'p', 'sources': []}
    manifest = {'inputs': inputs, 'fence': _digest(_bytes(inputs)), 'createdAt': '2026-10-29T00:00:00'}
    key = {'name': 'source.pdf'}
    payload = {'phase': 'complete', 'taskId': 'task-1', 'result': {'status': 'partial_success'}}
    entry = {'key': key, 'fence': manifest['fence'], 'payload': payload, 'digest': _digest(_bytes(payload))}
    with pytest.raises(ValueError, match='not a successful'):
        canonicalize_checkpoint(manifest, {_locator('remote-docling', key): entry})
