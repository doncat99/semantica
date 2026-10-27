import io
import json
from zipfile import ZipFile
import os
import threading
from types import SimpleNamespace
import urllib.error
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from semantica.semantic_artifact_builder import _canonical_graph_projection
from semantica.semantic_artifact_builder import build_semantic_artifacts, parse_source_artifact
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, ParseSourceRequest
from semantica.semantic_artifact_schema import KnowledgeEntity, KnowledgeRelation, ModelReceipt, SemanticArtifact, stable_digest
from semantica.semantic_worker import serve
from semantica.source import source_content_revision

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def _typed_prompt_context(payload):
    prompt = payload["messages"][0]["content"]
    marker = "Input JSON:\n"
    return json.JSONDecoder().raw_decode(prompt[prompt.index(marker) + len(marker):])[0]


def _native_report(payload, title="Explanation"):
    import re
    prompt = payload["messages"][0]["content"]
    refs = re.findall(r"^(?:- )?\[([^\]\n]+)\]: ", prompt, re.MULTILINE)
    assert refs, prompt
    return {"title": title, "summary": "Supported explanation", "findings": [
        {"summary": title, "explanation": "Explained from the source.",
         "citations": [{"evidence_id": refs[0]}]}]}


def _worker_output(stdout):
    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return events, events[-1]


def _host_snapshot(graph_path, project_id="project-1"):
    snapshot = SemanticArtifact.model_validate_json(graph_path.read_bytes())
    assert snapshot.project_id == project_id
    return snapshot


def test_worker_publishes_one_canonical_snapshot_queryable_without_reconstruction(tmp_path):
    from semantica.semantic_worker import handle_request
    from semantica.semantic_query_worker import handle_request as query
    source = tmp_path / "native.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    response = handle_request(_request(source, tmp_path))
    result = response["result"]
    graph = next(item for item in result["artifacts"] if item["kind"] == "semantic-graph")
    retrieval = next(item for item in result["artifacts"] if item["kind"] == "retrieval-index")
    snapshot = SemanticArtifact.model_validate_json(Path(graph["path"]).read_bytes())
    answer = query({"protocol": "semantica.semantic-query.v1", "id": "query:canonical", "method": "query",
        "params": {"projectId": snapshot.project_id, "snapshotId": snapshot.id,
            "snapshot": {k: graph[k] for k in ("digest", "path", "kind", "mediaType")},
            "retrieval": {k: retrieval[k] for k in ("digest", "path", "kind", "mediaType")},
            "query": "Ada", "limit": 5}})
    assert answer["ok"] is True, answer
    assert answer["result"]["contexts"]
    assert answer["result"]["retrievalManifestId"] == retrieval["revision"]


def test_worker_processes_parse_build_and_query_share_canonical_artifact(tmp_path):
    import subprocess
    import sys

    def invoke(module, request):
        completed = subprocess.run([sys.executable, '-m', module],
            input=json.dumps(request) + '\n', text=True, capture_output=True, timeout=90,
            env={**os.environ, 'PYTHONPATH': '', 'PYTHONHOME': '',
                 'ONTOSCIENCE_ACCEPTANCE_NO_CREDENTIAL': ''})
        assert completed.returncode == 0, completed.stderr
        messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        responses = [m for m in messages if m.get('id') == request['id'] and 'ok' in m]
        assert len(responses) == 1 and responses[0]['ok'] is True, json.dumps(responses, indent=2)
        assert responses[0]['protocol'] == request['protocol']
        return responses[0]['result']

    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    request = _request(source, tmp_path / 'build', prepare=False)
    params = request['params']
    for name, relay in params['relays'].items():
        relay['authorizationEnv'] = 'ONTOSCIENCE_ACCEPTANCE_NO_CREDENTIAL'
        endpoint = 'embeddings' if name == 'embedding' else 'chat/completions'
        relay['baseUrl'] = 'http://127.0.0.1:1/v1/' + endpoint
    parsed = invoke('semantica.semantic_worker', {
        'protocol': request['protocol'], 'id': 'parse', 'method': 'parse_source',
        'params': {'source': params['sources'][0], 'outputDir': str(tmp_path / 'parsed'),
                   'forceOcr': False, 'documentProcessing': {'mode': 'local'}}})
    params['parsedSources'] = [{'sourceId': params['sources'][0]['sourceId'],
        'artifactPath': parsed['artifactPath'], 'artifactDigest': parsed['artifactDigest']}]
    params['checkpointDir'] = str(tmp_path / 'saved-progress')
    built = invoke('semantica.semantic_worker', request)
    graph = next(a for a in built['artifacts'] if a['kind'] == 'semantic-graph')
    retrieval = next(a for a in built['artifacts'] if a['kind'] == 'retrieval-index')
    snapshot = SemanticArtifact.model_validate_json(Path(graph['path']).read_bytes())
    assert graph['revision'] == snapshot.id
    manifest = next(m for m in snapshot.retrieval_manifests if m.retrieval_type == 'graph')
    assert retrieval['revision'] == manifest.id
    assert manifest.source_snapshot_id == snapshot.id
    assert manifest.artifact_hash == retrieval['digest']
    assert (tmp_path / 'saved-progress' / 'manifest.json').is_file()
    answer = invoke('semantica.semantic_query_worker', {
        'protocol': 'semantica.semantic-query.v1', 'id': 'query', 'method': 'query',
        'params': {'projectId': snapshot.project_id, 'snapshotId': snapshot.id,
            'snapshot': {k: graph[k] for k in ('digest', 'path', 'kind', 'mediaType')},
            'retrieval': {k: retrieval[k] for k in ('digest', 'path', 'kind', 'mediaType')},
            'query': 'Ada', 'limit': 5}})
    assert answer['contexts']
    assert answer['retrievalManifestId'] == retrieval['revision']


def test_build_validates_native_identity_policy_before_model_calls(tmp_path, monkeypatch):
    source = tmp_path / "identity.txt"
    source.write_text("Same company")
    raw = _request(source, tmp_path / "output", recipe="model")["params"]
    raw['identityPropertySchema'] = {'key': {'identity': 'yes'}}
    request = SemanticArtifactBuildRequest.model_validate(raw)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid identity policy must fail before paid extraction')
    monkeypatch.setattr('semantica.semantic_artifact_builder._relay_json', forbidden)
    with pytest.raises(ValueError, match='invalid identity property'):
        build_semantic_artifacts(request)


