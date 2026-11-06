import io
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from semantica.semantic_artifact_schema import (
    KnowledgeAssertion,
    KnowledgeRelation,
    EvidenceSpan,
    SemanticArtifactBuildRequest,
    WorkerRequest,
    build_request_json_schema,
)
from semantica.semantic_worker import serve

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64
H4 = "sha256:" + "4" * 64
H5 = "sha256:" + "5" * 64
H6 = "sha256:" + "6" * 64
H7 = "sha256:" + "7" * 64
H8 = "sha256:" + "8" * 64


def test_worker_keeps_parser_diagnostics_out_of_protocol_stdout():
    script = """\
import os
from semantica import semantic_worker as worker
def handle(raw, progress=None):
    os.write(1, b'Docling table warning\\n')
    return {'protocol': 'semantica.semantic-worker.v1', 'id': raw['id'], 'ok': True, 'result': {}}
worker.handle_request = handle
worker.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], input='{"id":"parse-1"}\n', capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == {
        "protocol": "semantica.semantic-worker.v1", "id": "parse-1", "ok": True, "result": {},
    }
    assert "Docling table warning" in result.stderr




def _build_request_payload():
    return {
        "projectId": "project-1",
        "inputRevision": H1,
        "outputDir": "/tmp/semantica-output",
        "nativeCacheDir": "/tmp/semantica-native/cache",
        "nativeStoreDir": "/tmp/semantica-native/store",
        "organizationReports": {"baseUrl": "http://127.0.0.1:9021/v1/products/semantic-organization",
            "authorizationEnv": "OPENAI_API_KEY", "recipeDigest": H1},
        "parsedSources": [{"artifactDigest": H2, "artifactPath": "/tmp/parsed.json", "readerIndexPath": "/tmp/reader.sqlite", "readerIndexDigest": H1, "sourceId": "source-1", "representationRevision": H3}],
        "sources": [{"filePath": "/tmp/source.pdf", "materialRevision": "b3-" + "7" * 64, "mimeType": "application/pdf", "name": "source.pdf", "sourceId": "source-1"}],
        "recipe": {"forceOcrSourceIds": [], "id": "deterministic", "version": "1"},
        "relays": {
            "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.publication.embed", "modelId": "embedding-1", "receipts": "required"},
            "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.publication.generate", "contextWindowTokens": 500000, "maxOutputTokens": 393216, "modelId": "model-1", "receipts": "required"},
        },
        "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json"}},
    }


def test_build_schema_exposes_only_current_reference_input():
    props = build_request_json_schema()["properties"]
    assert {"nativeCacheDir", "nativeStoreDir", "organizationReports", "parsedSources"} <= props.keys()
    assert not {"baseSnapshot", "entities", "relations", "checkpointDir"} & props.keys()


@pytest.mark.parametrize("model,payload", [
    (KnowledgeAssertion, {"id": "assertion-1", "subject_id": "entity-ada", "predicate": "designed", "object": "Engine"}),
    (KnowledgeRelation, {"id": "relation-1", "source_entity_id": "entity-ada", "target_entity_id": "entity-engine", "type": "designed"}),
])
@pytest.mark.parametrize("qualifiers", [None, {}, {"polarity": "unknown"},
    {"polarity": "positive", "scope": "global"}, {"polarity": "positive", "condition": ""},
    {"polarity": "positive", "value": 42}])
def test_native_fact_rows_reject_invalid_qualifiers(model, payload, qualifiers):
    value = dict(payload)
    if qualifiers is not None:
        value["qualifiers"] = qualifiers
    with pytest.raises(ValidationError, match="qualifier|qualifiers"):
        model.model_validate(value)


def test_native_evidence_rejects_unavailable_locator():
    with pytest.raises(ValidationError, match="locator requires"):
        EvidenceSpan.model_validate({"id": "ev-1", "representation_id": "repr-1",
            "quote": "Ada", "origin": "observed",
            "locator": {"representation_id": "repr-1", "origin": "native", "quote": "Ada", "quality": "precise"}})


@pytest.mark.parametrize("field,value", [("baseSnapshot", None), ("checkpointDir", "/tmp/checkpoints"),
    ("entities", []), ("relations", [])])
def test_build_request_rejects_removed_aggregate_inputs(field, value):
    payload = _build_request_payload()
    payload[field] = value
    with pytest.raises(ValidationError, match=field):
        SemanticArtifactBuildRequest.model_validate(payload)


@pytest.mark.parametrize("media_types", [{}, {"document-representation": "application/json"},
    {"document-representation": "application/vnd.semantica.document-representation+json",
     "semantic-graph": "application/vnd.semantica.semantic-graph+json"}])
def test_build_request_rejects_stale_release_media_types(media_types):
    payload = _build_request_payload()
    payload["release"]["mediaTypes"] = media_types
    with pytest.raises(ValidationError, match="mediaTypes"):
        SemanticArtifactBuildRequest.model_validate(payload)



def test_build_request_accepts_sources_not_semantic_objects():
    request = SemanticArtifactBuildRequest.model_validate(_build_request_payload())
    assert request.sources[0].source_id == "source-1"

    bad = _build_request_payload()
    bad["entities"] = [{"id": "host-entity"}]
    with pytest.raises(ValidationError):
        SemanticArtifactBuildRequest.model_validate(bad)


def test_formula_semantics_requires_explicit_known_pdf_with_model_recipe():
    payload = _build_request_payload()
    default_recipe = SemanticArtifactBuildRequest.model_validate(payload).recipe
    assert default_recipe.formula_semantics_source_ids == []
    assert default_recipe.lineage_payload() == default_recipe.model_dump(mode="json", by_alias=True)
    payload["recipe"]["formulaSemanticsSourceIds"] = ["source-1"]
    with pytest.raises(ValidationError, match="model recipe"):
        SemanticArtifactBuildRequest.model_validate(payload)
    payload["recipe"]["id"] = "model"
    selected_recipe = SemanticArtifactBuildRequest.model_validate(payload).recipe
    assert selected_recipe.formula_semantics_source_ids == ["source-1"]
    assert selected_recipe.lineage_payload()["formulaSemanticsSourceIds"] == ["source-1"]
    payload["sources"][0]["name"] = "notes.txt"
    payload["sources"][0]["mimeType"] = "text/plain"
    with pytest.raises(ValidationError, match="PDF sources"):
        SemanticArtifactBuildRequest.model_validate(payload)


def test_build_request_preserves_host_source_and_provider_model_ids():
    payload = _build_request_payload()
    payload["sources"][0]["sourceId"] = "6996f3a7-b132-4474-aa13-d14d746218cd"
    payload["parsedSources"][0]["sourceId"] = payload["sources"][0]["sourceId"]
    payload["relays"]["embedding"]["modelId"] = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    request = SemanticArtifactBuildRequest.model_validate(payload)
    assert request.sources[0].source_id == payload["sources"][0]["sourceId"]
    assert request.relays["embedding"].model_id == payload["relays"]["embedding"]["modelId"]

    payload["relays"]["embedding"]["modelId"] = "../unsafe"
    with pytest.raises(ValidationError, match="model_id"):
        SemanticArtifactBuildRequest.model_validate(payload)


def test_build_request_requires_admitted_model_output_limits():
    payload = _build_request_payload()
    request = SemanticArtifactBuildRequest.model_validate(payload)
    assert request.relays["model"].context_window_tokens == 500000
    assert request.relays["model"].max_output_tokens == 393216

    for field in ("contextWindowTokens", "maxOutputTokens"):
        bad = _build_request_payload()
        del bad["relays"]["model"][field]
        with pytest.raises(ValidationError, match="model relay requires"):
            SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["maxOutputTokens"] = 500001
    with pytest.raises(ValidationError, match="cannot exceed"):
        SemanticArtifactBuildRequest.model_validate(bad)


def test_build_request_preserves_extraction_specification():
    payload = _build_request_payload()
    payload["recipe"]["id"] = "model"
    payload["recipe"]["extractionSpec"] = {
        "id": "finance", "version": "1",
        "entity_types": [{"name": "Issuer", "description": "A security issuer", "attributes": {
            "ticker": {"type": "string", "description": "Exchange ticker"},
        }}],
    }
    request = SemanticArtifactBuildRequest.model_validate(payload)
    assert request.recipe.extraction_spec.digest.startswith("sha256:")
    assert request.recipe.extraction_spec.entity_types[0].name == "Issuer"


def test_build_request_rejects_unsafe_release_and_source_boundaries():
    bad = _build_request_payload()
    bad["sources"][0]["filePath"] = "relative/source.pdf"
    with pytest.raises(ValidationError, match="absolute"):
        SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["sources"][0]["mimeType"] = "pdf"
    with pytest.raises(ValidationError, match="MIME type"):
        SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["release"]["artifactDigest"] = "not-a-digest"
    with pytest.raises(ValidationError, match="sha256"):
        SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["authorizationEnv"] = "secret-token-value"
    with pytest.raises(ValidationError, match="environment variable name"):
        SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["baseUrl"] = "https://api.example.com/v1"
    with pytest.raises(ValidationError, match="loopback"):
        SemanticArtifactBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["baseUrl"] = "http://127.0.0.1:9021/v1/responses"
    with pytest.raises(ValidationError, match="chat/completions"):
        SemanticArtifactBuildRequest.model_validate(bad)


def test_jsonl_worker_build_requires_a_real_source_file():
    request = {"protocol": "semantica.semantic-worker.v1", "id": "req-1", "method": "build_semantic_artifacts", "params": _build_request_payload()}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] in {"SemanticArtifactError", "FileNotFoundError"}


def test_jsonl_worker_rejects_removed_validate_artifact_method():
    request = {"protocol": "semantica.semantic-worker.v1", "id": "validate-1", "method": "validate_artifact", "params": {}}
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] == "ValidationError"


def test_jsonl_worker_validates_extraction_spec_with_semantica_owned_schema():
    request = {"protocol": "semantica.semantic-worker.v1", "id": "spec-1", "method": "validate_extraction_spec", "params": {
        "id": "general", "version": "1",
        "entity_types": [{"name": "Concept", "description": "A source-grounded concept"}],
    }}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert response["result"]["valid"] is True
    assert response["result"]["digest"].startswith("sha256:")


def test_jsonl_worker_schema_returns_only_current_build_request():
    request = {"protocol": "semantica.semantic-worker.v1", "id": "schema-1", "method": "schema"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert set(response["result"]) == {"build_request"}
    assert "sources" in response["result"]["build_request"]["properties"]


def test_worker_request_rejects_unknown_method():
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate({"id": "bad", "method": "fallback"})


@pytest.mark.parametrize("field,value", [
    ("readerIndexPath", None), ("readerIndexDigest", None),
    ("readerIndexPath", "relative.sqlite"), ("readerIndexDigest", "unbound"),
])
def test_parsed_source_requires_explicit_bound_reader_index(field, value):
    request = _build_request_payload()
    if value is None:
        del request['parsedSources'][0][field]
    else:
        request['parsedSources'][0][field] = value
    with pytest.raises(ValidationError, match=field):
        SemanticArtifactBuildRequest.model_validate(request)


@pytest.mark.parametrize('relay,retired', [
    ('embedding', 'knowledge.snapshot.embed'),
    ('model', 'knowledge.snapshot.generate'),
])
def test_build_request_rejects_retired_relay_capabilities(relay, retired):
    payload = _build_request_payload()
    payload['relays'][relay]['capability'] = retired
    with pytest.raises(ValidationError, match='capability'):
        SemanticArtifactBuildRequest.model_validate(payload)
