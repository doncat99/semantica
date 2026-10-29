from fastapi.testclient import TestClient

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.session import GraphSession


def test_record_decision_survives_session_restart_without_overwriting_input(tmp_path):
    path = tmp_path / "graph.json"
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("source", "document", content="Source report")
    graph.save_to_file(path)
    original = path.read_bytes()
    with TestClient(create_app(session=GraphSession.from_file(str(path)))) as client:
        response = client.post("/api/decisions", json={
            "category": "research", "scenario": "Review evidence",
            "reasoning": "The source supports this conclusion", "outcome": "accepted",
            "confidence": 0.8, "entities": ["source"],
        })
        assert response.status_code == 201, response.text
        decision_id = response.json()["decision_id"]
    assert path.read_bytes() == original
    with TestClient(create_app(session=GraphSession.from_file(str(path)))) as client:
        decisions = client.get("/api/decisions").json()
        assert decisions[0]["decision_id"] == decision_id
        assert decisions[0]["reasoning"] == "The source supports this conclusion"


def test_reasoning_facts_are_current_graph_ids():
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("a", "entity", content="Alpha")
    graph.add_node("b", "entity", content="Beta")
    graph.add_edge("a", "b", edge_type="supports")
    with TestClient(create_app(session=GraphSession(graph))) as client:
        response = client.get("/api/reason/facts")
        assert response.status_code == 200
        assert response.json()["facts"] == ["supports(a, b)"]