def test_scoped_explanation_reuses_native_grounding_and_rejects_foreign_evidence(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.semantic_artifact_schema import EvidenceSpan, DocumentLocator

    span = EvidenceSpan(id="evidence:1", representation_id="representation:1", quote="Exact source sentence.",
                        locator=DocumentLocator(representation_id="representation:1", origin="native",
                                                quote="Exact source sentence.", quality="precise", start_char=0, end_char=22))
    snapshot = SimpleNamespace(evidence_spans=[span], entities=[], assertions=[], relations=[])
    seen = []

    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            context = kwargs["validation_context"]
            seen.append(context)
            assert span.quote in prompt
            return schema.model_validate({"title": "Meaning", "summary": "Supported",
                "findings": [{"summary": "Meaning", "explanation": "Explained from the source.",
                              "citations": [{"evidence_id": span.id}]}]}, context=context)

    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    target = {"id": "chapter:1", "type": "source-scope", "title": "Foundations"}
    sections, _ = pipeline.explain_evidence(snapshot, target, [span.id], SimpleNamespace(model_id="test", context_window_tokens=500000, max_output_tokens=32768))
    assert sections[0].evidence_ids == [span.id]
    assert seen[0]["target"] == target
    with pytest.raises(pipeline.SemanticArtifactError, match="known evidence"):
        pipeline.explain_evidence(snapshot, target, ["foreign"], None)


def test_native_explanation_preserves_multiple_evidence_batches_with_its_target(monkeypatch):
    from semantica import semantic_artifact_builder as pipeline
    from semantica.semantic_artifact_schema import EvidenceSpan, DocumentLocator, ReportSection

    spans = {ref: EvidenceSpan(id=ref, representation_id="representation:1", quote=f"Source {ref}",
        locator=DocumentLocator(representation_id="representation:1", origin="native",
                                quote=f"Source {ref}", quality="precise", start_char=index * 20,
                                end_char=index * 20 + len(f"Source {ref}"))) for index, ref in enumerate(("evidence:1", "evidence:2"))}
    target = {"id": "chapter:1", "type": "source-scope", "title": "Topic"}
    for span in spans.values():
        span.quote = span.locator.quote = span.quote * 35
    seen = []
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            batch = kwargs["validation_context"]
            seen.append(batch["target"])
            return schema.model_validate({"title": "Source", "summary": "Supported",
                "findings": [{"summary": "Source", "explanation": "Explained",
                              "citations": [{"evidence_id": batch["evidence"][0]["id"]}]}]}, context=batch)
    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    sections, _ = pipeline._grounded_explanation({"target": target, "entities": [], "assertions": [],
        "relations": [], "evidence": [{"id": span.id, "quote": span.quote} for span in spans.values()]},
        SimpleNamespace(model_id='test', context_window_tokens=6500, max_output_tokens=1000))
    assert seen == [target, target]
    assert len(sections) == 2
    assert [section.evidence_ids for section in sections] == [["evidence:1"], ["evidence:2"]]


def test_explanation_reads_verified_semantic_artifact(tmp_path):
    from semantica.semantic_worker import EvidenceExplanationRequest, _verified_snapshot
    from tests.test_semantic_artifact_contract import _snapshot_payload

    artifact = _snapshot_payload()
    raw = json.dumps(artifact).encode()
    path = tmp_path / "semantic-artifact.json"
    path.write_bytes(raw)
    request = EvidenceExplanationRequest.model_validate({"snapshotPath": str(path),
        "snapshotDigest": "sha256:" + __import__("hashlib").sha256(raw).hexdigest(),
        "snapshotId": "snapshot:one", "projectId": "project-1", "outputDir": str(tmp_path),
        "target": {"id": "source:1", "type": "source-scope", "title": "Topic"}, "evidenceIds": ["ev-1"],
        "relay": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions",
                  "capability": "knowledge.snapshot.generate", "contextWindowTokens": 4096,
                  "maxOutputTokens": 1024, "modelId": "model-1", "receipts": "required"}})
    assert _verified_snapshot(request).id == "snapshot:one"

def test_semantic_worker_explains_verified_graph_and_returns_digest_and_receipt(tmp_path, monkeypatch):
    import hashlib
    from semantica import semantic_worker
    from semantica.semantic_artifact_schema import ReportSection, ModelReceipt
    from tests.test_semantic_artifact_contract import _snapshot_payload

    graph = _snapshot_payload()
    raw = json.dumps(graph).encode()
    path = tmp_path / "semantic-graph.json"
    path.write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    receipt = ModelReceipt.model_validate(_snapshot_payload()["model_receipts"][0])
    seen = []

    def explain(snapshot, target, evidence_ids, relay):
        seen.append((snapshot.id, target, evidence_ids, relay.model_id))
        return [ReportSection(title="Meaning", text="Grounded explanation.", evidence_ids=["ev-1"])], [receipt]

    from semantica import semantic_artifact_builder
    monkeypatch.setattr(semantic_artifact_builder, "explain_evidence", explain)
    params = {"snapshotPath": str(path), "snapshotDigest": digest, "snapshotId": "snapshot:one",
              "projectId": "project-1", "outputDir": str(tmp_path),
              "target": {"id": "section:1", "type": "source-scope", "title": "First section"},
              "evidenceIds": ["ev-1"],
              "relay": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions",
                        "capability": "knowledge.snapshot.generate", "contextWindowTokens": 4096,
                        "maxOutputTokens": 1024, "modelId": "model-1", "receipts": "required"}}
    request = {"protocol": "semantica.semantic-worker.v1", "id": "explain-1", "method": "explain_evidence", "params": params}
    response = semantic_worker.handle_request(request)
    assert response["ok"] is True
    result = response["result"]
    artifact = json.loads((tmp_path / "evidence-explanation.json").read_text())
    assert seen == [("snapshot:one", params["target"], ["ev-1"], "model-1")]
    assert artifact["snapshotDigest"] == digest and artifact["sections"][0]["evidence_ids"] == ["ev-1"]
    assert artifact["modelReceipts"][0]["id"] == receipt.id
    assert result["sectionCount"] == result["receiptCount"] == 1
    assert result["digest"] == "sha256:" + hashlib.sha256((tmp_path / "evidence-explanation.json").read_bytes()).hexdigest()

    (tmp_path / "evidence-explanation.json").unlink()
    with pytest.raises(semantic_worker.SemanticArtifactError, match="digest"):
        semantic_worker.handle_request({**request, "params": {**params, "snapshotDigest": H1}})
    assert not (tmp_path / "evidence-explanation.json").exists()


def test_unique_quote_ignores_model_position_but_duplicate_requires_occurrence():
    from semantica.semantic_extract.methods import _exact_occurrence
    from semantica.utils.exceptions import ProcessingError

    text = "Green Bonds and Private Equity. Green Bonds"
    assert _exact_occurrence(text, "Private Equity", 590) == (16, 30, 0)
    with pytest.raises(ProcessingError, match="occurrence"):
        _exact_occurrence(text, "Green Bonds", 590)


