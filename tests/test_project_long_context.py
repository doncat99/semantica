from types import SimpleNamespace

import pytest

from semantica import project_snapshot_pipeline as pipeline
from semantica.project_source import source_content_revision
from semantica.project_snapshot_schema import (
    ClassificationProfile, DocumentLocator, DocumentRepresentation, EvidenceSpan,
    KnowledgeEntity, ModelReceipt, SourceBuildInput,
)
from semantica.project_snapshot_worker import _relay_receipts


def receipt(operation, count):
    return ModelReceipt(id=f"receipt:{operation}:{count}", operation=operation, provider="test", model="test",
                        input_digest="sha256:" + "1" * 64, output_digest="sha256:" + "2" * 64)


def test_long_extraction_visits_tail_and_preserves_absolute_repeated_mentions(tmp_path, monkeypatch):
    text = ("Ada builds Engine.\n" + "x" * 700 + "\n") * 90 + "Tail built FinalEngine."
    calls = []

    def extract(window, relay):
        calls.append(window)
        names = [name for name in ("Ada", "Engine", "Tail", "FinalEngine") if name in window]
        return {"entities": [{"id": name, "name": name, "type": "CONCEPT", "occurrence": 0} for name in names], "relations": []}, receipt("structured_extraction", len(calls))

    monkeypatch.setattr(pipeline, "_structured_extract", extract)
    monkeypatch.setattr(pipeline, "_embed_text", lambda text, relay: ([1.0, 0.0], receipt("embedding", len(calls))))
    extracted, embeddings, receipts = pipeline._extract_and_embed(text, None, None)
    assert len(calls) > 10 and all(len(item) <= pipeline.TEXT_WINDOW_CHARS for item in calls)
    assert len(receipts) == len(calls) * 2
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
    assert len(ada) > 10 and all(len(entity.evidence_ids) == 1 for entity in ada)
    for span in built["evidence"]:
        assert text[span.locator.start_char:span.locator.end_char] == span.quote
    assert max(span.locator.start_char for span in built["evidence"]) > len(text) - 30


def test_extraction_rejects_quote_outside_current_window(monkeypatch):
    monkeypatch.setattr(pipeline, "_structured_extract", lambda *args: ({"entities": [{"id": "tail", "name": "Tail", "type": "CONCEPT", "occurrence": 0}], "relations": []}, receipt("structured_extraction", 1)))
    monkeypatch.setattr(pipeline, "_embed_text", lambda *args: ([1.0], receipt("embedding", 1)))
    with pytest.raises(pipeline.SnapshotBuildError, match="source window"):
        pipeline._extract_and_embed("x" * 10_000 + "Tail", None, None)


def test_classification_and_hierarchical_reports_visit_every_passage(tmp_path, monkeypatch):
    source = tmp_path / "long.txt"
    source.write_text("\n".join(f"Passage {index}: " + "fact " * 260 for index in range(90)))
    built = pipeline._build_source(SourceBuildInput(filePath=str(source), sourceId="long", materialRevision=source_content_revision(source), name=source.name, mimeType="text/plain"), False,
                                   {"entities": [], "relations": []})
    built["passages"] = pipeline._source_passages(built)
    seen = {"source_classification": set(), "knowledge_explanation": set()}
    calls = []

    def model(relay, operation, instruction, context):
        assert pipeline._context_size(context) <= pipeline.MODEL_CONTEXT_BYTES
        calls.append(operation)
        if operation == "knowledge_synthesis":
            refs = sorted({ref for section in context["sections"] for ref in section["evidence_ids"]})
            return {"sections": [{"title": "Synthesis", "text": "Connected explanation", "evidence_ids": refs[:1]}]}, receipt(operation, len(calls))
        seen[operation].update(item["id"] for item in context["evidence"])
        citations = [{"evidence_id": item["id"], "quote": item["quote"]} for item in context["evidence"]]
        if operation == "source_classification":
            result = {"assignments": [{"dimension_id": "subject", "item_id": "science", "confidence": 0.9, "citations": citations}]}
        else:
            result = {"sections": [{"title": "Details", "text": "Supported explanation", "citations": citations}]}
        return result, receipt(operation, len(calls))

    monkeypatch.setattr(pipeline, "_product_json", model)
    profile = ClassificationProfile(id="profile", version="1", label="Subject", description="Classification", dimensions=[{"id": "subject", "label": "Subject", "cardinality": "single", "vocabulary": [{"id": "science", "label": "Science"}]}])
    classification, _ = pipeline._classify_source(built, profile, None)
    reports, _ = pipeline._explanation_reports("project", [built], [], [], [], [], [], built["passages"], None)
    expected = {span.id for span in built["passages"]}
    assert seen["source_classification"] == seen["knowledge_explanation"] == expected
    assert set(classification.assignments[0].evidence_ids) == expected
    assert set(reports[0].evidence_ids) == expected
    assert calls.count("knowledge_explanation") > 1 and "knowledge_synthesis" in calls
    assert len(reports[0].sections) == calls.count("knowledge_explanation") + 1


