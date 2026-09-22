from types import SimpleNamespace

import pytest

from semantica.project_identity import resolve_project_identities
from semantica.project_snapshot_schema import KnowledgeEntity


def mention(identifier, name="Ada Lovelace", source="source:one", kind="PERSON"):
    return KnowledgeEntity(id=identifier, canonical_name=name, type=kind, evidence_ids=["evidence:" + identifier.split(":")[-1]], metadata={"source_ids": [source]})


def resolve(mentions, judgments, base=None):
    return resolve_project_identities(project_id="project:one", mentions=mentions, judgments=judgments, base_snapshot=base, receipt_id="receipt:identity")[:3]


def resolve_with_registry(mentions, judgments, base=None):
    return resolve_project_identities(project_id="project:one", mentions=mentions, judgments=judgments, base_snapshot=base, receipt_id="receipt:identity")


def test_shared_identity_preserves_mentions_evidence_and_id_after_original_source_removal():
    first = mention("mention:first")
    second = mention("mention:second", "Augusta Ada King", "source:two")
    entities, mapping, decisions = resolve([first, second], [{"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "Both source contexts identify the same mathematician by the explicit Ada Lovelace / Augusta Ada King alias."}])
    assert len(entities) == 1
    assert mapping[first.id] == mapping[second.id] == entities[0].id
    assert entities[0].evidence_ids == [*first.evidence_ids, *second.evidence_ids]
    assert decisions[0].from_entity_ids == [first.id, second.id]
    assert decisions[0].metadata["model_receipt_id"] == "receipt:identity"
    later, _, _ = resolve([second], [], SimpleNamespace(entities=entities))
    assert later[0].id == entities[0].id
    assert later[0].evidence_ids == second.evidence_ids


def test_homonyms_are_not_merged_without_a_judgment():
    entities, mapping, decisions = resolve([mention("mention:first"), mention("mention:second", source="source:two")], [])
    assert len(entities) == 2
    assert len(set(mapping.values())) == 2
    assert decisions == []


@pytest.mark.parametrize("judgment", [
    None,
    {"mention_ids": ["mention:first", "mention:unknown"], "evidence_ids": ["evidence:first", "evidence:second"], "reason": "invalid member"},
    {"mention_ids": ["mention:first", "mention:second"], "evidence_ids": ["evidence:first"], "reason": "missing second source evidence"},
    {"mention_ids": ["mention:first", "mention:second"], "evidence_ids": ["evidence:first", "evidence:second", "evidence:invented"], "reason": "invented citation"},
])
def test_unproven_identity_merge_is_rejected(judgment):
    with pytest.raises(ValueError, match="identity judgment"):
        resolve([mention("mention:first"), mention("mention:second", source="source:two")], [judgment])


def test_missing_merge_judgment_preserves_previous_identity():
    first, second = mention("mention:first"), mention("mention:second", source="source:two")
    original, _, _ = resolve([first, second], [{"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "corroborated alias"}])
    retained, _, _ = resolve([first, second], [], SimpleNamespace(entities=original, identity_decisions=[]))
    assert len(retained) == 1
    assert retained[0].id == original[0].id


def test_explicit_split_survives_rebuild_and_rejects_unacknowledged_remerge():
    first, second = mention("mention:first"), mention("mention:second", source="source:two")
    merge = {"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "corroborated alias"}
    original, _, _ = resolve([first, second], [merge])
    split = {**merge, "decision_type": "split", "groups": [[first.id], [second.id]], "reason": "Evidence identifies two different people"}
    separated, _, decisions = resolve([first, second], [split], SimpleNamespace(entities=original, identity_decisions=[]))
    assert len({item.id for item in separated}) == 2
    assert original[0].id in {item.id for item in separated}
    assert any(item.decision_type == "split" for item in decisions)
    base = SimpleNamespace(entities=separated, identity_decisions=decisions)
    repeated, _, next_decisions = resolve([first, second], [], base)
    assert {item.id for item in repeated} == {item.id for item in separated}
    assert any(item.decision_type == "split" for item in next_decisions)
    with pytest.raises(ValueError, match="split"):
        resolve([first, second], [merge], base)


def test_identity_registry_preserves_entity_across_sentence_edit_and_full_withdrawal():
    original = mention("mention:before", name="Alex")
    entities, _, decisions, registry = resolve_with_registry([original], [])
    base = SimpleNamespace(entities=entities, identity_decisions=decisions, identity_registry=registry)

    edited = mention("mention:after", name="Alex")
    rebuilt, mapping, _, registry = resolve_with_registry([edited], [], base)
    assert rebuilt[0].id == entities[0].id
    assert mapping[edited.id] == entities[0].id

    withdrawn, _, _, registry = resolve_with_registry(
        [], [], SimpleNamespace(entities=rebuilt, identity_decisions=[], identity_registry=registry)
    )
    assert withdrawn == []
    readded, mapping, _, _ = resolve_with_registry(
        [edited], [], SimpleNamespace(entities=[], identity_decisions=[], identity_registry=registry)
    )
    assert readded[0].id == entities[0].id
    assert mapping[edited.id] == entities[0].id


def test_split_does_not_break_later_merge_with_an_outsider():
    first = mention("mention:a", name="Alex")
    second = mention("mention:b", name="Alex", source="source:two")
    outsider = mention("mention:c", name="A. Example", source="source:three")
    merge_ab = {"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "same person"}
    merged, _, merge_decisions, registry = resolve_with_registry([first, second], [merge_ab])
    split_ab = {**merge_ab, "decision_type": "split", "groups": [[first.id], [second.id]], "reason": "different people"}
    separated, _, split_decisions, registry = resolve_with_registry(
        [first, second], [split_ab],
        SimpleNamespace(entities=merged, identity_decisions=merge_decisions, identity_registry=registry),
    )
    second_entity_id = next(item.id for item in separated if second.id in item.metadata["mention_ids"])

    merge_bc = {"mention_ids": [second.id, outsider.id], "evidence_ids": [*second.evidence_ids, *outsider.evidence_ids], "reason": "explicit alias"}
    merged_bc, _, decisions, registry = resolve_with_registry(
        [second, outsider], [merge_bc],
        SimpleNamespace(entities=separated, identity_decisions=split_decisions, identity_registry=registry),
    )
    assert len(merged_bc) == 1
    assert merged_bc[0].id == second_entity_id

    final, _, _, _ = resolve_with_registry(
        [first, second, outsider], [],
        SimpleNamespace(entities=merged_bc, identity_decisions=decisions, identity_registry=registry),
    )
    assert sorted(sorted(item.metadata["mention_ids"]) for item in final) == [
        [first.id], [second.id, outsider.id],
    ]


def test_persisted_split_keeps_unadjudicated_outsider_independent():
    first = mention("mention:a", name="Alex")
    second = mention("mention:b", name="Alex", source="source:two")
    outsider = mention("mention:c", name="Alex", source="source:three")
    merge = {"mention_ids": [first.id, second.id, outsider.id],
             "evidence_ids": [*first.evidence_ids, *second.evidence_ids, *outsider.evidence_ids],
             "reason": "initially treated as one person"}
    merged, _, decisions, registry = resolve_with_registry([first, second, outsider], [merge])
    split = {"mention_ids": [first.id, second.id], "decision_type": "split",
             "groups": [[first.id], [second.id]],
             "evidence_ids": [*first.evidence_ids, *second.evidence_ids],
             "reason": "evidence separates the first two mentions"}
    _, _, decisions, _ = resolve_with_registry(
        [first, second], [split],
        SimpleNamespace(entities=merged, identity_decisions=decisions, identity_registry=registry),
    )

    rebuilt, _, _, _ = resolve_with_registry(
        [first, second, outsider], [],
        SimpleNamespace(entities=merged, identity_decisions=decisions, identity_registry=registry),
    )
    assert sorted(item.metadata["mention_ids"] for item in rebuilt) == [
        [first.id], [second.id], [outsider.id],
    ]


def test_identity_decisions_are_immutable_and_split_has_no_single_target():
    first, second = mention("mention:first"), mention("mention:second", source="source:two")
    merge = {"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "same person"}
    original, _, merge_decisions, registry = resolve_with_registry([first, second], [merge])
    split = {**merge, "decision_type": "split", "groups": [[first.id], [second.id]], "reason": "different people"}
    separated, _, decisions, registry = resolve_with_registry(
        [first, second], [split],
        SimpleNamespace(entities=original, identity_decisions=merge_decisions, identity_registry=registry),
    )
    split_decision = next(item for item in decisions if item.decision_type == "split")
    assert split_decision.to_entity_id is None
    frozen = [item.model_dump(mode="json") for item in decisions]

    _, _, next_decisions, _ = resolve_with_registry(
        [second], [],
        SimpleNamespace(entities=separated, identity_decisions=decisions, identity_registry=registry),
    )
    assert [item.model_dump(mode="json") for item in next_decisions] == frozen
