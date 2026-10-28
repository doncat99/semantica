"""Reading reports consume knowledge, not the snapshot's storage indexes."""
import json
from types import SimpleNamespace

from semantica import semantic_artifact_builder as pipeline
from semantica.semantic_artifact_schema import EvidenceSpan, KnowledgeAssertion, KnowledgeEntity, KnowledgeRelation


def test_default_reading_plan_includes_grounded_topics_and_core_concepts_only():
    from semantica.semantic_artifact_schema import KnowledgeTopic
    entities = [KnowledgeEntity(id=f"e{i}", canonical_name=f"Concept {i}", type="CONCEPT") for i in range(50)]
    assertions = [KnowledgeAssertion(id=f"a{i}", subject_id=f"e{i}", predicate="has", object="evidence", qualifiers={"polarity": "positive"},
                    evidence_ids=["support"]) for i in range(20)]
    topics = [KnowledgeTopic(id=f"t{i}", title=f"Topic {i}", entity_ids=[f"e{i}"],
                           assertion_ids=[f"a{i}"], evidence_ids=["support"]) for i in range(20)]
    plan = pipeline._default_reading_report_targets("p", entities, assertions, [], topics)
    assert plan[0] == "p"
    assert len(plan) == len(set(plan)) == 13
    assert sum(ref.startswith("t") for ref in plan) == 6
    assert sum(ref.startswith("e") for ref in plan) == 6
    assert "e49" not in plan


