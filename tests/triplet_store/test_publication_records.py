import gc

import pytest

from semantica.semantic_extract.types import Entity
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from semantica.utils.exceptions import ProcessingError
RANGES = [dict(nativeRef='#/document/text', start=0, end=4, windowStart=0, windowEnd=4)]


def fixture(tmp_path):
    store = OxigraphStore(tmp_path / "facts")
    binding = dict(project="p", source="s", material="m", representation="r", recipe="recipe", model="model", specification="spec", parser="parser", grounding="grounding", window_start=0, window_end=4)
    entity = Entity("Acme", "ORG", 0, 4, .7, {"mention_id": "mention", "span_occurrence": 0})
    receipt = store.adopt_extraction(binding, "entities", [entity], text="Acme", native_ranges=RANGES, accepted_digest="paid")
    identity = ExtractionRecords(store, binding, "entities").entity_node(entity).value
    return store, binding, receipt, identity


def indexes():
    return dict(keyword=dict(kind="native-keyword", store_id="kw", recipe_digest="recipe"), semantic=dict(kind="native-vector", store_id="vectors", recipe_digest="recipe", space_id="space"))


def test_grounded_topics_validate_native_refs_and_survive_restart(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    page = store.read_grounded_reference_page('p', generation,
        dict(source='s', nativeRef='#/document/text', start=0, end=4))
    evidence = page['items'][0]['evidence']
    topic = dict(id='topic:one', title='Grounded theme', report_id='report:one',
        input_digest='sha256:input', members=['urn:canonical:acme'], member_count=1,
        evidence_ids=[evidence], evidence_count=1)
    with pytest.raises(ProcessingError, match='canonical'):
        store.stage_publication_topics('p', generation, [{**topic, 'members':['urn:foreign']}])
    with pytest.raises(ProcessingError, match='current publication|native evidence'):
        store.stage_publication_topics('p', generation, [{**topic, 'evidence_ids':[identity]}])
    store.stage_publication_topics('p', generation, [topic])
    with pytest.raises(ProcessingError, match='changed'):
        store.stage_publication_topics('p', generation, [{**topic, 'title':'Different theme'}])
    store.activate_publication('p', generation, indexes=indexes())
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    scene = store.read_publication_scene('p', generation, dict(kind='topics'))
    assert scene['nodes'] == [dict(id='topic:one', kind='topic', title='Grounded theme',
        memberCount=1, evidenceCount=1, organization=dict(basis='grounded-overview-section',
            report_id='report:one', input_digest='sha256:input', coverage='cited-knowledge-only'))]
    assert scene['next_cursor'] is None
    assert store.read_publication_scene('p', generation, dict(kind='topics', after='topic:one'))['nodes'] == []
    assert store.read_publication_scene('p', generation, dict(kind='nodes', topicId='topic:one'))['nodes'][0]['id'] == 'urn:canonical:acme'
    assert store.read_publication_scene('p', generation, dict(kind='nodes', topicId='topic:absent'))['nodes'] == []
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_publication_scene('p', generation, dict(kind='topics', maxBytes=10))
    store.withdraw_publication('p', expected_generation=generation)
    with pytest.raises(ProcessingError, match='not ready'):
        store.read_publication_scene('p', generation, dict(kind='topics'))
    store.close()


def test_topic_incomplete_membership_prevents_activation(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    evidence = store.read_grounded_reference_page('p', generation,
        dict(source='s', nativeRef='#/document/text', start=0, end=4))['items'][0]['evidence']
    store.stage_publication_topics('p', generation, [dict(id='topic:one', title='Theme',
        report_id='report:one', input_digest='sha256:input', members=['urn:canonical:acme'],
        member_count=2, evidence_ids=[evidence], evidence_count=1)])
    with pytest.raises(ProcessingError, match='Topic membership plan is incomplete'):
        store.activate_publication('p', generation, indexes=indexes())
    store.close()


def test_topic_staging_rejects_colliding_kinds_and_conflicting_batch_atomically(tmp_path):
    from semantica.triplet_store.publication_records import P
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    evidence = store.read_grounded_reference_page('p', generation,
        dict(source='s', nativeRef='#/document/text', start=0, end=4))['items'][0]['evidence']
    topic = dict(id='topic:one', title='Theme', report_id='report:one', input_digest='sha256:input',
        members=['urn:canonical:acme'], member_count=1, evidence_ids=[evidence], evidence_count=1)
    with pytest.raises(ProcessingError, match='kind'):
        store.stage_publication_topics('p', generation, [{**topic, 'id':'urn:canonical:acme'}])
    with pytest.raises(ProcessingError, match='changed'):
        store.stage_publication_topics('p', generation, [topic, {**topic, 'title':'Other'}])
    with pytest.raises(ProcessingError, match='reference'):
        store.stage_publication_topics('p', generation, [{**topic, 'evidence_ids':[{}]}])
    assert not list(store.store.quads_for_pattern(None, store._oxigraph.NamedNode(P+'title'), None, None))
    store.stage_publication_topics('p', generation, [topic])
    with pytest.raises(ProcessingError, match='kind'):
        store.stage_publication_communities('p', generation, [dict(id='topic:one',
            members=['urn:canonical:acme'], member_count=1)])
    with pytest.raises(ProcessingError, match='kind'):
        store.stage_publication_canonical('p', generation, [dict(id='topic:one',
            representative=identity, members=[identity], selectors=[], member_count=len([identity]), selector_count=len([]))])
    store.close()


def test_topic_catalog_and_memberships_page_past_128_without_loss(tmp_path):
    from semantica.triplet_store.extraction_records import ExtractionRecords
    store = OxigraphStore(tmp_path / 'facts')
    text = ' '.join('N'+str(n) for n in range(130))
    binding = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    entities, start = [], 0
    for n in range(130):
        name = 'N'+str(n)
        entities.append(Entity(name, 'ORG', start, start+len(name), .9,
            {'mention_id':'mention:'+str(n), 'span_occurrence':0}))
        start += len(name)+1
    receipt = store.adopt_extraction(binding, 'entities', entities, text=text,
        native_ranges=[dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0,
            windowEnd=len(text))], accepted_digest='paid')
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=130)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r',
        recipe='recipe', operation_count=1, operations=[receipt['operation_id']])])
    records = [dict(id='urn:canonical:'+str(n).zfill(3),
        representative=ExtractionRecords(store, binding, 'entities').entity_node(entity).value,
        members=[ExtractionRecords(store, binding, 'entities').entity_node(entity).value], selectors=[], member_count=len([ExtractionRecords(store, binding, 'entities').entity_node(entity).value]), selector_count=len([]))
        for n, entity in enumerate(entities)]
    for offset in range(0, 130, 128):
        store.stage_publication_canonical('p', generation, records[offset:offset+128])
    evidence, after = [], None
    while True:
        page = store.read_grounded_reference_page('p', generation,
            dict(source='s', nativeRef='#/document/text', start=0, end=len(text)), after=after)
        evidence.extend(item['evidence'] for item in page['items'])
        after = page['next_cursor']
        if after is None:
            break
    evidence = sorted(set(evidence))
    assert len(evidence) == 130
    members = [record['id'] for record in records]
    for offset in range(0, 130, 128):
        store.stage_publication_topics('p', generation, [dict(id='topic:wide', title='Wide theme',
            report_id='report:one', input_digest='sha256:input', members=members[offset:offset+128],
            member_count=130, evidence_ids=evidence[offset:offset+128], evidence_count=130)])
    for n in range(129):
        store.stage_publication_topics('p', generation, [dict(id='topic:'+str(n).zfill(3), title='Theme '+str(n),
            report_id='report:one', input_digest='sha256:input', members=members[:1], member_count=1,
            evidence_ids=evidence[:1], evidence_count=1)])
    store.activate_publication('p', generation, indexes=indexes())
    first = store.read_publication_scene('p', generation, dict(kind='topics'))
    second = store.read_publication_scene('p', generation, dict(kind='topics', after=first['next_cursor']))
    assert len(first['nodes']) == 128 and len(second['nodes']) == 2
    assert second['next_cursor'] is None and second['nodes'][-1]['memberCount'] == 130
    first = store.read_publication_scene('p', generation, dict(kind='nodes', topicId='topic:wide'))
    second = store.read_publication_scene('p', generation,
        dict(kind='nodes', topicId='topic:wide', after=first['next_cursor']))
    assert [n['id'] for n in first['nodes']+second['nodes']] == members
    assert second['next_cursor'] is None
    for fields in (['id'], ['id','name','sourceIds']):
        projected=[]; after=None
        while True:
            page=store.read_publication_scene('p',generation,dict(kind='nodes',topicId='topic:wide',fields=fields,**({'after':after} if after else {})))
            projected.extend(page['nodes']); after=page['next_cursor']
            if after is None: break
        assert [item['id'] for item in projected]==members
    store.close()