def test_relay_http_failure_preserves_safe_structured_error(monkeypatch):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _relay_json, SemanticArtifactError

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    def rejected(_request, timeout):
        raise urllib.error.HTTPError("http://127.0.0.1/", 500, "Internal Server Error", {}, io.BytesIO(
            b'{"error":{"code":"INTERNAL_ERROR","message":"provider failed for test-token","retryable":true,"status":500}}'))
    monkeypatch.setattr("urllib.request.urlopen", rejected)
    relay = SimpleNamespace(authorization_env="OPENAI_API_KEY", base_url="http://127.0.0.1/v1/chat/completions", model_id="model-1", binding_id="default", context_window_tokens=500000, max_output_tokens=32768)
    with pytest.raises(SemanticArtifactError, match="structured_extraction relay returned HTTP 500: INTERNAL_ERROR") as failure:
        _relay_json(relay, {"model": "model-1"}, "structured_extraction")
    assert failure.value.status == 500
    assert failure.value.code == "INTERNAL_ERROR"
    assert failure.value.retryable is True
    assert "test-token" not in str(failure.value)
    assert "provider failed" not in str(failure.value)


def test_relay_preserves_diagnostics_after_large_error_message(monkeypatch):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _relay_json, SemanticArtifactError

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    body = json.dumps({"error": {"code": "MODEL_GATEWAY_COOLDOWN", "message": "private " * 1000,
        "diagnostic": {"origin": "local_cooldown", "status": 403,
                       "code": "pre_consume_token_quota_failed", "upstreamRequestId": "upstream-1"}}}).encode()
    def rejected(_request, timeout):
        raise urllib.error.HTTPError("http://127.0.0.1/", 503, "Unavailable", {}, io.BytesIO(body))
    monkeypatch.setattr("urllib.request.urlopen", rejected)
    relay = SimpleNamespace(authorization_env="OPENAI_API_KEY", base_url="http://127.0.0.1/", model_id="m", binding_id="default", context_window_tokens=500000, max_output_tokens=32768)
    with pytest.raises(SemanticArtifactError) as failure:
        _relay_json(relay, {"model": "m"}, "structured_extraction")
    assert failure.value.diagnostic["code"] == "pre_consume_token_quota_failed"
    assert failure.value.diagnostic["upstreamRequestId"] == "upstream-1"
    assert "private" not in str(failure.value)


def test_relay_failure_recursively_projects_only_safe_gateway_diagnostics():
    from semantica.semantic_artifact_builder import _safe_diagnostic, _safe_gateway_receipt

    diagnostic = _safe_diagnostic({
        "origin": "upstream_http_error", "status": 503, "upstreamRequestId": "upstream-1",
        "safeDetails": "secret provider response", "trigger": {
            "occurredAt": "2026-10-08T00:00:00Z", "code": "MODEL_GATEWAY_COOLDOWN",
            "requestId": "local-1", "message": "secret nested message", "token": "secret-token",
        }, "token": "secret-token",
    })
    assert diagnostic == {
        "origin": "upstream_http_error", "status": 503, "upstreamRequestId": "upstream-1",
        "trigger": {"occurredAt": "2026-10-08T00:00:00Z", "code": "MODEL_GATEWAY_COOLDOWN", "requestId": "local-1"},
    }

    receipt = _safe_gateway_receipt({
        "requestId": "local-1", "policyRevision": "v1", "requested": {"bindingId": "default", "modelId": "m"},
        "attempts": [{"bindingId": "default", "modelId": "m", "index": 0, "status": 503,
                     "errorCode": "UPSTREAM_UNAVAILABLE", "errorMessage": "secret response",
                     "diagnostic": {"origin": "upstream_http_error", "status": 503,
                                    "safeDetails": "secret provider response", "token": "secret-token"}}],
        "diagnostic": {"origin": "upstream_http_error", "status": 503, "safeDetails": "secret response"},
        "prompt": "private source content",
    })
    rendered = json.dumps(receipt)
    assert "secret" not in rendered
    assert "private source" not in rendered
    assert receipt["attempts"][0]["diagnostic"] == {"origin": "upstream_http_error", "status": 503}


def test_relay_waits_for_complete_gateway_response(monkeypatch):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _relay_json

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"choices":[]}'

    def respond(_request, timeout):
        assert timeout > 15 * 60
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", respond)
    relay = SimpleNamespace(authorization_env="OPENAI_API_KEY", base_url="http://127.0.0.1/v1/chat/completions", model_id="model-1", binding_id="default", context_window_tokens=500000, max_output_tokens=32768)
    response, receipt = _relay_json(relay, {"model": "model-1"}, "structured_extraction")
    assert response == {"choices": []}
    assert receipt.operation == "structured_extraction"


