from semantica.kg.entity_resolver import EntityResolver
from semantica.semantic_artifact_builder import _resolve_native_entities, _remap_identity_facts
from semantica.semantic_artifact_schema import KnowledgeEntity, KnowledgeAssertion, KnowledgeRelation


import pytest


@pytest.mark.parametrize('quote,owner', [
    ('Acme manufactures medical instruments.', 'Acme'),
    (' Acme manufactures medical instruments. ', 'Acme'),
    ('Acme manufactures medical instruments.', 'Acme manufactures'),
])
def test_profile_offsets_survive_window_assembly_and_source_projection(tmp_path, quote, owner):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _assemble_grounded_windows, _build_source
    from semantica.semantic_extract.methods import extract_entities_llm
    from semantica.semantic_extract.schemas import EntitiesResponse, EntityOut
    from tests.semantic_extract.test_grounded_llm_extraction import TypedProvider
    prefix = 'Previous section.\n'
    window = 'Acme manufactures\nmedical instruments.'
    text = prefix + window
    provider = TypedProvider(EntitiesResponse(entities=[EntityOut(text='Acme', label='ORG', occurrence=0,
        identity_profile={'description': 'A medical instrument manufacturer', 'evidence': quote,
                          'evidence_occurrence': 0, 'referent_kind': 'named_entity',
                          'owner': owner})]))
    mentions = extract_entities_llm(window, provider='bifrost', provider_instance=provider, grounding='strict')
    result, _ = _assemble_grounded_windows([(len(prefix), len(text), window)],
        [({'entities': mentions, 'relations': []}, [], False)])
    source = SimpleNamespace(source_id='source:acme', name='Acme', file_path=str(tmp_path / 'source.txt'),
                             material_revision='b3-' + '1' * 64, mime_type='text/plain')
    built = _build_source(source, False, result,
        (text, {'text': text}, 'native', 'b3-' + '1' * 64, 'text', '1'))
    entity, = built['entities']
    support, = entity.metadata['description_evidence_ids']
    span = next(item for item in built['evidence'] if item.id == support)
    assert entity.description == 'A medical instrument manufacturer'
    assert entity.metadata['identity_profile']['owner'] == owner
    assert entity.metadata['identity_profile']['referent_kind'] == 'named_entity'
    assert span.locator.start_char == len(prefix)
    assert span.locator.end_char == len(text)
    assert text[span.locator.start_char:span.locator.end_char] == span.quote == window
    assert len(provider.prompts) == 1


@pytest.mark.parametrize('stored_start,stored_quote', [(1, 'Acme reports.'), (0, 'Acme invents.')])
def test_window_assembly_rejects_incorrect_profile_support(stored_start, stored_quote):
    from semantica.semantic_artifact_builder import _assemble_grounded_windows
    from semantica.semantic_artifact_errors import SemanticArtifactError
    from semantica.semantic_extract.types import Entity
    from semantica.utils.exceptions import ProcessingError
    window = 'Acme reports.'
    entity = Entity(text='Acme', label='ORG', start_char=0, end_char=4,
        metadata={'mention_id': 'mention:0', 'identity_profile': {
            'description': 'Company', 'evidence': stored_quote, 'evidence_occurrence': 0,
            'evidence_start': stored_start, 'evidence_end': len(window)}})
    with pytest.raises((SemanticArtifactError, ProcessingError)):
        _assemble_grounded_windows([(0, len(window), window)],
            [({'entities': [entity], 'relations': []}, [], True)])