def test_identity_batches_compare_cross_source_aliases_without_name_filter(monkeypatch):
    builds = []
    for index in range(4):
        source_id = f"source-{index}"
        spans = [SimpleNamespace(id=f"evidence-{index}-{j}", quote="Q" * 1600, locator=SimpleNamespace(start_char=0, end_char=1600)) for j in range(10)]
        entity = SimpleNamespace(id=f"mention-{index}", canonical_name=f"DifferentAlias{index}", type="PERSON", evidence_ids=[span.id for span in spans])
        builds.append({"source": SimpleNamespace(source_id=source_id), "text": "Q" * 2000, "entities": [entity], "evidence": spans})
    pairs = set()

    def model(candidates, relay):
        assert pipeline._context_size(candidates) <= pipeline.MODEL_CONTEXT_BYTES
        assert len(candidates) == 2
        pairs.add(tuple(item["mention_id"] for item in candidates))
        return [], receipt("identity_resolution", len(pairs))

    monkeypatch.setattr(pipeline, "_identity_batch", model)
    judgments, receipts = pipeline._identity_judgments(builds, None)
    assert judgments == []
    assert len(pairs) == 6 and 6 < len(receipts) < 100


def test_indivisible_context_is_rejected_without_truncation():
    with pytest.raises(pipeline.SnapshotBuildError, match="indivisible"):
        pipeline._context_batches({}, [("evidence", {"quote": "x" * 60_000})])


def test_synthesis_cannot_introduce_evidence_from_another_batch(monkeypatch):
    from semantica.project_snapshot_schema import ReportSection
    monkeypatch.setattr(pipeline, "_product_json", lambda *args: ({"sections": [
        {"title": "Invented", "text": "Unsupported", "evidence_ids": ["other-evidence"]}]}, receipt("knowledge_synthesis", 1)))
    with pytest.raises(pipeline.SnapshotBuildError, match="unsupported evidence"):
        pipeline._synthesize_sections({"id": "overview"}, [ReportSection(title="Original", text="Supported", evidence_ids=["source-evidence"])], None)


def _relationship_fixture(include_third=False):
    builds, entities, evidence = [], [], []
    rows = [
        ("Photosynthesis", "Photosynthesis stores light energy in glucose.", [1.0, 0.0]),
        ("Cellular respiration", "Cellular respiration releases energy from glucose.", [0.99, 0.01]),
    ]
    if include_third:
        rows.append(("Glucose metabolism", "Glucose metabolism connects storage and release.", [0.98, 0.02]))
    for index, (name, quote, vector) in enumerate(rows, start=1):
        representation_id = f"representation-{index}"
        representation = DocumentRepresentation(
            id=representation_id, source_id=f"source-{index}", material_revision_id="b3-" + str(index) * 64,
            input_revision="b3-" + str(index) * 64, media_type="text/plain", content_hash="b3-" + str(index) * 64,
            parser="test", parser_version="1", recipe_id="model", recipe_digest="sha256:" + "a" * 64,
            origin="native", artifact_ref_id=f"artifact-{index}",
        )
        mention_id = f"mention-{index}"
        mention = EvidenceSpan(
            id=mention_id, representation_id=representation_id, quote=name,
            locator=DocumentLocator(representation_id=representation_id, origin="native", quote=name,
                                    start_char=0, end_char=len(name), quality="precise"),
        )
        passage_id = f"passage-{index}"
        passage = EvidenceSpan(
            id=passage_id, representation_id=representation_id, quote=quote,
            locator=DocumentLocator(representation_id=representation_id, origin="native", quote=quote,
                                    start_char=0, end_char=len(quote), quality="precise"),
        )
        entity = KnowledgeEntity(id=f"entity-{index}", canonical_name=name, type="CONCEPT",
                                 evidence_ids=[mention_id], metadata={"source_ids": [f"source-{index}"]})
        builds.append({"source": SimpleNamespace(source_id=f"source-{index}"), "representation": representation,
                       "embeddings": [{"start_char": 0, "end_char": len(quote), "vector": vector}]})
        entities.append(entity)
        evidence.extend([mention, passage])
    return builds, entities, evidence