def test_product_output_rejects_citation_shape_through_native_typed_provider(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline

    outputs = [
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [5]}]},
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}]},
    ]
    prompts = []

    def relay_response(relay, payload, operation, *, business_context=None):
        prompts.append(payload["messages"][0]["content"])
        result = {"model": relay.model_id, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(outputs.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(prompts)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    result, receipts = pipeline._product_json(
            SimpleNamespace(model_id="model-1", binding_id="default", max_output_tokens=393216, context_window_tokens=500000),
            "source_classification",
            "Classify the source.",
            {"evidence": [{"id": "evidence:source", "quote": "Source quote"}]},
            pipeline._ClassificationOutput,
        )
    assert result.assignments[0].citations[0].evidence_id == "evidence:source"
    assert len(receipts) == 2
    assert not outputs


def test_typed_retry_rejects_cached_invalid_relay_response(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.project_checkpoint import active_checkpoint

    class Checkpoint:
        def __init__(self):
            self.created_at = "2026-10-26T00:00:00Z"
            self.entries = {}
            self.rejected = set()

        def _key(self, kind, key):
            return kind, json.dumps(key, sort_keys=True, separators=(",", ":"))

        def read(self, kind, key):
            return None if self._key(kind, key) in self.rejected else self.entries.get(self._key(kind, key))

        def write(self, kind, key, payload):
            self.entries[self._key(kind, key)] = payload

        def reject(self, kind, key, payload):
            self.rejected.add(self._key(kind, key))

    checkpoint = Checkpoint()
    valid = {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                              "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}]}
    responses = [{"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                                    "citations": [5]}]}, valid]
    calls = []

    def relay_response(relay, payload, operation, _checkpoint, _cache_key):
        calls.append(len(responses))
        result = {"model": relay.model_id, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(responses.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(calls)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_uncached", relay_response)
    relay = SimpleNamespace(model_id="model-1", binding_id="default", max_output_tokens=393216)
    token = active_checkpoint.set(checkpoint)
    try:
        result, receipts = pipeline._product_json(
            relay, "source_classification", "Classify the source.",
            {"evidence": [{"id": "evidence:source", "quote": "Source quote"}]},
            pipeline._ClassificationOutput,
        )
    finally:
        active_checkpoint.reset(token)

    assert result.model_dump(mode="json") == valid
    assert calls == [2, 1]
    assert [receipt.id for receipt in receipts] == ["receipt:1", "receipt:2"]


def test_product_result_rejects_cached_invalid_schema_and_regenerates(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.project_checkpoint import active_checkpoint

    class Checkpoint:
        def __init__(self):
            self.created_at = "2026-01-01T00:00:00Z"
            self.entries = {}
            self.rejected = []

        def _key(self, kind, key):
            return kind, json.dumps(key, sort_keys=True, separators=(",", ":"))

        def read(self, kind, key):
            marker = self._key(kind, key)
            rejected = any(self._key(rejected_kind, rejected_key) == marker
                           for rejected_kind, rejected_key, _ in self.rejected)
            return None if rejected else self.entries.get(marker)

        def write(self, kind, key, payload):
            self.entries[self._key(kind, key)] = payload

        def reject(self, kind, key, payload):
            self.rejected.append((kind, key, payload))

    checkpoint = Checkpoint()
    context = {"evidence": [{"id": "evidence:source", "quote": "Source quote"}]}
    key = {"operation": "source_classification", "context": context}
    checkpoint.write("product-result", key, {
        "result": {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                                     "citations": [5]}]},
        "receipts": [],
    })
    valid = {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                               "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}]}
    calls = []

    def relay_response(relay, payload, operation, *, business_context=None):
        calls.append(payload)
        result = {"model": relay.model_id, "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(valid)}}]}
        return result, ModelReceipt(id="receipt:fresh", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    relay = SimpleNamespace(model_id="model-1", binding_id="default", max_output_tokens=393216)
    token = active_checkpoint.set(checkpoint)
    try:
        result, receipts = pipeline._product_json(relay, "source_classification", "Classify the source.", context,
                                                   pipeline._ClassificationOutput)
    finally:
        active_checkpoint.reset(token)

    assert result.model_dump(mode="json") == valid
    assert len(calls) == 1
    assert len(checkpoint.rejected) == 1


@pytest.mark.parametrize('citation', [5, {'evidence_id': 'evidence:foreign'}])
def test_explanation_rejects_invalid_saved_result_and_reuses_replacement(tmp_path, monkeypatch, citation):
    from semantica import semantic_artifact_builder as pipeline
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica.semantic_artifact_schema import SourceBuildInput

    source = tmp_path / 'source.txt'
    source.write_text('Source quote')
    checkpoint = SnapshotCheckpoint.for_source(SourceBuildInput(
        source_id='source:1', name='source.txt', mime_type='text/plain',
        file_path=str(source), material_revision=source_content_revision(source)),
        output_dir=str(tmp_path / 'output'), scope_id='scope:1', recipe={}, created_at='2026-01-01T00:00:00Z')
    context = {'target': {'id': 'source:1', 'type': 'source-scope'},
               'entities': [], 'assertions': [], 'relations': [],
               'evidence': [{'id': 'evidence:source', 'quote': 'Source quote'}]}
    key = {'context': context}
    report = {'title': 'Source', 'summary': 'Supported', 'findings': [
        {'summary': 'Meaning', 'explanation': 'Explained from the source.', 'citations': [citation]}]}
    checkpoint.write('grounded-explanation', key, {'reports': [report], 'receipts': []})
    calls = []

    def relay_response(relay, payload, operation, _checkpoint, _cache_key):
        calls.append(payload)
        valid = {**report, 'findings': [{**report['findings'][0],
                 'citations': [{'evidence_id': 'evidence:source'}]}]}
        return {'model': relay.model_id, 'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(valid)}}]}, ModelReceipt(
                id='receipt:fresh', operation=operation, provider='test', model=relay.model_id,
                input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, '_relay_uncached', relay_response)
    relay = SimpleNamespace(model_id='test', context_window_tokens=500000, max_output_tokens=32768)
    token = active_checkpoint.set(checkpoint)
    try:
        sections, receipts = pipeline._grounded_explanation(context, relay)
        restored_sections, restored_receipts = pipeline._grounded_explanation(context, relay)
    finally:
        active_checkpoint.reset(token)
    assert len(calls) == 1
    assert sections == restored_sections
    assert sections[0].evidence_ids == ['evidence:source']
    assert [item.id for item in receipts] == [item.id for item in restored_receipts] == ['receipt:fresh']
    assert checkpoint.read('grounded-explanation', key)['reports'][0]['findings'][0]['citations'] == [
        {'evidence_id': 'evidence:source'}]


def test_product_output_uses_host_admitted_output_limit(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline

    payloads = []

    def relay_response(relay, payload, operation, *, business_context=None):
        payloads.append(payload)
        result = {"model": relay.model_id, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"assignments": [{
            "dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [
                {"evidence_id": "evidence:source", "quote": "Source quote"},
            ],
        }]})}}]}
        return result, ModelReceipt(id="receipt:1", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    pipeline._product_json(
        SimpleNamespace(model_id="model-1", binding_id="default", max_output_tokens=393216, context_window_tokens=500000),
        "source_classification",
        "Classify the source.",
        {"evidence": [{"id": "evidence:source", "quote": "Source quote"}]},
        pipeline._ClassificationOutput,
    )

    assert payloads[0]["max_tokens"] == 393216


def test_product_output_rejects_semantic_citation_and_vocabulary(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline

    valid = {"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
             "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}
    outputs = [
        {"assignments": [{**valid, "dimension_id": "invented", "citations": [
            {"evidence_id": "evidence:source", "quote": "Altered quote"}]}]},
        {"assignments": [valid]},
    ]
    prompts = []

    def relay_response(relay, payload, operation, *, business_context=None):
        prompts.append(payload["messages"][0]["content"])
        result = {"model": relay.model_id, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(outputs.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(prompts)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    context = {
        "profile": _classification_profile(),
        "evidence": [{"id": "evidence:source", "quote": "Source quote"}],
    }
    result, receipts = pipeline._product_json(
            SimpleNamespace(model_id="model-1", binding_id="default", max_output_tokens=393216, context_window_tokens=500000),
            "source_classification", "Classify the source.", context, pipeline._ClassificationOutput,
        )
    assert result.assignments[0].item_id == "history"
    assert len(receipts) == 2
    assert not outputs


def test_product_output_rejects_large_invalid_payload_without_repair(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline

    quote = "Grounded evidence. " * 2_400
    outputs = [
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [5], "invalid": "x" * 20_000}]},
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [{"evidence_id": "evidence:source", "quote": quote}]}]},
    ]

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self):
            return json.dumps({"model": "model-1", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(outputs.pop(0))}}]}).encode()

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    monkeypatch.setattr("urllib.request.urlopen", lambda _request, timeout: Response())
    result, receipts = pipeline._product_json(
            SimpleNamespace(model_id="model-1", binding_id="default", authorization_env="OPENAI_API_KEY",
                            base_url="http://127.0.0.1/v1/chat/completions", max_output_tokens=393216, context_window_tokens=500000),
            "source_classification",
            "Classify the source.",
            {"evidence": [{"id": "evidence:source", "quote": quote}]},
            pipeline._ClassificationOutput,
        )
    assert result.assignments[0].citations[0].evidence_id == "evidence:source"
    assert len(receipts) == 2
    assert not outputs


def test_source_relations_project_only_existing_multi_source_facts():
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _source_relations
    representations = [SimpleNamespace(id=f"rep:{index}", source_id=f"source:{index}") for index in (1, 2, 3)]
    evidence = [SimpleNamespace(id=f"evidence:{index}", representation_id=f"rep:{index}") for index in (1, 2, 3)]
    relation = KnowledgeRelation(id="relation:1", source_entity_id="left", target_entity_id="right",
        type="depends on", qualifiers={"polarity": "negative", "condition": "in winter"},
        evidence_ids=["evidence:1", "evidence:2"], support_ids=["evidence:1", "evidence:2"], status="candidate")
    original = relation.model_dump()
    projected = _source_relations([relation], evidence, representations)
    assert len(projected) == 1
    assert (projected[0].source_id, projected[0].target_id) == ("source:1", "source:2")
    assert projected[0].entity_relation_ids == [relation.id]
    assert projected[0].evidence_ids == relation.evidence_ids
    assert projected[0].status == "candidate"
    assert relation.model_dump() == original
    assert _source_relations([], evidence, representations) == []
    assert _source_relations([relation.model_copy(update={"evidence_ids": ["evidence:1"]})], evidence, representations) == []


def _classification_profile():
    return {"id": "profile:test", "version": "1", "label": "Document purpose", "description": "Source purpose",
        "dimensions": [{"id": "purpose", "label": "Purpose", "cardinality": "single", "vocabulary": [{"id": "history", "label": "History"}, {"id": "manual", "label": "Manual"}]},
            {"id": "topic", "label": "Topic", "cardinality": "multi", "vocabulary": []}]}


@pytest.mark.parametrize("corruption", ["unknown-id", "altered-quote", "missing-citation", "unknown-category", "cardinality"])
def test_semantic_classification_rejects_invalid_model_evidence(tmp_path, monkeypatch, corruption):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _build_source, _source_passages, _classify_source, SemanticArtifactError
    from semantica.semantic_artifact_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    citation = {"evidence_id": built["passages"][0].id, "quote": built["passages"][0].quote}
    assignment = {"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [citation]}
    if corruption == "unknown-id":
        citation["evidence_id"] = "evidence:invented"
    elif corruption == "altered-quote":
        citation["quote"] = "Ada invented a spaceship."
    elif corruption == "missing-citation":
        assignment["citations"] = []
    elif corruption == "unknown-category":
        assignment["item_id"] = "invented"
    assignments = [assignment]
    if corruption == "cardinality":
        assignments.append({**assignment, "item_id": "manual"})
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    calls = []
    def relay_response(*args, **kwargs):
        calls.append(args)
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"assignments": assignments})}}]}, receipt
    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", relay_response)
    with pytest.raises(SemanticArtifactError):
        _classify_source(built, ClassificationProfile.model_validate(_classification_profile()),
            SimpleNamespace(model_id="test", binding_id="default", max_output_tokens=32768, context_window_tokens=500000))
    assert len(calls) == 3


