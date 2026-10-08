import inspect
from types import SimpleNamespace

import pytest
import re
from pydantic import BaseModel

from semantica import semantic_artifact_builder
from semantica.semantic_artifact_builder import SemanticArtifactError
from semantica.semantic_artifact_schema import ModelReceipt
from semantica.semantic_extract.types import Entity, Relation
from semantica.utils.exceptions import ProcessingError


def test_entity_occurrence_index_preserves_identity_and_scans_each_name_once(monkeypatch):
    text = "Roof roof rooftop ROOF Roof"
    original = re.finditer
    calls = []
    def scan(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(semantic_artifact_builder.re, "finditer", scan)
    cache = {}
    for match in original("Roof", text, re.IGNORECASE):
        occurrence = sum(1 for prior in original("Roof", text[:match.end()], re.IGNORECASE) if prior.start() < match.start())
        expected = "mention:" + semantic_artifact_builder.stable_digest(["source", "object", "roof", occurrence]).split(":")[1][:32]
        assert semantic_artifact_builder._entity_id("source", "Roof", "object", text, match.start(), cache) == expected
    assert len(calls) == 1


def test_worker_internal_failure_retains_code_location_without_source_content():
    from semantica.semantic_worker import _response
    try:
        raise SemanticArtifactError("private document contents", code="SEMANTIC_SELF_RELATION")
    except SemanticArtifactError as error:
        response = _response("request-1", False, error=error)
    diagnostic = response["error"]["diagnostic"]
    assert diagnostic["code"] == "SEMANTIC_SELF_RELATION"
    assert diagnostic["fault"]["function"] == "test_worker_internal_failure_retains_code_location_without_source_content"
    assert diagnostic["fault"]["line"] > 0
    assert "private document" not in str(diagnostic)


def test_build_parallelism_accepts_host_ceiling_and_rejects_overflow():
    from pydantic import TypeAdapter, ValidationError
    from typing import Annotated
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    field = SemanticArtifactBuildRequest.model_fields["parallelism"]
    adapter = TypeAdapter(Annotated[int, *field.metadata])
    assert adapter.validate_python(16) == 16
    with pytest.raises(ValidationError):
        adapter.validate_python(17)


def test_semantic_artifact_extraction_uses_canonical_semantica_extractors(monkeypatch):
    calls = []

    class Provider:
        receipts = [ModelReceipt(
            id="receipt:extraction",
            operation="structured_extraction",
            provider="test",
            model="model-1",
            input_digest="sha256:" + "1" * 64,
            output_digest="sha256:" + "2" * 64,
        )]

    def grounded(text, **kwargs):
        calls.append(("grounded", text, kwargs))
        entities = [
            Entity("Reflective roofs", "measure", 0, 16, 0.9, {"mention_id": "mention:0", "span_occurrence": 0}),
            Entity("pedestrians", "population", 30, 41, 0.9, {"mention_id": "mention:1", "span_occurrence": 0}),
        ]
        relations = [Relation(
            entities[0], "shades", entities[1], 0.9,
            "Reflective roofs do not shade pedestrians.",
            {"qualifiers": {"polarity": "negative"}, "evidence_start": 0, "evidence_end": 43,
             "evidence_occurrence": 0, "subject_id": "mention:0", "object_id": "mention:1"},
        )]
        return entities, relations, Provider()

    monkeypatch.setattr(semantic_artifact_builder, "_project_model_provider", lambda _relay: Provider())
    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", grounded)
    monkeypatch.setattr(
        semantic_artifact_builder,
        "_embed_texts",
        lambda texts, _relay: ([[0.1, 0.2] for _ in texts], ModelReceipt(
            id="receipt:embedding",
            operation="embedding",
            provider="test",
            model="embedding-1",
            input_digest="sha256:" + "3" * 64,
            output_digest="sha256:" + "4" * 64,
        )),
    )

    result, embeddings, receipts = semantic_artifact_builder._extract_and_embed(
        "Reflective roofs do not shade pedestrians.", SimpleNamespace(model_id="model-1"), object()
    )

    assert [name for name, *_ in calls] == ["grounded"]
    assert calls[0][2]["extraction_spec"] is None
    assert result["entities"][0]["name"] == "Reflective roofs"
    assert result["relations"][0]["evidence"] == "Reflective roofs do not shade pedestrians."
    assert embeddings == [{"start_char": 0, "end_char": 42, "vector": [0.1, 0.2]}]
    assert {receipt.operation for receipt in receipts} == {"structured_extraction", "embedding"}


def test_semantic_artifact_has_no_parallel_structured_extractor():
    source = inspect.getsource(semantic_artifact_builder)
    assert "def _structured_extract" not in source
    assert "return _structured_extract" not in source
    assert "ThreadPoolExecutor" not in source
    assert "ParallelismManager" in source


def test_project_model_provider_uses_host_admitted_output_limit(monkeypatch):
    request = {}

    def relay_json(_relay, payload, operation):
        request.update(payload)
        return {
            "choices": [{"message": {"content": '{"entities": []}'}}],
            "model": "model-1",
        }, ModelReceipt(
            id="receipt:extraction",
            operation=operation,
            provider="test",
            model="model-1",
            input_digest="sha256:" + "1" * 64,
            output_digest="sha256:" + "2" * 64,
        )

    monkeypatch.setattr(semantic_artifact_builder, "_relay_json", relay_json)
    provider = semantic_artifact_builder._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=32768)
    )

    assert provider.generate("prompt", max_tokens=2048) == '{"entities": []}'
    assert request["max_tokens"] == 32768