def test_community_references_restart_and_canonical_membership_uniqueness(tmp_path):
    from semantica.triplet_store.publication_records import P
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    with pytest.raises(ProcessingError, match='already belongs'):
        store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:duplicate',
            representative=identity, members=[identity], selectors=[], member_count=len([identity]), selector_count=len([]))])
    with pytest.raises(ProcessingError, match='current canonical'):
        store.stage_publication_communities('p', generation, [dict(id='community:one',
            members=['urn:canonical:foreign'], member_count=1)])
    store.stage_publication_communities('p', generation, [dict(id='community:one',
        members=['urn:canonical:acme'], member_count=1)])
    store.activate_publication('p', generation, indexes=indexes())
    scene = store.read_native_source_scene('p', generation, dict(kind='sources', limit=1, maxBytes=262144))
    assert scene['nodes'] == [dict(id='s', kind='source', material='m', representation='r', source_ids=['s'], evidence_ids=[])]
    assert scene['links'] == [] and scene['next_cursor'] is None
    assert store.read_native_source_scene('p', generation, dict(kind='sources', after='s'))['nodes'] == []
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_native_source_scene('p', generation, dict(kind='sources', maxBytes=10))
    store.close()
    del store
    gc.collect()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.publication_status('p')['state'] == 'ready'
    community = store._oxigraph.NamedNode('community:one')
    assert any(q.object.value == 'urn:canonical:acme' for q in store.store.quads_for_pattern(
        community, store._oxigraph.NamedNode(P+'member'), None, None))
    assert any(q.object.value == 'unavailable_title' for q in store.store.quads_for_pattern(
        community, store._oxigraph.NamedNode(P+'titleState'), None, None))
    assert not any(q.predicate.value == P+'title' for q in store.store)
    scene=store.read_publication_scene('p',generation,dict(kind='communities'))
    assert scene['nodes']==[dict(id='community:one',kind='community',memberCount=1,titleState='unavailable_title')]
    assert store.read_publication_scene('p',generation,dict(kind='nodes',communityId='community:one'))['nodes'][0]['id']=='urn:canonical:acme'
    assert store.read_publication_scene('p',generation,dict(kind='nodes',communityId='community:absent'))['nodes']==[]
    assert store.read_publication_scene('p',generation,dict(kind='nodes',recordIds=[identity]))['nodes'][0]['id']=='urn:canonical:acme'
    section=store.read_native_section_records('p',generation,dict(sourceId='s',positions=[dict(nativeRef='#/document/text',start=1,end=3)]))
    assert section['records'][0]['id']==identity
    assert section['records'][0]['fields'][F+'name'][0]['value']=='Acme'
    assert section['records'][0]['evidenceIds'] and section['next_cursor'] is None
    assert store.read_native_section_records('p',generation,dict(sourceId='s',positions=[dict(nativeRef='#/document/other',start=0,end=4)]))['records']==[]
    with pytest.raises(ProcessingError,match='current publication'):
        store.read_native_section_records('p',generation,dict(sourceId='foreign',positions=[dict(nativeRef='#/document/text',start=0,end=4)]))


@pytest.mark.parametrize('unrelated_count', [64, 2048])
def test_canonical_member_admission_uses_reverse_point_reads(tmp_path, unrelated_count):
    from semantica.triplet_store.publication_records import P, PublicationRecords
    store, _, receipt, identity = fixture(tmp_path)
    generation = store.begin_publication('p', expected_generation=None,
        source_count=1, canonical_count=1)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m',
        representation='r', recipe='recipe', operation_count=1,
        operations=[receipt['operation_id']])])
    publication = PublicationRecords(store, 'p')
    ox = store._oxigraph
    member = ox.NamedNode(identity)
    member_predicate, canonical = ox.NamedNode(P+'member'), ox.NamedNode(P+'canonical')
    for index in range(unrelated_count):
        node = ox.NamedNode('urn:unrelated:canonical:'+str(index))
        store.store.add(ox.Quad(publication.head, canonical, node, publication.graph))
        store.store.add(ox.Quad(node, member_predicate,
            ox.NamedNode('urn:unrelated:member:'+str(index)), publication.graph))
    # Member references outside this head's canonical set must not block admission.
    for name in ('community', 'other-head-canonical'):
        node = ox.NamedNode('urn:'+name)
        store.store.add(ox.Quad(node, member_predicate, member, publication.graph))
    store.store.add(ox.Quad(publication.head, ox.NamedNode(P+'community'),
        ox.NamedNode('urn:community'), publication.graph))
    store.store.add(ox.Quad(ox.NamedNode('urn:other-head'), canonical,
        ox.NamedNode('urn:other-head-canonical'), publication.graph))
    underlying, reverse_rows, membership_reads = store.store, [], []

    class PointMembership:
        def __getattr__(self, name):
            return getattr(underlying, name)

        def query(self, text):
            assert not (text.startswith('ASK') and '?canonical' in text
                and str(canonical) in text and str(member_predicate) in text), 'project-wide canonical member join'
            return underlying.query(text)

        def quads_for_pattern(self, subject, predicate, object_, graph):
            if predicate == member_predicate:
                assert subject is None and object_ == member and graph == publication.graph
                for quad in underlying.quads_for_pattern(subject, predicate, object_, graph):
                    reverse_rows.append(quad)
                    yield quad
                return
            if subject == publication.head and predicate == canonical:
                assert object_ is not None and graph == publication.graph
                membership_reads.append(object_)
            yield from underlying.quads_for_pattern(subject, predicate, object_, graph)

    record = dict(id='urn:canonical:acme', representative=identity, members=[identity],
        selectors=[], member_count=1, selector_count=0)
    store.store = PointMembership()
    try:
        store.stage_publication_canonical('p', generation, [record])
        assert len(reverse_rows) == len(membership_reads) == 2
        with pytest.raises(ProcessingError, match='already belongs'):
            store.stage_publication_canonical('p', generation,
                [{**record, 'id':'urn:canonical:duplicate'}])
        assert 3 <= len(reverse_rows) <= 5
        assert len(reverse_rows) == len(membership_reads)
        assert next(underlying.quads_for_pattern(publication.head, canonical,
            ox.NamedNode('urn:canonical:duplicate'), publication.graph), None) is None
    finally:
        store.store = underlying
        store.close()


