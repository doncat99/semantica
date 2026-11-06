from tests.artifact_helpers import build_source_fixture
import io
import json
from zipfile import ZipFile
import os
from types import SimpleNamespace
import urllib.error
import pytest
from pathlib import Path

from semantica.semantic_publication_builder import build_semantic_artifacts, parse_source_artifact
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, ParseSourceRequest
from semantica.semantic_artifact_schema import KnowledgeRelation, ModelReceipt, stable_digest
from semantica.semantic_worker import serve
from semantica.source import source_content_revision

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def test_identifier_validation_does_not_visit_payload_fields():
    from semantica.semantic_artifact_schema import StrictModel

    class Record(StrictModel):
        id: str
        metadata: dict

        def __getattribute__(self, name):
            if name == "metadata":
                pytest.fail("ID validation must not visit unrelated payload fields")
            return super().__getattribute__(name)

    assert Record.model_validate({"id": "record-1", "metadata": {"text": "body"}}).id == "record-1"
    with pytest.raises(ValueError, match="invalid id"):
        Record.model_validate({"id": "invalid id", "metadata": {}})


@pytest.mark.parametrize("field,value", [
    ("source_id", "invalid id"), ("model_id", "invalid model"), ("evidence_ids", ["!invalid"]),
])
def test_identifier_validation_preserves_scalar_model_and_list_checks(field, value):
    from semantica.semantic_artifact_schema import StrictModel

    class Record(StrictModel):
        source_id: str
        model_id: str
        evidence_ids: list[str]

    valid = {"source_id": "source-1", "model_id": "provider/model", "evidence_ids": ["evidence-1"]}
    assert Record.model_validate(valid).model_id == "provider/model"
    with pytest.raises(ValueError, match=f"invalid {field}"):
        Record.model_validate({**valid, field: value})


def _typed_prompt_context(payload):
    prompt = payload["messages"][0]["content"]
    marker = "Input JSON:\n"
    return json.JSONDecoder().raw_decode(prompt[prompt.index(marker) + len(marker):])[0]


def _native_report(payload, title="Explanation"):
    import re
    prompt = payload['messages'][0]['content']
    refs = re.findall(r'^(?:- )?\[([^\]\n]+)\]: ', prompt, re.MULTILINE)
    assert refs, prompt
    return {'title': title, 'summary': 'Supported explanation', 'findings': [
        {'summary': title, 'explanation': 'Explained from the source.',
         'citations': [{'evidence_id': refs[0]}]}]}




def _worker_output(stdout):
    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return events, events[-1]










def test_build_validates_native_identity_policy_before_model_calls(tmp_path, monkeypatch):
    source = tmp_path / "identity.txt"
    source.write_text("Same company")
    raw = _request(source, tmp_path / "output", recipe="model")["params"]
    raw['identityPropertySchema'] = {'key': {'identity': 'yes'}}
    request = SemanticArtifactBuildRequest.model_validate(raw)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid identity policy must fail before paid extraction')
    monkeypatch.setattr('semantica.semantic_publication_builder._relay_json', forbidden)
    with pytest.raises(ValueError, match='invalid identity property'):
        build_semantic_artifacts(request)


def test_scoped_explanation_reuses_native_grounded_computation(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_publication_builder as pipeline
    from semantica.semantic_artifact_schema import EvidenceSpan, DocumentLocator

    span = EvidenceSpan(id="evidence:1", representation_id="representation:1", quote="Exact source sentence.",
                        locator=DocumentLocator(representation_id="representation:1", origin="native",
                                                quote="Exact source sentence.", quality="precise", start_char=0, end_char=22))
    seen = []

    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            context = kwargs["validation_context"]
            seen.append(context)
            assert span.quote in prompt
            return schema.model_validate({"title": "Meaning", "summary": "Supported",
                "findings": [{"summary": "Meaning", "explanation": "Explained from the source.",
                              "citations": [{"evidence_id": context["evidence"][0]["id"]}]}]}, context=context)

    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    target = {"id": "chapter:1", "type": "source-scope", "title": "Foundations"}
    sections, _ = pipeline._grounded_explanation(dict(target=target, entities=[], assertions=[], relations=[],
        evidence=[dict(id=span.id, quote=span.quote)]), SimpleNamespace(model_id="test", context_window_tokens=500000, max_output_tokens=32768))
    assert sections[0].evidence_ids == [span.id]
    assert seen[0]["target"] == target


def test_native_explanation_preserves_multiple_evidence_batches_with_its_target(monkeypatch):
    from semantica import semantic_publication_builder as pipeline
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


def test_unique_quote_ignores_model_position_but_duplicate_requires_occurrence():
    from semantica.semantic_extract.methods import _exact_occurrence
    from semantica.utils.exceptions import ProcessingError

    text = "Green Bonds and Private Equity. Green Bonds"
    assert _exact_occurrence(text, "Private Equity", 590) == (16, 30, 0)
    with pytest.raises(ProcessingError, match="occurrence"):
        _exact_occurrence(text, "Green Bonds", 590)


def test_relay_http_failure_preserves_safe_structured_error(monkeypatch):
    from types import SimpleNamespace
    from semantica.semantic_publication_builder import _relay_json, SemanticArtifactError

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
    from semantica.semantic_publication_builder import _relay_json, SemanticArtifactError

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
    from semantica.semantic_publication_builder import _safe_diagnostic, _safe_gateway_receipt

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
    from semantica.semantic_publication_builder import _relay_json

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self, size=-1): return b'{"choices":[]}'[:size]

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
    from semantica import semantic_publication_builder as pipeline

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