def test_semantic_classification_preserves_source_offsets_and_unclassified_dimensions(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.semantic_artifact_builder import _build_source, _source_passages, _classify_source
    from semantica.semantic_artifact_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    span = built["passages"][0]
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    output = {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [{"evidence_id": span.id, "quote": span.quote}]}]}
    monkeypatch.setattr(pipeline, "_relay_json", lambda *args, **kwargs: (
        {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}, receipt))
    validations = []
    native_validate = pipeline._ClassificationOutput.model_validate_json
    def validate(cls, value, **kwargs):
        validations.append(value)
        return native_validate(value, **kwargs)
    monkeypatch.setattr(pipeline._ClassificationOutput, "model_validate_json", classmethod(validate))
    classification, _ = _classify_source(built, ClassificationProfile.model_validate(_classification_profile()),
        SimpleNamespace(model_id="test", binding_id="default", max_output_tokens=32768, context_window_tokens=500000))
    assert len(validations) == 1
    assert classification.assignments[0].evidence_ids == [span.id]
    assert classification.unclassified_dimension_ids == ["topic"]
    assert built["text"][span.locator.start_char:span.locator.end_char] == span.quote


def test_docling_evidence_preserves_reading_order_and_physical_locators(tmp_path):
    from semantica.semantic_artifact_builder import _build_source, _docling_cell_evidence, _source_passages
    from semantica.semantic_artifact_schema import SourceBuildInput

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"source")
    source = SourceBuildInput(filePath=str(source_path), sourceId="4830a9a9-25ed-45ac-87d0-afcc80587480",
                              materialRevision=source_content_revision(source_path),
                              mimeType="application/pdf", name="source.pdf")
    text = "Chapter\nRepeated\nRepeated\nx = y\nROE\n12%"
    def bbox(top):
        return {"l": 10, "t": top, "r": 100, "b": top + 10, "coord_origin": "TOPLEFT"}
    raw = {
        "texts": [
            {"self_ref": "#/texts/0", "label": "section_header", "level": 1, "text": "Chapter", "prov": [{"page_no": 1, "bbox": bbox(10)}]},
            {"self_ref": "#/texts/1", "label": "text", "text": "Repeated", "prov": [{"page_no": 1, "bbox": bbox(30)}]},
            {"self_ref": "#/texts/2", "label": "text", "text": "Repeated", "prov": [{"page_no": 2, "bbox": bbox(10)}]},
            {"self_ref": "#/texts/3", "label": "formula", "text": "x = y", "orig": "x equals y", "prov": [{"page_no": 2, "bbox": bbox(30)}]},
        ],
        "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 3, "bbox": bbox(10)}],
                    "data": {"table_cells": [
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 0, "row_span": 1, "col_span": 1, "text": "ROE", "bbox": bbox(20)},
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 1, "row_span": 1, "col_span": 1, "text": "12%", "bbox": bbox(20)},
                    ]}}],
        "groups": [], "pictures": [], "key_value_items": [], "form_items": [],
        "body": {"children": [{"$ref": ref} for ref in
                              ("#/texts/0", "#/texts/1", "#/texts/2", "#/texts/3", "#/tables/0")]},
    }
    document = {"format": "docling", "document": raw, "text": text}
    model_result = {"entities": [{"id": "e1", "name": "Repeated", "type": "concept", "occurrence": 1}], "relations": []}
    built = _build_source(source, False, model_result=model_result,
                          parsed=(text, document, "native", source.material_revision, "docling", "2"))
    passages = _source_passages(built)
    assert all(len(span.id) <= 128 for span in passages)

    repeated = [span for span in passages if span.quote == "Repeated"]
    assert [span.locator.page for span in repeated] == [1, 2]
    assert repeated[1].locator.section_path == ["Chapter"]
    entity_span = next(span for span in built["evidence"] if span.quote == "Repeated")
    assert entity_span.locator.page == 2
    formula = next(span for span in passages if span.quote == "x = y")
    assert formula.metadata["source_kind"] == "formula"
    assert formula.metadata["structure"]["original_text"] == "x equals y"
    cell = next(span for span in _docling_cell_evidence(built) if span.quote == "12%")
    assert len(cell.id) <= 128
    assert cell.locator.table_id.startswith("table:")
    assert cell.metadata["source_ref"] == "#/tables/0"
    assert cell.locator.cell == "r0:c1"
    assert cell.locator.page == 3
    assert cell.locator.bbox == [10.0, 20.0, 100.0, 30.0]
    assert cell.locator.start_char is None and cell.locator.end_char is None