def test_publication_rejects_corrupt_native_facts_before_reference_admission(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    quad = next(store.store.quads_for_pattern(store._oxigraph.NamedNode(identity), store._oxigraph.NamedNode(F + "name"), None, None))
    store.store.remove(quad)
    generation = store.begin_publication("p", expected_generation=None, source_count=1, canonical_count=0)["generation"]
    with pytest.raises(ProcessingError, match="corrupt"):
        store.stage_publication_sources("p", generation, [dict(source="s", material="m", representation="r", recipe="processing-recipe", operation_count=1, operations=[receipt["operation_id"]])])
    assert store.publication_status("p")["state"] == "pending"


def test_flush_failure_still_releases_native_store_writer(tmp_path, monkeypatch):
    store = OxigraphStore(tmp_path / "facts")
    def failure():
        raise RuntimeError("flush failure")
    monkeypatch.setattr(store, "flush", failure)
    with pytest.raises(RuntimeError, match="flush failure"):
        store.close()
    assert not hasattr(store, "store")
    reopened = OxigraphStore(tmp_path / "facts")
    reopened.close()


def stage(store, receipt, identity, *, source="s"):
    status = store.begin_publication("p", expected_generation=(store.publication_status("p") or {}).get("generation"), source_count=1, canonical_count=1)
    generation = status["generation"]
    store.stage_publication_sources("p", generation, [dict(source=source, material="m", representation="r", recipe="recipe", operation_count=1, operations=[receipt["operation_id"]])])
    store.stage_publication_canonical("p", generation, [dict(id="urn:canonical:acme", representative=identity, members=[identity], selectors=[dict(field="name", record=identity)], member_count=len([identity]), selector_count=len([dict(field="name", record=identity)]))])
    return generation


def test_pending_ready_restart_withdraw_and_original_digest_unchanged(tmp_path):
    store, binding, receipt, identity = fixture(tmp_path)
    before = [str(q) for q in store.store if q.graph_name.value.startswith("urn:semantica:project:")]
    generation = stage(store, receipt, identity)
    with pytest.raises(ProcessingError, match="not ready"):
        store.read_native_records("p", generation, [identity])
    store.activate_publication("p", generation, indexes=indexes())
    assert store.read_native_records("p", generation, [identity])[0]["fields"][F + "name"][0]["value"] == "Acme"
    assert store.read_canonical_membership("p", generation)["records"][0]["members"] == [identity]
    assert store.extraction_receipt(binding, "entities") == receipt
    assert sorted(before) == sorted(str(q) for q in store.store if q.graph_name.value.startswith("urn:semantica:project:"))
    store.close()
    del store
    gc.collect()
    store = OxigraphStore(tmp_path / "facts")
    assert store.publication_status("p")["generation"] == generation
    assert store.read_publication_records("p", generation, source="wrong")["records"] == []
    store.withdraw_publication("p", expected_generation=generation)
    with pytest.raises(ProcessingError, match="not ready"):
        store.read_native_records("p", generation, [identity])


def test_cross_project_source_incomplete_and_stale_cas_rejected(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    status = store.begin_publication("p", expected_generation=None, source_count=1, canonical_count=0)
    generation = status["generation"]
    with pytest.raises(ProcessingError, match="CAS"):
        store.begin_publication("p", expected_generation=None, source_count=0, canonical_count=0)
    with pytest.raises(ProcessingError, match="another source"):
        store.stage_publication_sources("p", generation, [dict(source="other", material="m", representation="r", recipe="recipe", operation_count=1, operations=[receipt["operation_id"]])])
    with pytest.raises(ProcessingError, match="incomplete"):
        store.activate_publication("p", generation, indexes=indexes())
    with pytest.raises(ProcessingError, match="both"):
        store.activate_publication("p", generation, indexes={"keyword": indexes()["keyword"]})
    with pytest.raises(ProcessingError, match="stale"):
        store.read_native_records("other", generation, [identity])


def test_bounded_reads_and_no_canonical_body_copies(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    store.activate_publication("p", generation, indexes=indexes())
    with pytest.raises(ProcessingError, match="128"):
        store.read_native_records("p", generation, [identity] * 129)
    with pytest.raises(ProcessingError, match="byte"):
        store.read_native_records("p", generation, [identity], max_bytes=8)
    with pytest.raises(ProcessingError, match="128"):
        store.read_publication_records("p", generation, limit=129)
    publication = [q for q in store.store if q.graph_name.value.startswith("urn:semantica:publication:")]
    assert not any(q.object.value == "Acme" for q in publication)
    old = generation
    generation = store.begin_publication("p", expected_generation=old, source_count=0, canonical_count=0)["generation"]
    assert not any(q.object.value == identity for q in store.store if q.graph_name.value.startswith("urn:semantica:publication:"))
    with pytest.raises(ProcessingError, match="stale"):
        store.read_native_records("p", old, [identity])
    store.activate_publication("p", generation, indexes=indexes())
    with pytest.raises(ProcessingError, match="outside"):
        store.read_native_records("p", generation, [identity])


def test_point_record_read_never_enumerates_unselected_native_facts(tmp_path):
    """Instrument owner calls, not merely the final response's page size.

    This proves subject/graph-constrained owner access; it does not claim
    RocksDB physical I/O or process RSS measurements.
    """
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    store.activate_publication('p', generation, indexes=indexes())
    ox = store._oxigraph
    facts = next(q.graph_name for q in store.store.quads_for_pattern(ox.NamedNode(identity), None, None, None))
    for index in range(2000):
        store.store.add(ox.Quad(ox.NamedNode('urn:unselected:'+str(index)), ox.NamedNode(F+'name'),
            ox.Literal('Unselected body '+str(index)), facts))
    expected = store.read_native_records('p', generation, [identity])
    underlying = store.store
    calls, fact_rows, queries = [], [], []

    class PointReadsOnly:
        def __iter__(self):
            raise AssertionError('Record read must never iterate the native store')

        def quads_for_pattern(self, subject, predicate, object_, graph):
            assert graph is not None
            assert subject is not None or (predicate is not None and object_ is not None)
            calls.append((subject, predicate, object_, graph))
            for quad in underlying.quads_for_pattern(subject, predicate, object_, graph):
                if graph == facts:
                    if subject is None:
                        assert predicate.value == F+'ownedRecord' and object_.value == identity
                    else:
                        assert subject.value == identity
                        fact_rows.append(quad)
                yield quad

        def query(self, text):
            queries.append(text)
            # Membership authorization is an exact-record ASK, not SELECT *.
            assert text.startswith('ASK {') and '<'+identity+'>' in text
            return underlying.query(text)

    store.store = PointReadsOnly()
    try:
        assert store.read_native_records('p', generation, [identity]) == expected
        assert len(fact_rows) == sum(len(values) for values in expected[0]['fields'].values())
        assert len(queries) == 0
        assert calls
    finally:
        store.store = underlying
        store.close()


def test_reopened_production_point_read_reports_native_process_cost(tmp_path):
    """Measure the real native process, not just Python objects or mocked calls.

    This is a warm-OS-cache regression probe, not a cold-disk I/O guarantee.
    The writer is closed and each reader is a fresh process (empty engine cache).
    """
    import json
    import subprocess
    import sys

    measurements = []
    for count in (1000, 50000):
        directory = tmp_path / str(count)
        directory.mkdir()
        store, _, receipt, identity = fixture(directory)
        generation = stage(store, receipt, identity)
        store.activate_publication('p', generation, indexes=indexes())
        ox = store._oxigraph
        facts = next(store.store.quads_for_pattern(ox.NamedNode(identity), None, None, None)).graph_name
        # Unrelated scalar facts amplify the native store without adding a
        # copied body or fake publication to the production implementation.
        store.store.extend(ox.Quad(ox.NamedNode('urn:unselected:'+str(index)), ox.NamedNode(F+'name'),
            ox.Literal(str(index) + ':' + 'unselected' * 64), facts) for index in range(count))
        store.flush()
        store.close()
        del store
        gc.collect()
        code = '''
import json, resource, sys, time
from pathlib import Path
from semantica.triplet_store.oxigraph_store import OxigraphStore
def usage():
    value = resource.getrusage(resource.RUSAGE_SELF)
    return dict(rss=value.ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
        inputBlocks=value.ru_inblock, minorFaults=value.ru_minflt, majorFaults=value.ru_majflt)
before = usage()
started = time.perf_counter()
store = OxigraphStore(Path(sys.argv[1]) / 'facts')
opened = usage()
result = store.read_native_records('p', sys.argv[2], [sys.argv[3]], max_bytes=8192, source_ids=['s'])
after = usage()
assert 'semantica.semantic_extract.schemas' not in sys.modules, 'Native point reads must not initialize extraction wire schemas'
assert len(result) == 1 and result[0]['fields']['urn:semantica:field:name'][0]['value'] == 'Acme'
print(json.dumps(dict(elapsedMs=(time.perf_counter()-started)*1000,
    processHighWaterBytes=after['rss'], openHighWaterGrowthBytes=opened['rss']-before['rss'],
    queryHighWaterGrowthBytes=after['rss']-opened['rss'],
    inputBlocks=after['inputBlocks']-before['inputBlocks'],
    minorFaults=after['minorFaults']-before['minorFaults'],
    majorFaults=after['majorFaults']-before['majorFaults'], responseBytes=len(json.dumps(result).encode()))))
store.close()
'''
        child = subprocess.run([sys.executable, '-c', code, str(directory), generation, identity],
            capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stdout + child.stderr
        row = dict(records=count, **json.loads(child.stdout))
        # Bounds cover native allocations as well as Python, unlike tracemalloc.
        # Includes opening the native engine; deliberately not a latency SLA.
        assert row['queryHighWaterGrowthBytes'] < 16 * 1024 * 1024
        assert row['openHighWaterGrowthBytes'] < 64 * 1024 * 1024
        assert row['responseBytes'] < 8192
        measurements.append(row)
    print('production-native-point-process-cost=' + json.dumps(measurements, sort_keys=True))


def test_native_scene_is_bounded_reference_projection_and_generation_fenced(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    store.activate_publication('p', generation, indexes=indexes())
    page = store.read_publication_scene('p', generation, dict(kind='nodes', limit=1))
    node = page['nodes'][0]
    assert node['id'] == 'urn:canonical:acme'
    assert node['recordId'] == identity
    assert node['fields'][F+'name'][0]['value'] == 'Acme'
    assert node['sourceIds'] == ['s']
    assert node['members'] == [identity]
    assert node['selectors'] == [dict(field='name', record=identity)]
    assert page['next_cursor'] is None
    assert store.read_publication_scene('p', generation, dict(kind='nodes', sourceIds=['other']))['nodes'] == []
    assert store.read_publication_scene('p', generation, dict(kind='links', visibleIds=[node['id']]))['links'] == []
    with pytest.raises(ProcessingError, match='outside'):
        store.read_publication_scene('p', generation, dict(kind='nodes', nodeIds=['urn:missing']))
    with pytest.raises(ProcessingError, match='byte'):
        store.read_publication_scene('p', generation, dict(kind='nodes', maxBytes=32))
    with pytest.raises(ProcessingError, match='128'):
        store.read_publication_scene('p', generation, dict(kind='links', visibleIds=['urn:n']*129))
    store.begin_publication('p', expected_generation=generation, source_count=0, canonical_count=0)
    with pytest.raises(ProcessingError, match='stale'):
        store.read_publication_scene('p', generation, dict(kind='nodes'))


def test_visible_native_scene_links_preserve_relation_qualifiers(tmp_path, monkeypatch):
    from semantica.semantic_extract.types import Relation
    store = OxigraphStore(tmp_path / 'facts')
    text = 'Acme owns Engine'
    bound = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    ranges = [dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0, windowEnd=len(text))]
    acme = Entity('Acme', 'ORG', 0, 4, .7, dict(mention_id='a', span_occurrence=0))
    engine = Entity('Engine', 'ORG', 10, 16, .7, dict(mention_id='b', span_occurrence=0))
    entities = store.adopt_extraction(bound, 'entities', [acme, engine], text=text, native_ranges=ranges, accepted_digest='entities')
    relation = Relation(acme, 'owns', engine, .8, text, dict(subject_id='a', object_id='b',
        evidence_start=0, evidence_end=len(text), evidence_occurrence=0,
        qualifiers=dict(polarity='negative', condition='under contract', time='2026', unit='shares', value='10')))
    relations = store.adopt_extraction(bound, 'relations', [relation], text=text, native_ranges=ranges, accepted_digest='relations')
    ids = [ExtractionRecords(store,bound,'entities').entity_node(entity).value for entity in (acme,engine)]
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=2)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s',material='m',representation='r',recipe='recipe',operation_count=2,
        operations=[entities['operation_id'],relations['operation_id']])])
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:'+str(index),representative=identity,members=[identity],selectors=[], member_count=len([identity]), selector_count=len([]))
        for index,identity in enumerate(ids)])
    relation_id = ExtractionRecords(store,bound,'relations').node('relation:0').value
    store.stage_publication_facts('p', generation, [dict(id='urn:fact:owns', source='urn:canonical:0',
        target='urn:canonical:1', representative=relation_id, members=[relation_id], member_count=1, status='accepted')])
    store.activate_publication('p', generation, indexes=indexes())
    page = store.read_publication_scene('p', generation,dict(kind='links',visibleIds=['urn:canonical:0','urn:canonical:1']))
    link = page['links'][0]
    selected = store.read_publication_scene('p', generation, dict(kind='nodes',recordIds=[link['id']]))
    assert {node['id'] for node in selected['nodes']} == {'urn:canonical:0','urn:canonical:1'}
    assert (link['source'],link['target'],link['predicate']) == ('urn:canonical:0','urn:canonical:1','owns')
    assert link['fields'][F+'polarity'][0] == dict(type='iri',value=F+'negative')
    assert link['fields'][F+'qualifiedValue'][0]['value'] == '10'
    assert link['evidenceIds'] and link['sourceIds'] == ['s']
    assert store.read_publication_scene('p',generation,dict(kind='links',visibleIds=['urn:canonical:0']))['links'] == []
    incident = store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:canonical:0',limit=1))
    assert incident['links'] == page['links']
    assert {node['id'] for node in incident['nodes']} == {'urn:canonical:0','urn:canonical:1'}
    assert incident['next_cursor'] is None
    assert store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:canonical:1'))['links'] == page['links']
    with pytest.raises(ProcessingError, match='outside current'):
        store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:foreign'))
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:canonical:0',maxBytes=32))
    continuation = store.read_publication_scene('p', generation, dict(kind='incident',nodeId='urn:canonical:0',after=link['id']))
    assert continuation['links'] == []
    assert [node['id'] for node in continuation['nodes']] == ['urn:canonical:0']
    from semantica.triplet_store.publication_records import PublicationRecords
    def forbidden(*args, **kwargs):
        raise AssertionError('Incident projection hydrated unused fields/endpoints')
    monkeypatch.setattr(PublicationRecords,'_fact_scene_link',forbidden)
    monkeypatch.setattr(PublicationRecords,'_selected_scene_fields',forbidden)
    fields=['id','source','target','predicate']
    projected=store.read_publication_scene('p',generation,dict(kind='incident',nodeId='urn:canonical:0',fields=fields))
    assert projected['fields']==fields and projected['nodes']==[]
    assert projected['links']==[{key:link[key] for key in fields}]
    assert store.read_publication_scene('p',generation,dict(kind='incident',nodeId='urn:canonical:0',fields=fields,after=link['id']))['links']==[]
    with pytest.raises(ProcessingError,match='outside current'):
        store.read_publication_scene('p',generation,dict(kind='incident',nodeId='urn:foreign',fields=fields))


