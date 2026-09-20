import io
import json
from pathlib import Path

from semantica.project_snapshot_schema import ProjectSnapshot
from semantica.project_snapshot_worker import serve

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def _request(source: Path, output_dir: Path, *, recipe: str = "deterministic") -> dict:
    return {
        "protocol": "semantica.project-worker.v1",
        "id": "build-1",
        "method": "build_project_snapshot",
        "params": {
            "baseSnapshot": None,
            "inputRevision": H1,
            "outputDir": str(output_dir),
            "projectId": "project-1",
            "recipe": {"forceOcrSourceIds": [], "id": recipe, "version": "1"},
            "relays": {
                "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.snapshot.embed", "modelId": "embedding-1", "receipts": "required"},
                "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.snapshot.generate", "modelId": "model-1", "receipts": "required"},
            },
            "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json", "retrieval-index": "application/vnd.semantica.retrieval+json", "snapshot": "application/vnd.semantica.project-snapshot+json"}},
            "sources": [{"filePath": str(source), "materialRevision": "material-1", "mimeType": "text/plain", "name": source.name, "sourceId": "source-1"}],
        },
    }


def test_worker_builds_complete_snapshot_from_real_text_file(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine. The Engine influenced Charles Babbage.", encoding="utf-8")
    stdin = io.StringIO(json.dumps(_request(source, tmp_path)) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert [item["kind"] for item in response["result"]["artifacts"]] == ["document-representation", "retrieval-index", "snapshot"]
    assert response["result"]["relayReceipts"] == {"embedding": [], "model": []}

    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert snapshot.id == response["result"]["snapshot"]["snapshotId"]
    assert snapshot.entities
    assert snapshot.relations == []
    assert snapshot.assertions == []
    assert snapshot.identity_decisions == []
    assert snapshot.reports == []
    assert snapshot.evidence_spans
    assert snapshot.model_receipts == []
    assert all(span.quote == span.locator.quote for span in snapshot.evidence_spans)
    assert all(span.locator.representation_id == span.representation_id for span in snapshot.evidence_spans)


def test_worker_fails_closed_for_unsupported_source_format(tmp_path):
    source = tmp_path / "book.epub"
    source.write_bytes(b"not-an-epub")
    stdin = io.StringIO(json.dumps(_request(source, tmp_path)) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "unsupported source format" in response["error"]["message"]
