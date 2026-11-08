import pytest
import hashlib
from time import perf_counter
from semantica.utils.exceptions import ProcessingError
from semantica.semantic_extract.types import Entity, Relation
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from tests.triplet_store.test_publication_records import indexes

def stage_duplicate_observations(tmp_path, source_ids=('s1', 's2')):
    store = OxigraphStore(tmp_path / 'facts')
    text = 'Acme owns Engine'
    ids_by_endpoint = [[], []]
    sources = []
    native_relations = []
    for source in source_ids:
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
    generation = store.begin_publication('p', expected_generation=None, source_count=len(source_ids), canonical_count=2)['generation']
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


def test_fact_staging_rejects_relation_outside_publication_before_sealing_coverage(tmp_path):
    from semantica.triplet_store.publication_records import P, PublicationRecords
    store, generation, relations, plan = stage_duplicate_observations(tmp_path)
    publication = PublicationRecords(store, 'p')
    source = store._oxigraph.NamedNode(publication.graph.value + ':source:' + hashlib.sha256(b's2').hexdigest())
    relation = store._oxigraph.NamedNode(relations[1])
    operation = next(iter(store.store.query(f'''SELECT ?operation WHERE {{ GRAPH {publication.facts} {{
        ?operation <{F}ownedRecord> {relation} }} }}''')))['operation']
    store.store.update(f'''DELETE DATA {{ GRAPH {publication.graph} {{
        {source} <{P}operation> {operation} ; <{P}operationCount> "2" . }} }}''')
    store.store.update(f'''INSERT DATA {{ GRAPH {publication.graph} {{
        {source} <{P}operationCount> "1" . }} }}''')

    with pytest.raises(ProcessingError, match='outside the current publication'):
        store.stage_publication_facts('p', generation, [{**plan, 'members':relations}])
    store.close()


@pytest.mark.parametrize('complete', [False, True])
def test_fact_coverage_uses_relation_index_not_all_fact_pairs(tmp_path, monkeypatch, complete):
    store, generation, relations, plan = stage_duplicate_observations(tmp_path)
    from semantica.triplet_store.publication_records import P
    if complete:
        store.stage_publication_facts('p', generation, [{**plan, 'members':relations}])
    native = store.store
    coverage_queries = []
    class IndexedCoverage:
        def __getattr__(self, name):
            return getattr(native, name)
        def query(self, query, **kwargs):
            if 'COUNT(DISTINCT ?relation)' in query or 'SUM(xsd:integer(?expected))' in query:
                coverage_queries.append(query)
            return native.query(query, **kwargs)
    monkeypatch.setattr(store, 'store', IndexedCoverage())
    try:
        if complete:
            store.activate_publication('p', generation, indexes=indexes())
        else:
            with pytest.raises(ProcessingError, match='Canonical fact coverage is incomplete'):
                store.activate_publication('p', generation, indexes=indexes())
        assert len(coverage_queries) == 2
        assert any('COUNT(DISTINCT ?relation)' in query for query in coverage_queries)
        assert any('SUM(xsd:integer(?expected))' in query for query in coverage_queries)
        assert all(f'<{P}member> ?relation' not in query for query in coverage_queries)
    finally:
        store.close()


def test_activation_rejects_equal_count_foreign_member_replacement(tmp_path):
    from semantica.triplet_store.publication_records import P, PublicationRecords
    store, generation, relations, plan = stage_duplicate_observations(tmp_path)
    store.stage_publication_facts('p', generation, [{**plan, 'members':relations}])
    publication = PublicationRecords(store, 'p')
    fact = store._oxigraph.NamedNode(plan['id'])
    replaced = store._oxigraph.NamedNode(relations[1])
    foreign = store._oxigraph.NamedNode('urn:test:foreign-relation')
    store.store.update(f'''DELETE DATA {{ GRAPH {publication.graph} {{
        {fact} <{P}member> {replaced} . }} }}''')
    store.store.update(f'''INSERT DATA {{ GRAPH {publication.graph} {{
        {fact} <{P}member> {foreign} . }} }}''')

    with pytest.raises(ProcessingError, match='outside the current publication'):
        store.activate_publication('p', generation, indexes=indexes())
    assert store.publication_status('p')['state'] == 'pending'
    store.close()


