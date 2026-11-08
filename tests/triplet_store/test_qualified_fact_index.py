"""Native reference partitions preserve the complete qualified conflict oracle."""
import pytest

from semantica.conflicts.conflict_detector import ConflictDetector
from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from semantica.utils.exceptions import ProcessingError
from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations


def rows(refs, count=137):
    for number in range(count):
        qualifiers = dict(polarity='negative' if number == count-1 else 'positive', time='2025')
        assertion = KnowledgeAssertion(id='assertion:'+str(number), subject_id='urn:canonical:0',
            predicate='owns', object='Engine', object_entity_id='urn:canonical:1',
            qualifiers=qualifiers, evidence_ids=['urn:evidence:'+str(number)])
        relation = KnowledgeRelation(id='relation:'+str(number), source_entity_id=assertion.subject_id,
            target_entity_id=assertion.object_entity_id, type=assertion.predicate,
            qualifiers=qualifiers, evidence_ids=assertion.evidence_ids)
        # Several logical observations can be located on one native relation;
        # the slot is part of the reference identity and never a payload mirror.
        yield refs[number % len(refs)], 'assertion', assertion.model_dump()
        yield refs[number % len(refs)], 'relation', relation.model_dump()


def test_reference_index_crosses_pages_and_preserves_oracle(tmp_path):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    source = list(rows(refs))
    lookup = {(ref, kind, item['id']): item for ref, kind, item in source}
    index = QualifiedFactIndex(store, 'p', generation)
    index.build(iter(source))
    store.close()
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store = OxigraphStore(tmp_path/'facts')
    index = QualifiedFactIndex(store, 'p', generation)
    reads = []
    def read(ref, kind, identity):
        reads.append((ref,kind,identity))
        return lookup[ref,kind,identity]
    output = list(index.iter_reconciled(read,
        max_group_records=300, max_group_bytes=4*1024*1024))
    expected = ConflictDetector.reconcile_qualified_facts('p',
        [KnowledgeAssertion.model_validate(item) for _, kind, item in source if kind == 'assertion'],
        [KnowledgeRelation.model_validate(item) for _, kind, item in source if kind == 'relation'])
    assert [group[:3] for group in output] == [expected]
    assert len(reads) == len(lookup) == len(set(reads))
    for relation in output[0][1]:
        members,representative = output[0][3][relation.id]
        matching = [(ref,item) for ref,kind,item in source if kind == 'relation'
            and ConflictDetector.qualified_fact_identity('p',item,kind) == relation.id]
        assert set(members) == {ref for ref,_ in matching}
        assert any(ref == representative and item == relation.metadata['support_observations'][0]
            for ref,item in matching)
    assert len(output[0][2]) == 1
    assert len(output[0][0][0].metadata['support_observations']) in {1,136}
    store.close()


