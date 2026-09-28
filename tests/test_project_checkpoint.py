import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest
from tests.test_project_snapshot_pipeline import _request


def test_worker_process_restart_reuses_durable_parse_and_model_calls(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source explains durable knowledge production.", encoding="utf-8")
    request = _request(source, tmp_path / "output", recipe="model")
    parsed_log = tmp_path / "parsed.log"
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
                response = {"model": payload["model"], "data": [{"embedding": [1.0, 0.5]}]}
            else:
                user = payload["messages"][1]["content"]
                if user == source.read_text():
                    content = {"entities": [], "relations": []}
                else:
                    context = json.loads(user)
                    content = {"sections": [{"title": "Knowledge production", "text": context["evidence"][0]["quote"],
                        "citations": [{"evidence_id": item["id"], "quote": item["quote"]} for item in context["evidence"]]}]}
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

    # Instrument the real parser only; the worker, HTTP calls and disk recovery are real.
    script = """
import os
from pathlib import Path
import semantica.project_snapshot_pipeline as pipeline
from semantica.project_snapshot_worker import serve
original = pipeline.parse_source
def parse(*args, **kwargs):
    with Path(os.environ['PARSED_LOG']).open('a') as stream:
        stream.write('parsed\\n')
    return original(*args, **kwargs)
pipeline.parse_source = parse
raise SystemExit(serve())
"""
    def worker():
        return subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env={**os.environ, "OPENAI_API_KEY": "fixture", "PARSED_LOG": str(parsed_log)})

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
        result = json.loads(stdout)
        assert result["ok"], result
        assert parsed_log.read_text().splitlines() == ["parsed"]
        extraction_calls = [item for item in calls if "messages" in item and item["messages"][1]["content"] == source.read_text()]
        assert len(extraction_calls) == 1
        snapshot_artifact = next(item for item in result["result"]["artifacts"] if item["kind"] == "snapshot")
        snapshot = json.loads(Path(snapshot_artifact["path"]).read_bytes())
        extraction_receipt = next(item for item in snapshot["model_receipts"] if item["operation"] == "structured_extraction")
        assert f":{first_server.server_port}/" in extraction_receipt["parameters"]["relay_url"]
        count = len(calls)
        repeated = worker()
        stdout, stderr = repeated.communicate(json.dumps(request) + "\n", timeout=30)
        assert repeated.returncode == 0, stderr
        assert json.loads(stdout) == result
        assert len(calls) == count
        assert parsed_log.read_text().splitlines() == ["parsed"]
        source.write_text("The material changed without changing its declared revision.")
        changed = worker()
        stdout, stderr = changed.communicate(json.dumps(request) + "\n", timeout=30)
        assert changed.returncode == 0, stderr
        failure = json.loads(stdout)
        assert not failure["ok"]
        assert "inputs changed" in failure["error"]["message"]
        assert len(calls) == count
        assert parsed_log.read_text().splitlines() == ["parsed"]
    finally:
        resumed_server.shutdown()
        resumed_server.server_close()


def test_checkpoint_rejects_corrupt_payload_and_changed_recipe(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    request = _request(source, tmp_path / "output")
    checkpoint = SnapshotCheckpoint(ProjectSnapshotBuildRequest.model_validate(request["params"]))
    checkpoint.write("relay", {"id": 1}, {"response": "original"})
    entry = next(checkpoint.root.glob("relay-*.json"))
    payload = json.loads(entry.read_bytes())
    payload["payload"]["response"] = "altered"
    entry.write_text(json.dumps(payload))
    with pytest.raises(SnapshotCheckpointError, match="failed verification"):
        checkpoint.read("relay", {"id": 1})
    request["params"]["recipe"]["forceOcrSourceIds"] = ["source-1"]
    with pytest.raises(SnapshotCheckpointError, match="inputs changed"):
        SnapshotCheckpoint(ProjectSnapshotBuildRequest.model_validate(request["params"]))