def test_native_extraction_preserves_retryable_relay_failure(monkeypatch):
    relay_failure = SemanticArtifactError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )

    def grounded(_text, **_kwargs):
        raise ProcessingError("typed extraction failed") from relay_failure

    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", grounded)

    with pytest.raises(SemanticArtifactError) as failure:
        semantic_artifact_builder._extract_and_embed(
            "Retryable source text", SimpleNamespace(model_id="model-1"), object()
        )

    assert failure.value.status == 500
    assert failure.value.code == "INTERNAL_ERROR"
    assert failure.value.retryable is True


def test_typed_provider_keeps_relay_failure_as_its_cause(monkeypatch):
    class Output(BaseModel):
        entities: list = []

    relay_failure = SemanticArtifactError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )
    monkeypatch.setattr(
        semantic_artifact_builder,
        "_relay_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(relay_failure),
    )
    provider = semantic_artifact_builder._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=393216)
    )

    with pytest.raises(ProcessingError) as failure:
        provider.generate_typed("extract entities", Output, max_retries=1)

    assert failure.value.__cause__ is relay_failure


def test_restored_chunk_uses_native_grounding_without_repeating_model_calls(monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    text = "The committee supervises reporting."
    receipt = ModelReceipt(id="receipt:restored", operation="structured_extraction", provider="test", model="model-1",
        input_digest="sha256:" + "1" * 64, output_digest="sha256:" + "2" * 64)
    extracted = {"entities": [{"id": f"mention:{i}", "name": "committee", "type": "organization", "occurrence": 0} for i in range(2)],
        "relations": [{"subject": "mention:0", "predicate": "related_to", "object": "mention:1",
            "evidence": text, "evidence_occurrence": 0, "qualifiers": {"polarity": "positive"}, "confidence": 0.9}]}
    writes = []
    class Checkpoint:
        def read(self, kind, key):
            return {"extracted": extracted, "receipts": [receipt.model_dump(mode="json")]} if kind == "chunk-extraction" else None
        def write(self, kind, key, value):
            writes.append(value)
    monkeypatch.setattr(semantic_artifact_builder, "_text_windows", lambda _: [(0, len(text), text)])
    monkeypatch.setattr(semantic_artifact_builder, "_embed_batch_checkpointed", lambda *_: ([[0.1]], receipt))
    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", lambda *_a, **_k: pytest.fail("restored chunks must not call model"))
    token = active_checkpoint.set(Checkpoint())
    try:
        result, _, receipts = semantic_artifact_builder._extract_and_embed(text, SimpleNamespace(model_id="model-1"), object())
    finally:
        active_checkpoint.reset(token)
    assert result["relations"] == []
    assert len(result["entities"]) == 2
    assert len(writes) == 1
    assert "itself" in receipts[0].metadata["rejected_candidates"][0]["reason"]
