from types import SimpleNamespace

from semantica.core.orchestrator import Semantica


def test_extract_graph_sources_reads_pipeline_output_dict():
    sem = Semantica.__new__(Semantica)
    wrapped = {
        "success": True,
        "output": {
            "entities": [{"id": "e1", "name": "Entity 1"}],
            "relationships": [{"source": "e1", "target": "e1", "type": "self"}],
        },
    }

    assert sem._extract_graph_sources(wrapped) == [wrapped["output"]]


def test_extract_graph_sources_reads_execution_result_output_list():
    sem = Semantica.__new__(Semantica)
    wrapped = SimpleNamespace(
        output=[
            {"entities": [{"id": "a"}], "relationships": []},
            {"output": {"entities": [{"id": "b"}], "relationships": []}},
        ]
    )

    sources = sem._extract_graph_sources(wrapped)

    assert [source["entities"][0]["id"] for source in sources] == ["a", "b"]
