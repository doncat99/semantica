from tests.artifact_helpers import extract_source
from types import SimpleNamespace
from threading import Lock
from time import sleep

import pytest

from semantica import semantic_artifact_builder as pipeline
from semantica.source import source_content_revision
from semantica.semantic_artifact_schema import (
    ClassificationProfile, ModelReceipt, SourceBuildInput,
)
from semantica.semantic_worker import _relay_receipts
from semantica.semantic_extract.types import Entity, Relation


def receipt(operation, count):
    return ModelReceipt(id=f"receipt:{operation}:{count}", operation=operation, provider="test", model="test",
                        input_digest="sha256:" + "1" * 64, output_digest="sha256:" + "2" * 64)


def _stub_canonical_extraction(monkeypatch, extract):
    class Provider:
        def __init__(self):
            self.receipts = []
            self.result = None

    def grounded(text, **_kwargs):
        provider = _kwargs["provider_instance"]
        provider.result, model_receipt = extract(text, None)
        provider.receipts.append(model_receipt)
        entities = []
        for item in provider.result["entities"]:
            start, end = pipeline._exact_occurrence(text, item["name"], item.get("occurrence"))[:2]
            entities.append(Entity(
                item["name"], item["type"], start, end, item.get("confidence", 0.9),
                {"mention_id": item["id"], "span_occurrence": item.get("occurrence", 0)},
            ))
        by_id = {entity.metadata["mention_id"]: entity for entity in entities}
        relations = []
        for item in provider.result["relations"]:
            start, end = pipeline._exact_occurrence(text, item["evidence"], item.get("evidence_occurrence"))[:2]
            relations.append(Relation(
                by_id[item["subject"]], item["predicate"], by_id[item["object"]],
                item.get("confidence", 0.9), text[start:end], {
                    "subject_id": item["subject"], "object_id": item["object"],
                    "evidence_occurrence": item.get("evidence_occurrence", 0),
                    "evidence_start": start, "evidence_end": end,
                    "qualifiers": item.get("qualifiers", {}),
                },
            ))
        return entities, relations, provider

    monkeypatch.setattr(pipeline, "_project_model_provider", lambda _relay: Provider())
    monkeypatch.setattr(pipeline, "extract_grounded_window", grounded)


def test_long_extraction_visits_tail_and_preserves_absolute_repeated_mentions(tmp_path, monkeypatch):
    text = ("Ada builds Engine.\n" + "x" * 700 + "\n") * 90 + "Tail built FinalEngine."
    calls = []

    def extract(window, relay):
        calls.append(window)
        names = [name for name in ("Ada", "Engine", "Tail", "FinalEngine") if name in window]
        return {"entities": [{"id": name, "name": name, "type": "CONCEPT", "occurrence": 0} for name in names], "relations": []}, receipt("structured_extraction", len(calls))

    _stub_canonical_extraction(monkeypatch, extract)
    monkeypatch.setattr(pipeline, "_embed_texts", lambda texts, relay: ([[1.0, 0.0] for _ in texts], receipt("embedding", len(calls))))
    extracted, embeddings, receipts = extract_source(text, SimpleNamespace(model_id="test"), None)
    assert len(calls) >= 5 and all(len(item) <= pipeline.TEXT_WINDOW_CHARS for item in calls)
    assert len(receipts) == len(calls) + (len(calls) + 7) // 8
    assert embeddings[-1]["end_char"] == len(text)
    covered = set()
    for chunk in embeddings:
        covered.update(range(chunk["start_char"], chunk["end_char"]))
    assert len(covered) == len(text)
    source = tmp_path / "source.txt"
    source.write_text(text)
    built = pipeline._build_source(SourceBuildInput(filePath=str(source), sourceId="long", materialRevision=source_content_revision(source), name=source.name, mimeType="text/plain"), False, extracted)
    assert any(entity.canonical_name == "Tail" for entity in built["entities"])
    ada = [entity for entity in built["entities"] if entity.canonical_name == "Ada"]
    assert len(ada) >= 5 and all(len(entity.evidence_ids) == 1 for entity in ada)
    for span in built["evidence"]:
        assert text[span.locator.start_char:span.locator.end_char] == span.quote
    assert max(span.locator.start_char for span in built["evidence"]) > len(text) - 30


def test_extraction_rejects_unlocated_quote(monkeypatch):
    _stub_canonical_extraction(monkeypatch, lambda *args: ({"entities": [{"id": "missing", "name": "NotPresent", "type": "CONCEPT", "occurrence": 0}], "relations": []}, receipt("structured_extraction", 1)))
    monkeypatch.setattr(pipeline, "_embed_texts", lambda texts, relay: ([[1.0] for _ in texts], receipt("embedding", 1)))
    with pytest.raises(pipeline.SemanticArtifactError, match="outside source text"):
        extract_source("x" * 10_000 + "Tail", SimpleNamespace(model_id="test"), None)


