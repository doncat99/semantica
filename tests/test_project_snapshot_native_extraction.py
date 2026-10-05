import inspect
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from semantica import project_snapshot_pipeline
from semantica.project_snapshot_pipeline import SnapshotBuildError
from semantica.project_snapshot_schema import ModelReceipt
from semantica.semantic_extract.types import Entity, Relation
from semantica.utils.exceptions import ProcessingError


def test_project_snapshot_extraction_uses_canonical_semantica_extractors(monkeypatch):
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

    monkeypatch.setattr(project_snapshot_pipeline, "_project_model_provider", lambda _relay: Provider())
    monkeypatch.setattr(project_snapshot_pipeline, "extract_grounded_window", grounded)
    monkeypatch.setattr(
        project_snapshot_pipeline,
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

    result, embeddings, receipts = project_snapshot_pipeline._extract_and_embed(
        "Reflective roofs do not shade pedestrians.", SimpleNamespace(model_id="model-1"), object()
    )

    assert [name for name, *_ in calls] == ["grounded"]
    assert calls[0][2]["extraction_spec"] is None
    assert result["entities"][0]["name"] == "Reflective roofs"
    assert result["relations"][0]["evidence"] == "Reflective roofs do not shade pedestrians."
    assert embeddings == [{"start_char": 0, "end_char": 42, "vector": [0.1, 0.2]}]
    assert {receipt.operation for receipt in receipts} == {"structured_extraction", "embedding"}


def test_project_snapshot_has_no_parallel_structured_extractor():
    source = inspect.getsource(project_snapshot_pipeline)
    assert "def _structured_extract" not in source
    assert "return _structured_extract" not in source


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

    monkeypatch.setattr(project_snapshot_pipeline, "_relay_json", relay_json)
    provider = project_snapshot_pipeline._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=393216)
    )

    assert provider.generate("prompt", max_tokens=2048) == '{"entities": []}'
    assert request["max_tokens"] == 393216


def test_native_extraction_preserves_retryable_relay_failure(monkeypatch):
    relay_failure = SnapshotBuildError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )

    def grounded(_text, **_kwargs):
        raise ProcessingError("typed extraction failed") from relay_failure

    monkeypatch.setattr(project_snapshot_pipeline, "extract_grounded_window", grounded)

    with pytest.raises(SnapshotBuildError) as failure:
        project_snapshot_pipeline._extract_and_embed(
            "Retryable source text", SimpleNamespace(model_id="model-1"), object()
        )

    assert failure.value.status == 500
    assert failure.value.code == "INTERNAL_ERROR"
    assert failure.value.retryable is True


def test_typed_provider_keeps_relay_failure_as_its_cause(monkeypatch):
    class Output(BaseModel):
        entities: list = []

    relay_failure = SnapshotBuildError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )
    monkeypatch.setattr(
        project_snapshot_pipeline,
        "_relay_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(relay_failure),
    )
    provider = project_snapshot_pipeline._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=393216)
    )

    with pytest.raises(ProcessingError) as failure:
        provider.generate_typed("extract entities", Output, max_retries=1)

    assert failure.value.__cause__ is relay_failure