@pytest.mark.parametrize("citation", [[], [{"evidence_id": "evidence:invented", "quote": "unknown"}]])
def test_explanation_rejects_missing_or_hallucinated_citations(tmp_path, monkeypatch, citation):
    from semantica.semantic_artifact_builder import _build_source, _source_passages, _explanation_reports, SemanticArtifactError
    from semantica.semantic_artifact_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    receipt = ModelReceipt(id="receipt:test", operation="knowledge_explanation", provider="test", model="test", input_digest=H1, output_digest=H2)
    result = {"title": "Explanation", "summary": "Unsupported", "findings": [
        {"summary": "Explanation", "explanation": "Unsupported claim", "citations": citation}]}
    calls = []
    def respond(*args, **kwargs):
        calls.append(args)
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}, receipt
    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", respond)
    with pytest.raises(SemanticArtifactError):
        _explanation_reports("project-1", [built], built["entities"], [], [], [], [], [*built["evidence"], *built["passages"]], __import__('types').SimpleNamespace(model_id="test", max_output_tokens=1024, context_window_tokens=500000))
    assert len(calls) == 3


def _parsed_ref(params, source):
    result = parse_source_artifact(ParseSourceRequest.model_validate({
        "source": source, "outputDir": str(Path(params["outputDir"]) / "parsed"),
        "forceOcr": source["sourceId"] in params["recipe"]["forceOcrSourceIds"],
        "documentProcessing": params.get("documentProcessing", {"mode": "local"}),
    }))
    return {key: result[key] for key in ("artifactPath", "artifactDigest", "sourceId")}


def _request(source: Path, output_dir: Path, *, recipe: str = "deterministic", prepare: bool = True) -> dict:
    request = {
        "protocol": "semantica.semantic-worker.v1",
        "id": "build-1",
        "method": "build_semantic_artifacts",
        "params": {
            "baseSnapshot": None,
            "inputRevision": H1,
            "outputDir": str(output_dir),
            "projectId": "project-1",
            "recipe": {"forceOcrSourceIds": [], "id": recipe, "version": "1"},
            "relays": {
                "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.snapshot.embed", "modelId": "embedding-1", "receipts": "required"},
                "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.snapshot.generate", "contextWindowTokens": 500000, "maxOutputTokens": 393216, "modelId": "model-1", "receipts": "required"},
            },
            "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json", "retrieval-index": "application/vnd.semantica.retrieval+json", "semantic-graph": "application/vnd.semantica.semantic-graph+json"}},
            "sources": [{"filePath": str(source), "materialRevision": source_content_revision(source), "mimeType": "application/epub+zip" if source.suffix == ".epub" else "text/plain", "name": source.name, "sourceId": "source-1"}],
        },
    }
    request["params"]["parsedSources"] = [_parsed_ref(request["params"], request["params"]["sources"][0])] if prepare else []
    return request


def test_worker_builds_complete_snapshot_from_real_text_file(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine. The Engine influenced Charles Babbage.", encoding="utf-8")
    stdin = io.StringIO(json.dumps(_request(source, tmp_path)) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    events, response = _worker_output(stdout)
    assert events[0]["type"] == "progress"
    assert events[0]["stage"] == "document_parsing"
    assert response["ok"] is True
    assert [item["kind"] for item in response["result"]["artifacts"]] == ["document-representation", "retrieval-index", "semantic-graph"]
    assert response["result"]["relayReceipts"] == {"embedding": [], "model": []}
    assert not (tmp_path / "snapshot.json").exists()

    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "semantic-graph")
    snapshot = _host_snapshot(snapshot_path)
    assert snapshot.id == response["result"]["semanticGraph"]["artifactRevision"]
    assert snapshot.entities
    assert snapshot.relations == []
    assert snapshot.assertions == []
    assert "identity_decisions" not in snapshot.model_dump()
    assert len(snapshot.communities) == len(snapshot.entities)
    assert len(snapshot.topics) == len(snapshot.communities)
    assert "reports" not in json.loads(snapshot_path.read_text())
    assert snapshot.retrieval_manifests[0].community_ids
    assert snapshot.change_delta.added_ids
    assert snapshot.evidence_spans
    assert snapshot.model_receipts == []
    assert all(span.quote == span.locator.quote for span in snapshot.evidence_spans)
    assert all(span.locator.representation_id == span.representation_id for span in snapshot.evidence_spans)
    assert any(span.metadata.get("role") == "source-passage" for span in snapshot.evidence_spans)


def test_build_rejects_base_snapshot_from_another_project(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    initial_request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "initial")["params"])
    initial = build_semantic_artifacts(initial_request)
    request = _request(source, tmp_path / "next")["params"]
    request["projectId"] = "project-2"
    request["baseSnapshot"] = {
        "snapshotId": initial["snapshot"].id,
        "snapshotPath": str(initial["snapshot_path"]),
        "artifactDigest": initial["snapshot_digest"],
        "schemaDigest": H3,
    }
    with pytest.raises(Exception, match="project"):
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request))


def test_canonical_graph_projection_preserves_snapshot_identity():
    entities = [
        KnowledgeEntity(id="entity:ada", canonical_name="Ada Lovelace", type="PERSON"),
        KnowledgeEntity(id="entity:engine", canonical_name="Analytical Engine", type="CONCEPT"),
    ]
    relations = [
        KnowledgeRelation(
            id="relation:source-1:0",
            source_entity_id="entity:ada",
            target_entity_id="entity:engine",
            type="designed",
            qualifiers={"polarity": "positive"},
            evidence_ids=["evidence:source-1:0:42"],
        )
    ]

    graph_relationships = _canonical_graph_projection(entities, relations)

    assert {item["id"] for item in graph_relationships} == {relations[0].id}
    assert {edge["source"] for edge in graph_relationships} == {entities[0].id}
    assert {edge["target"] for edge in graph_relationships} == {entities[1].id}


def test_worker_fails_closed_for_unsupported_source_format(tmp_path):
    source = tmp_path / "source.unknown"
    source.write_bytes(b"not-an-epub")
    request = _request(source, tmp_path, prepare=False)
    request["params"]["sources"][0]["mimeType"] = "application/octet-stream"
    request["method"] = "parse_source"
    request["params"] = {"source": request["params"]["sources"][0], "outputDir": str(tmp_path), "forceOcr": False, "documentProcessing": {"mode": "local"}}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is False
    assert response["error"]["type"] == "SemanticArtifactError"
    assert "unsupported" in response["error"]["message"].lower()


