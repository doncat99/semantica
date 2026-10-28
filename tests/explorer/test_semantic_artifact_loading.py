import json

from semantica.explorer.session import GraphSession


def test_explorer_loads_native_semantic_artifact_relations(tmp_path):
    path = tmp_path / "semantic-graph.json"
    path.write_text(json.dumps({
        "entities": [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}],
        "relations": [{"id": "r", "source_entity_id": "a", "target_entity_id": "b", "type": "supports"}],
    }))
    session = GraphSession.from_file(str(path))
    assert session.get_stats()["node_count"] == 2
    assert session.get_stats()["edge_count"] == 1
    assert session.graph.find_edges()[0]["id"] == "r"