def test_native_record_literal_language_and_datatype_are_lossless(tmp_path):
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    store.activate_publication("p", generation, indexes=indexes())
    ox = store._oxigraph
    graph = next(q.graph_name for q in store.store.quads_for_pattern(ox.NamedNode(identity), None, None, None))
    store.store.add(ox.Quad(ox.NamedNode(identity), ox.NamedNode(F + 'localizedLabel'), ox.Literal('企业', language='zh'), graph))
    fields = store.read_native_records('p', generation, [identity])[0]['fields']
    assert fields[F + 'localizedLabel'] == [dict(type='literal', value='企业',
        datatype='http://www.w3.org/1999/02/22-rdf-syntax-ns#langString', language='zh')]
    assert fields[F + 'confidence'][0]['datatype'] == 'http://www.w3.org/2001/XMLSchema#double'


def test_multi_source_membership_withdrawal_and_multi_contributor_selectors(tmp_path):
    store, binding, receipt, identity = fixture(tmp_path)
    other = dict(binding, source="second", representation="r2")
    value = Entity("Acme", "ORG", 0, 4, .7, {"mention_id": "second", "span_occurrence": 0})
    receipt2 = store.adopt_extraction(other, "entities", [value], text="Acme", native_ranges=RANGES, accepted_digest="paid2")
    identity2 = ExtractionRecords(store, other, "entities").entity_node(value).value
    generation = store.begin_publication("p", expected_generation=None, source_count=2, canonical_count=1)["generation"]
    store.stage_publication_sources("p", generation, [dict(source="s", material="m", representation="r", recipe="recipe", operation_count=1, operations=[receipt["operation_id"]]), dict(source="second", material="m", representation="r2", recipe="recipe", operation_count=1, operations=[receipt2["operation_id"]])])
    store.stage_publication_canonical("p", generation, [dict(id="urn:canonical:shared", representative=identity, members=[identity, identity2], selectors=[dict(field="name", record=identity), dict(field="name", record=identity2)], member_count=len([identity, identity2]), selector_count=len([dict(field="name", record=identity), dict(field="name", record=identity2)]))])
    store.activate_publication("p", generation, indexes=indexes())
    assert len(store.read_canonical_membership("p", generation)["records"][0]["selectors"]) == 2
    scoped = store.read_publication_scene('p', generation, dict(kind='nodes', sourceIds=['second']))['nodes'][0]
    assert scoped['recordId'] == identity2
    assert scoped['members'] == [identity2]
    assert scoped['sourceIds'] == ['second']
    assert scoped['selectors'] == [dict(field='name', record=identity2)]
    assert store.read_native_records("p", generation, [identity], source_ids=["s"])
    assert store.read_native_records("p", generation, [identity2], source_ids=["second"])
    with pytest.raises(ProcessingError, match="outside"):
        store.read_native_records("p", generation, [identity2], source_ids=["s"])
    with pytest.raises(ProcessingError, match="outside"):
        store.read_native_records("p", generation, [identity], source_ids=["second"])
    with pytest.raises(ProcessingError, match="Duplicate"):
        store.read_native_records("p", generation, [identity], source_ids=["s", "s"])
    with pytest.raises(ProcessingError, match="128"):
        store.read_native_records("p", generation, [identity], source_ids=[])
    next_generation = store.begin_publication("p", expected_generation=generation, source_count=1, canonical_count=1)["generation"]
    store.stage_publication_sources("p", next_generation, [dict(source="second", material="m", representation="r2", recipe="recipe", operation_count=1, operations=[receipt2["operation_id"]])])
    store.stage_publication_canonical("p", next_generation, [dict(id="urn:canonical:shared", representative=identity2, members=[identity2], selectors=[], member_count=len([identity2]), selector_count=len([]))])
    store.activate_publication("p", next_generation, indexes=indexes())
    with pytest.raises(ProcessingError, match="outside"):
        store.read_native_records("p", next_generation, [identity])
    assert store.read_native_records("p", next_generation, [identity2])
    assert store.extraction_receipt(binding, "entities") == receipt
    assert store.extraction_receipt(other, "entities") == receipt2


