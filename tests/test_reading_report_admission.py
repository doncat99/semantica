"""Reading reports consume knowledge through current native owners."""
import json
import pytest
from types import SimpleNamespace

from semantica import semantic_publication_builder as pipeline
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


def test_topics_are_grounded_report_sections_not_connected_component_names():
    from semantica.semantic_artifact_schema import KnowledgeReport, ReportSection
    evidence = [span("s1", "A cuts energy use."), span("s2", "B cuts energy use.", "source:2"),
                span("s3", "C publishes accounts.")]
    entities = [KnowledgeEntity(id="entity:" + name.lower(), canonical_name=name, type="ORG", evidence_ids=[ref])
                for name, ref in [("A", "s1"), ("B", "s2"), ("C", "s3")]]
    claims = [KnowledgeAssertion(id="assertion:a", subject_id="entity:a", predicate="cuts", object="energy use",
                                qualifiers={"polarity": "positive"}, evidence_ids=["s1"])]
    report = KnowledgeReport(id="report:overview", report_type="overview", title="Overview",
        content_hash="sha256:" + "1" * 64, evidence_ids=["s1", "s2"],
        sections=[ReportSection(title="Energy efficiency", text="Both companies reduce energy use.",
                                evidence_ids=["s1", "s2"])])
    communities = pipeline._semantic_organization({"entities": [{"id": item.id, "name": item.canonical_name} for item in entities], "relationships": []})
    topics = pipeline._grounded_topics(entities, claims, evidence, communities, [report])
    assert len(communities) == 3  # Disconnected topology does not decide subject membership.
    assert len(topics) == 1
    assert topics[0].title == "Energy efficiency"
    assert topics[0].entity_ids == ["entity:a", "entity:b"]
    assert topics[0].assertion_ids == ["assertion:a"]
    assert topics[0].evidence_ids == ["s1", "s2"]
    assert topics[0].metadata["organization"]["basis"] == "grounded-overview-section"
    assert "entity:c" not in topics[0].entity_ids  # Uncited knowledge remains unclassified, not lost.
    assert pipeline._grounded_topics(entities, claims, evidence, communities, []) == []


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
    from tests.artifact_helpers import organization_report_owner
    with organization_report_owner(monkeypatch):
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


def test_native_canonical_identity_does_not_depend_on_build_directory(tmp_path, monkeypatch):
    from tests.test_semantic_artifact import _request
    from semantica.semantic_worker import handle_request
    from semantica.triplet_store.publication_records import PublicationRecords
    stage = PublicationRecords.stage_canonical
    selections = []
    def capture(owner, generation, records):
        selections.append(json.dumps(records, sort_keys=True))
        return stage(owner, generation, records)
    monkeypatch.setattr(PublicationRecords, "stage_canonical", capture)
    source = tmp_path / "source.txt"
    source.write_text("Ada designed the Engine.")
    request = _request(source, tmp_path / "first")
    first = handle_request(request)
    first_selections = selections[:]
    selections.clear()
    request["params"]["outputDir"] = str(tmp_path / "second")
    second = handle_request(request)
    assert first["ok"] and second["ok"]
    assert first_selections and first_selections == selections
    # Generations identify publication attempts; canonical selections identify content.
    assert first["result"]["semanticStore"]["path"] == second["result"]["semanticStore"]["path"]
    for directory in ("first", "second"):
        assert not (tmp_path / directory / "semantic-graph.json").exists()
        assert not (tmp_path / directory / "snapshot.json").exists()


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
    from tests.artifact_helpers import organization_report_owner
    with organization_report_owner(monkeypatch):
        pipeline._explanation_reports("project", [], [entity], claims, [], [], [topic], evidence,
                                      SimpleNamespace(model_id="test"), target_ids=["acme", "topic"])
    assert {context["target"]["type"] for context in contexts} == {"concept", "topic"}
    assert all(len(context["assertions"]) == 4 for context in contexts)
    assert len(claims) == 100


