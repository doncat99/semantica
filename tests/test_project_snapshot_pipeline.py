import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"not-an-epub")
    request = _request(source, tmp_path)
    request["params"]["sources"][0]["mimeType"] = "application/msword"
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "dedicated adapter" in response["error"]["message"] or "does not match" in response["error"]["message"]


def test_model_recipe_uses_bifrost_chat_and_embedding_and_records_receipts(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")

    class RelayHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers["content-length"])
            payload = json.loads(self.rfile.read(length))
            if self.path == "/v1/chat/completions":
                response = {
                    "choices": [{"message": {"content": json.dumps({
                        "entities": [
                            {"name": "Ada Lovelace", "type": "PERSON"},
                            {"name": "Analytical Engine", "type": "CONCEPT"},
                        ],
                        "relations": [{"subject": "Ada Lovelace", "predicate": "designed", "object": "Analytical Engine", "evidence": "Ada Lovelace designed the Analytical Engine."}],
                    }), "role": "assistant"}}],
                    "model": payload["model"],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8},
                }
            elif self.path == "/v1/embeddings":
                response = {"data": [{"embedding": [0.25, 0.5, 0.75], "index": 0}], "model": "embedding-1", "usage": {"prompt_tokens": 4, "total_tokens": 4}}
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    previous_token = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "relay-test-token"
    try:
        request = _request(source, tmp_path, recipe="model")
        request["params"]["relays"]["model"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        request["params"]["relays"]["embedding"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/embeddings"
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        response = json.loads(stdout.getvalue())
    finally:
        if previous_token is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_token
        server.shutdown()
        server.server_close()

    assert response["ok"] is True
    assert len(response["result"]["relayReceipts"]["model"]) == 1
    assert len(response["result"]["relayReceipts"]["embedding"]) == 1
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert len(snapshot.model_receipts) == 2
    assert all(receipt.input_digest.startswith("sha256:") and receipt.output_digest.startswith("sha256:") for receipt in snapshot.model_receipts)
    assert snapshot.relations[0].status == "candidate"
    assert snapshot.relations[0].evidence_ids
    assert snapshot.retrieval_manifests[0].model_receipt_ids == [receipt.id for receipt in snapshot.model_receipts]
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    assert json.loads(retrieval_path.read_text())["embeddings"] == [{"source_id": "source-1", "vector": [0.25, 0.5, 0.75]}]


def test_model_recipe_fails_closed_without_relay_token(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    previous_token = os.environ.pop("OPENAI_API_KEY", None)
    try:
        stdin = io.StringIO(json.dumps(_request(source, tmp_path, recipe="model")) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        response = json.loads(stdout.getvalue())
    finally:
        if previous_token is not None:
            os.environ["OPENAI_API_KEY"] = previous_token
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "authorization" in response["error"]["message"]
