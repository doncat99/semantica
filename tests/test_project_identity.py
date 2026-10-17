from semantica.kg.entity_resolver import EntityResolver
from semantica.semantic_artifact_builder import _resolve_native_entities, _remap_identity_facts
from semantica.semantic_artifact_schema import KnowledgeEntity, KnowledgeAssertion, KnowledgeRelation


def test_artifact_uses_native_resolution_ids_and_membership_without_model_calls(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("native identity resolution must not call a model")
    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", unexpected)
    monkeypatch.setattr("semantica.semantic_artifact_builder._product_json", unexpected)
    mentions = [KnowledgeEntity(id=f"mention:{index}", canonical_name=name, type="PERSON",
        evidence_ids=[f"evidence:{index}"], metadata={"source_ids": [f"source:{index}"]})
        for index, name in enumerate(["Ada Lovelace", "Ada Lovelace", "Charles Babbage"])]
    native = EntityResolver().resolve_entities([
        {"id": item.id, "name": item.canonical_name, "type": item.type,
         "properties": item.attributes, "metadata": item.metadata} for item in mentions])
    entities, remap, registry = _resolve_native_entities(mentions)
    assert [item.id for item in entities] == [item["id"] for item in native]
    for entity, row in zip(entities, native):
        members = row.get("merged_from") or [row["id"]]
        assert entity.metadata["mention_ids"] == members
        assert all(remap[member] == row["id"] for member in members)
        assert set(entity.evidence_ids) == {ref for item in mentions if item.id in members for ref in item.evidence_ids}
    assert {item.mention_id: item.entity_id for item in registry} == remap
    assertions = [KnowledgeAssertion(id="assertion:1", subject_id=mentions[1].id,
        predicate="knows", object="Charles Babbage", qualifiers={"polarity": "positive"},
        object_entity_id=mentions[2].id, evidence_ids=["evidence:1"])]
    relations = [KnowledgeRelation(id="relation:1", source_entity_id=mentions[1].id,
        target_entity_id=mentions[2].id, type="knows", qualifiers={"polarity": "positive"},
        evidence_ids=["evidence:1"])]
    assertions, relations = _remap_identity_facts(assertions, relations, remap, entities)
    assert assertions[0].subject_id == relations[0].source_entity_id == remap[mentions[1].id]
    assert assertions[0].object_entity_id == relations[0].target_entity_id == remap[mentions[2].id]
    assert assertions[0].evidence_ids == relations[0].evidence_ids == ["evidence:1"]


def test_native_projection_handles_empty_input():
    assert _resolve_native_entities([]) == ([], {}, [])


def test_identity_cannot_bypass_native_detection_and_merging(monkeypatch):
    import socket
    from semantica.deduplication.duplicate_detector import DuplicateDetector
    from semantica.deduplication.entity_merger import EntityMerger
    calls = {}
    for owner, method in [(EntityResolver, 'resolve_entities'),
                          (DuplicateDetector, 'detect_duplicate_groups'),
                          (EntityMerger, 'merge_duplicates')]:
        original = getattr(owner, method)
        def tracked(self, *args, _original=original, _method=method, **kwargs):
            calls[_method] = calls.get(_method, 0) + 1
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(owner, method, tracked)
    def network_forbidden(*args, **kwargs):
        raise AssertionError('identity must not send network requests')
    monkeypatch.setattr(socket.socket, 'connect', network_forbidden)
    monkeypatch.setattr(socket, 'create_connection', network_forbidden)
    entities, remap, _ = _resolve_native_entities([
        KnowledgeEntity(id=f'mention:{index}', canonical_name='Ada Lovelace', type='PERSON')
        for index in range(2)])
    assert len(entities) == 1
    assert len(set(remap.values())) == 1
    assert calls['resolve_entities'] == calls['merge_duplicates'] == 1
    assert calls['detect_duplicate_groups'] >= 1
