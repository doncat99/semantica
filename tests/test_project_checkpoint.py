import json
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError
from semantica.semantic_artifact_builder import build_semantic_artifacts
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request, _typed_prompt_context


def test_embedding_restart_uses_one_verified_payload_and_original_receipt(tmp_path, monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    from semantica.semantic_artifact_builder import _embed_texts

    source = tmp_path / "source.txt"
    source.write_text("A source")
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "first")["params"])
    checkpoint = SnapshotCheckpoint(request)
    relay = request.relays["embedding"]
    calls = []

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self):
            return json.dumps({"model": relay.model_id, "usage": {"total_tokens": 2},
                "data": [{"index": 0, "embedding": [1.0, 0.5]}]}).encode()

    def send(request, timeout):
        calls.append(request.data)
        return Response()

    monkeypatch.setenv(relay.authorization_env, "fixture")
    monkeypatch.setattr("urllib.request.urlopen", send)
    token = active_checkpoint.set(checkpoint)
    try:
        vectors, receipt = _embed_texts(["A source"], relay)
    finally:
        active_checkpoint.reset(token)
    second = _request(source, tmp_path / "second")
    second["params"]["resumeCheckpointDirs"] = [str(checkpoint.root)]
    restored = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))
    token = active_checkpoint.set(restored)
    try:
        resumed_vectors, resumed_receipt = _embed_texts(["A source"], relay)
    finally:
        active_checkpoint.reset(token)
    assert resumed_vectors == vectors == [[1.0, 0.5]]
    assert resumed_receipt.model_dump() == receipt.model_dump()
    assert resumed_receipt._checkpoint_restored is True
    assert len(calls) == 1
    assert len(list(checkpoint.root.glob("relay-*.json"))) == 1
    assert len(list(restored.root.glob("relay-*.json"))) == 1
    assert not list(checkpoint.root.glob("embedding-batch-*.json"))
    assert not list(restored.root.glob("embedding-batch-*.json"))
    key = {"operation": "embedding", "bindingId": relay.binding_id,
           "modelId": relay.model_id, "payload": json.loads(calls[0])}
    cached = restored.read("relay", key)
    cached["response"]["data"][0]["index"] = 1
    restored.write("relay", key, cached)
    token = active_checkpoint.set(restored)
    try:
        with pytest.raises(Exception, match="index does not match input order"):
            _embed_texts(["A source"], relay)
    finally:
        active_checkpoint.reset(token)
    assert len(calls) == 1


