"""Stable identity and one diff contract for graph and typed collections."""
import pytest

from semantica.change_management.managers import TemporalVersionManager
from semantica.utils.exceptions import ValidationError


def test_parallel_qualified_edges_are_compared_by_stable_identity():
    first = {"id": "fact:2024", "source": "issuer", "target": "emissions",
             "type": "reports", "year": 2024, "value": 12}
    second = {**first, "id": "fact:2025", "year": 2025}
    updated = {**first, "value": 10}
    before, after = [first, second], [updated, second]
    manager = TemporalVersionManager()
    detailed = manager.compare_versions({"nodes": [], "edges": before},
                                        {"nodes": [], "edges": after})
    typed = manager.compare_collections({"facts": before}, {"facts": after})
    assert typed == {"added_ids": [], "removed_ids": [], "updated_ids": [first["id"]]}
    assert len(detailed["edges_modified"]) == 1
    assert detailed["edges_modified"][0]["before"] == first
    assert detailed["edges_modified"][0]["after"] == updated


@pytest.mark.parametrize("collection", ["nodes", "edges"])
def test_graph_diff_rejects_duplicate_stable_ids(collection):
    duplicate = {"nodes": [], "edges": [], collection: [{"id": "same"}, {"id": "same"}]}
    with pytest.raises(ValidationError, match="duplicate IDs"):
        TemporalVersionManager().compare_versions(duplicate, {"nodes": [], "edges": []})


def test_new_version_stores_one_graph_representation_and_restores_after_restart(tmp_path):
    path = str(tmp_path / "versions.db")
    graph = {"entities": [{"id": "issuer"}], "relationships": []}
    TemporalVersionManager(path).create_snapshot(graph, "v1", "test@example.com", "fixture")
    restored = TemporalVersionManager(path).get_version("v1")
    assert restored["nodes"] == graph["entities"]
    assert "entities" not in restored and "relationships" not in restored
    assert TemporalVersionManager(path).verify_checksum(restored)


def test_historical_dual_representation_keeps_checksum_and_diff_after_restart(tmp_path):
    from semantica.change_management.version_storage import compute_checksum

    path = str(tmp_path / "versions.db")
    manager = TemporalVersionManager(path)
    old = {"label": "legacy", "nodes": [{"id": "issuer"}], "edges": [],
           "entities": [{"id": "issuer"}], "relationships": []}
    old["checksum"] = compute_checksum(old)
    manager.storage.save(old)
    restarted = TemporalVersionManager(path)
    restored = restarted.get_version("legacy")
    assert restored == old and restarted.verify_checksum(restored)
    current = restarted.create_snapshot({"nodes": old["nodes"], "edges": []},
                                        "current", "test@example.com", "same content")
    assert not any(restarted.compare_versions(restored, current)["summary"].values())
