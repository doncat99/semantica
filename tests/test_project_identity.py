from types import SimpleNamespace

import pytest

from semantica.project_identity import resolve_project_identities
from semantica.project_snapshot_schema import KnowledgeEntity


def mention(identifier, name="Ada Lovelace", source="source:one", kind="PERSON"):
    return KnowledgeEntity(id=identifier, canonical_name=name, type=kind, evidence_ids=["evidence:" + identifier.split(":")[-1]], metadata={"source_ids": [source]})


def resolve(mentions, judgments, base=None):
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


def test_split_keeps_one_previous_identity_and_gives_distinct_identity_to_other_group():
    first, second = mention("mention:first"), mention("mention:second", source="source:two")
    original, _, _ = resolve([first, second], [{"mention_ids": [first.id, second.id], "evidence_ids": [*first.evidence_ids, *second.evidence_ids], "reason": "corroborated alias"}])
    separated, _, decisions = resolve([first, second], [], SimpleNamespace(entities=original))
    assert len({item.id for item in separated}) == 2
    assert original[0].id in {item.id for item in separated}
    assert any(item.decision_type == "split" for item in decisions)
