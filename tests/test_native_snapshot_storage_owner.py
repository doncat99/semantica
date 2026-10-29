"""Appending stored observations must not load the source-build pipeline."""
import builtins
from copy import deepcopy

from semantica.graph_store import GraphStore
from semantica.semantic_artifact_schema import SemanticArtifact
from tests.test_native_persistent_center import snapshot


def test_append_is_builder_independent_and_preserves_cas_retry(monkeypatch):
    store = object.__new__(GraphStore)
    state = {"head": SemanticArtifact.model_validate(snapshot("scope")), "attempts": 0}
    def commit(value):
        state["attempts"] += 1
        if state["attempts"] == 1:
            raise ValueError("stale_snapshot_head")
        state["head"] = value
        return {"snapshot_id": value.id}
    store.read_snapshot = lambda *args: state["head"]
    store.commit_snapshot = commit
    incoming = deepcopy(snapshot("scope", "observation:new"))
    incoming["entities"].append({"id": "new", "canonical_name": "New", "type": "Company"})
    original = builtins.__import__
    def import_without_builder(name, *args, **kwargs):
        if name.endswith("semantic_artifact_builder"):
            raise AssertionError("storage cannot import artifact builder")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_without_builder)
    result = store.append_snapshot(incoming)
    assert result["snapshot_id"] == state["head"].id
    assert state["attempts"] == 2
    assert {item.id for item in state["head"].entities} == {"company:one", "new"}
    identifier = state["head"].id
    store.append_snapshot(incoming)
    assert state["head"].id == identifier
