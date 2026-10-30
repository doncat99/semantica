"""Knowledge publication references the admitted parser output without copying it."""
import json
from pathlib import Path

from semantica.semantic_worker import handle_request
from tests.test_semantic_artifact import _request


def test_worker_references_parsed_source_without_another_document(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada designed the Engine.", encoding="utf-8")
    request = _request(source, tmp_path / "output")
    parsed = request["params"]["parsedSources"][0]
    result = handle_request(request)["result"]
    representation = next(item for item in result["artifacts"] if item["kind"] == "document-representation")
    assert representation["path"] == parsed["artifactPath"]
    assert representation["digest"] == parsed["artifactDigest"]
    graph = json.loads(Path(next(item["path"] for item in result["artifacts"] if item["kind"] == "semantic-graph")).read_bytes())
    metadata = graph["document_representations"][0]["metadata"]
    assert "document" not in metadata
    document = json.loads(Path(parsed["artifactPath"]).read_bytes())["document"]
    assert metadata["document_format"] == document["format"]
    assert graph["artifact_manifest"][0]["artifact_hash"] == parsed["artifactDigest"]
    assert not list((tmp_path / "output").glob("representation-*.json"))