def test_explanation_does_not_persist_intermediate_model_response(tmp_path, monkeypatch):
    from semantica import semantic_publication_builder as pipeline
    context = {'target': {'id': 'source:1', 'type': 'source-scope'},
               'entities': [], 'assertions': [], 'relations': [],
               'evidence': [{'id': 'evidence:source', 'quote': 'Source quote'}]}
    calls = []
    def respond(relay, payload, operation):
        calls.append(payload)
        report = {'title': 'Source', 'summary': 'Supported', 'findings': [
            {'summary': 'Meaning', 'explanation': 'Explained from the source.',
             'citations': [{'evidence_id': 'e1'}]}]}
        return {'model': relay.model_id, 'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(report)}}]}, ModelReceipt(
                id='receipt:fresh', operation=operation, provider='test', model=relay.model_id,
                input_digest=H1, output_digest=H2)
    monkeypatch.setattr(pipeline, '_relay_uncached', respond)
    relay = SimpleNamespace(model_id='test', context_window_tokens=500000, max_output_tokens=32768)
    first, receipts = pipeline._grounded_explanation(context, relay)
    second, _ = pipeline._grounded_explanation(context, relay)
    assert len(calls) == 2
    assert first == second and first[0].evidence_ids == ['evidence:source']
    assert [item.id for item in receipts] == ['receipt:fresh']
    assert not list(tmp_path.iterdir())


def test_product_output_uses_host_admitted_output_limit(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_publication_builder as pipeline

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
    from semantica import semantic_publication_builder as pipeline

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
    from semantica import semantic_publication_builder as pipeline

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
        def read(self, size=-1):
            return json.dumps({"model": "model-1", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(outputs.pop(0))}}]}).encode()[:size]

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
    from semantica.semantic_publication_builder import _source_relations
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
    from semantica.semantic_publication_builder import _source_passages, _classify_source, SemanticArtifactError
    from semantica.semantic_artifact_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = build_source_fixture(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    citation = {"evidence_id": "e1", "quote": built["passages"][0].quote}
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
    monkeypatch.setattr("semantica.semantic_publication_builder._relay_json", relay_response)
    with pytest.raises(SemanticArtifactError):
        _classify_source(built, ClassificationProfile.model_validate(_classification_profile()),
            SimpleNamespace(model_id="test", binding_id="default", max_output_tokens=32768, context_window_tokens=500000))
    assert len(calls) == 3


def test_semantic_classification_preserves_source_offsets_and_unclassified_dimensions(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_publication_builder as pipeline
    from semantica.semantic_publication_builder import _source_passages, _classify_source
    from semantica.semantic_artifact_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = build_source_fixture(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    span = built["passages"][0]
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    output = {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [{"evidence_id": "e1", "quote": span.quote}]}]}
    def respond(relay, payload, operation, **kwargs):
        context = json.loads(payload["messages"][0]["content"].split("Input JSON:\n", 1)[1].split("\nReturn one JSON", 1)[0])
        assert context["evidence"] == [{"id": "e1", "quote": span.quote}]
        assert span.id not in payload["messages"][0]["content"]
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}, receipt
    monkeypatch.setattr(pipeline, "_relay_json", respond)
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


def test_classification_short_refs_restore_canonical_without_product_result_storage(monkeypatch):
    from semantica import semantic_publication_builder as pipeline
    context = {"evidence": [{"id": "evidence:canonical:23213:23231", "quote": "ENERGY & EMISSIONS"}]}
    receipt = ModelReceipt(id="receipt:short", operation="source_classification", provider="test",
        model="test", input_digest=H1, output_digest=H2)
    calls = []
    def respond(*args, **kwargs):
        calls.append(args)
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                "citations": [{"evidence_id": "e1"}]}]})}}]}, receipt
    monkeypatch.setattr(pipeline, "_relay_json", respond)
    relay = SimpleNamespace(model_id="test", max_output_tokens=1024)
    for _ in range(2):
        result, receipts = pipeline._product_json(relay, "source_classification", "Classify.", context,
            pipeline._ClassificationOutput, short_evidence_refs=True)
        assert result.assignments[0].citations[0].evidence_id == context["evidence"][0]["id"]
        assert receipts[0].id == receipt.id
    assert len(calls) == 2


