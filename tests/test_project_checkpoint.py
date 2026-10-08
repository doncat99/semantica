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


def test_worker_process_restart_reuses_durable_parse_and_model_calls(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source explains durable knowledge production.", encoding="utf-8")
    request = _request(source, tmp_path / "output", recipe="model")
    parsed_artifact = Path(request["params"]["parsedSources"][0]["artifactPath"])
    parsed_bytes = parsed_artifact.read_bytes()
    second_call = threading.Event()
    release_call = threading.Event()
    calls = []

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(payload)
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
        if not second_call.wait(15):
            child.kill()
            stdout, stderr = child.communicate(timeout=10)
            pytest.fail(f"worker did not reach its second model request: {stdout} {stderr}")
        assert len(list((tmp_path / "output" / "checkpoint").glob("relay-*.json"))) == 1
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
    source.write_text("A source explains durable knowledge production. " * 110, encoding="utf-8")
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
        return Response({"model": payload["model"], "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(content)}}], "usage": {"completion_tokens": 100}})

    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setattr("urllib.request.urlopen", relay)
    with pytest.raises(Exception, match="MODEL_GATEWAY_COOLDOWN"):
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(first["params"]))
    checkpoint = tmp_path / "first" / "checkpoint"
    assert len(list(checkpoint.glob("relay-*.json"))) == 2
    first_window_prompts = calls[:2]

    second = _request(source, tmp_path / "second", recipe="model")
    second["params"]["parallelism"] = 1
    second["params"]["relays"]["model"]["maxOutputTokens"] = 32768
    second["params"]["resumeCheckpointDirs"] = [str(checkpoint)]
    second["params"]["resumeCheckpointModelTokenLimits"] = {str(checkpoint): 393216}
    quota_exhausted = False
    result = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert result["snapshot"] is not None
    assert all(calls.count(prompt) == 1 for prompt in first_window_prompts)
    assert len(list((tmp_path / "second" / "checkpoint").glob("relay-*.json"))) >= 4


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
    assert second_checkpoint.read("document", {"source": "source-1"}) is None
    assert len(list(second_checkpoint.root.glob("relay-*.json"))) == 1


def test_completed_model_response_survives_lower_output_limit(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source", encoding="utf-8")
    first = _request(source, tmp_path / "first", recipe="model")
    first["params"]["relays"]["model"]["maxOutputTokens"] = 393216
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    key = {"operation": "structured_extraction", "bindingId": "default", "modelId": "model-1",
           "payload": {"model": "model-1", "messages": [{"role": "user", "content": "Extract entities"}],
                       "max_tokens": 393216}}
    saved = {"response": {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                          "usage": {"completion_tokens": 100}}, "receipt": {"id": "receipt:saved"}}
    first_checkpoint.write("relay", key, saved)
    second = _request(source, tmp_path / "second", recipe="model")
    second["params"]["relays"]["model"]["maxOutputTokens"] = 32768
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    second["params"]["resumeCheckpointModelTokenLimits"] = {str(first_checkpoint.root): 393216}
    second_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))
    current_key = {**key, "payload": {**key["payload"], "max_tokens": 32768}}
    assert second_checkpoint.read("relay", current_key) is None
    assert second_checkpoint.read_with_lower_model_limit(current_key) == saved
    assert second_checkpoint.read("relay", current_key) == saved
    second_checkpoint.reject("relay", current_key, saved)
    assert second_checkpoint.read("relay", current_key) is None
    assert second_checkpoint.read_with_lower_model_limit(current_key) is None

    first_checkpoint.write("relay", key, {**saved, "response": {**saved["response"],
        "choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}})
    assert second_checkpoint.read_with_lower_model_limit(current_key) is None
    first_checkpoint.write("relay", key, {**saved, "response": {**saved["response"],
        "usage": {"completion_tokens": 40000}}})
    assert second_checkpoint.read_with_lower_model_limit(current_key) is None


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
