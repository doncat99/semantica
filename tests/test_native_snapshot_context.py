from semantica.semantic_artifact_builder import reconcile_qualified_facts
from semantica.semantic_artifact_schema import KnowledgeAssertion


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
