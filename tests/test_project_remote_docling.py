import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
from semantica.project_remote_docling import RemoteDoclingError, parse_remote_docling
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest
from tests.test_project_snapshot_pipeline import _request


@pytest.fixture
def gateway(tmp_path):
    calls = []
    polling = threading.Event()
    release = threading.Event()
    result = {"status": "success", "document": {"text_content": "Remote evidence.", "doctags_content": "<text>Remote evidence.</text>", "json_content": {"texts": [{"text": "Remote evidence.", "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}, "charspan": [0, 16]}]}]}}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            calls.append(("POST", self.path, self.headers.get("X-Api-Key"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            if result.get("http_status"):
                self.send_response(result["http_status"])
                self.send_header("Location", "/credential-redirect")
                self.end_headers()
                self.wfile.write(b"secret-fixture must not appear in errors")
                return
            self.respond({"task_id": "task-1", "task_status": "pending"})

        def do_GET(self):
            calls.append(("GET", self.path, self.headers.get("X-Api-Key")))
            if "/status/" in self.path:
                polling.set()
                release.wait(20)
                self.respond({"task_id": "task-1", "task_status": "success"})
            else:
                self.respond(result)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = {"mode": "remote", "endpoint": f"http://127.0.0.1:{server.server_port}/docling", "bindingId": "fixture", "authorizationEnv": "TEST_DOCLING_KEY", "remoteCancellation": "unsupported"}
    try:
        yield profile, calls, polling, release, result
    finally:
        release.set()
        server.shutdown()
        server.server_close()


def test_remote_task_survives_actual_process_kill_without_resubmission(tmp_path, gateway):
    profile, calls, polling, release, _ = gateway
    source = tmp_path / "source.pdf"
    source.write_bytes(b"synthetic protocol fixture")
    request = _request(source, tmp_path / "output")
    request["params"]["documentProcessing"] = profile
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request["params"]))
    script = """
import json,sys
from pathlib import Path
from semantica.project_checkpoint import SnapshotCheckpoint,active_checkpoint
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest
from semantica.project_source import parse_source
r=ProjectSnapshotBuildRequest.model_validate_json(Path(sys.argv[1]).read_text())
active_checkpoint.set(SnapshotCheckpoint(r))
d=parse_source(Path(r.sources[0].file_path),name='source.pdf',mime_type='application/pdf',force_ocr=True,document_processing=r.document_processing.model_dump(mode='json',by_alias=True))
print(json.dumps({'origin':d.origin,'document':d.document}))
"""
    def start():
        return subprocess.Popen([sys.executable, "-c", script, str(request_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, "TEST_DOCLING_KEY": "secret-fixture"})
    first = start()
    try:
        assert polling.wait(15)
        first.kill()
        first.communicate(timeout=5)
        release.set()
        second = start()
        stdout, stderr = second.communicate(timeout=15)
        assert second.returncode == 0, stderr
        document = json.loads(stdout)
        assert document["origin"] == "external"
        assert document["document"]["metadata"]["text_origin"] == "unreported"
        assert document["document"]["document"]["texts"][0]["prov"][0]["page_no"] == 1
        assert len([call for call in calls if call[0] == "POST"]) == 1
        assert all(call[2] == "secret-fixture" for call in calls)
        count = len(calls)
        third = start()
        stdout_again, stderr = third.communicate(timeout=15)
        assert third.returncode == 0, stderr
        assert json.loads(stdout_again) == document
        assert len(calls) == count
        assert "secret-fixture" not in "".join(p.read_text() for p in (tmp_path / "output" / "checkpoint").glob("*.json"))
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=5)


def test_missing_auth_and_uncertain_submit_fail_closed(tmp_path, gateway, monkeypatch):
    profile, calls, _, release, _ = gateway
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    request = ProjectSnapshotBuildRequest.model_validate(_request(source, tmp_path / "output")["params"])
    checkpoint = SnapshotCheckpoint(request)
    token = active_checkpoint.set(checkpoint)
    try:
        monkeypatch.delenv("TEST_DOCLING_KEY", raising=False)
        with pytest.raises(RemoteDoclingError, match="credential"):
            parse_remote_docling(source, name=source.name, force_ocr=False, profile=profile)
        assert calls == []
        monkeypatch.setenv("TEST_DOCLING_KEY", "secret-fixture")
        monkeypatch.setattr(checkpoint, "read", lambda *args: {"phase": "submitting"})
        with pytest.raises(RemoteDoclingError, match="outcome unknown"):
            parse_remote_docling(source, name=source.name, force_ocr=False, profile=profile)
        assert calls == []
    finally:
        active_checkpoint.reset(token)


def test_partial_result_is_not_adopted(tmp_path, gateway, monkeypatch):
    profile, _, _, release, result = gateway
    result["status"] = "partial_success"
    release.set()
    monkeypatch.setenv("TEST_DOCLING_KEY", "secret-fixture")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    request = ProjectSnapshotBuildRequest.model_validate(_request(source, tmp_path / "output")["params"])
    token = active_checkpoint.set(SnapshotCheckpoint(request))
    try:
        with pytest.raises(RemoteDoclingError, match="not a successful"):
            parse_remote_docling(source, name=source.name, force_ocr=False, profile=profile)
    finally:
        active_checkpoint.reset(token)


@pytest.mark.parametrize("status", [401, 302])
def test_auth_error_redaction_and_redirect_refusal(tmp_path, gateway, monkeypatch, status):
    profile, calls, _, release, result = gateway
    result["http_status"] = status
    monkeypatch.setenv("TEST_DOCLING_KEY", "secret-fixture")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    request = ProjectSnapshotBuildRequest.model_validate(_request(source, tmp_path / "output")["params"])
    token = active_checkpoint.set(SnapshotCheckpoint(request))
    try:
        with pytest.raises(RemoteDoclingError, match=f"HTTP {status}") as error:
            parse_remote_docling(source, name=source.name, force_ocr=False, profile=profile)
        assert "secret-fixture" not in str(error.value)
        assert len(calls) == 1
    finally:
        active_checkpoint.reset(token)