def test_publication_activation_at_esg_observation_scale(tmp_path):
    from semantica.triplet_store.publication_records import P, PublicationRecords
    from semantica.triplet_store.extraction_records import F, RDF_TYPE
    from semantica.triplet_store.oxigraph_store import OxigraphStore

    relation_count, fact_count = 56_700, 21_620
    store = OxigraphStore(tmp_path / 'scale')
    generation = store.begin_publication('scale', expected_generation=None,
        source_count=1, canonical_count=0)['generation']
    publication = PublicationRecords(store, 'scale')
    ox = store._oxigraph
    operation = ox.NamedNode('urn:test:operation')
    source = ox.NamedNode(publication.graph.value + ':source:' + hashlib.sha256(b'source').hexdigest())
    quads = [
        ox.Quad(publication.head, ox.NamedNode(P+'source'), source, publication.graph),
        ox.Quad(source, ox.NamedNode(P+'operation'), operation, publication.graph),
        ox.Quad(source, ox.NamedNode(P+'operationCount'), ox.Literal(1), publication.graph),
    ]
    relation_ids = [ox.NamedNode(f'urn:test:relation:{index}') for index in range(relation_count)]
    for relation in relation_ids:
        quads.extend((
            ox.Quad(operation, ox.NamedNode(F+'ownedRecord'), relation, publication.facts),
            ox.Quad(relation, ox.NamedNode(RDF_TYPE), ox.NamedNode(F+'Relation'), publication.facts),
        ))
    offset = 0
    for fact_index in range(fact_count):
        size = 3 if fact_index < relation_count - 2 * fact_count else 2
        fact = ox.NamedNode(f'urn:test:fact:{fact_index}')
        members = relation_ids[offset:offset + size]
        quads.extend((
            ox.Quad(publication.head, ox.NamedNode(P+'fact'), fact, publication.graph),
            ox.Quad(fact, ox.NamedNode(P+'memberCount'), ox.Literal(size), publication.graph),
            ox.Quad(fact, ox.NamedNode(P+'representative'), members[0], publication.graph),
            *(ox.Quad(fact, ox.NamedNode(P+'member'), member, publication.graph) for member in members),
        ))
        offset += size
    assert offset == relation_count
    store.store.extend(quads)
    store.flush()
    store.close()
    store = OxigraphStore(tmp_path / 'scale')

    started = perf_counter()
    store.activate_publication('scale', generation, indexes=indexes())
    activation_seconds = perf_counter() - started
    print(f'56,700 relation / 21,620 fact activation: {activation_seconds:.3f}s')
    assert activation_seconds <= 5.0, f'56,700-observation activation took {activation_seconds:.3f}s'
    store.close()


def test_fact_staging_validates_a_full_member_page_with_bounded_store_reads(tmp_path, monkeypatch):
    store, generation, relations, plan = stage_duplicate_observations(
        tmp_path, source_ids=tuple(f'source-{number}' for number in range(128)))
    native = store.store
    calls = {'patterns': 0, 'queries': 0}
    class CountedStore:
        def __getattr__(self, name):
            return getattr(native, name)
        def query(self, query, **kwargs):
            calls['queries'] += 1
            return native.query(query, **kwargs)
        def quads_for_pattern(self, *args, **kwargs):
            calls['patterns'] += 1
            yield from native.quads_for_pattern(*args, **kwargs)
    monkeypatch.setattr(store, 'store', CountedStore())
    try:
        store.stage_publication_facts('p', generation, [{**plan, 'member_count':len(relations), 'members':relations}])
        assert calls['queries'] <= 8
        assert calls['patterns'] <= 24
    finally:
        store.close()
