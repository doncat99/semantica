"""Retired aggregate knowledge snapshots must have no executable public owner."""
import importlib

import pytest


@pytest.mark.parametrize('module,name', [
    ('semantica.change_management', 'TemporalVersionManager'),
    ('semantica.change_management.managers', 'TemporalVersionManager'),
    ('semantica.kg', 'TemporalVersionManager'),
    ('semantica.kg.temporal_query', 'TemporalVersionManager'),
])
def test_knowledge_snapshot_manager_is_removed(module, name):
    assert not hasattr(importlib.import_module(module), name)


def test_context_has_no_knowledge_checkpoint_api():
    from semantica.context.agent_context import AgentContext
    from semantica.context.context_graph import ContextGraph
    for name in ('checkpoint', 'diff_checkpoints', 'flush_checkpoint', '_capture_checkpoint_state'):
        assert not hasattr(AgentContext, name)
    assert not hasattr(ContextGraph, 'state_at')


def test_storage_rejects_aggregate_knowledge_payload(tmp_path):
    from semantica.change_management.version_storage import InMemoryVersionStorage, SQLiteVersionStorage
    from semantica.utils.exceptions import ValidationError
    payload = {'label': 'retired', 'nodes': [{'id': 'secret', 'content': 'knowledge'}], 'edges': []}
    for storage in (InMemoryVersionStorage(), SQLiteVersionStorage(str(tmp_path / 'ontology.sqlite'))):
        with pytest.raises(ValidationError):
            storage.save(payload)
        assert storage.get('retired') is None


def test_storage_rejects_retired_persisted_knowledge_rows(tmp_path):
    import json
    import sqlite3
    from semantica.change_management.version_storage import InMemoryVersionStorage, SQLiteVersionStorage
    from semantica.utils.exceptions import ValidationError

    payload = {'label': 'retired', 'nodes': [{'id': 'secret'}], 'edges': []}
    memory = InMemoryVersionStorage()
    memory._storage['retired'] = payload
    persistent = SQLiteVersionStorage(str(tmp_path / 'retired.sqlite'))
    with sqlite3.connect(persistent.storage_path) as conn:
        conn.execute(
            'INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?)',
            ('retired', '', '', '', '', json.dumps(payload), ''),
        )
    for storage in (memory, persistent):
        with pytest.raises(ValidationError):
            storage.get('retired')
        with pytest.raises(ValidationError):
            storage.list_all()
        # Offline cleanup can still physically remove the rejected old row.
        assert storage.delete('retired')
        assert not storage.exists('retired')


def test_ontology_revision_survives_restart_with_checksum(tmp_path):
    from semantica.change_management import OntologyVersionManager

    path = str(tmp_path / 'ontology.sqlite')
    manager = OntologyVersionManager(storage_path=path)
    revision = manager.create_snapshot(
        {'uri': 'https://example.org/ontology', 'structure': {'classes': ['Company']}},
        'initial', 'editor@example.org', 'Initial ontology',
    )
    restarted = OntologyVersionManager(storage_path=path)
    assert restarted.get_version('initial') == revision
    assert restarted.verify_checksum(restarted.get_version('initial'))
