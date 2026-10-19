from types import SimpleNamespace

import pytest

from semantica.context.context_retriever import ContextRetriever
from semantica.semantic_artifact_builder import reconcile_qualified_facts
from semantica.semantic_artifact_schema import KnowledgeAssertion, SemanticArtifact, KnowledgeConflict, KnowledgeEntity
from tests.test_native_persistent_center import snapshot


def fact(identifier, value, *, time="2026", status="accepted", predicate="website"):
    return KnowledgeAssertion(id=identifier, subject_id="company:one", predicate=predicate,
        object=value, qualifiers={"polarity": "positive", "time": time}, status=status)


def test_functional_conflicts_preserve_time_and_structured_values():
    inputs = [fact("fact:one", {"a": 1, "b": 2}), fact("fact:two", {"b": 2, "a": 1}),
              fact("fact:three", {"a": 3}), fact("fact:old", "old", time="2025"),
              fact("fact:gone", "gone", status="retracted"),
              fact("fact:tag1", "one", predicate="tag"), fact("fact:tag2", "two", predicate="tag")]
    assertions, _, conflicts = reconcile_qualified_facts("scope:one", inputs, [], functional_predicates={"website"})
    assert len(conflicts) == 1
    assert len(conflicts[0].assertion_ids) == 2
    assert sum(item.status == "contradicted" for item in assertions) == 2
    reversed_result = reconcile_qualified_facts("scope:one", inputs[::-1], [], functional_predicates={"website"})
    assert reversed_result == (assertions, [], conflicts)


def test_context_is_explicitly_scoped_versioned_and_never_silently_truncated():
    data = snapshot("scope:one")
    data["assertions"] = [fact("fact:one", "https://example.org").model_dump()]
    artifact = SemanticArtifact.model_validate(data)

    def read(scope, version):
        return artifact if scope == "scope:one" and version in (None, "snapshot:one") else None

    retriever = ContextRetriever(knowledge_graph=SimpleNamespace(read_snapshot=read))
    result = retriever.retrieve_snapshot_context("scope:one", ["company:one"])
    assert result["snapshot_id"] == "snapshot:one" and result["truncated"] is False
    assert result["assertions"][0]["object"] == "https://example.org"
    assert result['assertion_groups'][0]['status'] == 'accepted'
    assert result['assertion_groups'][0]['values'] == ['https://example.org']
    for scope, version in (("scope:other", None), ("scope:one", "snapshot:missing")):
        with pytest.raises(ValueError, match="semantic_snapshot_not_found"):
            retriever.retrieve_snapshot_context(scope, ["company:one"], version)
    with pytest.raises(ValueError, match="entity_not_found"):
        retriever.retrieve_snapshot_context("scope:one", ["company:other"])
    with pytest.raises(ValueError, match="budget_exceeded"):
        retriever.retrieve_snapshot_context("scope:one", ["company:one"], max_bytes=20)


def test_merge_status_is_order_independent_and_withdrawn_support_is_not_live():
    from itertools import permutations
    inputs = [fact("fact:import", "same", status="candidate"),
              fact("fact:reviewed", "same"), fact("fact:withdrawn", "same", status="retracted")]
    for item in inputs:
        item.evidence_ids = ["evidence:" + item.id.split(":")[1]]
        item.metadata = {"source": item.id}
    expected = None
    for ordering in permutations(inputs):
        merged, _, _ = reconcile_qualified_facts("scope:one", list(ordering), [])
        assert merged[0].status == "accepted"
        assert merged[0].support_ids == ["evidence:import", "evidence:reviewed"]
        assert len(merged[0].metadata["support_observations"]) == 3
        expected = expected or merged
        assert merged == expected
    assert reconcile_qualified_facts("scope:one", expected, [])[0] == expected
    assert reconcile_qualified_facts("scope:one", [inputs[0], inputs[2]], [])[0][0].status == "candidate"
    assert reconcile_qualified_facts("scope:one", [inputs[2]], [])[0][0].status == "retracted"


def test_context_closes_transitive_conflicts_and_enforces_budget_after_expansion():
    data = snapshot("scope:one")
    data["entities"] += [KnowledgeEntity(id="company:two", canonical_name="Other", type="Company").model_dump()]
    first = fact("fact:one", "one")
    second = fact("fact:two", "two").model_copy(update={"subject_id": "company:two"})
    third = fact("fact:three", "three").model_copy(update={"subject_id": "company:two"})
    data["assertions"] = [item.model_dump() for item in [first, second, third]]
    data["conflicts"] = [KnowledgeConflict(id="conflict:" + str(index), conflict_type="assertion",
        assertion_ids=refs, reason="test").model_dump() for index, refs in
        enumerate([[first.id, second.id], [second.id, third.id]])]
    artifact = SemanticArtifact.model_validate(data)
    retriever = ContextRetriever(knowledge_graph=SimpleNamespace(read_snapshot=lambda *args: artifact))
    context = retriever.retrieve_snapshot_context("scope:one", ["company:one"])
    assert {item["id"] for item in context["assertions"]} == {first.id, second.id, third.id}
    assert len(context["entities"]) == 2
    assert all(item['status'] == 'contradicted' for item in context['assertion_groups'])
    with pytest.raises(ValueError, match="budget_exceeded"):
        retriever.retrieve_snapshot_context("scope:one", ["company:one"], max_facts=1)


def test_explicit_selection_keeps_conflict_closure_without_unrelated_properties():
    data = snapshot('scope:one')
    data['assertions'] = [fact('website:one', 'one').model_dump(), fact('website:two', 'two').model_dump(),
                          fact('phone:one', 'one', predicate='phone').model_dump(),
                          fact('phone:two', 'two', predicate='phone').model_dump()]
    data['conflicts'] = [KnowledgeConflict(id='conflict:' + predicate, conflict_type='assertion',
        entity_ids=['company:one'], assertion_ids=[predicate+':one', predicate+':two'],
        reason='test').model_dump() for predicate in ('website', 'phone')]
    artifact = SemanticArtifact.model_validate(data)
    retriever = ContextRetriever(knowledge_graph=SimpleNamespace(read_snapshot=lambda *args: artifact))
    result = retriever.retrieve_snapshot_context('scope:one', ['company:one'],
        predicates=['website'], relation_types=[], max_facts=2)
    assert {item['id'] for item in result['assertions']} == {'website:one', 'website:two'}
    assert [item['id'] for item in result['conflicts']] == ['conflict:website']
    assert result['assertion_groups'][0]['status'] == 'contradicted'
    assert not retriever.retrieve_snapshot_context('scope:one', ['company:one'],
        predicates=[], relation_types=[])['assertions']
