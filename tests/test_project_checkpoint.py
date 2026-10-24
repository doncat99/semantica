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
from semantica.semantic_artifact_errors import SemanticArtifactError
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request, _typed_prompt_context


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_completed_results_are_rejected_independent_of_directory_order(tmp_path, reverse):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    roots = []
    for name in ("first", "second"):
        checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / name)["params"]))
        checkpoint.write("completed", "same-unit", {"text": name})
        roots.append(str(checkpoint.root))
    params = _request(source, tmp_path / "resume")["params"]
    params["resumeCheckpointDirs"] = list(reversed(roots)) if reverse else roots
    with pytest.raises(SnapshotCheckpointError, match="conflicting completed work"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert not (tmp_path / "resume" / "checkpoint").exists()


def test_completed_result_cannot_be_overwritten_with_different_content(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "output")["params"]))
    checkpoint.write("completed", "same-unit", {"text": "first"})
    with pytest.raises(SnapshotCheckpointError, match="conflicting completed work"):
        checkpoint.write("completed", "same-unit", {"text": "second"})
    assert checkpoint.read("completed", "same-unit") == {"text": "first"}


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
    from semantica.project_checkpoint import _bytes, _digest
    entry_path = restored._path("relay", key)
    entry_path.write_bytes(_bytes({"fence": restored.fence, "digest": _digest(_bytes(cached)), "payload": cached}))
    token = active_checkpoint.set(restored)
    try:
        with pytest.raises(SnapshotCheckpointError, match="failed verification"):
            _embed_texts(["A source"], relay)
    finally:
        active_checkpoint.reset(token)
    assert len(calls) == 1