def test_docling_evidence_preserves_reading_order_and_physical_locators(tmp_path):
    from semantica.semantic_publication_builder import _docling_cell_evidence, _source_passages
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
    from tests.artifact_helpers import native_docling_fixture, docling_fixture_text
    document = {"format": "docling", "document": native_docling_fixture(raw)}
    text = document['text'] = docling_fixture_text(document)
    model_result = {"entities": [{"id": "e1", "name": "Repeated", "type": "concept", "occurrence": 1}], "relations": []}
    built = build_source_fixture(source, False, model_result=model_result,
                          parsed=(text, document, "native", source.material_revision, "docling", "2"))
    passages = _source_passages(built)
    assert all(len(span.id) <= 128 for span in passages)

    repeated = [span for span in passages if span.quote == "Repeated"]
    assert [span.locator.page for span in repeated] == [1, 2]
    assert repeated[1].locator.section_path == ["Chapter"]
    entity_span = next(span for span in built["evidence"] if span.quote == "Repeated")
    assert entity_span.locator.page == 2
    # Extraction and reader use the same native scalar, without decoration.
    formula = next(span for span in passages if span.quote == "x = y")
    assert formula.locator.page == 2
    assert formula.locator.bbox == [10.0, 30.0, 100.0, 40.0]
    # Formula provenance remains in the unique native document, rather than
    # being copied into every passage DTO.
    assert document['document']['texts'][3]['orig'] == 'x equals y'
    assert 'original_text' not in formula.metadata
    cell = next(span for span in _docling_cell_evidence(built) if span.quote == "12%")
    assert len(cell.id) <= 128
    assert cell.locator.table_id.startswith("table:")
    assert cell.metadata["source_ref"] == "#/tables/0"
    assert cell.locator.cell == "r0:c1"
    assert cell.locator.page == 3
    assert cell.locator.bbox == [10.0, 20.0, 100.0, 30.0]
    assert text[cell.locator.start_char:cell.locator.end_char] == '12%'


@pytest.mark.parametrize("citation", [[], [{"evidence_id": "evidence:invented", "quote": "unknown"}]])
def test_explanation_rejects_missing_or_hallucinated_citations(tmp_path, monkeypatch, citation):
    from semantica.semantic_publication_builder import _source_passages, _grounded_explanation, SemanticArtifactError
    from semantica.semantic_artifact_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = build_source_fixture(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    receipt = ModelReceipt(id="receipt:test", operation="knowledge_explanation", provider="test", model="test", input_digest=H1, output_digest=H2)
    result = {"title": "Explanation", "summary": "Unsupported", "findings": [
        {"summary": "Explanation", "explanation": "Unsupported claim", "citations": citation}]}
    calls = []
    def respond(*args, **kwargs):
        calls.append(args)
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}, receipt
    monkeypatch.setattr("semantica.semantic_publication_builder._relay_json", respond)
    with pytest.raises(SemanticArtifactError):
        _grounded_explanation({"target": {"id": "project-1", "type": "overview"},
            "entities": [], "assertions": [], "relations": [],
            "evidence": [span.model_dump(mode="json") for span in built["passages"]]},
            __import__('types').SimpleNamespace(model_id="test", max_output_tokens=1024, context_window_tokens=500000))
    assert len(calls) == 3


def _parsed_ref(params, source):
    result = parse_source_artifact(ParseSourceRequest.model_validate({
        "source": source, "outputDir": str(Path(params["outputDir"]) / "parsed"),
        "forceOcr": source["sourceId"] in params["recipe"]["forceOcrSourceIds"],
        "documentProcessing": params.get("documentProcessing", {"mode": "local"}),
    }))
    return {key: result[key] for key in ("artifactPath", "artifactDigest", "sourceId", "representationRevision", "readerIndexPath", "readerIndexDigest")}


def _request(source: Path, output_dir: Path, *, recipe: str = "deterministic", prepare: bool = True) -> dict:
    request = {
        "protocol": "semantica.semantic-worker.v1",
        "id": "build-1",
        "method": "build_semantic_artifacts",
        "params": {
            "inputRevision": H1,
            "outputDir": str(output_dir),
            "nativeCacheDir": str(source.parent / 'native-cache'),
            "nativeStoreDir": str(source.parent / 'native-store'),
            "organizationReports": {"baseUrl": "http://127.0.0.1:9021/v1/products/semantic-organization",
                "authorizationEnv": "OPENAI_API_KEY", "recipeDigest": H1},
            "projectId": "project-1",
            "recipe": {"forceOcrSourceIds": [], "id": recipe, "version": "1"},
            "relays": {
                "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.publication.embed", "modelId": "embedding-1", "receipts": "required"},
                "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.publication.generate", "contextWindowTokens": 500000, "maxOutputTokens": 393216, "modelId": "model-1", "receipts": "required"},
            },
            "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json"}},
            "sources": [{"filePath": str(source), "materialRevision": source_content_revision(source), "mimeType": "application/epub+zip" if source.suffix == ".epub" else "text/plain", "name": source.name, "sourceId": "source-1"}],
        },
    }
    request["params"]["parsedSources"] = [_parsed_ref(request["params"], request["params"]["sources"][0])] if prepare else []
    return request








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
