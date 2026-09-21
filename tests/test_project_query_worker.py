import io
import json
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


def _build(tmp_path: Path):
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