def test_scene_applies_selected_member_fields_without_persisting_another_body(tmp_path, monkeypatch):
    from semantica.semantic_extract.schema import ExtractionSpecification
    store, binding, receipt, identity = fixture(tmp_path)
    text = 'Acme Incorporated'
    second = dict(binding, source='second', material='m2', representation='r2', window_end=len(text))
    value = Entity(text, 'COMPANY', 0, len(text), .9, dict(mention_id='second', span_occurrence=0))
    value.attributes = dict(description='Selected description', sector='Energy')
    specification = ExtractionSpecification.model_validate(dict(id='spec', version='1', entity_types=[dict(
        name='COMPANY', description='company', attributes={name:dict(type='string', description=name)
            for name in ('description', 'sector')})]))
    ranges = [dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0, windowEnd=len(text))]
    receipt2 = store.adopt_extraction(second, 'entities', [value], text=text, native_ranges=ranges,
        accepted_digest='paid2', extraction_spec=specification)
    identity2 = ExtractionRecords(store, second, 'entities').entity_node(value).value
    generation = store.begin_publication('p', expected_generation=None, source_count=2, canonical_count=1)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r', recipe='recipe',
        operation_count=1, operations=[receipt['operation_id']]), dict(source='second', material='m2', representation='r2',
        recipe='recipe', operation_count=1, operations=[receipt2['operation_id']])])
    sector = store.publication_attribute_reference('p', generation, identity2, 'sector')
    selectors = [dict(field=name, record=identity2) for name in ('name','type','description')]
    selectors.append(dict(field='properties.sector', record=sector))
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:shared', representative=identity,
        members=[identity, identity2], selectors=selectors, member_count=len([identity, identity2]), selector_count=len(selectors))])
    store.activate_publication('p', generation, indexes=indexes())
    before = len(list(store.store))
    from semantica.triplet_store.publication_records import PublicationRecords
    read = PublicationRecords.read
    calls = []
    def bounded_read(owner, current, ids, **kwargs):
        assert len(ids) == 1 and kwargs['max_bytes'] == 262144
        calls.extend(ids)
        return read(owner, current, ids, **kwargs)
    monkeypatch.setattr(PublicationRecords, 'read', bounded_read)
    node = store.read_publication_scene('p', generation, dict(kind='nodes'))['nodes'][0]
    assert len(calls) == 4 and len(set(calls)) == 4
    monkeypatch.setattr(PublicationRecords, 'read', read)
    assert node['recordId'] == identity
    assert node['fields'][F+'name'][0]['value'] == text
    assert node['fields'][F+'entityType'][0]['value'] == 'COMPANY'
    assert node['fields'][F+'description'][0]['value'] == 'Selected description'
    assert node['fields'][F+'attribute'] == [dict(type='iri', value=sector)]
    assert node['sourceIds'] == ['s', 'second'] and node['selectors'] == selectors
    selected_evidence = store.read_native_records('p', generation, [identity2])[0]['fields'][F+'mention'][0]['value']
    assert selected_evidence in node['evidenceIds']
    assert len(list(store.store)) == before
    assert store.read_native_records('p', generation, [identity])[0]['fields'][F+'name'][0]['value'] == 'Acme'
    calls.clear()
    def scoped_read(owner, current, ids, **kwargs):
        assert kwargs['source_ids'] == ['s'] and ids == [identity]
        calls.extend(ids)
        return read(owner, current, ids, **kwargs)
    monkeypatch.setattr(PublicationRecords, 'read', scoped_read)
    scoped = store.read_publication_scene('p', generation, dict(kind='nodes', sourceIds=['s']))['nodes'][0]
    assert scoped['fields'][F+'name'][0]['value'] == 'Acme'
    assert scoped['sourceIds'] == ['s'] and scoped['selectors'] == []
    assert calls == [identity] and selected_evidence not in scoped['evidenceIds']
    monkeypatch.setattr(PublicationRecords, 'read', read)
    second_scope = store.read_publication_scene('p', generation, dict(kind='nodes', sourceIds=['second']))['nodes'][0]
    assert second_scope['fields'][F+'name'][0]['value'] == text
    assert second_scope['sourceIds'] == ['second'] and selected_evidence in second_scope['evidenceIds']
    assert second_scope['members'] == [identity2] and second_scope['selectors'] == selectors
    for scope, expected in [(None,text),(['s'],'Acme'),(['second'],text)]:
        projected=store.read_publication_scene('p',generation,dict(kind='nodes',fields=['id','name','sourceIds'],**({'sourceIds':scope} if scope else {})))['nodes'][0]
        assert projected['name']==expected
        assert projected['sourceIds']==(scope if scope else ['s','second'])