def test_extraction_reports_active_stage_and_preserves_exact_evidence(monkeypatch):
    text = "CFA Institute thanks the authors:\nAlice   Bob"
    events = []

    _stub_canonical_extraction(monkeypatch, lambda *args: ({
        "entities": [
            {"id": "cfa", "name": "CFA Institute", "type": "ORG", "occurrence": 0},
            {"id": "authors", "name": "authors", "type": "GROUP", "occurrence": 0},
        ],
        "relations": [{
            "subject": "cfa", "predicate": "thanks", "object": "authors",
                "evidence": text,
            "evidence_occurrence": 0, "qualifiers": {"polarity": "positive"},
        }],
    }, receipt("structured_extraction", 1)))
    monkeypatch.setattr(pipeline, "_embed_texts", lambda texts, relay: ([[1.0] for _ in texts], receipt("embedding", 1)))

    extracted, _, _ = extract_source(text, SimpleNamespace(model_id="test"), None, progress=events.append)

    assert [event["stage"] for event in events] == ["extracting"] * 3 + ["embedding"] * 3
    assert events[0]["metadata"]["completedChunks"] == 0
    assert events[2]["metadata"]["completedChunks"] == 1
    assert events[2]["metadata"]["restoredChunks"] == 0
    evidence = extracted["relations"][0]["evidence"]
    assert evidence == text


def test_extraction_reports_restored_checkpoint_chunks(monkeypatch):
    events = []
    restored = receipt("structured_extraction", 1)
    object.__setattr__(restored, "_checkpoint_restored", True)
    _stub_canonical_extraction(monkeypatch, lambda *args: ({"entities": [], "relations": []}, restored))
    embedding = receipt("embedding", 1)
    object.__setattr__(embedding, "_checkpoint_restored", True)
    monkeypatch.setattr(pipeline, "_embed_texts", lambda texts, relay: ([[1.0] for _ in texts], embedding))

    extract_source("source", SimpleNamespace(model_id="test"), None, progress=events.append)

    assert events[2]["metadata"]["completedChunks"] == events[-1]["metadata"]["completedChunks"] == 1
    assert events[2]["metadata"]["restoredChunks"] == events[-1]["metadata"]["restoredChunks"] == 1


def test_stage_progress_precedes_relay_calls(monkeypatch):
    events = []

    def extract(*args):
        assert events[-1]["stage"] == "extracting"
        assert events[-1]["metadata"]["completedChunks"] == 0
        assert events[-1]["metadata"]["totalChunks"] == 1
        return {"entities": [], "relations": []}, receipt("structured_extraction", 1)

    def embed(texts, relay):
        assert events[-1]["stage"] == "embedding"
        assert events[-1]["metadata"]["completedChunks"] == 0
        assert events[-1]["metadata"]["totalChunks"] == 1
        return [[1.0] for _ in texts], receipt("embedding", 1)

    _stub_canonical_extraction(monkeypatch, extract)
    monkeypatch.setattr(pipeline, "_embed_texts", embed)
    extract_source("source", SimpleNamespace(model_id="test"), None, progress=events.append)


def test_parallel_extraction_is_bounded_and_preserves_window_order(monkeypatch):
    windows = [(index * 10, index * 10 + len(f"Fact{index}"), f"Fact{index}") for index in range(4)]
    monkeypatch.setattr(pipeline, "_text_windows", lambda text: iter(windows))
    lock = Lock()
    active = peak = 0

    def extract(window, relay):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.02 if window == "Fact0" else 0.005)
        with lock:
            active -= 1
        return {"entities": [{"id": window, "name": window, "type": "CONCEPT", "occurrence": 0}], "relations": []}, receipt("structured_extraction", int(window[-1]))

    _stub_canonical_extraction(monkeypatch, extract)
    monkeypatch.setattr(pipeline, "_embed_texts", lambda texts, relay: ([[1.0, 0.0] for _ in texts], receipt("embedding", 1)))
    text = "".join(f"Fact{index}".ljust(10) for index in range(4))
    result, embeddings, receipts = extract_source(text, SimpleNamespace(model_id="test"), None, parallelism=2)
    assert peak == 2
    assert [entity["name"] for entity in result["entities"]] == [item[2] for item in windows]
    assert [item["start_char"] for item in embeddings] == [item[0] for item in windows]
    assert [item.id for item in receipts[:4]] == [f"receipt:structured_extraction:{index}" for index in range(4)]


def test_parallel_embedding_batches_are_bounded_and_ordered(monkeypatch):
    windows = [(index * 10, index * 10 + len(f"Fact{index}"), f"Fact{index}") for index in range(24)]
    monkeypatch.setattr(pipeline, "_text_windows", lambda text: iter(windows))
    _stub_canonical_extraction(monkeypatch, lambda window, relay: ({"entities": [], "relations": []}, receipt("structured_extraction", int(window[4:]))))
    lock = Lock()
    active = peak = 0

    def embed(texts, relay):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.02 if texts[0] == "Fact0" else 0.005)
        with lock:
            active -= 1
        return [[float(int(text[4:]))] for text in texts], receipt("embedding", int(texts[0][4:]))

    monkeypatch.setattr(pipeline, "_embed_texts", embed)
    text = "".join(f"Fact{index}".ljust(10) for index in range(24))
    _, embeddings, receipts = extract_source(text, SimpleNamespace(model_id="test"), None, parallelism=2)
    assert peak == 2
    assert [chunk["vector"] for chunk in embeddings] == [[float(index)] for index in range(24)]
    assert [item.id for item in receipts[-3:]] == [f"receipt:embedding:{index}" for index in (0, 8, 16)]