def test_worker_process_restart_reuses_durable_parse_and_model_calls(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source explains durable knowledge production.", encoding="utf-8")
    request = _request(source, tmp_path / "output", recipe="model")
    parsed_artifact = Path(request["params"]["parsedSources"][0]["artifactPath"])
    parsed_bytes = parsed_artifact.read_bytes()
    first_call = threading.Event()
    second_call = threading.Event()
    release_call = threading.Event()
    calls = []

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(payload)
            first_call.set()
            if len(calls) == 2:
                second_call.set()
                release_call.wait(30)
            if "input" in payload:
                response = {"model": payload["model"], "data": [
                    {"index": index, "embedding": [1.0, 0.5]}
                    for index, _ in enumerate(payload["input"])
                ]}
            else:
                prompt = payload["messages"][0]["content"]
                if "Explain the supplied knowledge" in prompt:
                    context = _typed_prompt_context(payload)
                    content = {"sections": [{"title": "Knowledge production", "text": context["evidence"][0]["quote"],
                        "citations": [{"evidence_id": item["id"], "quote": item["quote"]} for item in context["evidence"]]}]}
                elif "Synthesize the supplied grounded explanations" in prompt:
                    context = _typed_prompt_context(payload)
                    content = {"sections": [{"title": "Knowledge production", "text": "Connected explanation",
                        "evidence_ids": [context["sections"][0]["evidence_ids"][0]]}]}
                else:
                    content = {"relations": []} if "Extract source-grounded relations" in prompt else {
                        "entities": [{"text": "A source", "label": "CONCEPT", "occurrence": 0}]}
                response = {"model": payload["model"], "choices": [{"message": {"content": json.dumps(content)}}]}
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def server():
        instance = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
        threading.Thread(target=instance.serve_forever, daemon=True).start()
        for name, relay in request["params"]["relays"].items():
            endpoint = "embeddings" if name == "embedding" else "chat/completions"
            relay["baseUrl"] = f"http://127.0.0.1:{instance.server_port}/v1/{endpoint}"
        return instance

    def worker():
        return subprocess.Popen([sys.executable, "-m", "semantica.semantic_worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env={**os.environ, "OPENAI_API_KEY": "fixture"})

    first_server = server()
    child = worker()
    try:
        child.stdin.write(json.dumps(request) + "\n")
        child.stdin.flush()
        # Separate cold imports from progress; restarted workers already get 30s.
        if not first_call.wait(30):
            child.kill()
            stdout, stderr = child.communicate(timeout=10)
            pytest.fail(f"worker did not reach its first model request: {stdout} {stderr}")
        if not second_call.wait(15):
            child.kill()
            stdout, stderr = child.communicate(timeout=10)
            pytest.fail(f"worker did not reach its second model request: {stdout} {stderr}")
        assert len(list((tmp_path / "output" / "checkpoint").glob("extraction-entities-*.json"))) == 1
        child.kill()
        child.communicate(timeout=10)
        assert child.returncode != 0
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)
        release_call.set()
        first_server.shutdown()
        first_server.server_close()

    resumed_server = server()
    try:
        resumed = worker()
        stdout, stderr = resumed.communicate(json.dumps(request) + "\n", timeout=30)
        assert resumed.returncode == 0, stderr
        result = json.loads(stdout.strip().splitlines()[-1])
        assert result["ok"], result
        assert parsed_artifact.read_bytes() == parsed_bytes
        entity_calls = [item for item in calls if "messages" in item and
            "Extract named entities" in item["messages"][0]["content"]]
        assert len(entity_calls) == 1
        snapshot_artifact = next(item for item in result["result"]["artifacts"] if item["kind"] == "semantic-graph")
        snapshot = json.loads(Path(snapshot_artifact["path"]).read_bytes())
        extraction_receipt = next(item for item in snapshot["model_receipts"] if item["operation"] == "structured_extraction")
        assert f":{first_server.server_port}/" in extraction_receipt["parameters"]["relay_url"]
        count = len(calls)
        repeated = worker()
        stdout, stderr = repeated.communicate(json.dumps(request) + "\n", timeout=30)
        assert repeated.returncode == 0, stderr
        assert json.loads(stdout.strip().splitlines()[-1]) == result
        assert len(calls) == count
        assert not list((tmp_path / "output" / "checkpoint").glob("provenance-*.json"))
        assert parsed_artifact.read_bytes() == parsed_bytes
        source.write_text("The material changed without changing its declared revision.")
        changed = worker()
        stdout, stderr = changed.communicate(json.dumps(request) + "\n", timeout=30)
        assert changed.returncode == 0, stderr
        failure = json.loads(stdout.strip().splitlines()[-1])
        assert not failure["ok"]
        assert "inputs changed" in failure["error"]["message"]
        assert len(calls) == count
        assert parsed_artifact.read_bytes() == parsed_bytes
    finally:
        resumed_server.shutdown()
        resumed_server.server_close()


def test_quota_failure_new_run_reuses_completed_extraction_windows(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    # Keep two substantive native windows so the test exercises checkpoint
    # reuse without relying on a trailing whitespace-only chunk.
    source.write_text("A source explains durable knowledge production. " * 300, encoding="utf-8")
    first = _request(source, tmp_path / "first", recipe="model")
    first["params"]["parallelism"] = 1
    first["params"]["relays"]["model"]["maxOutputTokens"] = 393216
    calls = []
    quota_exhausted = False

    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return self.payload

    def relay(request, timeout):
        nonlocal quota_exhausted
        payload = json.loads(request.data)
        if "input" in payload:
            return Response({"model": payload["model"], "data": [
                {"index": index, "embedding": [1.0, 0.5]}
                for index, _ in enumerate(payload["input"])
            ]})
        prompt = payload["messages"][0]["content"]
        calls.append(prompt)
        if len(calls) == 3:
            quota_exhausted = True
        if quota_exhausted:
            raise urllib.error.HTTPError(request.full_url, 503, "Quota exhausted", {}, io.BytesIO(
                b'{"error":{"code":"MODEL_GATEWAY_COOLDOWN","retryable":true}}'))
        if "Resolve project entity identity" in prompt:
            content = {"merges": [], "splits": []}
        elif "Explain the supplied knowledge" in prompt:
            context = _typed_prompt_context(payload)
            content = {"sections": [{"title": "Knowledge production", "text": context["evidence"][0]["quote"],
                "citations": [{"evidence_id": item["id"], "quote": item["quote"]} for item in context["evidence"]]}]}
        elif "Synthesize the supplied grounded explanations" in prompt:
            context = _typed_prompt_context(payload)
            content = {"sections": [{"title": "Knowledge production", "text": "Connected explanation",
                "evidence_ids": [context["sections"][0]["evidence_ids"][0]]}]}
        else:
            content = {"relations": []} if "Extract source-grounded relations" in prompt else {
                "entities": [{"text": "A source", "label": "CONCEPT", "occurrence": 0}]}
        return Response({"model": payload["model"], "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(content)}}], "usage": {"completion_tokens": 100}})

    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setattr("urllib.request.urlopen", relay)
    with pytest.raises(Exception, match="MODEL_GATEWAY_COOLDOWN"):
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(first["params"]))
    checkpoint = tmp_path / "first" / "checkpoint"
    assert not list(checkpoint.glob("relay-*.json"))
    assert len(list(checkpoint.glob("extraction-*.json"))) == 2
    first_window_prompts = calls[:2]

    second = _request(source, tmp_path / "second", recipe="model")
    second["params"]["parallelism"] = 1
    second["params"]["relays"]["model"]["maxOutputTokens"] = 393216
    second["params"]["resumeCheckpointDirs"] = [str(checkpoint)]
    quota_exhausted = False
    result = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert result["snapshot"] is not None
    assert all(calls.count(prompt) == 1 for prompt in first_window_prompts)
    second_checkpoint = tmp_path / "second" / "checkpoint"
    assert len(list(second_checkpoint.glob("extraction-entities-*.json"))) >= 2
    assert not list(second_checkpoint.glob("embedding-batch-*.json"))
    embedding_entries = [json.loads(path.read_bytes())["payload"]
                         for path in second_checkpoint.glob("relay-*.json")
                         if json.loads(path.read_bytes())["payload"]["receipt"]["operation"] == "embedding"]
    assert embedding_entries


def test_checkpoint_rejects_corrupt_payload_and_changed_recipe(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    request = _request(source, tmp_path / "output")
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(request["params"]))
    checkpoint.write("relay", {"id": 1}, {"response": "original"})
    entry = next(checkpoint.root.glob("relay-*.json"))
    payload = json.loads(entry.read_bytes())
    payload["payload"]["response"] = "altered"
    entry.write_text(json.dumps(payload))
    with pytest.raises(SnapshotCheckpointError, match="failed verification"):
        checkpoint.read("relay", {"id": 1})
    request["params"]["recipe"]["forceOcrSourceIds"] = ["source-1"]
    with pytest.raises(SnapshotCheckpointError, match="inputs changed"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(request["params"]))


def test_new_run_reuses_only_matching_verified_relay_entries(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    first = _request(source, tmp_path / "first")
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    first_checkpoint.write("relay", {"operation": "embedding", "input": ["Alpha"]}, {"response": "saved"})
    first_checkpoint.write("document", {"source": "source-1"}, {"document": "old"})

    second = _request(source, tmp_path / "second")
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    second_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))

    assert second_checkpoint.read("relay", {"operation": "embedding", "input": ["Alpha"]}) == {"response": "saved"}
    assert second_checkpoint.read("relay", {"operation": "embedding", "input": ["Beta"]}) is None
    assert second_checkpoint.read("document", {"source": "source-1"}) == {"document": "old"}
    assert len(list(second_checkpoint.root.glob("relay-*.json"))) == 1
    assert len(list(second_checkpoint.root.glob("document-*.json"))) == 1


def test_new_run_does_not_reuse_checkpoint_after_recipe_change(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source", encoding="utf-8")
    first = _request(source, tmp_path / "first")
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    first_checkpoint.write("document", {"source": "source-1"}, {"document": "old"})

    second = _request(source, tmp_path / "second")
    second["params"]["recipe"]["forceOcrSourceIds"] = ["source-1"]
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    with pytest.raises(SnapshotCheckpointError, match="inputs changed"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))


def test_external_checkpoint_entry_must_match_its_manifest_fence(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source", encoding="utf-8")
    first = _request(source, tmp_path / "first")
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    first_checkpoint.write("document", {"source": "source-1"}, {"document": "saved"})
    entry_path = next(first_checkpoint.root.glob("document-*.json"))
    entry = json.loads(entry_path.read_bytes())
    entry["fence"] = "sha256:" + "0" * 64
    entry_path.write_text(json.dumps(entry), encoding="utf-8")

    second = _request(source, tmp_path / "second")
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    second_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))

    with pytest.raises(SnapshotCheckpointError, match="failed verification"):
        second_checkpoint.read("document", {"source": "source-1"})



def test_new_run_skips_semantically_rejected_relay_payload(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    first = _request(source, tmp_path / "first")
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    key = {"operation": "structured_extraction", "input": "Alpha"}
    rejected = {"response": "invalid", "receipt": {"id": "receipt:invalid"}}
    first_checkpoint.write("relay", key, rejected)
    first_checkpoint.reject("relay", key, rejected)

    second = _request(source, tmp_path / "second")
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    second_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))

    assert second_checkpoint.read("relay", key) is None


def test_package_upgrade_rejects_historical_completed_chunks(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    first = _request(source, tmp_path / "first", recipe="model")
    prior = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    key = {"sourceText": "same-text", "window": {"start": 0, "end": 8, "digest": "same-window"}}
    saved = {"extracted": {"entities": [], "relations": []}, "receipts": []}
    prior.write("extraction-entities", key, saved)
    original = next(prior.root.glob("extraction-entities-*.json")).read_bytes()
    second = _request(source, tmp_path / "second", recipe="model")
    second["params"]["release"]["artifactDigest"] = "sha256:" + "9" * 64
    second["params"]["inputRevision"] = "sha256:" + "8" * 64
    second["params"]["resumeCheckpointDirs"] = [str(prior.root)]
    with pytest.raises(SnapshotCheckpointError, match="inputs changed"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert next(prior.root.glob("extraction-entities-*.json")).read_bytes() == original