def test_canonical_field_hydration_enforces_joint_read_budget(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords
    store, _, _, identity = fixture(tmp_path)
    reader = PublicationRecords(store, 'p')
    calls = []
    def oversized_read(_owner, generation, ids, **kwargs):
        calls.extend(ids)
        return [dict(id=ids[0], fields={F+'name':[dict(type='literal', value='x'*140000)]})]
    monkeypatch.setattr(PublicationRecords, 'read', oversized_read)
    with pytest.raises(ProcessingError, match='hydration exceeds byte budget'):
        reader._selected_scene_fields('g', identity, [dict(field='name', record='urn:selected')], None)
    assert calls == [identity, 'urn:selected']
    store.close()


def test_begin_generation_compare_and_swap_has_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store = OxigraphStore(tmp_path / "facts")
    barrier = Barrier(2)
    def begin():
        barrier.wait()
        try:
            return store.begin_publication("p", expected_generation=None, source_count=0, canonical_count=0)["generation"]
        except ProcessingError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: begin(), range(2)))
    assert len([r for r in results if r is not None]) == 1
    assert store.publication_status("p")["generation"] in results


def test_more_than_128_sources_and_records_publish_in_bounded_batches(tmp_path):
    store, binding, _, _ = fixture(tmp_path)
    sources, canonical = [], []
    for index in range(129):
        bound = dict(binding, source="source-" + str(index))
        value = Entity("Acme", "ORG", 0, 4, .7, {"mention_id": "mention", "span_occurrence": 0})
        receipt = store.adopt_extraction(bound, "entities", [value], text="Acme", native_ranges=RANGES, accepted_digest="paid")
        identity = ExtractionRecords(store, bound, "entities").entity_node(value).value
        sources.append(dict(source=bound["source"], material="m", representation="r", recipe="recipe", operation_count=1, operations=[receipt["operation_id"]]))
        canonical.append(dict(id="urn:canonical:" + str(index), representative=identity, members=[identity], selectors=[], member_count=len([identity]), selector_count=len([])))
    generation = store.begin_publication("p", expected_generation=None, source_count=129, canonical_count=129)["generation"]
    for start in (0, 128):
        store.stage_publication_sources("p", generation, sources[start:start + 128])
        store.stage_publication_canonical("p", generation, canonical[start:start + 128])
    store.activate_publication("p", generation, indexes=indexes())
    page = store.read_canonical_membership("p", generation)
    assert len(page["records"]) == 128
    assert page["next_cursor"]
    last = store.read_canonical_membership("p", generation, after=page["next_cursor"])
    assert len(last["records"]) == 1
    assert last["next_cursor"] is None
    assert store.publication_status("p")["source_count"] == 129
    scene_ids, cursor = [], None
    while True:
        selection = dict(kind='nodes', limit=128, maxBytes=8192)
        if cursor is not None:
            selection['after'] = cursor
        scene = store.read_publication_scene('p', generation, selection)
        import json
        assert len(json.dumps(scene, ensure_ascii=False).encode()) <= 8192
        scene_ids.extend(node['id'] for node in scene['nodes'])
        cursor = scene['next_cursor']
        if cursor is None:
            break
    assert len(scene_ids) == len(set(scene_ids)) == 129


def test_incomplete_source_operation_plan_cannot_activate(tmp_path):
    store, _, receipt, _ = fixture(tmp_path)
    generation = store.begin_publication("p", expected_generation=None, source_count=1, canonical_count=0)["generation"]
    source = dict(source="s", material="m", representation="r", recipe="recipe", operation_count=2, operations=[receipt["operation_id"]])
    store.stage_publication_sources("p", generation, [source])
    with pytest.raises(ProcessingError, match="operation plan is incomplete"):
        store.activate_publication("p", generation, indexes=indexes())
    with pytest.raises(ProcessingError, match="plan changed"):
        store.stage_publication_sources("p", generation, [dict(source, operation_count=1)])