def test_source_keeps_paraphrased_description_with_separately_located_support(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _build_source
    text = 'Acme reports.\nAcme manufactures medical instruments.'
    quote = text
    profile = {'description': 'A medical instrument manufacturer', 'evidence': quote,
               'evidence_start': text.index(quote), 'evidence_end': len(text), 'evidence_occurrence': 0}
    result = {'entities': [dict(id='a', name='Acme', type='ORG', occurrence=0,
                               attributes={}, identity_profile=profile)], 'relations': []}
    source = SimpleNamespace(source_id='source:acme', name='Acme', file_path=str(tmp_path / 'source.txt'),
                             material_revision='b3-' + '1' * 64, mime_type='text/plain')
    parsed = (text, {'text': text}, 'native', 'b3-' + '1' * 64, 'text', '1')
    built = _build_source(source, False, result, parsed)
    entity, = built['entities']
    assert entity.description == profile['description']
    assert entity.context == 'Acme reports.\n'
    support, = entity.metadata['description_evidence_ids']
    assert next(span.quote for span in built['evidence'] if span.id == support) == quote
    assert support in entity.evidence_ids
    without_profile = {key: value for key, value in result['entities'][0].items() if key != 'identity_profile'}
    without_profile['id'] = 'overlapping-window-mention'
    overlapped = _build_source(source, False,
        {'entities': [without_profile, result['entities'][0]], 'relations': []}, parsed)
    assert len(overlapped['entities']) == 1
    assert overlapped['entities'][0].description == profile['description']
    assert overlapped['entities'][0].metadata['description_evidence_ids'] == [support]
    repeated = entity.model_copy(deep=True)
    repeated.id = 'repeated'
    repeated.description = ''
    repeated.metadata.pop('description_evidence_ids')
    repeated.metadata.pop('identity_profile')
    canonical, _, _ = _resolve_native_entities([repeated, entity])
    assert len(canonical) == 1
    assert canonical[0].description == profile['description']
    assert canonical[0].metadata['description_evidence_ids'] == [support]


def test_source_identity_context_is_located_and_description_must_be_grounded(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _build_source
    text = 'Earlier sentence. Acme is a manufacturer of precision medical instruments. Next sentence.'
    result = {'entities': [dict(id='acme', name='Acme', type='ORG', occurrence=0,
                               attributes={'description': 'manufacturer of precision medical instruments'})],
              'relations': []}
    source = SimpleNamespace(source_id='source:acme', name='Acme', file_path=str(tmp_path / 'source.txt'),
                             material_revision='b3-' + '1' * 64, mime_type='text/plain')
    parsed = (text, {'text': text}, 'native', 'b3-' + '1' * 64, 'text', '1')
    built = _build_source(source, False, result, parsed)
    entity = built['entities'][0]
    assert entity.context.strip() == 'Acme is a manufacturer of precision medical instruments.'
    spans = {span.id: span for span in built['evidence']}
    located = spans[entity.metadata['identity_context_evidence_id']]
    assert located.quote == entity.context
    assert text[located.locator.start_char:located.locator.end_char] == entity.context
    assert located.id in entity.evidence_ids
    assert entity.description == result['entities'][0]['attributes']['description']
    result['entities'][0]['attributes']['description'] = 'An ungrounded generated description'
    assert _build_source(source, False, result, parsed)['entities'][0].description == ''


def test_artifact_uses_native_resolution_ids_and_membership_without_model_calls(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("native identity resolution must not call a model")
    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", unexpected)
    monkeypatch.setattr("semantica.semantic_artifact_builder._product_json", unexpected)
    mentions = [KnowledgeEntity(id=f"mention:{index}", canonical_name=name, type="PERSON",
        context=f"{name} worked on mechanical computation and mathematics.",
        evidence_ids=[f"evidence:{index}"], metadata={"source_ids": [f"source:{index}"]})
        for index, name in enumerate(["Ada Lovelace", "Ada Lovelace", "Charles Babbage"])]
    native = EntityResolver(strategy="contextual").resolve_entities([
        {"id": item.id, "name": item.canonical_name, "type": item.type,
         "properties": item.attributes, "metadata": item.metadata, "context": item.context} for item in mentions])
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
                        type='ORGANIZATION', aliases=['IBM'],
                        context='International Business Machines (IBM) manufactures computers.'),
        KnowledgeEntity(id='short', canonical_name='IBM', type='ORGANIZATION',
                        context='International Business Machines (IBM) manufactures computers.')])
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
    assert calls['detect_duplicate_groups'] == 1


def test_projection_scoped_conflict_veto_preserves_native_mapping_and_endpoints():
    mentions = [KnowledgeEntity(id=f'entity:{key}', canonical_name='ZZZZZZZ' if key == 'd' else 'Same company', type='ORGANIZATION',
                               attributes=props, evidence_ids=[f'proof:{key}'])
                for key, props in [('a', {'key': '1', 'scope': 'X'}),
                                   ('b', {'key': '1', 'scope': 'X'}),
                                   ('c', {'key': '2', 'scope': 'X'}),
                                   ('d', {})]]
    # Undeclared properties are not trusted identity evidence.
    assert len(_resolve_native_entities(mentions)[0]) == 4
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


def test_project_default_identity_resolution_does_not_merge_fuzzy_names():
    mentions = [
        KnowledgeEntity(id="mention:one", canonical_name="Acme Holdings", type="ORG"),
        KnowledgeEntity(id="mention:two", canonical_name="Acne Holding", type="ORG"),
    ]
    entities, remap, _ = _resolve_native_entities(mentions)
    assert len(entities) == 2
    assert remap["mention:one"] != remap["mention:two"]


def test_source_scope_and_description_are_reused_by_native_projection(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _build_source
    description = "manufacturer of precision medical instruments"
    text = "Acme reports results. Acme is a " + description + ". Acme publishes accounts."
    source = SimpleNamespace(source_id="source:acme", name="Acme", material_revision="b3-" + "1" * 64,
                             mime_type="text/plain")
    result = {"entities": [dict(id=str(index), name="Acme", type="ORG", occurrence=index,
        attributes={"description": description} if index == 1 else {}) for index in range(3)], "relations": []}
    built = _build_source(source, False, result, (text, {"text": text}, "native", "b3-" + "1" * 64, "text", "1"))
    assert {item.metadata["identity_scope"] for item in built["entities"]} == {built["representation"].id}
    before = [item.model_dump(mode="json") for item in built["entities"]]
    entities, remap, registry = _resolve_native_entities(built["entities"])
    entity, = entities
    assert len(set(remap.values())) == 1 and len(registry) == 3
    assert entity.description == description and description in entity.context
    assert entity.metadata["description_mention_id"] in entity.metadata["mention_ids"]
    assert set(entity.metadata["description_evidence_ids"]) <= set(entity.evidence_ids)
    spans = {item.id: item for item in built["evidence"]}
    assert spans[entity.metadata["identity_context_evidence_id"]].quote == entity.context
    assert [item.model_dump(mode="json") for item in built["entities"]] == before


def test_representation_revision_is_an_identity_scope_boundary():
    from types import SimpleNamespace
    from semantica.semantic_artifact_builder import _build_source
    source = SimpleNamespace(source_id="source:acme", name="Acme", material_revision="b3-" + "1" * 64,
                             mime_type="text/plain")
    result = {"entities": [dict(id="a", name="Acme", type="ORG", occurrence=0, attributes={})], "relations": []}
    builds = [_build_source(source, False, result, (text, {"text": text}, "native", "b3-" + char * 64, "text", "1"))
              for char, text in [("1", "Acme reports results."), ("2", "Acme publishes accounts.")]]
    assert builds[0]["entities"][0].metadata["identity_scope"] != builds[1]["entities"][0].metadata["identity_scope"]