def test_relationship_discovery_uses_cross_source_candidates_and_exact_evidence(monkeypatch):
    builds, entities, evidence = _relationship_fixture()
    seen = []

    def discover(candidates, relay):
        seen.extend(candidates)
        candidate = candidates[0]
        return [{
            "candidate_id": candidate["candidate_id"],
            "source_entity_id": "entity-1", "target_entity_id": "entity-2",
            "predicate": "provides substrate for", "qualifiers": {"polarity": "positive"},
            "citations": [{"evidence_id": row["id"], "quote": row["quote"]}
                           for row in candidate["evidence"] if row["id"].startswith("passage-")],
            "reason": "Both sources explicitly identify glucose as the stored and released energy carrier.",
        }], receipt("relationship_discovery", 1)

    monkeypatch.setattr(pipeline, "_relationship_batch", discover)
    assertions, relations, receipts = pipeline._discover_cross_source_relationships(
        "project", builds, entities, [], [], evidence, None,
    )
    assert len(seen) == len(assertions) == len(relations) == len(receipts) == 1
    assert {row["source_id"] for row in seen[0]["evidence"]} == {"source-1", "source-2"}
    assert set(relations[0].evidence_ids) == {"passage-1", "passage-2"}
    assert relations[0].metadata["model_receipt_ids"] == [receipts[0].id]


def test_relationship_discovery_skips_single_source_without_model_call(monkeypatch):
    builds, entities, evidence = _relationship_fixture()
    monkeypatch.setattr(pipeline, "_relationship_batch", lambda *args: pytest.fail("single source reached relationship model"))
    assert pipeline._discover_cross_source_relationships(
        "project", builds[:1], entities[:1], [], [], evidence[:2], None,
    ) == ([], [], [])


def test_relationship_candidates_keep_all_cross_source_pairs():
    builds, entities, evidence = _relationship_fixture(include_third=True)
    candidates = pipeline._relationship_candidates(builds, entities, [], [], evidence)
    assert len(candidates) == 3
    assert {frozenset((item["source_entity"]["id"], item["target_entity"]["id"])) for item in candidates} == {
        frozenset(("entity-1", "entity-2")),
        frozenset(("entity-1", "entity-3")),
        frozenset(("entity-2", "entity-3")),
    }


def test_relationship_discovery_rejects_evidence_from_one_source(monkeypatch):
    builds, entities, evidence = _relationship_fixture()

    def discover(candidates, relay):
        candidate = candidates[0]
        citation = next(row for row in candidate["evidence"] if row["source_id"] == "source-1")
        return [{
            "candidate_id": candidate["candidate_id"],
            "source_entity_id": "entity-1", "target_entity_id": "entity-2",
            "predicate": "related", "qualifiers": {"polarity": "positive"},
            "citations": [{"evidence_id": citation["id"], "quote": citation["quote"]}],
            "reason": "Unsupported",
        }], receipt("relationship_discovery", 1)

    monkeypatch.setattr(pipeline, "_relationship_batch", discover)
    with pytest.raises(pipeline.SnapshotBuildError, match="both endpoints and sources"):
        pipeline._discover_cross_source_relationships("project", builds, entities, [], [], evidence, None)


def test_worker_receipt_manifest_includes_synthesis_and_relationship_discovery():
    receipts = [receipt(operation, index) for index, operation in enumerate((
        "embedding", "knowledge_synthesis", "relationship_discovery",
    ), start=1)]
    manifest = _relay_receipts(receipts)
    assert manifest == {
        "embedding": [receipts[0].id],
        "model": [receipts[1].id, receipts[2].id],
    }