def test_grounding_reference_pages_keep_all_shared_scalar_observations(tmp_path):
    store, binding, _, _ = fixture(tmp_path)
    entities = [Entity('Acme', 'ORG', 0, 4, .7,
        {'mention_id': f'mention-{i:03}', 'span_occurrence': i}) for i in range(257)]
    receipt = store.adopt_extraction(dict(binding, model='many'), 'entities', entities,
        text='Acme', native_ranges=RANGES, accepted_digest='paid-many')
    generation = store.begin_publication('p', expected_generation=None,
        source_count=1, canonical_count=0)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m',
        representation='r', recipe='recipe', operation_count=1,
        operations=[receipt['operation_id']])])
    position = dict(source='s', nativeRef='#/document/text', start=0, end=4)
    values, cursor, lengths = [], None, []
    while True:
        page = store.read_grounded_reference_page('p', generation, position,
            after=cursor, limit=128)
        lengths.append(len(page['items']))
        values.extend(page['items'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert lengths == [128, 128, 1]
    assert len({(v['id'], v['evidence']) for v in values}) == 257
    assert values == sorted(values, key=lambda v: (v['id'], v['evidence']))
    assert all(set(v) == {'id', 'evidence', 'source'} and v['source'] == 's' for v in values)
    assert store.read_grounded_reference_page('p', generation,
        dict(position, source='foreign'))['items'] == []
    next_generation = store.begin_publication('p', expected_generation=generation,
        source_count=0, canonical_count=0)['generation']
    with pytest.raises(ProcessingError, match='stale'):
        store.read_grounded_reference_page('p', generation, position)
    assert next_generation != generation


@pytest.mark.parametrize('changed', [None, 'polarity', 'condition', 'time', 'unit', 'value'])
def test_canonical_fact_predicate_normalization_preserves_qualifier_identity(tmp_path, changed):
    from semantica.semantic_extract.types import Relation
    store = OxigraphStore(tmp_path / 'facts')
    text = 'Acme owns Engine under contract in 2026 for 10 shares'
    bound = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    ranges = [dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0, windowEnd=len(text))]
    acme = Entity('Acme', 'ORG', 0, 4, .7, dict(mention_id='a', span_occurrence=0))
    engine = Entity('Engine', 'ORG', 10, 16, .7, dict(mention_id='b', span_occurrence=0))
    entities = store.adopt_extraction(bound, 'entities', [acme, engine], text=text, native_ranges=ranges, accepted_digest='entities')
    qualifiers = dict(polarity='positive', condition='under contract', time='2026', unit='shares', value='10')
    other = dict(qualifiers)
    if changed:
        other[changed] = 'negative' if changed == 'polarity' else other[changed] + ' changed'
    relations = [Relation(acme, predicate, engine, .8, text, dict(subject_id='a', object_id='b',
        evidence_start=0, evidence_end=len(text), evidence_occurrence=0, qualifiers=value))
        for predicate, value in [(' owns ', qualifiers), ('OWNS', other)]]
    receipt = store.adopt_extraction(bound, 'relations', relations, text=text, native_ranges=ranges, accepted_digest='relations')
    ids = [ExtractionRecords(store, bound, 'entities').entity_node(value).value for value in (acme, engine)]
    refs = [ExtractionRecords(store, bound, 'relations').node('relation:' + str(i)).value for i in range(2)]
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=2)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r', recipe='recipe',
        operation_count=2, operations=[entities['operation_id'], receipt['operation_id']])])
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:'+str(i), representative=ref, members=[ref], selectors=[], member_count=len([ref]), selector_count=len([]))
        for i, ref in enumerate(ids)])
    record = dict(id='urn:fact:owns', source='urn:canonical:0', target='urn:canonical:1', representative=refs[0],
        members=refs, member_count=2, status='accepted')
    if changed:
        with pytest.raises(ProcessingError, match='qualifier or predicate differs'):
            store.stage_publication_facts('p', generation, [record])
        assert store.publication_status('p')['state'] == 'pending'
    else:
        store.stage_publication_facts('p', generation, [record])
        store.activate_publication('p', generation, indexes=indexes())
        link = store.read_publication_scene('p', generation, dict(kind='links', visibleIds=['urn:canonical:0', 'urn:canonical:1']))['links'][0]
        assert link['predicate'] == 'owns'
        assert store.read_publication_fact_members('p', generation, 'urn:fact:owns')['members'] == sorted(refs)
    store.close()


def test_canonical_membership_and_selectors_append_complete_pages_past_128(tmp_path):
    from tests.triplet_store.test_build_record_cursor import staged
    store,generation,ids=staged(tmp_path,131,canonical_count=None)
    plan=dict(id='urn:canonical:wide',representative=ids[0],member_count=131,selector_count=131)
    first={**plan,'members':ids[:128],'selectors':[dict(field='name',record=ref) for ref in ids[:128]]}
    store.stage_publication_canonical('p',generation,[first])
    store.seal_publication_canonical_count('p',generation,1)
    with pytest.raises(ProcessingError,match='Canonical membership plan is incomplete'):
        store.activate_publication('p',generation,indexes=indexes())
    with pytest.raises(ProcessingError,match='already belongs|exceeded'):
        store.stage_publication_canonical('p',generation,[first])
    with pytest.raises(ProcessingError,match='changed'):
        store.stage_publication_canonical('p',generation,[{**plan,'member_count':132,'members':ids[128:],'selectors':[]}])
    store.stage_publication_canonical('p',generation,[{**plan,'members':ids[128:],'selectors':[]}])
    with pytest.raises(ProcessingError,match='Canonical selector plan is incomplete'):
        store.activate_publication('p',generation,indexes=indexes())
    store.stage_publication_canonical('p',generation,[{**plan,'members':[],'selectors':[dict(field='name',record=ref) for ref in ids[128:]]}])
    store.activate_publication('p',generation,indexes=indexes())
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    assert store.publication_status('p')['state']=='ready'
    store.close()


def test_canonical_ready_reads_span_staging_pages_after_restart(tmp_path):
    """A complete canonical item can have more members than a write page."""
    text = ' '.join(['Acme'] * 130)
    binding = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    store = OxigraphStore(tmp_path / 'facts')
    entities = [Entity('Acme', 'ORG', i*5, i*5+4, .9,
        {'mention_id':'mention:'+str(i), 'span_occurrence':i}) for i in range(130)]
    receipt = store.adopt_extraction(binding, 'entities', entities, text=text,
        native_ranges=[dict(nativeRef='#/document/text', start=0, end=len(text),
            windowStart=0, windowEnd=len(text))], accepted_digest='paid')
    owner = ExtractionRecords(store, binding, 'entities')
    members = [owner.entity_node(entity).value for entity in entities]
    selectors = [dict(field='name', record=member) for member in members]
    generation = store.begin_publication('p', expected_generation=None,
        source_count=1, canonical_count=1)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m',
        representation='r', recipe='recipe', operation_count=1, operations=[receipt['operation_id']])])
    for offset in range(0,130,128):
        store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:wide',
            representative=members[0], member_count=130, selector_count=130,
            members=members[offset:offset+128], selectors=selectors[offset:offset+128])])
    store.activate_publication('p', generation, indexes=indexes())
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    page = store.read_canonical_membership('p', generation)
    assert page['records'] == [dict(id='urn:canonical:wide', representative=members[0],
        members=sorted(members), selectors=selectors)]
    for scope in ({}, dict(sourceIds=['s'])):
        scene = store.read_publication_scene('p', generation, dict(kind='nodes', **scope))
        item = scene['nodes'][0]
        assert item['members'] == sorted(members)
        assert item['selectors'] == selectors
        assert item['fields'][F+'name'][0]['value'] == 'Acme'
        assert len(item['evidenceIds']) == 130
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_canonical_membership('p', generation, max_bytes=1024)
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_publication_scene('p', generation, dict(kind='nodes', maxBytes=1024))
    store.close()


