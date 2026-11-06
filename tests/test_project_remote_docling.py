"""Remote task durability belongs to the host job, not parser checkpoints."""
import io
import json
import subprocess
import sys

import pytest

from semantica.project_remote_docling import RemoteDoclingError, parse_remote_docling
from semantica.semantic_artifact_schema import DocumentProcessingProfile
from semantica.semantic_worker_context import document_processing_authorization, document_processing_token


def _native_document(text):
    from docling_core.types.doc import DoclingDocument, DocItemLabel, ProvenanceItem, BoundingBox
    document = DoclingDocument(name="remote-fixture")
    document.add_text(label=DocItemLabel.TEXT, text=text, prov=ProvenanceItem(
        page_no=1, bbox=BoundingBox(l=1, t=2, r=3, b=4), charspan=(0, len(text))))
    return {"status": "success", "document": {"json_content": document.export_to_dict()}}


@pytest.fixture
def conversion(tmp_path, monkeypatch):
    from semantica import project_remote_docling as module
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    calls, result = [], _native_document("Remote evidence.")
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            payload = ({"task_id": "task-1"} if request.data else
                {"task_id": "task-1", "task_status": "success"} if "/status/" in request.full_url else result)
            return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(module, "build_opener", lambda *_: Opener())
    token = document_processing_authorization.set("fixture")
    try:
        yield source, calls, result
    finally:
        document_processing_authorization.reset(token)


def _parse(source, **options):
    return parse_remote_docling(source, name=source.name, force_ocr=False,
        profile={"endpoint": "http://localhost/docling"}, **options)


def test_direct_worker_remote_parse_without_checkpoint(conversion, tmp_path):
    from pathlib import Path
    from semantica.semantic_worker import handle_request
    from semantica.source import source_content_revision
    source, calls, _ = conversion
    events = []
    raw = {"id": "parse", "method": "parse_source", "documentProcessingAuthorization": "fixture", "params": {
        "source": {"sourceId": "source-1", "filePath": str(source), "name": source.name,
            "mimeType": "application/pdf", "materialRevision": source_content_revision(source)},
        "outputDir": str(tmp_path / "output"), "forceOcr": False,
        "documentProcessing": {"mode": "remote", "endpoint": "http://localhost/docling", "bindingId": "fixture"},
        "remoteTask": {}}}
    response = handle_request(raw, progress=events.append)
    assert response["ok"], response
    assert response['result']['sourceHeader']['parser'] == 'docling-serve'
    assert response['result']['sourceHeader']['origin'] == 'external'
    assert [event["remoteTask"] for event in events if "remoteTask" in event] == [{"taskId": "task-1"}]
    payload = json.loads(Path(response["result"]["artifactPath"]).read_text())
    assert payload["origin"] == "external"
    assert payload["document"]["document"]["texts"][0]["text"] == "Remote evidence."
    assert json.loads(calls[0].data)["options"]["to_formats"] == ["json"]
    assert not list(tmp_path.rglob("*checkpoint*"))
    assert not list(tmp_path.rglob("*remote-docling*"))


def test_resume_does_not_read_source_or_submit(conversion, monkeypatch):
    source, calls, _ = conversion
    monkeypatch.setattr(type(source), "read_bytes", lambda _: pytest.fail("resume must not upload/read source"))
    result = _parse(source, remote_task={"taskId": "task-1"})
    assert result["text"] == "Remote evidence."
    assert all(request.data is None for request in calls)


