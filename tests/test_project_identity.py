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
    native = EntityResolver(strategy="exact").resolve_entities([
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


def test_native_resolution_does_not_mutate_source_mentions():
    mentions = [KnowledgeEntity(id=f'mention:{index}', canonical_name='Ada Lovelace',
        type='PERSON', attributes={'key': '1'}, aliases=['Ada'],
        metadata={'source_ids': [f'source:{index}']}) for index in range(2)]
    before = [item.model_dump(mode='json') for item in mentions]
    _resolve_native_entities(mentions)
    assert [item.model_dump(mode='json') for item in mentions] == before


def test_native_projection_preserves_native_alias_resolution():
    entities, remap, _ = _resolve_native_entities([
        KnowledgeEntity(id='long', canonical_name='International Business Machines',
                        type='ORGANIZATION', aliases=['IBM']),
        KnowledgeEntity(id='short', canonical_name='IBM', type='ORGANIZATION')])
    assert len(entities) == 1
    assert remap['long'] == remap['short']
    assert {entities[0].canonical_name, *entities[0].aliases} == {
        'IBM', 'International Business Machines'}
    assert 'identity_status' not in entities[0].metadata


def test_identity_cannot_bypass_native_detection_and_merging(monkeypatch):
    import socket
    from semantica.deduplication.duplicate_detector import DuplicateDetector
    from semantica.deduplication.entity_merger import EntityMerger
    calls = {}
    for owner, method in [(EntityResolver, 'resolve_entities'),
                          (DuplicateDetector, 'detect_duplicate_groups'),
                          (EntityMerger, 'merge_entity_group')]:
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
        KnowledgeEntity(id=f'mention:{index}', canonical_name='Ada Lovelace', type='PERSON',
                        attributes={'external_key': '1'})
        for index in range(2)], property_schema={'external_key': {'identity': True}})
    assert len(entities) == 1
    assert len(set(remap.values())) == 1
    assert calls['resolve_entities'] == calls['merge_entity_group'] == 1
    assert calls.get('detect_duplicate_groups', 0) == 0


def test_projection_scoped_conflict_veto_preserves_native_mapping_and_endpoints():
    mentions = [KnowledgeEntity(id=f'entity:{key}', canonical_name='ZZZZZZZ' if key == 'd' else 'Same company', type='ORGANIZATION',
                               attributes=props, evidence_ids=[f'proof:{key}'])
                for key, props in [('a', {'key': '1', 'scope': 'X'}),
                                   ('b', {'key': '1', 'scope': 'X'}),
                                   ('c', {'key': '2', 'scope': 'X'}),
                                   ('d', {})]]
    # Without conflict semantics, native positive resolution is unchanged.
    assert len(_resolve_native_entities(mentions)[0]) == 2
    entities, remap, registry = _resolve_native_entities(
        mentions, property_schema={'key': {'identity': True, 'scope': ['scope']}})
    assert len(entities) == 3
    assert remap['entity:a'] == remap['entity:b']
    assert len({remap['entity:a'], remap['entity:c'], remap['entity:d']}) == 3
    merged = next(item for item in entities if item.id == remap['entity:a'])
    assert set(merged.evidence_ids) == {'proof:a', 'proof:b'}
    assert {item.entity_id for item in registry if item.mention_id in ('entity:a', 'entity:b')} == {merged.id}
    relations = [KnowledgeRelation(id='relation:1', source_entity_id='entity:a', target_entity_id='entity:d',
                                   type='mentions', qualifiers={'polarity': 'positive'})]
    _, relations = _remap_identity_facts([], relations, remap, entities)
    assert relations[0].source_entity_id == remap['entity:a']
    assert relations[0].target_entity_id == 'entity:d'


def test_artifact_delegates_to_supplied_native_threshold():
    mentions = [KnowledgeEntity(id=key, canonical_name=name, type='ORG')
                for key, name in [('mention:a', 'Acme Holdings'), ('mention:b', 'Acne Holding')]]
    assert len(_resolve_native_entities(mentions)[0]) == 2
    assert len(_resolve_native_entities(mentions, resolver=EntityResolver(similarity_threshold=0.99))[0]) == 2


def test_project_default_identity_resolution_is_exact_not_fuzzy():
    mentions = [
        KnowledgeEntity(id="mention:one", canonical_name="Acme Holdings", type="ORG"),
        KnowledgeEntity(id="mention:two", canonical_name="Acne Holding", type="ORG"),
    ]
    entities, remap, _ = _resolve_native_entities(mentions)
    assert len(entities) == 2
    assert remap["mention:one"] != remap["mention:two"]