@pytest.mark.parametrize("data", [
    [{"index": 1, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}],
    [{"index": 0, "embedding": [1.0]}],
    [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0, 2.0]}],
])
def test_batch_embedding_rejects_invalid_response(monkeypatch, data):
    monkeypatch.setattr(pipeline, "_relay_json", lambda *args, **kwargs: ({"model": "test", "data": data}, receipt("embedding", 1)))
    with pytest.raises(pipeline.SemanticArtifactError, match="embedding response"):
        pipeline._embed_texts(["one", "two"], SimpleNamespace(model_id="test"))


def test_classification_and_native_reports_visit_every_passage(tmp_path, monkeypatch):
    source = tmp_path / "long.txt"
    source.write_text("\n".join(f"Passage {index}: " + "fact " * 260 for index in range(90)))
    built = pipeline._build_source(SourceBuildInput(filePath=str(source), sourceId="long", materialRevision=source_content_revision(source), name=source.name, mimeType="text/plain"), False,
                                   {"entities": [], "relations": []})
    built["passages"] = pipeline._source_passages(built)
    seen = {"source_classification": set(), "knowledge_explanation": set()}
    calls = []

    def model(relay, operation, instruction, context, schema):
        assert pipeline._context_size(context) <= pipeline.MODEL_CONTEXT_BYTES
        calls.append(operation)
        assert operation == "source_classification"
        seen[operation].update(item["id"] for item in context["evidence"])
        citations = [{"evidence_id": item["id"], "quote": item["quote"]} for item in context["evidence"]]
        if operation == "source_classification":
            result = {"assignments": [{"dimension_id": "subject", "item_id": "science", "confidence": 0.9, "citations": citations}]}
        else:
            result = {"sections": [{"title": "Details", "text": "Supported explanation", "citations": citations}]}
        return schema.model_validate(result, context=context), [receipt(operation, len(calls))]

    monkeypatch.setattr(pipeline, "_product_json", model)
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            batch = kwargs["validation_context"]
            calls.append("knowledge_explanation")
            for item in batch["evidence"]:
                assert f"[{item['id']}]: {item['quote']}" in prompt
                seen["knowledge_explanation"].add(item["id"])
            return schema.model_validate({"title": "Details", "summary": "Supported",
                "findings": [{"summary": "Details", "explanation": "Supported explanation",
                              "citations": [{"evidence_id": item["id"]} for item in batch["evidence"]]}]},
                context=batch)
    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    profile = ClassificationProfile(id="profile", version="1", label="Subject", description="Classification", dimensions=[{"id": "subject", "label": "Subject", "cardinality": "single", "vocabulary": [{"id": "science", "label": "Science"}]}])
    classification, _ = pipeline._classify_source(built, profile, None)
    reports, _ = pipeline._explanation_reports("project", [built], [], [], [], [], [], built["passages"], None)
    expected = {span.id for span in built["passages"]}
    assert seen["source_classification"] == seen["knowledge_explanation"] == expected
    assert set(classification.assignments[0].evidence_ids) == expected
    assert set(reports[0].evidence_ids) == expected
    assert calls.count("knowledge_explanation") > 1 and "knowledge_synthesis" not in calls
    assert len(reports[0].sections) == calls.count("knowledge_explanation")


def test_indivisible_context_is_rejected_without_truncation():
    with pytest.raises(pipeline.SemanticArtifactError, match="indivisible"):
        pipeline._context_batches({}, [("evidence", {"quote": "x" * 60_000})])


def test_native_report_cannot_introduce_evidence_from_another_batch(monkeypatch):
    result = {"title": "Invented", "summary": "Unsupported", "findings": [
        {"summary": "Invented", "explanation": "Unsupported",
         "citations": [{"evidence_id": "other-evidence"}]}]}
    calls = []
    def respond(*args, **kwargs):
        calls.append(args)
        return {"model": "test", "choices": [{"finish_reason": "stop", "message": {"content": __import__('json').dumps(result)}}]}, receipt("knowledge_explanation", 1)
    monkeypatch.setattr(pipeline, "_relay_json", respond)
    with pytest.raises(pipeline.SemanticArtifactError):
        pipeline._grounded_explanation({"target": {"id": "overview"}, "entities": [],
            "assertions": [], "relations": [], "evidence": [{"id": "source-evidence", "quote": "Supported"}]}, SimpleNamespace(model_id="test", max_output_tokens=1024))
    assert len(calls) == 1


def test_worker_receipt_manifest_preserves_legacy_model_receipts():
    receipts = [receipt(operation, index) for index, operation in enumerate((
        "embedding", "knowledge_synthesis", "relationship_discovery", "identity_resolution",
    ), start=1)]
    manifest = _relay_receipts(receipts)
    assert manifest == {
        "embedding": [receipts[0].id],
        "model": [receipts[1].id, receipts[2].id, receipts[3].id],
    }
