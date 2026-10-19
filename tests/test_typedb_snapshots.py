"""Real TypeDB transaction tests; only a disposable test database is created."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from semantica.graph_store.graph_store import GraphStore
from semantica.semantic_artifact_schema import SemanticArtifact, stable_digest


def artifact(sid='snapshot-1', scope='scope-1', base=None):
    digest = stable_digest({})
    return SemanticArtifact(snapshot_id=sid, project_id=scope, base_snapshot_id=base,
        lineage=dict(schema_digest=digest, recipe_id='test-recipe', recipe_digest=digest,
                     rule_version='test-1', rule_digest=digest,
                     ontology_version='test-1', ontology_digest=digest),
        artifact_manifest=[], document_representations=[], evidence_spans=[],
        entities=[dict(id='person-1', canonical_name='Original author', type='Person')])


@pytest.fixture
def store():
    address = os.environ.get('SEMANTICA_TEST_TYPEDB_ADDRESS')
    if not address:
        pytest.skip('SEMANTICA_TEST_TYPEDB_ADDRESS must point at disposable TypeDB')
    from typedb.driver import Credentials, DriverOptions, DriverTlsConfig, TypeDB
    driver = TypeDB.driver(address, Credentials('admin', 'password'),
                          DriverOptions(DriverTlsConfig.disabled()))
    database = 'semantica_snapshot_test_' + uuid4().hex
    driver.databases.create(database)
    store = GraphStore(backend='typedb', driver=driver, database=database)
    store.initialize_snapshot_storage()
    yield store
    # TypeDB 3.13 may panic deleting databases with draining query-cache refs.
    # The disposable acceptance container owns cleanup, never a production DB.
    driver.close()


def test_restart_replay_scope_and_immutable_history(store):
    first = artifact()
    assert store.read_snapshot('scope-1') is None
    receipt = store.commit_snapshot(first)
    assert not receipt['replayed']
    assert store.commit_snapshot(first)['replayed']
    assert store.read_snapshot('scope-2', first.id) is None
    store.initialize_snapshot_storage()
    restarted = GraphStore(backend='typedb', driver=store._store_backend.driver,
                           database=store._store_backend.database)
    assert restarted.read_snapshot('scope-1') == first
    second = artifact('snapshot-2', base=first.id)
    assert restarted.commit_snapshot(second)['head_snapshot_id'] == second.id
    assert restarted.read_snapshot('scope-1', first.id) == first
    assert restarted.commit_snapshot(first)['head_snapshot_id'] == second.id
    assert restarted.read_snapshot('scope-1') == second
    with pytest.raises(Exception, match='immutable_snapshot_id_reused'):
        store.commit_snapshot(first.model_copy(update={'metadata': {'changed': True}}))
    with pytest.raises(Exception, match='stale_snapshot_head'):
        store.commit_snapshot(artifact('stale-1', base=first.id))
    assert restarted.read_snapshot('scope-1') == second
    store.close()
    assert restarted.read_snapshot('scope-1') == second  # driver remains host-owned


def test_concurrent_writers_cannot_both_advance_same_base(store):
    first = artifact()
    store.commit_snapshot(first)

    def commit(sid):
        try:
            return store.commit_snapshot(artifact(sid, base=first.id))
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, ['snapshot-a', 'snapshot-b']))
    assert sum(isinstance(r, dict) for r in results) == 1, results
    winner = next(r['snapshot_id'] for r in results if isinstance(r, dict))
    assert store.read_snapshot('scope-1').id == winner
    loser = 'snapshot-a' if winner == 'snapshot-b' else 'snapshot-b'
    assert store.read_snapshot('scope-1', loser) is None


def test_rollback_preserves_head_and_records(store, monkeypatch):
    first = artifact()
    store.commit_snapshot(first)
    import semantica.graph_store.typedb_store as module
    original = module._json

    def fail(value):
        if value == 'entities':
            raise RuntimeError('injected-mid-transaction')
        return original(value)

    with monkeypatch.context() as patch:
        patch.setattr(module, '_json', fail)
        with pytest.raises(RuntimeError, match='injected-mid-transaction'):
            store.commit_snapshot(artifact('snapshot-2', base=first.id))
    assert store.read_snapshot('scope-1') == first
    assert store.read_snapshot('scope-1', 'snapshot-2') is None


def test_validation_and_unsupported_operations_fail_closed(store):
    with pytest.raises(Exception):
        store.commit_snapshot({'snapshot_id': 'invalid'})
    with pytest.raises(NotImplementedError, match='not Cypher'):
        store.execute_query('CREATE (n)')
    assert store.read_snapshot('scope-1') is None
