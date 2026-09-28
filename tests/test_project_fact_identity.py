from semantica import project_snapshot_pipeline as pipeline
from semantica.project_snapshot_schema import KnowledgeAssertion, KnowledgeRelation, SourceBuildInput
from semantica.project_source import source_content_revision


def build(tmp_path, text, extraction):
    path = tmp_path / "source.txt"
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId="source:one", name=path.name,
                             materialRevision=source_content_revision(path), mimeType="text/plain")
    return pipeline._build_source(source, False, extraction)


def test_homonymous_occurrences_and_typed_endpoints_are_distinct(tmp_path):
    text = "Alex leads Alpha. Alex leads Beta."
    extraction = {"entities": [
        {"id": "alex-a", "name": "Alex", "type": "PERSON", "occurrence": 0},
        {"id": "alex-b", "name": "Alex", "type": "PERSON", "occurrence": 1},
        {"id": "alpha", "name": "Alpha", "type": "ORG", "occurrence": 0},
        {"id": "beta", "name": "Beta", "type": "ORG", "occurrence": 0}],
        "relations": [
            {"subject": "alex-a", "predicate": "leads", "object": "alpha", "evidence": "Alex leads Alpha.", "qualifiers": {"polarity": "positive"}},
            {"subject": "alex-b", "predicate": "leads", "object": "beta", "evidence": "Alex leads Beta.", "qualifiers": {"polarity": "positive"}}]}
    built = build(tmp_path, text, extraction)
    alex = [item for item in built["entities"] if item.canonical_name == "Alex"]
    assert len(alex) == 2
    assert len({item.source_entity_id for item in built["relations"]}) == 2
    reordered = build(tmp_path, text, {**extraction, "entities": list(reversed(extraction["entities"])), "relations": list(reversed(extraction["relations"]))})
    assert {item.id for item in built["entities"]} == {item.id for item in reordered["entities"]}
    assert {item.id for item in built["relations"]} == {item.id for item in reordered["relations"]}
    shifted = build(tmp_path, "Unrelated preface. " + text, extraction)
    assert {item.id for item in built["entities"]} == {item.id for item in shifted["entities"]}


def test_sentence_edit_preserves_mention_assertion_and_relation_ids(tmp_path):
    extraction = {"entities": [
        {"id": "alex", "name": "Alex", "type": "PERSON", "occurrence": 0},
        {"id": "alpha", "name": "Alpha", "type": "ORG", "occurrence": 0}],
        "relations": [
            {"subject": "alex", "predicate": "leads", "object": "alpha",
             "evidence": "Alex leads Alpha.", "qualifiers": {"polarity": "positive"}}]}
    original = build(tmp_path, "Alex leads Alpha.", extraction)
    edited_extraction = {**extraction, "relations": [{
        **extraction["relations"][0], "evidence": "Alex clearly leads Alpha.",
    }]}
    edited = build(tmp_path, "Alex clearly leads Alpha.", edited_extraction)

    assert {item.id for item in edited["entities"]} == {item.id for item in original["entities"]}
    assert {item.id for item in edited["assertions"]} == {item.id for item in original["assertions"]}
    assert {item.id for item in edited["relations"]} == {item.id for item in original["relations"]}


def facts(source, negated=False, year="2025"):
    qualifiers = {"polarity": "negative" if negated else "positive", "time": year, "condition": "at rest", "unit": "kg"}
    assertion = KnowledgeAssertion(id="assertion:" + source, subject_id="entity:alex", predicate="weighs", object="Mass", object_entity_id="entity:mass", qualifiers=qualifiers, evidence_ids=["evidence:" + source])
    relation = KnowledgeRelation(id="relation:" + source, source_entity_id=assertion.subject_id, target_entity_id=assertion.object_entity_id, type=assertion.predicate, qualifiers=qualifiers, evidence_ids=assertion.evidence_ids)
    return assertion, relation


def test_shared_fact_survives_reorder_and_support_withdrawal():
    first, second = facts("one"), facts("two")
    assertions, relations, conflicts = pipeline._shared_facts("project:one", [first[0], second[0]], [first[1], second[1]])
    assert len(assertions) == len(relations) == 1 and not conflicts
    assert assertions[0].support_ids == ["evidence:one", "evidence:two"]
    assert relations[0].support_ids == assertions[0].support_ids
    repeated = pipeline._shared_facts("project:one", [second[0], first[0]], [second[1], first[1]])
    assert repeated == (assertions, relations, conflicts)
    withdrawn = pipeline._shared_facts("project:one", [second[0]], [second[1]])
    assert withdrawn[0][0].id == assertions[0].id
    assert withdrawn[1][0].id == relations[0].id
    assert withdrawn[0][0].support_ids == ["evidence:two"]
    assert withdrawn[0][0].qualifiers == second[0].qualifiers


def test_only_opposite_polarity_under_identical_conditions_is_explicit_conflict():
    positive, negative, another_time = facts("one"), facts("two", True), facts("three", True, "2026")
    assertions, relations, conflicts = pipeline._shared_facts("project:one", [positive[0], negative[0], another_time[0]], [positive[1], negative[1], another_time[1]])
    assert len(assertions) == 3 and len(conflicts) == 1
    conflict = conflicts[0]
    assert set(conflict.evidence_ids) == {"evidence:one", "evidence:two"}
    assert len(conflict.assertion_ids) == len(conflict.relation_ids) == 2
    assert len([item for item in assertions if item.status == "contradicted"]) == 2
