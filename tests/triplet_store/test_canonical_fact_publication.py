import pytest
from semantica.utils.exceptions import ProcessingError
from semantica.semantic_extract.types import Entity, Relation
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.extraction_records import ExtractionRecords
from tests.triplet_store.test_publication_records import indexes

def stage_duplicate_observations(tmp_path):
    store = OxigraphStore(tmp_path / 'facts')
    text = 'Acme owns Engine'
    ids_by_endpoint = [[], []]
    sources = []
    native_relations = []
    for source in ('s1', 's2'):
        bound = dict(project='p', source=source, material='m', representation='r:'+source,
            recipe='recipe', model='model', specification='spec', parser='parser',
            grounding='grounding', window_start=0, window_end=len(text))
        ranges = [dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0, windowEnd=len(text))]
        acme = Entity('Acme', 'ORG', 0, 4, .7, dict(mention_id='a', span_occurrence=0))
        engine = Entity('Engine', 'ORG', 10, 16, .7, dict(mention_id='b', span_occurrence=0))
        entities = store.adopt_extraction(bound, 'entities', [acme, engine], text=text,
            native_ranges=ranges, accepted_digest='entities:'+source)
        relation = Relation(acme, 'owns', engine, .8, text, dict(subject_id='a', object_id='b',
            evidence_start=0, evidence_end=len(text), evidence_occurrence=0,
            qualifiers=dict(polarity='positive')))
        relations = store.adopt_extraction(bound, 'relations', [relation], text=text,
            native_ranges=ranges, accepted_digest='relations:'+source)
        native_relations.append(ExtractionRecords(store,bound,'relations').node('relation:0').value)
        for endpoint, entity in enumerate((acme, engine)):
            records = ExtractionRecords(store, bound, 'entities')
            identity = records.entity_node(entity).value
            records.write_identity_projection(identity, mention_id=entity.metadata['mention_id'],
                representation_id='r:'+source, context_start=0, context_end=len(text),
                evidence_ids=['e:'+source+':'+str(endpoint)],
                metadata=dict(source_ids=[source], identity_scope='r:'+source))
            ids_by_endpoint[endpoint].append(identity)
        sources.append(dict(source=source, material='m', representation='r:'+source, recipe='recipe',
            operation_count=2, operations=[entities['operation_id'], relations['operation_id']]))
    generation = store.begin_publication('p', expected_generation=None, source_count=2, canonical_count=2)['generation']
    store.stage_publication_sources('p', generation, sources)
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:'+str(i), representative=members[0],
        members=members, selectors=[], member_count=len(members), selector_count=len([])) for i, members in enumerate(ids_by_endpoint)])
    plan = dict(id='urn:canonical:fact', source='urn:canonical:0', target='urn:canonical:1',
        representative=native_relations[0], member_count=2, status='accepted')
    return store, generation, native_relations, plan


def test_duplicate_native_observations_publish_one_canonical_fact_with_all_support(tmp_path):
    store, generation, native_relations, plan = stage_duplicate_observations(tmp_path)
    # Append separate cursor pages without retaining the full group in staging.
    store.stage_publication_facts('p', generation, [{**plan, 'members':[native_relations[0]]}])
    with pytest.raises(ProcessingError, match='membership plan is incomplete'):
        store.activate_publication('p', generation, indexes=indexes())
    store.stage_publication_facts('p', generation, [{**plan, 'members':[native_relations[1]]}])
    store.activate_publication('p', generation, indexes=indexes())
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    scene = store.read_publication_scene('p', generation, dict(kind='links', visibleIds=['urn:canonical:0', 'urn:canonical:1']))
    assert len(scene['links']) == 1
    assert set(scene['links'][0]['sourceIds']) == {'s1', 's2'}
    assert len(scene['links'][0]['evidenceIds']) == 2
    assert store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:canonical:0'))['links'] == scene['links']
    assert {n['id'] for n in store.read_publication_scene('p', generation, dict(kind='nodes',recordIds=[plan['id']]))['nodes']} == {'urn:canonical:0','urn:canonical:1'}
    first = store.read_publication_fact_members('p', generation, plan['id'], limit=1)
    second = store.read_publication_fact_members('p', generation, plan['id'], limit=1, after=first['next_cursor'])
    assert first['member_count'] == second['member_count'] == 2
    assert first['next_cursor'] and second['next_cursor'] is None
    assert set(first['members'] + second['members']) == set(native_relations)
    for member in native_relations:
        assert store.read_record_binding('p', generation, member)['source'] in {'s1','s2'}
    store.withdraw_publication('p', expected_generation=generation)
    with pytest.raises(ProcessingError, match='not ready'):
        store.read_publication_scene('p', generation, dict(kind='links',visibleIds=['urn:canonical:0','urn:canonical:1']))
    store.close()


def test_unstaged_native_relation_is_not_silently_published(tmp_path):
    store, generation, _, _ = stage_duplicate_observations(tmp_path)
    with pytest.raises(ProcessingError, match='Canonical fact coverage is incomplete'):
        store.activate_publication('p', generation, indexes=indexes())
    store.close()


def test_fact_membership_rejects_changed_plan_wrong_endpoint_and_duplicate_owner(tmp_path):
    store, generation, native_relations, plan = stage_duplicate_observations(tmp_path)
    row = {**plan, 'members':native_relations}
    with pytest.raises(ProcessingError, match='endpoint differs'):
        store.stage_publication_facts('p', generation, [{**row, 'target':plan['source']}])
    store.stage_publication_facts('p', generation, [row])
    with pytest.raises(ProcessingError, match='plan changed'):
        store.stage_publication_facts('p', generation, [{**row, 'status':'retracted'}])
    with pytest.raises(ProcessingError, match='another canonical fact'):
        store.stage_publication_facts('p', generation, [{**row, 'id':'urn:other:fact'}])
    store.close()
