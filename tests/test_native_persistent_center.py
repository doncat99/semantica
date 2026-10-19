"""Native contract tests; integration uses an explicitly isolated Neo4j URI."""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest

from semantica.context.decision_models import Policy
from semantica.context.policy_engine import PolicyEngine
from semantica.graph_store import GraphStore


def snapshot(scope, identifier="snapshot:one", base=None):
    digest = "sha256:" + "1" * 64
    return {"snapshot_id": identifier, "project_id": scope, "base_snapshot_id": base,
            "created_at": "2026-10-19T00:00:00Z", "artifact_manifest": [],
            "document_representations": [], "evidence_spans": [],
            "entities": [{"id": "company:one", "canonical_name": "Example", "type": "Company"}],
            "lineage": {"schema_digest": digest, "recipe_id": "native-test",
                        "recipe_digest": digest, "rule_version": "1", "rule_digest": digest,
                        "ontology_version": "1", "ontology_digest": digest}}


@pytest.fixture
def store():
    uri = os.environ.get("SEMANTICA_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("explicit isolated Neo4j URI required")
    graph = GraphStore(backend="neo4j", uri=uri, user="neo4j", password="test")
    graph.connect()
    graph.initialize_snapshot_storage()
    yield graph
    graph.close()


@pytest.fixture
def scope(store):
    value = "contract-test:" + uuid4().hex
    yield value
    store.execute_query("MATCH (n) WHERE n.scope_id=$scope DETACH DELETE n", {"scope": value})


def test_snapshot_restart_replay_and_immutable_ids(store, scope):
    first = snapshot(scope)
    store.commit_snapshot(first)
    loaded = store.read_snapshot(scope)
    assert loaded.entities[0].canonical_name == "Example"
    second = snapshot(scope, "snapshot:two", "snapshot:one")
    store.commit_snapshot(second)
    assert store.commit_snapshot(first)["head_snapshot_id"] == "snapshot:two"
    changed = copy.deepcopy(first)
    changed["entities"][0]["canonical_name"] = "Changed"
    with pytest.raises(ValueError, match="immutable_snapshot_id_reused"):
        store.commit_snapshot(changed)
    with pytest.raises(ValueError, match="stale_snapshot_head"):
        store.commit_snapshot(snapshot(scope, "snapshot:stale"))
    # A new driver instance must not depend on process-local ID/cache state.
    reopened = GraphStore(backend="neo4j", uri=os.environ["SEMANTICA_TEST_NEO4J_URI"],
                          user="neo4j", password="test")
    reopened.connect()
    try:
        assert reopened.read_snapshot(scope).id == "snapshot:two"
        assert reopened.read_snapshot(scope, "snapshot:one").id == "snapshot:one"
        assert reopened.read_snapshot(scope + ":other") is None
    finally:
        reopened.close()


def test_invalid_reference_rejected_before_commit(store, scope):
    invalid = snapshot(scope)
    invalid["entities"][0]["evidence_ids"] = ["missing"]
    with pytest.raises(ValueError):
        store.commit_snapshot(invalid)
    assert store.read_snapshot(scope) is None


def test_archival_export_preserves_unsupported_contract_without_weakening_reads(store, scope):
    from semantica.semantic_artifact_schema import stable_digest

    original = snapshot(scope)
    original["experimental_section"] = [{"id": "archived-only", "value": 7}]
    # Simulate an artifact committed by a different schema version.
    store._store_backend.commit_snapshot(original)
    assert store.export_snapshot(scope) == original
    assert store.export_snapshot(scope, original['snapshot_id']) == original
    assert store.export_snapshot(scope + ':other') is None
    with pytest.raises(ValueError, match="experimental_section"):
        store.read_snapshot(scope)
    store.execute_query('MATCH (s:SemanticSnapshot {scope_id:$scope}) SET s.digest=$digest',
                        {'scope': scope, 'digest': stable_digest({})})
    with pytest.raises(Exception, match="semantic_snapshot_digest_mismatch"):
        store.export_snapshot(scope)


def test_two_writers_only_one_can_advance_base(store, scope):
    store.commit_snapshot(snapshot(scope))

    def commit(index):
        try:
            store.commit_snapshot(snapshot(scope, f"snapshot:concurrent-{index}", "snapshot:one"))
            return "committed"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(commit, range(2))) == ["committed", "stale_snapshot_head"]


def test_append_retries_concurrent_observations_and_replay_does_not_advance(store, scope):
    store.commit_snapshot(snapshot(scope))

    def append(index):
        data = snapshot(scope, f"observation:{index}")
        data['entities'].append({'id': f'entity:{index}', 'canonical_name': str(index), 'type': 'Company'})
        return store.append_snapshot(data)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(item['snapshot_id'] for item in executor.map(append, range(2)))
    head = store.read_snapshot(scope)
    assert {item.id for item in head.entities} == {'company:one', 'entity:0', 'entity:1'}
    assert append(0)['head_snapshot_id'] == head.id
    assert store.read_snapshot(scope) == head


def test_transaction_failure_does_not_advance_head(store, scope, monkeypatch):
    store.commit_snapshot(snapshot(scope))
    backend = store._store_backend
    original = backend.get_session

    class FailingTransaction:
        def __init__(self, transaction):
            self.transaction = transaction

        def run(self, query, **parameters):
            if "UNWIND $records" in query:
                raise RuntimeError("injected_record_failure")
            return self.transaction.run(query, **parameters)

    class Session:
        def __enter__(self):
            self.session = original()
            return self

        def __exit__(self, *args):
            self.session.close()

        def write_transaction(self, callback, *args):
            return self.session.write_transaction(lambda tx: callback(FailingTransaction(tx), *args))

    with monkeypatch.context() as context:
        context.setattr(backend, "get_session", Session)
        with pytest.raises(RuntimeError, match="injected_record_failure"):
            store.commit_snapshot(snapshot(scope, "snapshot:failed", "snapshot:one"))
    assert store.read_snapshot(scope).id == "snapshot:one"
    assert store.read_snapshot(scope, "snapshot:failed") is None
    assert store.commit_snapshot(snapshot(scope, "snapshot:failed", "snapshot:one"))["head_snapshot_id"] == "snapshot:failed"


def test_large_snapshot_stages_in_bounded_transactions(store, scope):
    data = snapshot(scope)
    data['entities'] = [{'id': f'entity:{i}', 'canonical_name': f'Entity {i}', 'type': 'Company'}
                        for i in range(1200)]
    receipt = store.commit_snapshot(data)
    assert receipt['head_snapshot_id'] == data['snapshot_id']
    assert len(store.read_snapshot(scope).entities) == 1200


def test_policy_actual_native_envelope_round_trip(store):
    identifier = "policy-test:" + uuid4().hex
    engine = PolicyEngine(store)
    now = datetime.now()
    policy = Policy(policy_id=identifier, name="Test", description="Native contract",
                    rules={"min_confidence": .8}, category="test", version="1.0",
                    created_at=now, updated_at=now, metadata={"nested": {"scope": "test"}})
    try:
        engine.add_policy(policy)
        assert engine.get_policy(identifier).rules == policy.rules
        assert engine.get_policy(identifier).metadata == policy.metadata
        engine.update_policy(identifier, {"min_confidence": .9}, "tighten", "2.0")
        assert engine.get_policy(identifier).version == "2.0"
        assert len(engine.get_policy_history(identifier)) == 2
        assert engine.analyze_policy_impact(identifier, {"min_confidence": .95})["affected_decisions"] == 0
    finally:
        store.execute_query("MATCH (n:Policy {policy_id:$id}) DETACH DELETE n", {"id": identifier})
