from tests.artifact_helpers import build_source_fixture
from semantica import semantic_publication_builder as pipeline
from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation, SourceBuildInput
from semantica.source import source_content_revision


def build(tmp_path, text, extraction):
    path = tmp_path / "source.txt"
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId="source:one", name=path.name,
                             materialRevision=source_content_revision(path), mimeType="text/plain")
    return build_source_fixture(source, False, extraction)


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
    assert {item.id for item in built["entities"]}.isdisjoint(item.id for item in shifted["entities"])


def test_new_immutable_parse_has_new_observation_addresses(tmp_path):
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

    for kind in ('entities', 'assertions', 'relations'):
        assert {item.id for item in edited[kind]}.isdisjoint(item.id for item in original[kind])


def facts(source, negated=False, year="2025"):
    qualifiers = {"polarity": "negative" if negated else "positive", "time": year, "condition": "at rest", "unit": "kg"}
    assertion = KnowledgeAssertion(id="assertion:" + source, subject_id="entity:alex", predicate="weighs", object="Mass", object_entity_id="entity:mass", qualifiers=qualifiers, evidence_ids=["evidence:" + source])
    relation = KnowledgeRelation(id="relation:" + source, source_entity_id=assertion.subject_id, target_entity_id=assertion.object_entity_id, type=assertion.predicate, qualifiers=qualifiers, evidence_ids=assertion.evidence_ids)
    return assertion, relation


def test_shared_fact_survives_reorder_and_support_withdrawal():
    first, second = facts("one"), facts("two")
    assertions, relations, conflicts = pipeline.reconcile_qualified_facts("project:one", [first[0], second[0]], [first[1], second[1]])
    assert len(assertions) == len(relations) == 1 and not conflicts
    assert assertions[0].support_ids == ["evidence:one", "evidence:two"]
    assert relations[0].support_ids == assertions[0].support_ids
    repeated = pipeline.reconcile_qualified_facts("project:one", [second[0], first[0]], [second[1], first[1]])
    assert repeated == (assertions, relations, conflicts)
    withdrawn = pipeline.reconcile_qualified_facts("project:one", [second[0]], [second[1]])
    assert withdrawn[0][0].id == assertions[0].id
    assert withdrawn[1][0].id == relations[0].id
    assert withdrawn[0][0].support_ids == ["evidence:two"]
    assert withdrawn[0][0].qualifiers == second[0].qualifiers


def test_only_opposite_polarity_under_identical_conditions_is_explicit_conflict():
    positive, negative, another_time = facts("one"), facts("two", True), facts("three", True, "2026")
    assertions, relations, conflicts = pipeline.reconcile_qualified_facts("project:one", [positive[0], negative[0], another_time[0]], [positive[1], negative[1], another_time[1]])
    assert len(assertions) == 3 and len(conflicts) == 1
    conflict = conflicts[0]
    assert set(conflict.evidence_ids) == {"evidence:one", "evidence:two"}
    assert len(conflict.assertion_ids) == len(conflict.relation_ids) == 2
    assert len([item for item in assertions if item.status == "contradicted"]) == 2


def test_entity_object_and_typed_literal_do_not_share_identity_or_polarity():
    from semantica.conflicts.conflict_detector import ConflictDetector
    base=dict(id='assertion:a',subject_id='entity:s',predicate='p',object='entity:target',
        qualifiers={'polarity':'positive'},evidence_ids=['evidence:e'])
    values=[dict(base,object_entity_id='entity:target'),base,
        dict(base,object=1),dict(base,object=True),dict(base,object='1'),
        dict(base,object={'value':'1','datatype':'integer'}),
        dict(base,object={'value':'1','datatype':'string'})]
    assert len({ConflictDetector.qualified_fact_identity('p',item,'assertion') for item in values})==len(values)
    positive=KnowledgeAssertion(**values[0])
    negative=KnowledgeAssertion(**dict(base,id='assertion:b',qualifiers={'polarity':'negative'}))
    assertions,_,conflicts=ConflictDetector.reconcile_qualified_facts('p',[positive,negative],[])
    assert len(assertions)==2 and not conflicts
