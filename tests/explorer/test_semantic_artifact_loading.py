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


def test_explorer_uses_native_canonical_names_without_changing_identity(tmp_path):
    path = tmp_path / "semantic-graph.json"
    path.write_text(json.dumps({
        "entities": [
            {"id": "mention:a", "canonical_name": "Sustainability Accounting Standards Board", "type": "ORG"},
            {"id": "mention:b", "canonical_name": "Christmas", "type": "EVENT"},
        ],
        "relations": [{"id": "r", "source_entity_id": "mention:a", "target_entity_id": "mention:b", "type": "mentions"}],
    }))
    session = GraphSession.from_file(str(path))
    assert session.graph.nodes["mention:a"].content == "Sustainability Accounting Standards Board"
    assert session.graph.nodes["mention:b"].content == "Christmas"
    assert set(session.graph.nodes) == {"mention:a", "mention:b"}
    assert session.get_stats()["edge_count"] == 1


def test_canonical_name_preserves_explicit_content_and_existing_name_inputs():
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph(advanced_analytics=False)
    graph.add_nodes([
        {"id": "explicit", "content": "Display content", "canonical_name": "Canonical"},
        {"id": "native", "canonical_name": "Canonical"},
        {"id": "demo", "name": "Alice"},
        {"id": "unnamed"},
    ])
    assert [node.content for node in graph.nodes.values()] == ["Display content", "Canonical", "Alice", "unnamed"]