def test_worker_reuses_existing_default_reports_without_model_calls(monkeypatch, tmp_path):
    from semantica import semantic_worker as worker
    snapshot = SimpleNamespace(id="snapshot", project_id="project", entities=[], assertions=[], relations=[],
        topics=[], communities=[], evidence_spans=[], document_representations=[])
    monkeypatch.setattr(worker, "_verified_snapshot", lambda request: snapshot)
    monkeypatch.setattr(pipeline, "_report_support_sources", lambda *args: None)
    monkeypatch.setattr(pipeline, "_explanation_reports", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paid call")))
    worker._reading_reports({"snapshotPath": "/unused", "snapshotDigest": "sha256:" + "1" * 64,
        "snapshotId": "snapshot", "projectId": "project", "outputDir": str(tmp_path),
        "existingTargetIds": ["project"], "relay": {"authorizationEnv": "OPENAI_API_KEY",
            "baseUrl": "http://127.0.0.1:9999/v1/chat/completions", "bindingId": "binding:test",
            "modelId": "test/model", "contextWindowTokens": 10000, "maxOutputTokens": 1000,
            "capability": "knowledge.snapshot.generate", "receipts": "required"}}, None)
    artifact = json.loads((tmp_path / "reading-reports.json").read_text())
    assert artifact["plannedTargetIds"] == ["project"]
    assert artifact["reports"] == artifact["modelReceipts"] == []


def test_report_wire_schema_declares_required_finding_and_citation_fields():
    schema = pipeline._GroundedCommunityReport.model_json_schema()
    item = schema["properties"]["findings"]["items"]
    finding = schema["$defs"][item["$ref"].split("/")[-1]]
    assert set(finding["required"]) >= {"summary", "explanation", "citations"}
    citation_ref = finding["properties"]["citations"]["items"]["$ref"]
    assert "evidence_id" in schema["$defs"][citation_ref.split("/")[-1]]["required"]


def span(ref, quote, representation="source:1", start=0):
    return EvidenceSpan(id=ref, representation_id=representation, quote=quote,
        locator=dict(representation_id=representation, origin="native", quote=quote,
                     start_char=start, end_char=start + len(quote), quality="precise"))


def test_report_admits_qualified_facts_and_source_support_not_all_mentions(monkeypatch):
    mentions = [span(f"mention:{i}", "Acme", start=i * 10) for i in range(3000)]
    supports = [span("fact:one", "Acme reduced emissions in 2025."),
                span("fact:repeat", "Acme reduced emissions in 2025.", start=100),
                span("fact:two", "Acme did not reduce emissions in 2026.", "source:2")]
    raw = [span("raw:one", "Unrelated boilerplate " * 100),
           span("raw:two", "Unrelated boilerplate " * 100, "source:2"),
           span("raw:three", "Third source has no extracted claims.", "source:3")]
    entity = KnowledgeEntity(id="acme", canonical_name="Acme", type="ORG",
                             evidence_ids=[item.id for item in mentions])
    claims = [KnowledgeAssertion(id=f"claim:{i}", subject_id="acme", predicate="reduced",
        object="emissions", qualifiers={"polarity": polarity, "time": year},
        status=status, evidence_ids=refs) for i, (polarity, year, status, refs) in enumerate([
            ("positive", "2025", "accepted", ["fact:one", "fact:repeat"]),
            ("negative", "2026", "contradicted", ["fact:two"]),
        ])]
    captured = []
    def explain(context, _relay):
        captured.append(context)
        return [pipeline.ReportSection(title="Summary", text="Grounded",
            evidence_ids=[row["id"] for row in context["evidence"]])], []
    monkeypatch.setattr(pipeline, "_grounded_explanation", explain)
    pipeline._explanation_reports("project", [{"passages": raw}], [entity], claims, [], [], [],
                                  [*mentions, *supports, *raw], SimpleNamespace(model_id="test"))
    context = captured[0]
    assert {item["id"] for item in context["evidence"]} == {"fact:one", "fact:two", "raw:three"}
    assert len(json.dumps(context)) < 5000
    assert [(item["qualifiers"], item["status"]) for item in context["assertions"]] == [
        (item.qualifiers, item.status) for item in claims]
    assert len(entity.evidence_ids) == 3000  # Admission must not mutate provenance.


def test_grounded_payload_never_repeats_storage_reference_arrays(monkeypatch):
    prompts = []
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            prompts.append(prompt)
            return schema.model_validate({"title": "Summary", "summary": "Grounded", "findings": [
                {"summary": "Fact", "explanation": "Grounded", "citations": [{"evidence_id": "e1"}]}]},
                context=kwargs["validation_context"])
    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    entity = KnowledgeEntity(id="acme", canonical_name="Acme", type="ORG",
        evidence_ids=["ev", *[f"unused:{i}" for i in range(3000)]])
    sections, _ = pipeline._grounded_explanation({"target": {"id": "project"},
        "entities": [entity.model_dump(mode="json")], "assertions": [], "relations": [],
        "evidence": [{"id": "ev", "quote": "Acme"}]},
        SimpleNamespace(model_id="test", context_window_tokens=12000, max_output_tokens=1000))
    assert len(prompts) == 1
    assert "unused:" not in prompts[0]
    assert "evidence_ids" not in prompts[0]
    assert "[e1]: Acme" in prompts[0]
    assert sections[0].evidence_ids == ["ev"]


def test_snapshot_bytes_do_not_depend_on_build_directory(tmp_path):
    from tests.test_semantic_artifact import _request
    from semantica.semantic_worker import handle_request
    source = tmp_path / "source.txt"
    source.write_text("Ada designed the Engine.")
    request = _request(source, tmp_path / "first")
    first = handle_request(request)
    request["params"]["resumeCheckpointDirs"] = [str(tmp_path / "first" / "checkpoint")]
    request["params"]["outputDir"] = str(tmp_path / "second")
    second = handle_request(request)
    assert first["ok"] and second["ok"]
    graph = lambda result: next(item for item in result["result"]["artifacts"] if item["kind"] == "semantic-graph")
    assert graph(first)["digest"] == graph(second)["digest"]


def test_short_reference_from_another_batch_is_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            assert [item['id'] for item in kwargs['validation_context']['evidence']] == ['e1']
            return schema.model_validate({'title': 'Report', 'summary': 'Summary', 'findings': [
                {'summary': 'Fact', 'explanation': 'Explanation', 'citations': [{'evidence_id': 'e2'}]}]},
                context=kwargs['validation_context'])
    monkeypatch.setattr(pipeline, '_project_model_provider', lambda *args: Provider())
    with pytest.raises(ValidationError, match='supplied evidence_id'):
        pipeline._grounded_explanation({'target': {'id': 'project'}, 'entities': [],
            'assertions': [], 'relations': [], 'evidence': [
                {'id': 'storage:first', 'quote': 'First source. ' * 35},
                {'id': 'storage:second', 'quote': 'Second source. ' * 35}]},
            SimpleNamespace(model_id='test', context_window_tokens=6500, max_output_tokens=1000))


def test_report_preserves_structural_support_and_merges_duplicate_edge_projection():
    evidence = [span("header", "2025 Scope 1 (tonnes)"), span("cell", "42"),
                span("note", "Excludes subsidiaries"), span("other", "Acme owns Plant", "source:2")]
    for item in evidence[:3]:
        item.metadata["structural_ref"] = {"id": item.id}
    entities = [KnowledgeEntity(id=ref, canonical_name=ref, type="ORG", evidence_ids=["other"])
                for ref in ("acme", "plant")]
    claim = KnowledgeAssertion(id="claim", subject_id="acme", predicate="owns", object="plant",
        object_entity_id="plant", qualifiers={"time": "2025", "polarity":"positive"}, status="accepted",
        evidence_ids=["header", "cell", "note"])
    edge = KnowledgeRelation(id="edge", source_entity_id="acme", target_entity_id="plant",
        type="owns", qualifiers={"time": "2025", "polarity":"positive"}, status="accepted", evidence_ids=["other"])
    context, selected = pipeline._reading_report_context(
        {"type": "overview"}, entities, [claim], [edge], {item.id:item for item in evidence}, [])
    assert set(selected) == {item.id for item in evidence}
    assert context["relations"] == []
    assert set(context["assertions"][0]["evidence_ids"]) == set(selected)
    assert context["assertions"][0]["qualifiers"] == {"time": "2025", "polarity":"positive"}


def test_scoped_report_does_not_pull_other_sources_from_endpoint_mentions():
    evidence = [span("fact", "Acme owns Plant"), span("unrelated", "Plant", "source:2")]
    entities = [KnowledgeEntity(id=ref, canonical_name=ref, type="ORG", evidence_ids=["unrelated"])
                for ref in ("acme", "plant")]
    claim = KnowledgeAssertion(id="claim", subject_id="acme", predicate="owns", object="plant",
        object_entity_id="plant", qualifiers={"polarity":"positive"}, evidence_ids=["fact"])
    context, selected = pipeline._reading_report_context(
        {"type": "concept"}, entities, [claim], [], {item.id:item for item in evidence},
        [{"passages":evidence}])
    assert set(selected) == {"fact"}


def test_overview_selects_source_balanced_families_without_discarding_variants():
    evidence = [span(f"ev:{i}", f"Located support {i}", f"source:{i % 2}") for i in range(100)]
    entities = [KnowledgeEntity(id="acme", canonical_name="Acme", type="ORG")]
    claims = [KnowledgeAssertion(id=f"claim:{i}", subject_id="acme", predicate=f"metric:{i}",
        object=i, qualifiers={"time":"2025", "polarity":"positive"}, evidence_ids=[f"ev:{i}"]) for i in range(100)]
    # Variants and conflicts remain visible together, even outside the first four families.
    claims.extend([claims[0].model_copy(update={"id":"variant", "qualifiers":{"time":"2026", "polarity":"positive"}}),
                   claims[-1].model_copy(update={"id":"conflict", "status":"contradicted"})])
    _, selected, _ = pipeline._overview_knowledge(entities, claims, [], {x.id:x for x in evidence})
    assert len({x.predicate for x in selected}) == 9  # Four per source plus the conflict family.
    assert {x.id for x in selected} >= {"claim:0", "variant", "claim:99", "conflict"}
    _, reversed_selection, _ = pipeline._overview_knowledge(entities, list(reversed(claims)), [], {x.id:x for x in evidence})
    assert {x.id for x in selected} == {x.id for x in reversed_selection}


def test_concept_and_topic_reports_select_knowledge_before_prompting(monkeypatch):
    from semantica.semantic_artifact_schema import KnowledgeTopic
    evidence = [span(f"ev:{i}", f"Located support {i}") for i in range(100)]
    entity = KnowledgeEntity(id="acme", canonical_name="Acme", type="ORG")
    claims = [KnowledgeAssertion(id=f"claim:{i}", subject_id="acme", predicate=f"metric:{i}",
        object=i, qualifiers={"polarity": "positive"}, evidence_ids=[f"ev:{i}"]) for i in range(100)]
    topic = KnowledgeTopic(id="topic", title="Acme", entity_ids=["acme"],
        assertion_ids=[item.id for item in claims], evidence_ids=[item.id for item in evidence])
    contexts = []
    def explain(context, _relay):
        contexts.append(context)
        return [pipeline.ReportSection(title="Summary", text="Grounded", evidence_ids=[context["evidence"][0]["id"]])], []
    monkeypatch.setattr(pipeline, "_grounded_explanation", explain)
    pipeline._explanation_reports("project", [], [entity], claims, [], [], [topic], evidence,
                                  SimpleNamespace(model_id="test"), target_ids=["acme", "topic"])
    assert {context["target"]["type"] for context in contexts} == {"concept", "topic"}
    assert all(len(context["assertions"]) == 4 for context in contexts)
    assert len(claims) == 100