def test_reconciliation_pages_references_across_many_small_partitions(tmp_path):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    source = list(rows(refs, 300))
    for number, (_, kind, item) in enumerate(source):
        item['predicate' if kind == 'assertion' else 'type'] += ':' + str(number // 4)
    lookup = {(ref, kind, item['id']): item for ref, kind, item in source}
    index = QualifiedFactIndex(store, 'p', generation)
    index.build(iter(source))
    native, queries = store.store, []
    class ObservedStore:
        def __getattr__(self, name):
            return getattr(native, name)
        def query(self, query, *args, **kwargs):
            if 'SELECT ?partition ?entry ?reference ?kind ?observation ?identity' in query:
                queries.append(query)
            return native.query(query, *args, **kwargs)
    store.store = ObservedStore()
    reads = []
    try:
        output = list(index.iter_reconciled(lambda ref, kind, identity: (
            reads.append((ref, kind, identity)) or lookup[ref, kind, identity]
        )))
        expected = ConflictDetector.reconcile_qualified_facts('p',
            [KnowledgeAssertion.model_validate(item) for _, kind, item in source if kind == 'assertion'],
            [KnowledgeRelation.model_validate(item) for _, kind, item in source if kind == 'relation'])
        assert len(queries) == 5
        assert not any('SELECT DISTINCT ?partition' in query for query in queries)
        assert len(output) == 150
        assert len(reads) == len(set(reads)) == len(source)
        assert sorted((item for group in output for item in group[0]), key=lambda item: item.id) == sorted(expected[0], key=lambda item: item.id)
        assert sorted((item for group in output for item in group[1]), key=lambda item: item.id) == sorted(expected[1], key=lambda item: item.id)
    finally:
        store.close()


def test_index_rejects_oversized_group_without_emitting_partial_semantics(tmp_path):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    source = list(rows(refs, 3))
    lookup = {(ref, kind, item['id']): item for ref, kind, item in source}
    index = QualifiedFactIndex(store, 'p', generation)
    index.build(iter(source))
    with pytest.raises(ProcessingError, match='record budget'):
        next(index.iter_reconciled(lambda ref, kind, identity: lookup[ref, kind, identity], max_group_records=5))
    with pytest.raises(ProcessingError, match='byte budget'):
        next(index.iter_reconciled(lambda ref, kind, identity: lookup[ref, kind, identity], max_group_bytes=20))
    with pytest.raises(ProcessingError, match='identity changed'):
        next(index.iter_reconciled(lambda ref, kind, identity: {**lookup[ref, kind, identity], 'predicate' if kind == 'assertion' else 'type':'changed'}))
    store.begin_publication('p', expected_generation=generation, source_count=0, canonical_count=0)
    with pytest.raises(ProcessingError, match='not pending'):
        next(index.iter_reconciled(lambda ref, kind, identity: lookup[ref, kind, identity]))
    store.close()


def test_partition_reads_seek_before_checking_current_membership(tmp_path):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    index = QualifiedFactIndex(store, 'p', generation)
    source = list(rows(refs, 3))
    index.build(iter(source))
    partition = index.partition(source[0][2], source[0][1])
    p = index.publication
    orphan = p.iri('urn:orphan:qualified-entry')
    original = next(index._references(partition))
    store.store.update('INSERT DATA { GRAPH '+str(p.graph)+' { '+ '\n'.join([
        p.triple(orphan, 'qualifiedPartition', p.scalar(partition)),
        *[p.triple(orphan, field, p.scalar(original[key])) for field, key in (
            ('qualifiedReference', 'reference'), ('qualifiedKind', 'kind'),
            ('qualifiedObservation', 'observation'), ('qualifiedIdentity', 'identity'))],
    ])+' } }')
    native, queries, updates = store.store, [], []
    class ObservedStore:
        def __getattr__(self, name):
            return getattr(native, name)
        def query(self, query, *args, **kwargs):
            if 'SELECT ?entry ?reference ?kind ?observation ?identity' in query:
                queries.append(query)
            return native.query(query, *args, **kwargs)
        def update(self, query, *args, **kwargs):
            if 'qualifiedReconciledStatus' in query:
                updates.append(query)
            return native.update(query, *args, **kwargs)
    store.store = ObservedStore()
    try:
        assert len(list(index._references(partition))) == len(source)
        assert queries
        assert all(query.index('qualifiedPartition') < query.index('qualifiedEntry')
            and 'FILTER EXISTS' in query for query in queries)
        lookup = {(ref, kind, item['id']): item for ref, kind, item in source}
        for claims, links, _, _ in index.iter_reconciled(lambda *key: lookup[key]):
            index.stage_reconciled(claims, links)
        assert len(updates) == 1
        assert all(query.index('qualifiedIdentity') < query.index('qualifiedEntry')
            and 'FILTER EXISTS' in query for query in updates)
    finally:
        store.close()


def test_reconciled_status_writes_use_the_publication_checkpoint(tmp_path, monkeypatch):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    source = list(rows(refs, 3))
    for number, (_, kind, item) in enumerate(source):
        item['predicate' if kind == 'assertion' else 'type'] += ':' + str(number // 2)
    lookup = {(ref, kind, item['id']): item for ref, kind, item in source}
    index = QualifiedFactIndex(store, 'p', generation)
    index.build(iter(source))
    flushes = 0
    original_flush = store.flush
    def count_flushes():
        nonlocal flushes
        flushes += 1
        return original_flush()
    monkeypatch.setattr(store, 'flush', count_flushes)
    with index.publication.build_scope(generation), index.publication.checkpointed(generation):
        for claims, links, _, _ in index.iter_reconciled(lambda ref, kind, identity: lookup[ref, kind, identity]):
            index.stage_reconciled(claims, links)
        assert flushes == 0
    assert flushes == 1
    store.close()


def test_complete_partitions_preserve_functional_values_times_and_withdrawal(tmp_path):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    source = list(rows(refs, 140))
    for offset, (_, kind, item) in enumerate(source):
        number = offset//2
        item['qualifiers']['time'] = '2026' if number >= 130 else '2025'
        if number % 2:
            if kind == 'assertion':
                item['object'], item['object_entity_id'] = 'Other', 'urn:canonical:other'
            else:
                item['target_entity_id'] = 'urn:canonical:other'
        if number % 11 == 0:
            item['status'] = 'retracted'
    lookup = {(ref,kind,item['id']):item for ref,kind,item in source}
    index = QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    groups = list(index.iter_reconciled(lambda ref,kind,identity:lookup[ref,kind,identity],
        functional_predicates=iter(['owns'])))
    actual = tuple(sorted((item for group in groups for item in group[column]),key=lambda item:item.id)
        for column in range(3))
    oracle = ConflictDetector.reconcile_qualified_facts('p',
        [KnowledgeAssertion.model_validate(item) for _,kind,item in source if kind == 'assertion'],
        [KnowledgeRelation.model_validate(item) for _,kind,item in source if kind == 'relation'],
        functional_predicates=['owns'])
    assert actual == tuple(sorted(values,key=lambda item:item.id) for values in oracle)
    assert len(groups) == 2
    assert len(actual[2]) == 3
    for _,links,_,supports in groups:
        for relation in links:
            members,representative = supports[relation.id]
            matching = [(ref,item) for ref,kind,item in source if kind == 'relation'
                and ConflictDetector.qualified_fact_identity('p',item,kind) == relation.id]
            assert set(members) == {ref for ref,_ in matching}
            assert any(ref == representative and item == relation.metadata['support_observations'][0]
                for ref,item in matching)
    store.close()


def test_incomplete_duplicate_and_foreign_reference_index_cannot_be_read(tmp_path):
    store,generation,refs,_ = stage_duplicate_observations(tmp_path)
    index = QualifiedFactIndex(store,'p',generation)
    with pytest.raises(ProcessingError,match='not sealed'):
        next(index.iter_reconciled(lambda *args:None))
    first = next(rows(refs,1))
    with pytest.raises(ProcessingError,match='Duplicate'):
        index.build(iter([first,first]))
    with pytest.raises(ProcessingError,match='not sealed'):
        next(index.iter_reconciled(lambda *args:None))
    with pytest.raises(ProcessingError,match='current publication'):
        index.build(iter([('urn:foreign',first[1],first[2])]))
    store.close()


def test_canonical_pages_select_native_partition_and_preserve_oracle(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    source=list(rows(refs,3))
    for ref,kind,item in list(source):
        other={**item,'id':item['id']+':other','qualifiers':{**item['qualifiers'],'time':'2026'},
               'evidence_ids':['urn:evidence:other']}
        source.append((ref,kind,other))
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    calls=[]
    def read(ref,kind,observation):
        calls.append(observation)
        return lookup[ref,kind,observation]
    first=index.canonical_page('assertion',read,evidence_ids=['urn:evidence:0'],limit=1)
    assert len(first['records'])==1
    assert all(':other' not in call for call in calls)
    oracle=ConflictDetector.reconcile_qualified_facts('p',
        [KnowledgeAssertion.model_validate(item) for _,kind,item in source[:6] if kind=='assertion'],
        [KnowledgeRelation.model_validate(item) for _,kind,item in source[:6] if kind=='relation'])
    assert first['records'][0] in oracle[0]
    assert len(first['records'][0].evidence_ids)==2
    assert first['records'][0].status==oracle[0][0].status
    calls.clear()
    assert index.canonical_page('assertion',read,evidence_ids=['urn:absent'])=={'records':[],'next_cursor':None}
    assert calls==[]
    with pytest.raises(ProcessingError,match='page limit'):
        index.canonical_page('assertion',read,limit=129)
    store.close()


def test_topology_page_reads_only_staged_native_endpoints(tmp_path):
    store,generation,refs,plan=stage_duplicate_observations(tmp_path)
    store.stage_publication_facts('p',generation,[{**plan,'members':refs}])
    index=QualifiedFactIndex(store,'p',generation)
    index.build(rows(refs,1))
    assert index.topology_page(limit=1)['records']==[
        {'id':plan['id'],'source':plan['source'],'target':plan['target'],'type':'owns'}]
    assert index.topology_page(after=plan['id'])['records']==[]
    store.close()


def test_canonical_seek_pages_reopen_and_exact_complete_partition_oracle(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    source=list(rows(refs,4))
    for number,(_,kind,item) in enumerate(source):
        item['qualifiers']['time']=str(2024+number//4)
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    index=QualifiedFactIndex(store,'p',generation)
    for kind,column in (('assertion',0),('relation',1)):
        actual=[]
        cursor=None
        while True:
            page=index.canonical_page(kind,lambda ref,k,id:lookup[ref,k,id],after=cursor,limit=1)
            actual.extend(page['records'])
            cursor=page['next_cursor']
            if cursor is None:
                break
        oracle=ConflictDetector.reconcile_qualified_facts('p',
            [KnowledgeAssertion.model_validate(item) for _,k,item in source if k=='assertion'],
            [KnowledgeRelation.model_validate(item) for _,k,item in source if k=='relation'])[column]
        assert sorted(actual,key=lambda item:item.id)==sorted(oracle,key=lambda item:item.id)
    with pytest.raises(ProcessingError,match='item exceeds byte budget'):
        index.canonical_page('assertion',lambda ref,k,id:lookup[ref,k,id],max_bytes=20)
    store.begin_publication('p',expected_generation=generation,source_count=0,canonical_count=0)
    with pytest.raises(ProcessingError,match='not pending'):
        index.canonical_page('assertion',lambda *args:None)
    store.close()


def test_native_family_metadata_matches_complete_qualified_oracle(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    source=list(rows(refs,3))
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    with pytest.raises(ProcessingError,match='reconciliation incomplete'):
        index.family_page()
    for claims,links,_,_ in index.iter_reconciled(lambda ref,kind,id:lookup[ref,kind,id]):
        index.stage_reconciled(claims,links)
    assert index.family_page()['records']==[dict(subject='urn:canonical:0',predicate='owns',
        representations=['r:s1','r:s2'],required=True)]
    assert index.canonical_page('assertion',lambda ref,kind,id:lookup[ref,kind,id],
        subject_ids=['urn:canonical:0'],predicates=['absent'])['records']==[]
    assert len(index.canonical_page('relation',lambda ref,kind,id:lookup[ref,kind,id],
        subject_ids=['urn:canonical:0'],predicates=['owns'])['records'])==2
    store.close()


def test_native_family_seek_and_budgets_preserve_every_required_family(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    source=[]
    for family in ('owns','supplies','uses'):
        for ref,kind,item in rows(refs,2):
            item['id']+=':'+family
            item['predicate' if kind=='assertion' else 'type']=family
            if family=='supplies':
                item['status']='retracted'
            source.append((ref,kind,item))
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    for claims,links,_,_ in index.iter_reconciled(lambda ref,kind,id:lookup[ref,kind,id]):
        index.stage_reconciled(claims,links)
    result=[]
    cursor=None
    while True:
        page=index.family_page(after=cursor,limit=1)
        result.extend(page['records'])
        cursor=page['next_cursor']
        if cursor is None:
            break
    assert [row['predicate'] for row in result]==['owns','supplies','uses']
    assert all(row['required'] for row in result)
    with pytest.raises(ProcessingError,match='source budget'):
        index.family_page(max_family_sources=1)
    with pytest.raises(ProcessingError,match='exceeds byte budget'):
        index.family_page(max_bytes=20)
    with pytest.raises(ProcessingError,match='cursor'):
        index.family_page(after='invalid')
    store.close()


def test_index_persists_bounded_native_batches_and_cancellation_stays_unsealed(tmp_path, monkeypatch):
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    from semantica.triplet_store.publication_records import PublicationRecords, MAX_BYTES, MAX_ROWS
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    index=QualifiedFactIndex(store,'p',generation)
    original=PublicationRecords.mutate
    batches=[]
    def observe(owner,generation,triples,**kwargs):
        batches.append(list(triples))
        assert len('\n'.join(triples).encode())<=MAX_BYTES
        assert sum('<urn:semantica:publication:qualifiedEntry>' in triple for triple in triples)<=MAX_ROWS
        return original(owner,generation,triples,**kwargs)
    monkeypatch.setattr(PublicationRecords,'mutate',observe)
    index.build(rows(refs,140))
    assert len(batches)<20
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    index=QualifiedFactIndex(store,'p',generation)
    assert list(index.iter_reconciled(lambda ref,kind,identity: dict(next(value for _,kind2,value in rows(refs,140) if kind2==kind and value['id']==identity))))
    event=Event()
    def canceled_rows():
        for position,row in enumerate(rows(refs,140)):
            if position==150:
                event.set()
            yield row
    token=query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError,match='canceled'):
            with index.publication.build_scope(generation):
                index.build(canceled_rows())
        assert store._build_plan_scope is None
    finally:
        query_cancellation.reset(token)
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    index=QualifiedFactIndex(store,'p',generation)
    with pytest.raises(ProcessingError,match='not sealed'):
        next(index.iter_reconciled(lambda *args:None))
    # An explicit retry replaces partial rows, then seals only complete input.
    index.build(rows(refs,2))
    store.close()


def test_index_pending_batch_cannot_cross_generation_change(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    index=QualifiedFactIndex(store,'p',generation)
    first=next(rows(refs,1))
    def replaced_rows():
        yield first
        store.begin_publication('p',expected_generation=generation,source_count=0,canonical_count=0)
        yield refs[0],'relation',next(value for _,kind,value in rows(refs,1) if kind=='relation')
    with pytest.raises(ProcessingError,match='not pending'):
        with index.publication.build_scope(generation):
            index.build(replaced_rows())
    assert store._build_plan_scope is None
    store.close()


def test_fact_scope_validates_complete_plan_only_at_stage_boundaries(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    native=store.store
    plan_queries=[]
    class ObservedStore:
        def __getattr__(self,name):
            return getattr(native,name)
        def query(self,query,*args,**kwargs):
            if 'HAVING(COUNT(?operation)' in query:
                plan_queries.append(query)
            return native.query(query,*args,**kwargs)
    store.store=ObservedStore()
    source=list(rows(refs,140))
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    try:
        with index.publication.build_scope(generation):
            index.build(iter(source))
            for claims,links,_,_ in index.iter_reconciled(lambda *key:lookup[key]):
                index.stage_reconciled(claims,links)
            assert len(plan_queries)==1
        assert len(plan_queries)==2
        assert store._build_plan_scope is None
    finally:
        store.close()


def test_native_family_ordered_subject_scope_crosses_pages_without_global_sort(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    source=[]
    for subject in ('urn:canonical:a','urn:canonical:b','urn:canonical:c'):
        for predicate in ('owns','supplies'):
            for ref,kind,item in rows(refs,2):
                item['id']+=':'+subject+':'+predicate
                item['subject_id' if kind=='assertion' else 'source_entity_id']=subject
                item['predicate' if kind=='assertion' else 'type']=predicate
                source.append((ref,kind,item))
    lookup={(ref,kind,item['id']):item for ref,kind,item in source}
    index=QualifiedFactIndex(store,'p',generation)
    index.build(iter(source))
    for claims,links,_,_ in index.iter_reconciled(lambda ref,kind,id:lookup[ref,kind,id]):
        index.stage_reconciled(claims,links)
    actual=[]
    cursor=None
    while True:
        page=index.family_page(subject_ids=['urn:canonical:c','urn:canonical:a'],after=cursor,limit=1)
        actual.extend((row['subject'],row['predicate']) for row in page['records'])
        cursor=page['next_cursor']
        if cursor is None:
            break
    assert actual==[(s,p) for s in ('urn:canonical:c','urn:canonical:a') for p in ('owns','supplies')]
    assert index.family_page(subject_ids=[])==dict(records=[],next_cursor=None)
    for subjects in (['x']*129,['x','x'],[None]):
        with pytest.raises(ProcessingError,match='scope'):
            index.family_page(subject_ids=subjects)
    with pytest.raises(ProcessingError,match='cursor'):
        index.family_page(subject_ids=['urn:canonical:a'],after='["urn:canonical:b","owns"]')
    store.close()
