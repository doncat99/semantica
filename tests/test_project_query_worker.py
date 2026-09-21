import io
import json
import pytest
from hashlib import sha256
from pathlib import Path

from semantica.project_query_worker import serve
from semantica.project_snapshot_pipeline import build_project_snapshot
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest


H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def _digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _build(tmp_path: Path, second_source=False):
    source = tmp_path / "source.txt"
    source.write_text(
        "Ada Lovelace designed the Analytical Engine. Charles Babbage worked with Ada Lovelace.",
        encoding="utf-8",
    )
    request = ProjectSnapshotBuildRequest.model_validate({
        "baseSnapshot": None,
        "inputRevision": H1,
        "outputDir": str(tmp_path),
        "projectId": "project-1",
        "recipe": {"forceOcrSourceIds": [], "id": "deterministic", "version": "1"},
        "relays": {
            "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.snapshot.embed", "modelId": "embedding-1", "receipts": "required"},
            "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.snapshot.generate", "modelId": "model-1", "receipts": "required"},
        },
        "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json", "retrieval-index": "application/vnd.semantica.retrieval+json", "snapshot": "application/vnd.semantica.project-snapshot+json"}},
        "sources": [{"filePath": str(source), "materialRevision": "material-1", "mimeType": "text/plain", "name": source.name, "sourceId": "source-1"}],
    })
    if second_source:
        source2 = tmp_path / "source2.txt"
        source2.write_text("Ada designed machines.", encoding="utf-8")
        request.sources.append(request.sources[0].model_copy(update={"file_path": str(source2), "source_id": "source-2", "name": source2.name}))
    return build_project_snapshot(request)


def _request(built, query="Ada"):
    return {
        "protocol": "semantica.project-query.v1",
        "id": "query-1",
        "method": "query",
        "params": {
            "projectId": built["snapshot"].project_id,
            "snapshotId": built["snapshot"].id,
            "snapshot": {
                "path": str(built["snapshot_path"]),
                "digest": built["snapshot_digest"],
                "kind": "snapshot",
                "mediaType": "application/vnd.semantica.project-snapshot+json",
            },
            "retrieval": {
                "path": str(built["retrieval_path"]),
                "digest": built["retrieval_digest"],
                "kind": "retrieval-index",
                "mediaType": "application/vnd.semantica.retrieval+json",
            },
            "query": query,
            "limit": 5,
        },
    }


def test_query_worker_returns_snapshot_bound_evidence(tmp_path):
    built = _build(tmp_path)
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(_request(built)) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    result = response["result"]
    assert result["snapshotId"] == built["snapshot"].id
    assert result["retrievalManifestId"] == "retrieval:graph"
    assert result["contexts"]
    assert all(context["sourceIds"] == ["source-1"] for context in result["contexts"] if context["evidenceIds"])
    assert any(context["kind"] == "evidence" and "Ada Lovelace" in context["text"] for context in result["contexts"])


def test_query_worker_returns_empty_contexts_without_fallback(tmp_path):
    built = _build(tmp_path)
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(_request(built, "nonexistent-token")) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert response["result"]["contexts"] == []


def test_query_worker_rejects_tampered_retrieval_artifact(tmp_path):
    built = _build(tmp_path)
    built["retrieval_path"].write_text("{}", encoding="utf-8")
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(_request(built)) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] == "QueryError"
    assert "digest" in response["error"]["message"]


def test_query_worker_filters_sources_before_limit(tmp_path):
    built = _build(tmp_path, second_source=True)
    request = _request(built)
    request["params"].update({"sourceIds": ["source-2"], "limit": 1, "mode": "keyword"})
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert len(response["result"]["contexts"]) == 1
    assert response["result"]["contexts"][0]["sourceIds"] == ["source-2"]


def test_query_worker_empty_scope_never_means_all_sources(tmp_path):
    built = _build(tmp_path)
    request = _request(built)
    request["params"].update({"sourceIds": [], "limit": 1000})
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert response["result"]["contexts"] == []


def test_query_worker_does_not_mislabel_keyword_as_semantic(tmp_path):
    built = _build(tmp_path)
    request = _request(built)
    request["params"]["mode"] = "semantic"
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    assert json.loads(stdout.getvalue())["ok"] is False


def _semantic_request(tmp_path):
    built = _build(tmp_path, second_source=True)
    retrieval = json.loads(built["retrieval_path"].read_text())
    retrieval["embedding_space"] = {"binding_id": "binding-1", "model_id": "embedding-1", "dimensions": 2}
    retrieval["embeddings"] = [
        {"source_id": "source-1", "start_char": 0, "end_char": 100, "vector": [0.0, 1.0]},
        {"source_id": "source-2", "start_char": 0, "end_char": 22, "vector": [1.0, 0.0]},
    ]
    built["retrieval_path"].write_text(json.dumps(retrieval))
    built["retrieval_digest"] = _digest(built["retrieval_path"])
    snapshot = json.loads(built["snapshot_path"].read_text())
    for manifest in snapshot["retrieval_manifests"]:
        if manifest["id"] == "retrieval:graph":
            manifest["artifact_hash"] = built["retrieval_digest"]
    for artifact in snapshot["artifact_manifest"]:
        if artifact["artifact_type"] == "retrieval":
            artifact["artifact_hash"] = built["retrieval_digest"]
    built["snapshot_path"].write_text(json.dumps(snapshot))
    built["snapshot_digest"] = _digest(built["snapshot_path"])
    request = _request(built, "mathematical innovation")
    request["params"].update({"mode": "semantic", "limit": 1,
        "embedding": {"bindingId": "binding-1", "modelId": "embedding-1", "vector": [1.0, 0.0]}})
    return request


def test_semantic_query_finds_evidence_without_lexical_overlap(tmp_path):
    request = _semantic_request(tmp_path)
    stdout = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), stdout)
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    hit = response["result"]["contexts"][0]
    assert hit["sourceIds"] == ["source-2"]
    assert hit["score"] == 1.0
    assert hit["evidenceIds"]
    request["params"]["sourceIds"] = ["source-1"]
    stdout = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), stdout)
    assert json.loads(stdout.getvalue())["result"]["contexts"][0]["sourceIds"] == ["source-1"]


@pytest.mark.parametrize("change", [
    {"modelId": "wrong-model"}, {"bindingId": "wrong-binding"},
    {"vector": [1.0]}, {"vector": [0.0, 0.0]}, {"vector": [float("nan"), 1.0]}, {"vector": [True, False]},
])
def test_semantic_query_rejects_incompatible_vectors_without_keyword_fallback(tmp_path, change):
    request = _semantic_request(tmp_path)
    request["params"]["query"] = "Ada"
    request["params"]["embedding"].update(change)
    stdout = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), stdout)
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert not response.get("result")