@pytest.mark.parametrize("legacy_membership", [False, True])
def test_topic_and_community_reports_respect_membership_before_shared_entity_expansion(monkeypatch, legacy_membership):
    from semantica.semantic_artifact_schema import KnowledgeCommunity, KnowledgeTopic
    evidence = [span("inside", "Acme operates Plant"), span("outside", "Acme funds unrelated research", "source:2")]
    entities = [KnowledgeEntity(id=ref, canonical_name=ref, type="ORG", evidence_ids=["inside", "outside"])
                for ref in ("acme", "plant", "outside")]
    claims = [KnowledgeAssertion(id="member", subject_id="acme", predicate="operates", object="Plant",
        object_entity_id="plant", qualifiers={"polarity": "positive"}, evidence_ids=["inside", "outside"]),
        KnowledgeAssertion(id="other", subject_id="acme", predicate="funds", object="research",
        object_entity_id="outside", qualifiers={"polarity": "positive"}, evidence_ids=["outside"])]
    relations = [KnowledgeRelation(id="member-edge", source_entity_id="acme", target_entity_id="plant",
        type="operates", qualifiers={"polarity": "positive"}, evidence_ids=["inside"]),
        KnowledgeRelation(id="boundary-edge", source_entity_id="acme", target_entity_id="outside",
        type="funds", qualifiers={"polarity": "positive"}, evidence_ids=["outside"])]
    community = KnowledgeCommunity(id="community", level=0, title="Operations",
        entity_ids=["acme", "plant"], relation_ids=["member-edge"])
    topic = KnowledgeTopic(id="topic", title="Operations", entity_ids=["acme", "plant"],
        assertion_ids=["member", "other"] if legacy_membership else ["member"],
        evidence_ids=["inside", "outside"] if legacy_membership else ["inside"], community_ids=["community"])
    contexts = []
    def explain(context, _relay):
        contexts.append(context)
        return [pipeline.ReportSection(title="Support", text="Grounded", evidence_ids=["inside"])], []
    monkeypatch.setattr(pipeline, "_grounded_explanation", explain)
    from tests.artifact_helpers import organization_report_owner
    with organization_report_owner(monkeypatch):
        pipeline._explanation_reports("project", [], entities, claims, relations, [community], [topic],
            evidence, SimpleNamespace(model_id="test"), target_ids=["topic", "community"])
    assert len(contexts) == 2
    for context in contexts:
        assert {item["id"] for item in context["assertions"]} == {"member"}
        assert all(item["id"] != "boundary-edge" for item in context["relations"])
        assert {item["id"] for item in context["entities"]} == {"acme", "plant"}
    topic_context = next(item for item in contexts if item["target"]["type"] == "topic")
    assert {item["id"] for item in topic_context["assertions"]} == {"member"}
    if not legacy_membership:
        assert {item["id"] for item in topic_context["evidence"]} == {"inside"}
    assert claims[0].evidence_ids == ["inside", "outside"]


def test_topic_organization_does_not_admit_uncited_assertions(monkeypatch):
    from semantica.kg import CommunityDetector
    monkeypatch.setattr(CommunityDetector, "detect_communities", lambda *args, **kwargs:
        {"communities": [["acme", "plant"], ["outside"]]})
    entities = [KnowledgeEntity(id=ref, canonical_name=ref, type="ORG") for ref in ("acme", "plant", "outside")]
    claims = [KnowledgeAssertion(id="inside", subject_id="acme", predicate="operates", object="plant",
        object_entity_id="plant", qualifiers={"polarity": "positive"}, evidence_ids=["in"]),
        KnowledgeAssertion(id="boundary", subject_id="acme", predicate="funds", object="outside",
        object_entity_id="outside", qualifiers={"polarity": "positive"}, evidence_ids=["out"])]
    from semantica.semantic_artifact_schema import KnowledgeReport, ReportSection
    report = KnowledgeReport(id="report:overview", report_type="overview", title="Overview",
        content_hash="sha256:" + "1" * 64, evidence_ids=["in"],
        sections=[ReportSection(title="Operations", text="Acme operates the plant.", evidence_ids=["in"])])
    topics = pipeline._grounded_topics(entities, claims, [span("in", "Operations"), span("out", "Research")], [], [report])
    topic = next(item for item in topics if "plant" in item.entity_ids)
    assert topic.assertion_ids == ["inside"]
    assert topic.evidence_ids == ["in"]


def test_reader_roles_use_distinct_native_instructions_without_diagnostic_questions(monkeypatch):
    prompts = []
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            prompts.append(prompt)
            return schema.model_validate({"title": "Report", "summary": "Grounded", "findings": [
                {"summary": "Meaning", "explanation": "Grounded", "citations": [{"evidence_id": "e1"}]}]},
                context=kwargs["validation_context"])
    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *args: Provider())
    for kind in ("overview", "topic", "concept"):
        pipeline._grounded_explanation({"target": {"id": kind, "type": kind, "title": "Subject"},
            "entities": [], "assertions": [], "relations": [],
            "evidence": [{"id": "support", "quote": "The subject has a source-backed meaning."}]},
            SimpleNamespace(model_id="test", context_window_tokens=12000, max_output_tokens=1000))
    assert "Orient the reader" in prompts[0]
    assert "Explain only the named topic" in prompts[1]
    assert "Explain the named concept" in prompts[2]
    assert all("Do not turn extraction diagnostics" in prompt for prompt in prompts)