def test_model_switch_preserves_generation_but_rebuilds_embedding_space(tmp_path, monkeypatch):
    from copy import deepcopy
    from semantica.project_checkpoint import active_checkpoint
    from semantica.semantic_artifact_builder import _embed_texts, _project_model_provider

    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "output", recipe="model")["params"]
    calls = []

    class Response:
        status = 200
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self):
            return json.dumps(self.payload).encode()

    def send(request, timeout):
        payload = json.loads(request.data)
        calls.append(payload)
        if "input" in payload:
            # Both spaces deliberately have the same dimension.
            return Response({"model": payload["model"], "data": [{"index": 0, "embedding": [1.0, 0.5]}]})
        return Response({"model": payload["model"], "choices": [{"finish_reason": "stop",
            "message": {"content": '{"answer":"saved"}'}}]})

    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setattr("urllib.request.urlopen", send)
    original = None
    for index in range(3):
        current = deepcopy(params)
        if index:
            current["inputRevision"] = "sha256:" + str(index) * 64
            current["relays"]["model"].update({"modelId": f"model-{index + 1}", "bindingId": f"provider-{index}"})
            current["relays"]["embedding"].update({"modelId": "embedding-2", "bindingId": "new-vector-space"})
        request = SemanticArtifactBuildRequest.model_validate(current)
        token = active_checkpoint.set(SnapshotCheckpoint(request))
        try:
            provider = _project_model_provider(request.relays["model"], "knowledge_explanation")
            assert json.loads(provider.generate(f"Prompt revision {index}", business_context={"source": "immutable"})) == {"answer": "saved"}
            receipt = provider.receipts[0]
            if original is None:
                original = receipt.model_dump()
            assert receipt.model_dump() == original
            _, embedding = _embed_texts(["A source"], request.relays["embedding"])
            assert embedding.model == ("embedding-1" if index == 0 else "embedding-2")
        finally:
            active_checkpoint.reset(token)
    assert len([call for call in calls if "messages" in call]) == 1
    assert len([call for call in calls if "input" in call]) == 2


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
                        "entities": [{"text": "A source", "label": "CONCEPT", "occurrence": 0,
                                      "attributes": {}, "confidence": 0.9}]}
                response = {"model": payload["model"], "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}
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
        # Native imports can take over 30s on a cold machine; this is not a relay timeout.
        if not first_call.wait(90):
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
        stdout, stderr = resumed.communicate(json.dumps(request) + "\n", timeout=90)
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
        stdout, stderr = repeated.communicate(json.dumps(request) + "\n", timeout=90)
        assert repeated.returncode == 0, stderr
        assert json.loads(stdout.strip().splitlines()[-1]) == result
        assert len(calls) == count
        assert not list((tmp_path / "output" / "checkpoint").glob("provenance-*.json"))
        assert parsed_artifact.read_bytes() == parsed_bytes
        source.write_text("The material changed without changing its declared revision.")
        changed = worker()
        try:
            stdout, stderr = changed.communicate(json.dumps(request) + "\n", timeout=90)
        except subprocess.TimeoutExpired:
            changed.kill()
            changed.communicate(timeout=10)
            raise
        assert changed.returncode == 0, stderr
        failure = json.loads(stdout.strip().splitlines()[-1])
        assert not failure["ok"]
        assert "source material revision does not match immutable bytes" in failure["error"]["message"]
        assert len(calls) == count
        assert parsed_artifact.read_bytes() == parsed_bytes
    finally:
        resumed_server.shutdown()
        resumed_server.server_close()


@pytest.mark.parametrize("switch_model", [False, True])
@pytest.mark.parametrize("material_change", ["none", "add", "remove", "revision"])
@pytest.mark.parametrize("completed", [False, True])
def test_new_run_reuses_extraction_windows(tmp_path, monkeypatch, switch_model, material_change, completed, formula_change=None):
    source = tmp_path / "source.txt"
    # Keep two substantive native windows so the test exercises checkpoint
    # reuse without relying on a trailing whitespace-only chunk.
    source.write_text("A source explains durable knowledge production. " * 300, encoding="utf-8")
    first = _request(source, tmp_path / "first", recipe="model")
    from tests.test_semantic_artifact import _parsed_ref
    if formula_change:
        import fitz
        source = tmp_path / "source.pdf"
        with fitz.open() as pdf:
            for _ in range(3):
                page = pdf.new_page()
                page.insert_textbox(fitz.Rect(30, 30, 560, 800),
                    "A source explains durable knowledge production. " * 55, fontsize=10)
            pdf.save(source)
        first = _request(source, tmp_path / "first", recipe="model", prepare=False)
        first["params"]["sources"][0]["mimeType"] = "application/pdf"
        first["params"]["documentProcessing"] = {"mode": "native"}
        first["params"]["parsedSources"] = [_parsed_ref(first["params"], first["params"]["sources"][0])]
        if formula_change == "disable":
            first["params"]["recipe"]["formulaSemanticsSourceIds"] = ["source-1"]
    from copy import deepcopy
    extra = tmp_path / "extra.txt"
    extra.write_text("A source describes a different durable topic.")
    secondary = _request(extra, tmp_path / "extra", recipe="model")["params"]["sources"][0]
    secondary["sourceId"] = "source-2"
    if material_change in ("remove", "revision", "keep"):
        first["params"]["sources"].append(secondary)
        first["params"]["parsedSources"].append(_parsed_ref(first["params"], secondary))
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
        if len(calls) == 3 and not completed:
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
                "entities": [{"text": "A source", "label": "CONCEPT", "occurrence": 0,
                              "attributes": {}, "confidence": 0.9}]}
        return Response({"model": payload["model"], "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(content)}}], "usage": {"completion_tokens": 100}})

    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setattr("urllib.request.urlopen", relay)
    from semantica import semantic_artifact_builder as builder
    if completed:
        first_result = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(first["params"]))
    else:
        with pytest.raises(Exception, match="MODEL_GATEWAY_COOLDOWN"):
            build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(first["params"]))
    checkpoint = tmp_path / "first" / "checkpoint"
    if not completed:
        assert not list(checkpoint.glob("relay-*.json"))
        assert len(list(checkpoint.glob("extraction-*.json"))) == 2
    first_window_prompts = calls[:2]
    first_call_count = len(calls)
    unchanged_prompts = [prompt for prompt in calls if "different durable topic" in prompt]

    second = deepcopy(first)
    second["params"]["outputDir"] = str(tmp_path / "second")
    if formula_change:
        second["params"]["recipe"]["formulaSemanticsSourceIds"] = ["source-1"] if formula_change == "enable" else []
    if completed:
        second["params"]["baseSnapshot"] = {"snapshotId": first_result["snapshot"].id,
            "snapshotPath": str(first_result["snapshot_path"]), "artifactDigest": first_result["snapshot_digest"],
            "schemaDigest": first["params"]["release"]["schemaDigest"]}
    if material_change == "remove":
        second["params"]["sources"] = second["params"]["sources"][:1]
        second["params"]["parsedSources"] = second["params"]["parsedSources"][:1]
    elif material_change in ("add", "revision"):
        if material_change == "revision":
            from semantica.source import source_content_revision
            extra.write_text("A source describes a revised durable topic.")
            secondary["materialRevision"] = source_content_revision(extra)
        second["params"]["sources"] = [second["params"]["sources"][0], secondary]
        second["params"]["parsedSources"] = [second["params"]["parsedSources"][0], _parsed_ref(second["params"], secondary)]
    second["params"]["parallelism"] = 1
    second["params"]["relays"]["model"]["maxOutputTokens"] = 393216
    if switch_model:
        second["params"]["inputRevision"] = "sha256:" + "9" * 64
        second["params"]["relays"]["model"].update({
            "modelId": "replacement-model", "bindingId": "replacement-provider",
            "contextWindowTokens": 1000000, "maxOutputTokens": 32768,
        })
    second["params"]["resumeCheckpointDirs"] = [str(checkpoint)]
    quota_exhausted = False
    result = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert result["snapshot"] is not None
    if switch_model:
        models = {receipt.model for receipt in result["snapshot"].model_receipts
                  if receipt.operation == "structured_extraction"}
        assert models == ({"model-1", "replacement-model"} if not completed or material_change in ("add", "revision") else {"model-1"})
    if formula_change:
        assert len(calls) > first_call_count
        assert unchanged_prompts
        assert all(calls.count(prompt) == 1 for prompt in unchanged_prompts)
    else:
        assert all(calls.count(prompt) == 1 for prompt in first_window_prompts)
    second_checkpoint = tmp_path / "second" / "checkpoint"
    assert len(list(second_checkpoint.glob("extraction-entities-*.json"))) >= 2
    assert not list(second_checkpoint.glob("embedding-batch-*.json"))
    embedding_entries = [json.loads(path.read_bytes())["payload"]
                         for path in second_checkpoint.glob("relay-*.json")
                         if json.loads(path.read_bytes())["payload"]["receipt"]["operation"] == "embedding"]
    assert embedding_entries

    # A vector-space change must reuse the entire non-vector pipeline.
    from copy import deepcopy
    third = deepcopy(second)
    third["params"]["outputDir"] = str(tmp_path / "third")
    third["params"]["resumeCheckpointDirs"] = [str(second_checkpoint)]
    third["params"]["baseSnapshot"] = {"snapshotId": result["snapshot"].id,
        "snapshotPath": str(result["snapshot_path"]), "artifactDigest": result["snapshot_digest"],
        "schemaDigest": second["params"]["release"]["schemaDigest"]}
    third["params"]["relays"]["embedding"].update({"modelId": "new-vector-model", "bindingId": "new-vector-binding"})
    third["params"]["release"]["schemaDigest"] = "sha256:" + "e" * 64
    completed_calls = len(calls)
    monkeypatch.setattr(builder, "_parse_source", lambda *args, **kwargs: pytest.fail("completed source was reparsed"), raising=False)
    rebuilt = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(third["params"]))
    assert len(calls) == completed_calls
    if formula_change:
        reverted = deepcopy(third)
        reverted["params"]["outputDir"] = str(tmp_path / "reverted")
        reverted["params"]["resumeCheckpointDirs"] = [str(tmp_path / "third" / "checkpoint")]
        reverted["params"]["recipe"] = deepcopy(first["params"]["recipe"])
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(reverted["params"]))
        assert len(calls) == completed_calls

    # A surviving window plan alone is insufficient: a missing paid result
    # must not turn into a new provider request either.
    import shutil
    partial_checkpoint = tmp_path / "partial-checkpoint"
    shutil.copytree(second_checkpoint, partial_checkpoint)
    for path in partial_checkpoint.glob("extraction-entities-*.json"):
        path.unlink()
    partial = deepcopy(third)
    partial["params"]["outputDir"] = str(tmp_path / "partial-completed-work")
    partial["params"]["resumeCheckpointDirs"] = [str(partial_checkpoint)]
    with pytest.raises(SemanticArtifactError, match="completed work.*missing") as gap:
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(partial["params"]))
    assert gap.value.code == "COMPLETED_WORK_RECOVERY_GAP"
    assert len(calls) == completed_calls
    assert rebuilt["snapshot"].entities == result["snapshot"].entities
    assert rebuilt["snapshot"].evidence_spans == result["snapshot"].evidence_spans
    assert any(receipt.model == "new-vector-model" for receipt in rebuilt["snapshot"].model_receipts)

    # Old hosts deleted completed checkpoints. Never silently pay again when
    # the adopted snapshot proves this source was already processed.
    missing = deepcopy(third)
    missing["params"]["outputDir"] = str(tmp_path / "missing-completed-work")
    missing["params"]["resumeCheckpointDirs"] = []
    with pytest.raises(SemanticArtifactError, match="completed work.*missing") as gap:
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(missing["params"]))
    assert gap.value.code == "COMPLETED_WORK_RECOVERY_GAP"
    assert len(calls) == completed_calls