def test_process_kill_resumes_existing_host_task_without_resubmission(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    calls, polling, release = [], threading.Event(), threading.Event()
    native = _native_document('Remote evidence.')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            calls.append('submit')
            self.respond({'task_id':'task-1'})
        def do_GET(self):
            calls.append(self.path)
            if '/status/' in self.path:
                polling.set()
                release.wait(15)
                self.respond({'task_id':'task-1','task_status':'success'})
            else:
                self.respond(native)
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    source = tmp_path/'source.pdf'
    source.write_bytes(b'fixture')
    script = '''
import json,sys
from pathlib import Path
from semantica.semantic_worker import handle_request
from semantica.source import source_content_revision
source=Path(sys.argv[1])
def progress(event):
    print(json.dumps(event),flush=True)
raw={'id':'parse','method':'parse_source','documentProcessingAuthorization':'fixture','params':{
  'source':{'sourceId':'source-1','filePath':str(source),'name':'source.pdf',
    'mimeType':'application/pdf','materialRevision':source_content_revision(source)},
  'outputDir':str(source.parent/'output'),'forceOcr':False,
  'documentProcessing':{'mode':'remote','endpoint':sys.argv[2],'bindingId':'fixture'},
  'remoteTask':json.loads(sys.argv[3])}}
print(json.dumps(handle_request(raw,progress=progress)),flush=True)
'''
    def start(task):
        return subprocess.Popen([sys.executable,'-c',script,str(source),
            f'http://127.0.0.1:{server.server_port}',json.dumps(task)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    first = start({})
    try:
        event = json.loads(first.stdout.readline())
        assert event['remoteTask'] == {'taskId':'task-1'}
        assert polling.wait(10)
        first.kill()
        first.communicate(timeout=5)
        release.set()
        second = start(event['remoteTask'])
        stdout,stderr = second.communicate(timeout=15)
        assert second.returncode == 0, stderr
        assert json.loads(stdout.splitlines()[-1])['ok']
        assert calls.count('submit') == 1
        assert not list(tmp_path.rglob('*checkpoint*'))
        assert not list(tmp_path.rglob('*remote-docling*'))
    finally:
        release.set()
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=5)
        server.shutdown()
        server.server_close()


def test_deadline_then_host_task_resume_never_resubmits(conversion, monkeypatch):
    from semantica import project_remote_docling as module
    source, calls, _ = conversion
    now, accepted = [0.0], []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            if request.data:
                return io.BytesIO(b'{"task_id":"task-1"}')
            now[0] += 2
            return io.BytesIO(b'{"task_id":"task-1","task_status":"pending"}')
    monkeypatch.setattr(module, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    for task in ({}, {"taskId": "task-1"}):
        with pytest.raises(RemoteDoclingError, match="deadline.*task-1"):
            _parse(source, remote_task=task, on_remote_task=accepted.append, wait_timeout_seconds=3)
    assert accepted == [{"taskId": "task-1"}]
    assert sum(request.data is not None for request in calls) == 1


@pytest.mark.parametrize("mutation,error", [("partial", "not a successful"), ("invalid", "invalid native"),
    ("text_content", "duplicate content"), ("doctags_content", "duplicate content")])
def test_invalid_result_is_not_persisted(conversion, mutation, error):
    source, _, result = conversion
    if mutation == "partial":
        result["status"] = "partial_success"
    elif mutation == "invalid":
        result["document"]["json_content"] = {}
    else:
        result["document"][mutation] = "duplicate"
    with pytest.raises(RemoteDoclingError, match=error):
        _parse(source, remote_task={}, on_remote_task=lambda _: None)
    assert list(source.parent.iterdir()) == [source]


def test_missing_auth_or_control_never_submits(conversion):
    source, calls, _ = conversion
    token = document_processing_authorization.set(None)
    try:
        with pytest.raises(RemoteDoclingError, match="credential"):
            _parse(source)
    finally:
        document_processing_authorization.reset(token)
    with pytest.raises(RemoteDoclingError, match="host-owned task") as failure:
        _parse(source)
    assert failure.value.code == 'REMOTE_PARSE_SUBMISSION_UNKNOWN'
    with pytest.raises(RemoteDoclingError, match="progress persistence"):
        _parse(source, remote_task={})
    assert calls == []


@pytest.mark.parametrize("status", [401, 302])
def test_http_error_and_redirect_redact_credentials(conversion, monkeypatch, status):
    from urllib.error import HTTPError
    from semantica import project_remote_docling as module
    source, _, _ = conversion
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, status, 'fixture-secret', {}, None)
    monkeypatch.setattr(module, "build_opener", lambda *_: Opener())
    with pytest.raises(RemoteDoclingError, match=f"HTTP {status}") as failure:
        _parse(source, remote_task={}, on_remote_task=lambda _: None)
    assert 'fixture-secret' not in str(failure.value)
    assert module._NoRedirect().redirect_request(None, None, status, '', {}, 'http://other') is None


def test_remote_profile_has_no_credential_configuration():
    assert "authorizationEnv" not in json.dumps(DocumentProcessingProfile.model_json_schema(by_alias=True))
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        DocumentProcessingProfile.model_validate({"mode": "remote", "endpoint": "https://docling.test",
            "bindingId": "docling", "authorizationEnv": "SHOULD_NOT_EXIST"})


def test_real_jsonl_worker_rejects_unknown_submission_with_typed_error(tmp_path):
    from semantica.source import source_content_revision
    source = tmp_path/'source.pdf'
    source.write_bytes(b'fixture')
    raw = {'id':'parse','method':'parse_source','documentProcessingAuthorization':'fixture','params':{
        'source':{'sourceId':'pdf','filePath':str(source),'name':source.name,
                  'mimeType':'application/pdf','materialRevision':source_content_revision(source)},
        'outputDir':str(tmp_path/'output'),'forceOcr':False,
        'documentProcessing':{'mode':'remote','endpoint':'http://not-used','bindingId':'fixture'}}}
    process = subprocess.run([sys.executable,'-m','semantica.semantic_worker'],input=json.dumps(raw)+'\n',
                             capture_output=True,text=True,timeout=15,check=True)
    response = json.loads(process.stdout.splitlines()[-1])
    assert response['ok'] is False
    assert response['error']['code'] == 'REMOTE_PARSE_SUBMISSION_UNKNOWN'
    assert not (tmp_path/'output').exists()


def test_remote_input_response_and_task_identity_are_byte_bounded(conversion, monkeypatch):
    from semantica import project_remote_docling as module
    from semantica.semantic_artifact_schema import RemoteConversionTask
    source, calls, _ = conversion
    monkeypatch.setattr(module, 'MAX_UPLOAD_BYTES', 3)
    with pytest.raises(RemoteDoclingError, match='upload byte budget'):
        _parse(source,remote_task={},on_remote_task=lambda _: None)
    assert calls == []
    monkeypatch.setattr(module, 'MAX_RESULT_BYTES', 10)
    with pytest.raises(RemoteDoclingError, match='response exceeded byte budget'):
        _parse(source,remote_task={'taskId':'task-1'})
    assert all(request.data is None for request in calls)
    with pytest.raises(ValueError, match='1024 UTF-8 bytes'):
        RemoteConversionTask.model_validate({'taskId':'漢'*342})
    with pytest.raises(RemoteDoclingError, match='task identity is invalid'):
        _parse(source,remote_task={'taskId':'漢'*342})


def test_worker_requests_isolate_document_processing_authorization(monkeypatch):
    from semantica import semantic_worker
    monkeypatch.setattr(semantic_worker, "_dispatch", lambda request, progress: {"token": document_processing_token()})
    for credential in ("secret-one", "secret-two", None):
        assert semantic_worker.handle_request({"id": "fixture", "method": "schema",
            "documentProcessingAuthorization": credential})["token"] == credential


@pytest.mark.parametrize('task',[None,{}])
def test_remote_profile_plain_text_reports_native_owner_without_submission(tmp_path,task):
    from semantica.semantic_worker import handle_request
    from semantica.source import source_content_revision
    source = tmp_path/'source.txt'
    source.write_text('Native content')
    events = []
    result = handle_request({'id':'parse','method':'parse_source','params':{
        'source':{'sourceId':'text','filePath':str(source),'name':source.name,
                  'mimeType':'text/plain','materialRevision':source_content_revision(source)},
        'outputDir':str(tmp_path/'output'),'forceOcr':False,
        'documentProcessing':{'mode':'remote','endpoint':'http://not-used','bindingId':'fixture'},
        **({'remoteTask':task} if task is not None else {})}},progress=events.append)
    assert result['ok'], result
    assert result['result']['sourceHeader']['parser'] == 'semantica.text'
    assert result['result']['sourceHeader']['origin'] == 'native'
    assert not any('remoteTask' in event for event in events)