def test_cross_source_same_name_stays_unresolved(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    second.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    request = _request(first, tmp_path)
    request["params"]["sources"].append({
        "filePath": str(second),
        "materialRevision": source_content_revision(second),
        "mimeType": "text/plain",
        "name": second.name,
        "sourceId": "source-2",
    })
    request["params"]["parsedSources"].append(_parsed_ref(request["params"], request["params"]["sources"][-1]))
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is True
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "semantic-graph")
    snapshot = _host_snapshot(snapshot_path)
    ada_candidates = [entity for entity in snapshot.entities if entity.canonical_name == "Ada Lovelace"]
    assert len(ada_candidates) == 2
    assert ada_candidates[0].id != ada_candidates[1].id
    assert "identity_decisions" not in snapshot.model_dump()
    assert snapshot.conflicts == []
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["format"] == "semantica.retrieval-reference.v1"
    assert "identity_decisions" not in retrieval and "conflicts" not in retrieval


def test_epub_adapter_preserves_adapter_locator_origin(tmp_path):
    source = tmp_path / "book.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/chapter.xhtml",
            "<html><body><h1>Ada Lovelace</h1><p>Designed the Analytical Engine.</p></body></html>",
        )
    request = _request(source, tmp_path)
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is True
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "semantic-graph")
    snapshot = _host_snapshot(snapshot_path)
    assert snapshot.evidence_spans
    assert {item.locator.origin for item in snapshot.evidence_spans} == {"adapter"}
    representation_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "document-representation")
    persisted = json.loads(representation_path.read_text())
    assert "Ada Lovelace" in persisted["text"]
    assert all(persisted["text"][span.locator.start_char:span.locator.end_char] == span.quote for span in snapshot.evidence_spans)


def test_model_recipe_uses_bifrost_chat_and_embedding_and_records_receipts(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")

    class RelayHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers["content-length"])
            payload = json.loads(self.rfile.read(length))
            if self.path == "/v1/chat/completions":
                prompt = payload["messages"][0]["content"]
                explanation = "Explain the supplied knowledge" in prompt
                if explanation:
                    content = _native_report(payload, "Historical role")
                else:
                    content = ({
                        "relations": [{
                            "subject_id": "mention:0", "confidence": 0.9,
                            "predicate": "designed",
                            "object_id": "mention:1",
                            "evidence": "Ada Lovelace designed the Analytical Engine.",
                            "evidence_occurrence": 0,
                            "qualifiers": {"polarity": "positive"}, "supporting_refs": [],
                        }],
                    } if "Extract source-grounded relations" in prompt else {
                        "entities": [
                            {"text": "Ada Lovelace", "label": "PERSON", "occurrence": 0, "attributes": {}, "confidence": 0.9},
                            {"text": "Analytical Engine", "label": "CONCEPT", "occurrence": 0, "attributes": {}, "confidence": 0.9},
                        ],
                    })
                response = {
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content), "role": "assistant"}}],
                    "model": payload["model"],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8},
                }
                if "Classify this source" in payload["messages"][0]["content"]:
                    context = _typed_prompt_context(payload)
                    response["choices"][0]["message"]["content"] = json.dumps({"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.95, "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]})
            elif self.path == "/v1/embeddings":
                assert payload["model"] == "embedding-1"
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
        request["params"]["recipe"]["classificationProfile"] = _classification_profile()
        request["params"]["relays"]["model"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        request["params"]["relays"]["embedding"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/embeddings"
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        _, response = _worker_output(stdout)
    finally:
        if previous_token is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_token
        server.shutdown()
        server.server_close()

    assert response["ok"] is True
    assert len(response["result"]["relayReceipts"]["model"]) >= 2
    assert len(response["result"]["relayReceipts"]["embedding"]) == 1
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "semantic-graph")
    snapshot = _host_snapshot(snapshot_path)
    assert len(snapshot.model_receipts) == len(response["result"]["relayReceipts"]["model"]) + 1
    extraction_receipts = [receipt for receipt in snapshot.model_receipts if receipt.operation == "structured_extraction"]
    assert {receipt.metadata["extraction_stage"] for receipt in extraction_receipts} == {"entities", "relations"}
    assert snapshot.source_classifications[0].assignments[0].item_id == "history"
    assert snapshot.classification_profile.id == "profile:test"
    assert "classification:source-1" in snapshot.change_delta.added_ids
    assert "reports" not in json.loads(snapshot_path.read_text())
    assert all(receipt.input_digest.startswith("sha256:") and receipt.output_digest.startswith("sha256:") for receipt in snapshot.model_receipts)
    assert snapshot.relations[0].status == "candidate"
    assert snapshot.relations[0].evidence_ids
    assert snapshot.retrieval_manifests[0].model_receipt_ids == [receipt.id for receipt in snapshot.model_receipts]
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["embeddings"] == [{"source_id": "source-1", "start_char": 0, "end_char": len(source.read_text()), "vector": [0.25, 0.5, 0.75]}]
    assert "provenance" not in retrieval
    assert "model_receipt_ids" not in retrieval
    evidence = {item.id: item for item in snapshot.evidence_spans}
    representations = {item.id: item for item in snapshot.document_representations}
    assert all(representations[evidence[ref].representation_id].source_id == "source-1"
               for ref in snapshot.relations[0].evidence_ids)
    assert any(item.quote == "Ada Lovelace" and item.locator.start_char == 0
               and item.locator.end_char == 12 for item in snapshot.evidence_spans)


def test_model_recipe_fails_closed_without_relay_token(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    previous_token = os.environ.pop("OPENAI_API_KEY", None)
    try:
        stdin = io.StringIO(json.dumps(_request(source, tmp_path, recipe="model")) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        _, response = _worker_output(stdout)
    finally:
        if previous_token is not None:
            os.environ["OPENAI_API_KEY"] = previous_token
    assert response["ok"] is False
    assert response["error"]["type"] == "SemanticArtifactError"
    assert "authorization" in response["error"]["message"]


def test_incremental_delta_ignores_audit_time_and_tracks_changed_knowledge(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    second.write_text("Charles Babbage designed machines.", encoding="utf-8")
    request = _request(first, tmp_path / "first-build")["params"]
    request["sources"].append({"filePath": str(second), "materialRevision": source_content_revision(second), "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    request["parsedSources"].append(_parsed_ref(request, request["sources"][-1]))
    initial = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request))
    request["baseSnapshot"] = {"snapshotId": initial["snapshot"].id, "snapshotPath": str(initial["snapshot_path"]), "artifactDigest": initial["snapshot_digest"], "schemaDigest": H3}
    request["inputRevision"] = H2
    request["outputDir"] = str(tmp_path / "identical-build")
    identical = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request))["snapshot"]
    assert identical.change_delta.updated_ids == []
    assert identical.change_delta.added_ids == []

    first.write_text("Grace Hopper studied mathematics.", encoding="utf-8")
    request["sources"][0]["materialRevision"] = source_content_revision(first)
    request["outputDir"] = str(tmp_path / "changed-build")
    request["parsedSources"][0] = _parsed_ref(request, request["sources"][0])
    updated = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request))["snapshot"]
    unchanged_entities = {entity.id for entity in initial["snapshot"].entities if "Charles Babbage" in entity.canonical_name}
    assert unchanged_entities
    changed_representations = {item.id for snapshot in [initial["snapshot"], updated] for item in snapshot.document_representations if item.source_id == "source-1"}
    assert set(updated.change_delta.changed_representation_ids) == changed_representations
    assert len(changed_representations) == 2
    assert not unchanged_entities.intersection(updated.change_delta.updated_ids + updated.change_delta.retracted_ids)
    removed_entities = {entity.id for entity in initial["snapshot"].entities if "Ada Lovelace" in entity.canonical_name}
    assert removed_entities.issubset(set(updated.change_delta.retracted_ids))