@pytest.mark.parametrize("change", ["enable", "disable"])
def test_formula_requirement_change_allows_new_work_and_protects_completed_retry(tmp_path, monkeypatch, change):
    test_new_run_reuses_extraction_windows(tmp_path, monkeypatch, False, "keep", True, formula_change=change)


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
    with pytest.raises(SnapshotCheckpointError, match="entry digest or fence mismatch"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(request["params"]))


def test_checkpoint_preserves_extraction_across_identity_policy_changes(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    request = _request(source, tmp_path / "output")
    original = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(request["params"]))
    key = "a" * 64
    original.write("extraction-entities", key, {"paid": True})
    request["params"]["identityPropertySchema"] = {"external_key": {"identity": True}}
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(request["params"]))
    assert resumed.read("extraction-entities", key) == {"paid": True}


def test_checkpoint_retains_results_across_native_resolution_version_changes(tmp_path, monkeypatch):
    from semantica.project_checkpoint import PROCESSING_CONTRACTS

    source = tmp_path / "source.txt"
    source.write_text("A source")
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "output")["params"])
    checkpoint = SnapshotCheckpoint(request)
    checkpoint.write('completed', 'unit', {'text': 'saved'})
    manifest = (checkpoint.root / "manifest.json").read_bytes()
    monkeypatch.setitem(PROCESSING_CONTRACTS, "identityResolution", "different-policy")
    assert SnapshotCheckpoint(request).read('completed', 'unit') == {'text': 'saved'}
    assert (checkpoint.root / "manifest.json").read_bytes() == manifest


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


def test_new_run_reuses_only_matching_document_after_ocr_change(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source", encoding="utf-8")
    first = _request(source, tmp_path / "first")
    first_checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(first["params"]))
    key = {"sourceId": "source-1", "contentHash": first["params"]["sources"][0]["materialRevision"], "forceOcr": False}
    first_checkpoint.write("document", key, {"document": "old"})

    second = _request(source, tmp_path / "second")
    second["params"]["recipe"]["forceOcrSourceIds"] = ["source-1"]
    second["params"]["resumeCheckpointDirs"] = [str(first_checkpoint.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert resumed.read("document", key) == {"document": "old"}
    assert resumed.read("document", {**key, "forceOcr": True}) is None


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
    with pytest.raises(SnapshotCheckpointError, match="failed verification"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))



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


def test_package_upgrade_reuses_historical_completed_chunks(tmp_path):
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
    restored = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(second["params"]))
    assert restored.read("extraction-entities", key) == saved
    assert next(prior.root.glob("extraction-entities-*.json")).read_bytes() == original