def test_canonical_checkpoint_scope_batches_durability_and_reopens(tmp_path, monkeypatch):
    from tests.triplet_store.test_build_record_cursor import staged
    from semantica.triplet_store.publication_records import PublicationRecords
    store, generation, refs = staged(tmp_path, 140, canonical_count=None)
    publication = PublicationRecords(store, 'p')
    flushes = []
    original = store.flush
    def flush():
        flushes.append(True)
        return original()
    monkeypatch.setattr(store, 'flush', flush)
    def record(n):
        return dict(id='urn:canonical:'+str(n), representative=refs[n], members=[refs[n]],
            member_count=1, selectors=[], selector_count=0)
    with publication.checkpointed(generation):
        for n in range(len(refs)):
            publication.stage_canonical(generation, [record(n)])
    assert len(flushes) < 10
    publication.seal_canonical_count(generation, len(refs))
    store.close()
    store = OxigraphStore(tmp_path/'facts')
    try:
        publication = PublicationRecords(store, 'p')
        assert publication.status()['canonical_count'] == len(refs)
        assert len(list(store.store.quads_for_pattern(publication.head,
            store._oxigraph.NamedNode('urn:semantica:publication:canonical'), None, publication.graph))) == len(refs)
    finally:
        store.close()


@pytest.mark.parametrize('failure', ['cancel', 'generation'])
def test_canonical_checkpoint_failure_never_seals_partial_output(tmp_path, failure):
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    from semantica.triplet_store.publication_records import PublicationRecords
    from tests.triplet_store.test_build_record_cursor import staged
    store, generation, refs = staged(tmp_path, 2, canonical_count=None)
    publication = PublicationRecords(store, 'p')
    event = Event()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled|not pending'):
            with publication.checkpointed(generation):
                publication.stage_canonical(generation, [dict(id='urn:canonical:0',
                    representative=refs[0], members=[refs[0]], member_count=1,
                    selectors=[], selector_count=0)])
                if failure == 'cancel':
                    event.set()
                else:
                    store.begin_publication('p', expected_generation=generation,
                        source_count=0, canonical_count=None)
    finally:
        query_cancellation.reset(token)
        store.close()
    store = OxigraphStore(tmp_path/'facts')
    try:
        status = PublicationRecords(store, 'p').status()
        assert status['state'] == 'pending'
        assert status['canonical_count'] is None
    finally:
        store.close()


def test_scene_explicit_fields_avoids_unrequested_hydration(tmp_path, monkeypatch):
    import json, time
    from semantica.triplet_store.publication_records import PublicationRecords
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    store.activate_publication('p', generation, indexes=indexes())
    calls=[]
    original=PublicationRecords._read
    def measured(owner, ids, **kwargs):
        rows=original(owner, ids, **kwargs)
        calls.append(dict(fields=kwargs.get('fields'), records=len(rows),
                          terms=sum(len(v) for row in rows for v in row['fields'].values()),
                          bytes=len(json.dumps(rows).encode())))
        return rows
    monkeypatch.setattr(PublicationRecords, '_read', measured)
    start=time.perf_counter()
    full=store.read_publication_scene('p', generation, dict(kind='nodes'))
    before=dict(seconds=time.perf_counter()-start, reads=list(calls)); calls.clear()
    def forbidden(*args, **kwargs):
        raise AssertionError('Projected scene hydrated unrequested references or fields')
    for name in ('_canonical_references', '_selected_scene_fields', '_scene_references'):
        monkeypatch.setattr(PublicationRecords, name, forbidden)
    fields=['id','name','sourceIds']
    start=time.perf_counter()
    page=store.read_publication_scene('p', generation, dict(kind='nodes', fields=fields))
    after=dict(seconds=time.perf_counter()-start, reads=list(calls))
    assert page['fields']==fields
    assert page['nodes']==[dict(id=full['nodes'][0]['id'],name='Acme',sourceIds=['s'])]
    assert all(call['fields']==[F+'name'] for call in calls)
    assert sum(call['terms'] for call in calls)<sum(call['terms'] for call in before['reads'])
    calls.clear()
    assert store.read_publication_scene('p', generation,dict(kind='nodes',fields=['id']))['nodes']==[dict(id='urn:canonical:acme')]
    assert calls==[]
    assert store.read_publication_scene('p', generation,dict(kind='nodes',fields=fields,sourceIds=['foreign']))['nodes']==[]
    with pytest.raises(ProcessingError,match='outside'):
        store.read_publication_scene('p', generation,dict(kind='nodes',fields=fields,nodeIds=['urn:foreign']))
    for invalid in (None,[],['name'],['id','fields'],['id','id']):
        with pytest.raises(ProcessingError,match='projection'):
            store.read_publication_scene('p',generation,dict(kind='nodes',fields=invalid))
    with pytest.raises(ProcessingError,match='byte'):
        store.read_publication_scene('p',generation,dict(kind='nodes',fields=fields,maxBytes=32))
    print('native-scene-projection-measure='+json.dumps(dict(before=before,after=after)))
    store.withdraw_publication('p',expected_generation=generation)
    with pytest.raises(ProcessingError,match='not ready'):
        store.read_publication_scene('p',generation,dict(kind='nodes',fields=['id']))
    store.close()


def test_organization_member_projection_survives_full_reference_budget_failure(tmp_path, monkeypatch):
    # Regression for captured G56 scene #96: community member enumeration only
    # consumes identity; full canonical hydration exceeded 262144 bytes.
    from semantica.triplet_store.publication_records import PublicationRecords
    from semantica.semantic_worker_context import query_cancellation
    from threading import Event
    store, _, receipt, identity=fixture(tmp_path)
    generation=stage(store,receipt,identity)
    community='community:d9ee7a78ace79c7787476296'
    store.stage_publication_communities('p',generation,[dict(id=community,members=['urn:canonical:acme'],member_count=1)])
    store.activate_publication('p',generation,indexes=indexes())
    def exhausted(*args, **kwargs):
        raise ProcessingError('Canonical read exceeds byte budget')
    monkeypatch.setattr(PublicationRecords,'_canonical_references',exhausted)
    selection=dict(kind='nodes',communityId=community,limit=128,maxBytes=262144)
    with pytest.raises(ProcessingError,match='Canonical read exceeds byte budget'):
        store.read_publication_scene('p',generation,selection)
    projected=store.read_publication_scene('p',generation,dict(selection,fields=['id']))
    assert projected['nodes']==[dict(id='urn:canonical:acme')] and projected['next_cursor'] is None
    event=Event();event.set();token=query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError,match='canceled'):
            store.read_publication_scene('p',generation,dict(selection,fields=['id']))
    finally: query_cancellation.reset(token)
    store.close()