def test_community_and_topic_deltas_update_knowledge_without_embedded_reports(tmp_path):
    from semantica.semantic_artifact_builder import _change_delta

    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    base = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "build")["params"]))["snapshot"]
    revised = base.model_copy(deep=True)
    revised.communities[0].title += " revised"
    revised.topics[0].title += " revised"
    delta = _change_delta(base, "next-snapshot", revised.document_representations, revised.entities,
        revised.assertions, revised.relations, revised.communities, revised.topics,
        [item.id for item in revised.retrieval_manifests], revised.evidence_spans, revised.source_classifications)
    assert {revised.communities[0].id, revised.topics[0].id}.issubset(delta.updated_ids)
    assert not any(value.startswith("report:") for value in [*delta.added_ids, *delta.updated_ids, *delta.retracted_ids])


@pytest.mark.parametrize("declared_identity", [False, True])
def test_model_identity_remaps_graph_and_keeps_all_source_provenance(tmp_path, monkeypatch, declared_identity):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    text = "Ada Lovelace designed the Analytical Engine."
    first.write_text(text, encoding="utf-8")
    second.write_text(text + " Ada Lovelace was a mathematician.", encoding="utf-8")
    operations = []

    def relay_response(relay, payload, operation, *, business_context=None):
        operations.append(operation)
        if operation == "embedding":
            result = {"data": [
                {"index": index, "embedding": [0.25, 0.5, 0.75]}
                for index, _ in enumerate(payload["input"])
            ], "model": relay.model_id}
        else:
            if operation == "structured_extraction":
                prompt = payload["messages"][0]["content"]
                content = ({"relations": [{
                    "subject_id": "mention:0", "confidence": 0.9,
                    "predicate": "designed",
                    "object_id": "mention:1", "evidence": text,
                    "evidence_occurrence": 0,
                    "qualifiers": {"polarity": "positive"}, "supporting_refs": [],
                }]} if "Extract source-grounded relations" in prompt else {
                    "entities": [
                        {"text": "Ada Lovelace", "label": "PERSON", "occurrence": 0,
                         "attributes": {"fixture_key": "person-1"}, "confidence": 0.9},
                        {"text": "Analytical Engine", "label": "CONCEPT", "occurrence": 0,
                         "attributes": {"fixture_key": "concept-1"}, "confidence": 0.9},
                    ],
                })
            elif operation == "knowledge_explanation":
                content = _native_report(payload, "Design")
            else:
                content = {}
            result = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}], "model": relay.model_id}
        receipt = ModelReceipt(id="receipt:" + stable_digest([operation, payload]).split(":")[1], operation=operation,
            provider="fixture", model=relay.model_id, input_digest=stable_digest(payload), output_digest=stable_digest(result))
        return result, receipt

    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", relay_response)
    request = _request(first, tmp_path / "build", recipe="model")
    request["params"]["recipe"]["extractionSpec"] = {
        "id": "fixture", "version": "1", "entity_types": [
            {"name": kind, "description": kind, "attributes": {
                "fixture_key": {"type": "string", "description": "Fixture identity"}}}
            for kind in ("PERSON", "CONCEPT")],
        "relation_types": [{"name": "designed", "description": "Designed",
                            "domain": ["PERSON"], "range": ["CONCEPT"]}],
    }
    if declared_identity:
        request["params"]["identityPropertySchema"] = {"fixture_key": {"identity": True}}
    request["params"]["sources"].append({"filePath": str(second), "materialRevision": source_content_revision(second), "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    request["params"]["parsedSources"].append(_parsed_ref(request["params"], request["params"]["sources"][-1]))
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    events, response = _worker_output(stdout)
    embedding_progress = [event for event in events if event.get("stage") == "embedding"]
    assert {key: embedding_progress[-1]["metadata"][key] for key in ("completedChunks", "restoredChunks", "totalChunks")} == {
        "completedChunks": 2,
        "restoredChunks": 0,
        "totalChunks": 2,
    }
    assert response["ok"] is True, response
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "semantic-graph")
    snapshot = _host_snapshot(snapshot_path)
    assert len(snapshot.entity_mentions) == 4
    # Declaring nonconflicting fields must not change native positive resolution.
    assert len(snapshot.entities) == 2
    assert all('status' not in item.model_dump() for item in snapshot.identity_registry)
    assert snapshot.conflicts == []
    assert "identity_decisions" not in snapshot.model_dump()
    assert "identity_resolution" not in operations
    assert "relationship_discovery" not in operations
    assert operations.count("structured_extraction") == 4
    assert [item.type for item in snapshot.source_relations] == ["designed"]
    assert len(snapshot.relations) == 1
    assert operations.count("knowledge_explanation") == 0
    base_path = tmp_path / "base-snapshot.json"
    base_path.write_text(snapshot.model_dump_json(by_alias=True))
    request["params"]["baseSnapshot"] = {"snapshotId": snapshot.id, "snapshotPath": str(base_path), "artifactDigest": "sha256:" + __import__("hashlib").sha256(base_path.read_bytes()).hexdigest(), "schemaDigest": H3}
    request["params"]["resumeCheckpointDirs"] = [str(Path(request["params"]["outputDir"]) / "checkpoint")]
    request["params"]["outputDir"] = str(tmp_path / "repeat")
    repeated = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request["params"]))["snapshot"]
    assert operations.count("structured_extraction") == 4
    assert operations.count("knowledge_explanation") == 0
    assert repeated.change_delta.updated_ids == []
    canonical_ids = {entity.id for entity in snapshot.entities}
    assert {relation.source_entity_id for relation in snapshot.relations}.issubset(canonical_ids)
    assert {relation.target_entity_id for relation in snapshot.relations}.issubset(canonical_ids)
    assert {assertion.subject_id for assertion in snapshot.assertions}.issubset(canonical_ids)
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["format"] == "semantica.retrieval-reference.v1"
    assert "identity_decisions" not in retrieval and "conflicts" not in retrieval
    for entity in snapshot.entities:
        evidence = {item.id: item for item in snapshot.evidence_spans}
        representations = {item.id: item for item in snapshot.document_representations}
        assert {representations[evidence[ref].representation_id].source_id
                for ref in entity.evidence_ids} == set(entity.metadata["source_ids"])
        assert len(entity.metadata["source_ids"]) == 2
