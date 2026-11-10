"""Native physical inputs, final decisions and exact recovery boundaries."""
from collections import Counter
import pytest
from semantica.conflicts.conflict_detector import ConflictDetector
from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from semantica.triplet_store.publication_records import P
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError
from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations
from tests.triplet_store.test_fact_direct_decisions import projections
from tests.triplet_store.test_publication_records import indexes


def oracle_views(row):
    shared=dict(qualifiers=row['qualifiers'],evidence_ids=row['evidence'],
        support_ids=row['evidence'],status='candidate',metadata={})
    return (dict(id=row['assertion'],subject_id=row['source'],object_entity_id=row['target'],
                 predicate=row['predicate'],object=row['object'],**shared),
            dict(id=row['id'],source_entity_id=row['source'],target_entity_id=row['target'],
                 type=row['predicate'],**shared))


def prepared(tmp_path, count=1):
    store,generation,refs,_=stage_duplicate_observations(tmp_path,relations_per_source=count)
    projections(store,refs)
    return store,generation,refs,QualifiedFactIndex(store,'p',generation)


def page_all(index,kind,**options):
    result=[]
    cursor=None
    while True:
        page=index.canonical_page(kind,after=cursor,**options)
        result.extend(page['records'])
        cursor=page['next_cursor']
        if cursor is None:
            return result


def test_cross_page_input_matches_semantic_oracle_and_reads_each_native_once(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path,70)
    try:
        observations=[(kind,item) for _,row in index._physical_rows()
            for kind,item in zip(('assertion','relation'),oracle_views(row))]
        expected=ConflictDetector.reconcile_qualified_facts('p',observations=observations)
        reads=Counter()
        original=index._physical_rows
        def read():
            for reference,row in original():
                reads[reference]+=1
                yield reference,row
        monkeypatch.setattr(index,'_physical_rows',read)
        monkeypatch.setattr(ExtractionRecords,'read_fact_projection_page',
            lambda *a,**k:pytest.fail('coordination restored complete fact objects'))
        with index.publication.build_scope(generation):
            index.reconcile_and_stage(input_key='input')
        assert reads==Counter(refs)
        def summary(items):
            return sorted((item.id,item.status,tuple(sorted(item.evidence_ids))) for item in items)
        for kind,oracle in zip(('assertion','relation'),expected[:2]):
            assert summary(page_all(index,kind,limit=1))==summary(oracle)
        assert len(index.topology_page()['records'])==1
        family=index.family_page()['records']
        assert family==[dict(subject='urn:canonical:0',predicate='owns',
            representations=['r:s1','r:s2'],required=False)]
    finally:
        store.close()


def test_completed_read_never_reconciles_or_serializes_support_bodies(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    try:
        index.reconcile_and_stage(input_key='input')
        monkeypatch.setattr(ConflictDetector,'reconcile_qualified_facts',lambda *a,**k:pytest.fail('read reran reducer'))
        with monkeypatch.context() as guard:
            guard.setattr(index.publication,'qualified_members',lambda *a,**k:pytest.fail('ordinary read enumerated supports'))
            for kind in ('assertion','relation'):
                item=page_all(index,kind)[0]
                assert 'support_observation_ids' not in item.metadata
                assert 'support_observations' not in item.metadata
        identity=page_all(index,'relation')[0].id
        assert index.topology_page()['records'] and index.family_page()['records']
        store.activate_publication('p',generation,indexes=indexes())
        first=index.publication.fact_members(generation,identity,limit=1)
        second=index.publication.fact_members(generation,identity,after=first['next_cursor'],limit=1)
        assert first['members']+second['members']==sorted(refs)
        assert second['next_cursor'] is None
    finally:
        store.close()


def test_ranked_family_admission_uses_indexed_fields_not_per_family_queries(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path,70)
    try:
        index.reconcile_and_stage(input_key='input')
        expected=index.family_page()['records']
        native=store.store
        class IndexedOnly:
            def __getattr__(self,name): return getattr(native,name)
            def query(self,*args,**kwargs):
                pytest.fail('ranked family admission executed SPARQL instead of indexed metadata reads')
        with index.publication.build_scope(generation):
            monkeypatch.setattr(store,'store',IndexedOnly())
            actual=index.family_page(subject_ids=['urn:canonical:0'],limit=1)
            monkeypatch.setattr(store,'store',native)
        assert actual==dict(records=expected,next_cursor=None)
    finally:
        store.close()


def test_scoped_canonical_reads_seek_decisions_without_global_graph_joins(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path,70)
    try:
        index.reconcile_and_stage(input_key='input')
        expected={kind:index.canonical_page(kind)['records'] for kind in ('assertion','relation')}
        native=store.store
        class IndexedOnly:
            def __getattr__(self,name): return getattr(native,name)
            def query(self,*args,**kwargs):
                pytest.fail('scoped canonical read executed a global graph query')
        with index.publication.build_scope(generation):
            monkeypatch.setattr(store,'store',IndexedOnly())
            try:
                for kind in expected:
                    actual=index.canonical_page(kind,subject_ids=['urn:canonical:0'],predicates=['owns'])
                    assert actual==dict(records=expected[kind],next_cursor=None)
            finally:
                monkeypatch.setattr(store,'store',native)
    finally:
        store.close()


def test_build_topology_traverses_once_and_preserves_byte_limited_lookahead(tmp_path,monkeypatch):
    store,generation,refs,_=stage_duplicate_observations(tmp_path,relations_per_source=10)
    index=QualifiedFactIndex(store,'p',generation)
    try:
        for number,reference in enumerate(refs):
            records=ExtractionRecords.from_fact_reference(store,'p',reference)
            # Distinct qualifiers produce distinct decisions with identical endpoints.
            store.store.add(records.ox.Quad(records.ox.NamedNode(reference),records.ox.NamedNode(F+'time'),
                records.ox.Literal(str(number)),records.graph))
            records.write_fact_projection(reference,assertion_id=f'a:{number}',relation_id=f'r:{number}',
                source_id='urn:canonical:0',target_id='urn:canonical:1',predicate='owns',
                qualifiers={'polarity':'positive','time':str(number)},evidence_ids=[f'e:{number}'])
        index.reconcile_and_stage(input_key='input')
        expected=index.topology_page()['records']
        native=store.store
        queries=[]
        class Counted:
            def __getattr__(self,name): return getattr(native,name)
            def query(self,query,**options):
                if 'SELECT ?id ?source ?target ?predicate' in query: queries.append(query)
                return native.query(query,**options)
        monkeypatch.setattr(store,'store',Counted())
        with index.publication.build_scope(generation):
            cursor=None;actual=[]
            while True:
                page=index.topology_page(after=cursor,limit=13,max_bytes=600)
                actual.extend(page['records']);cursor=page['next_cursor']
                if cursor is None: break
        assert actual==expected
        assert len(queries)==1
        assert store._publication_cursor is None
    finally:
        store.close()


def test_small_groups_use_projected_input_and_one_import(tmp_path,monkeypatch):
    store,generation,refs,_=stage_duplicate_observations(tmp_path,relations_per_source=70)
    try:
        for number,reference in enumerate(refs):
            records=ExtractionRecords.from_fact_reference(store,'p',reference)
            store.store.add(records.ox.Quad(records.ox.NamedNode(reference),records.ox.NamedNode(F+'time'),
                records.ox.Literal(str(number)),records.graph))
            records.write_fact_projection(reference,assertion_id=f'a:{number}',relation_id=f'r:{number}',
                source_id='urn:canonical:0',target_id='urn:canonical:1',predicate='owns',
                qualifiers={'polarity':'positive','time':str(number)},evidence_ids=[f'e:{number}'])
        monkeypatch.setattr(ExtractionRecords,'read_fact_projection_page',
            lambda *a,**k:pytest.fail('coordination restored complete fact objects'))
        index=QualifiedFactIndex(store,'p',generation)
        imports=[]
        original_import=store.store.bulk_load
        def bulk_load(**options):
            imports.append(True)
            return original_import(**options)
        monkeypatch.setattr(store.store,'bulk_load',bulk_load)
        index.reconcile_and_stage(input_key='input')
        assert imports==[True]
        assert index.publication.one(index.publication.head,'qualifiedDecisionCount')=='140'
    finally:
        store.close()


def test_completion_survives_generation_and_reopen_without_native_reads(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    index.reconcile_and_stage(input_key='input')
    next_generation=store.begin_publication('p',expected_generation=generation,source_count=2,canonical_count=2)['generation']
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    try:
        index=QualifiedFactIndex(store,'p',next_generation)
        monkeypatch.setattr(ExtractionRecords,'read_fact_projection_page',lambda *a,**k:pytest.fail('completion scanned native facts'))
        assert index.publication.fact_stage_status(next_generation,'input')
        with pytest.raises(ProcessingError, match='input changed'):
            index.publication.fact_stage_status(next_generation,'changed')
        with pytest.raises(ProcessingError, match='input changed'):
            index.publication.fact_stage_status(next_generation,'input',functional_predicates=['owns'])
    finally:
        store.close()


def test_changed_input_rejects_corrupt_previous_policy(tmp_path):
    store,generation,refs,index=prepared(tmp_path)
    try:
        index.reconcile_and_stage(input_key='input')
        p=index.publication
        graph,head=p.graph,p.head
        store.store.update(f'DELETE WHERE {{ GRAPH {graph} {{ {head} <{P}qualifiedFunctionalPredicates> ?v }} }}')
        store.store.update(f'INSERT DATA {{ GRAPH {graph} {{ {p.triple(head,"qualifiedFunctionalPredicates",p.scalar("not-json"))} }} }}')
        next_generation=store.begin_publication('p',expected_generation=generation,source_count=2,canonical_count=2)['generation']
        sources=[]
        for source in ('s1','s2'):
            operations=sorted({reference.rsplit(':relation:',1)[0] for reference in refs
                if ExtractionRecords.from_fact_reference(store,'p',reference).binding['source']==source})
            entities=ExtractionRecords(store,ExtractionRecords.from_fact_reference(store,'p',operations[0]+':relation:0').binding,'entities').operation.value
            sources.append(dict(source=source,material='m',representation='r:'+source,recipe='recipe',
                operation_count=2,operations=[entities,*operations]))
        store.stage_publication_sources('p',next_generation,sources)
        with pytest.raises(ProcessingError,match='Completed fact policy is corrupt'):
            QualifiedFactIndex(store,'p',next_generation).reconcile_and_stage(input_key='changed')
    finally:
        store.close()


@pytest.mark.parametrize('defect',['missing','foreign','duplicate','orphan'])
def test_writer_rejects_invalid_decision_coverage_before_completion(tmp_path,monkeypatch,defect):
    store,generation,refs,index=prepared(tmp_path)
    original=index._reduce_partition
    def corrupt(*args):
        result=original(*args)
        members=result[2]
        identity=next(iter(members))
        if defect=='missing':
            members[identity].pop()
        elif defect=='foreign':
            members[identity][-1]='urn:foreign'
        elif defect=='duplicate':
            members[identity].append(members[identity][0])
        else:
            members['orphan']=[]
        return result
    try:
        monkeypatch.setattr(index,'_reduce_partition',corrupt)
        with pytest.raises(ProcessingError,match='coverage differs'):
            index.reconcile_and_stage(input_key='input')
        assert not index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


@pytest.mark.parametrize('field',['buildPredicate','buildAssertionId','buildRelationId'])
def test_duplicate_input_projection_rejected_before_completion(tmp_path,field):
    store,generation,refs,index=prepared(tmp_path)
    p=index.publication
    try:
        records=ExtractionRecords.from_fact_reference(store,'p',refs[0])
        store.store.add(p.ox.Quad(p.iri(refs[0]),p.ox.NamedNode(F+field),p.scalar('other'),records.fact_projection_graph))
        with pytest.raises(ProcessingError,match='missing or duplicated'):
            index.reconcile_and_stage(input_key='input')
        assert not p.fact_stage_status(generation,'input')
    finally:
        store.close()


def test_admitted_subset_cannot_claim_complete_native_coverage(tmp_path):
    store,generation,refs,index=prepared(tmp_path)
    try:
        records=ExtractionRecords.from_fact_reference(store,'p',refs[1])
        store.store.update(f'DELETE WHERE {{ GRAPH {records.fact_projection_graph} {{ <{refs[1]}> ?p ?o }} }}')
        with pytest.raises(ProcessingError,match='missing or duplicated'):
            index.reconcile_and_stage(input_key='input')
        assert not index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


def test_input_traversal_omission_never_commits_completion(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    original=index._physical_rows
    def incomplete():
        yield from (item for item in original() if item[0]!=refs[1])
    try:
        monkeypatch.setattr(index,'_physical_rows',incomplete)
        with pytest.raises(ProcessingError,match='admitted coverage incomplete'):
            index.reconcile_and_stage(input_key='input')
        assert not index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


@pytest.mark.parametrize('budget',[dict(max_group_records=1),dict(max_group_bytes=1)])
def test_group_limits_fail_explicitly_without_sealing(tmp_path,budget):
    store,generation,refs,index=prepared(tmp_path)
    try:
        with pytest.raises(ProcessingError,match='budget'):
            index.reconcile_and_stage(input_key='input',**budget)
        assert not index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


def test_ambiguous_canonical_membership_rejected(tmp_path):
    store,generation,refs,index=prepared(tmp_path)
    try:
        p=index.publication
        source=next(store.store.quads_for_pattern(p.iri(refs[0]),p.ox.NamedNode(F+'sourceEntity'),None,p.facts)).object
        store.store.add(p.ox.Quad(p.iri('urn:canonical:1'),p.ox.NamedNode(P+'member'),source,p.graph))
        with pytest.raises(ProcessingError,match='unique canonical'):
            index.reconcile_and_stage(input_key='input')
        assert not index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


@pytest.mark.parametrize('prefix',[5,-1])
def test_partial_import_never_commits_signature_and_retry_recomputes(tmp_path,monkeypatch,prefix):
    store,generation,refs,index=prepared(tmp_path)
    p=index.publication
    original=p.import_batches
    try:
        def interrupted(generation,batches):
            iterator=iter(batches)
            batch=next(iterator)
            # Simulate a bulk importer that durably wrote only a prefix.
            original(generation,iter([batch[:prefix]]))
            raise ProcessingError('interrupted')
        monkeypatch.setattr(p,'import_batches',interrupted)
        with pytest.raises(ProcessingError,match='interrupted'):
            index.reconcile_and_stage(input_key='input')
        assert not any(store.store.quads_for_pattern(None,p.ox.NamedNode(P+'qualifiedInput'),None,p.graph))
        assert not p.fact_stage_status(generation,'input')
        store.close()
        store=OxigraphStore(tmp_path/'facts')
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='input')
        assert index.publication.fact_stage_status(generation,'input')
    finally:
        store.close()


def test_unchanged_partitions_keep_decisions_and_skip_reducer(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    try:
        index.reconcile_and_stage(input_key='input')
        p=index.publication
        before=set(store.store.quads_for_pattern(None,None,None,p.graph))
        monkeypatch.setattr(index,'_reduce_partition',lambda *a,**k:pytest.fail('unchanged group reduced'))
        index.reconcile_and_stage(input_key='input')
        assert set(store.store.quads_for_pattern(None,None,None,p.graph))==before
    finally:
        store.close()


@pytest.mark.parametrize('completed',[True,False])
def test_new_generation_references_unchanged_fact_partition_without_copying_members(tmp_path,monkeypatch,completed):
    from tests.triplet_store.test_publication_records import indexes
    store,generation,refs,index=prepared(tmp_path)
    try:
        index.reconcile_and_stage(input_key='before')
        prior=index.publication
        old_graph=prior.graph
        if not completed:
            key=prior._completion_key('fact','before')
            store.store.remove(prior.ox.Quad(key,prior.iri(P+'completedGraph'),old_graph,prior.registry))
        sources=[]
        endpoints=[[],[]]
        for reference in refs:
            records=ExtractionRecords.from_fact_reference(store,'p',reference)
            binding=records.binding
            entity=ExtractionRecords(store,binding,'entities')
            sources.append(dict(source=binding['source'],material=binding['material'],
                representation=binding['representation'],recipe=binding['recipe'],
                operation_count=2,operations=[entity.operation.value,records.operation.value]))
            for i,field in enumerate(('sourceEntity','targetEntity')):
                endpoints[i].append(records.one(prior.iri(reference),field))
        generation=store.begin_publication('p',expected_generation=generation,
            source_count=2,canonical_count=2)['generation']
        store.stage_publication_sources('p',generation,sources)
        store.stage_publication_canonical('p',generation,[dict(id='urn:canonical:'+str(i),
            representative=members[0],members=members,member_count=2,selectors=[],selector_count=0)
            for i,members in enumerate(endpoints)])
        index=QualifiedFactIndex(store,'p',generation)
        reductions=[]
        reduce=index._reduce_partition
        def checked_reduce(*args):
            if completed:
                pytest.fail('unchanged completed partition reduced')
            reductions.append(1)
            return reduce(*args)
        monkeypatch.setattr(index,'_reduce_partition',checked_reduce)
        index.reconcile_and_stage(input_key='after')
        p=index.publication
        assert p.graph!=old_graph
        assert bool(list(store.store.quads_for_pattern(None,p.iri(P+'member'),None,p.graph))) is not completed
        assert bool(reductions) is not completed
        for kind in ('assertion','relation'):
            assert len(page_all(index,kind))==1
        assert len(index.topology_page()['records'])==1
        assert len(index.family_page()['records'])==1
        fact=page_all(index,'relation')[0]
        store.activate_publication('p',generation,indexes=indexes())
        assert set(store.read_publication_fact_members('p',generation,fact.id)['members'])==set(refs)
        scene=store.read_publication_scene('p',generation,dict(kind='links',
            visibleIds=['urn:canonical:0','urn:canonical:1']))
        assert len(scene['links'])==1
    finally:
        store.close()


@pytest.mark.parametrize('marker',['old','qualified-reference-records','native-final-decisions'])
def test_obsolete_layout_requires_offline_reset(tmp_path,marker):
    store,generation,refs,index=prepared(tmp_path)
    try:
        p=index.publication
        p.mutate(generation,[p.triple(p.head,'qualifiedIndexLayout',p.scalar(marker))])
        with pytest.raises(ProcessingError,match='offline reset'):
            index.reconcile_and_stage(input_key='input')
        p.reset_fact_stage(generation)
        index.reconcile_and_stage(input_key='input')
    finally:
        store.close()


@pytest.mark.parametrize('field,value',[('status','invalid'),('evidence_ids',[{}]),('qualifiers',{'polarity':'invalid'})])
def test_reducer_validates_every_input_before_merge(field,value):
    from pydantic import ValidationError
    item=dict(id='a',subject_id='s',predicate='owns',object='Engine',
        qualifiers=dict(polarity='positive'),evidence_ids=['e'])
    item[field]=value
    with pytest.raises(ValidationError):
        ConflictDetector.reconcile_qualified_facts('p',[item],[])


@pytest.mark.parametrize('kind',['assertion','relation'])
def test_endpoint_and_read_bounds(tmp_path,kind):
    store,generation,refs,index=prepared(tmp_path)
    try:
        assert index.canonical_endpoint_page(refs)=={ref:('urn:canonical:0','urn:canonical:1') for ref in refs}
        with pytest.raises(ProcessingError):
            index.canonical_endpoint_page([refs[0]]*129)
        index.reconcile_and_stage(input_key='input')
        assert not index.canonical_page(kind,subject_ids=[])['records']
        assert not index.canonical_page(kind,predicates=['other'])['records']
        with pytest.raises(ProcessingError,match='byte budget'):
            index.canonical_page(kind,max_bytes=1)
    finally:
        store.close()


def test_native_groups_preserve_polarity_and_separate_recorded_conditions(tmp_path):
    store,generation,refs,_=stage_duplicate_observations(tmp_path,source_ids=('s1','s2','s3','s4'))
    index=QualifiedFactIndex(store,'p',generation)
    try:
        for number,ref in enumerate(refs):
            records=ExtractionRecords.from_fact_reference(store,'p',ref)
            qualifiers=dict(polarity='negative' if number==1 else 'positive',
                time='2025' if number<2 else '2026',unit='shares',condition='audited')
            store.store.update(f'DELETE WHERE {{ GRAPH {records.graph} {{ <{ref}> <{F}polarity> ?v }} }}')
            for field,value in qualifiers.items():
                store.store.add(records.ox.Quad(records.ox.NamedNode(ref),records.ox.NamedNode(F+field),
                    records.ox.NamedNode(F+value) if field=='polarity' else records.ox.Literal(value),records.graph))
            records.write_fact_projection(ref,assertion_id=f'a:{number}',relation_id=f'r:{number}',
                source_id='urn:canonical:0',target_id='urn:canonical:1',predicate='owns',
                qualifiers=qualifiers,evidence_ids=[f'e:{number}'])
        observations=[(kind,item) for _,row in index._physical_rows()
            for kind,item in zip(('assertion','relation'),oracle_views(row))]
        expected=ConflictDetector.reconcile_qualified_facts('p',observations=observations)
        index.reconcile_and_stage(input_key='input')
        for kind,oracle in zip(('assertion','relation'),expected[:2]):
            expected=[item.model_copy(update={'metadata':{key:value for key,value in item.metadata.items()
                if key!='support_observation_ids'}}) for item in oracle]
            assert page_all(index,kind)==expected
        assertions=page_all(index,'assertion')
        assert sorted(item.status for item in assertions)==['candidate','contradicted','contradicted']
        assert len({item.qualifiers['time'] for item in assertions})==2
    finally:
        store.close()


def test_source_removal_replaces_only_affected_final_memberships(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    p=index.publication
    try:
        index.reconcile_and_stage(input_key='before')
        old_graph=p.graph
        # Withdrawal creates another publication; completed decisions stay immutable.
        source=ExtractionRecords.from_fact_reference(store,'p',refs[0])
        binding=source.binding
        entity=ExtractionRecords(store,binding,'entities')
        generation=store.begin_publication('p',expected_generation=generation,
            source_count=1,canonical_count=2)['generation']
        store.stage_publication_sources('p',generation,[dict(source=binding['source'],
            material=binding['material'],representation=binding['representation'],
            recipe=binding['recipe'],operation_count=2,
            operations=[entity.operation.value,source.operation.value])])
        endpoints=[source.one(p.iri(refs[0]),field) for field in ('sourceEntity','targetEntity')]
        store.stage_publication_canonical('p',generation,[dict(id='urn:canonical:'+str(i),
            representative=mention,members=[mention],selectors=[],member_count=1,selector_count=0)
            for i,mention in enumerate(endpoints)])
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='after')
        assert next(store.store.quads_for_pattern(None,p.iri(P+'member'),p.iri(refs[1]),old_graph),None)
        for kind in ('assertion','relation'):
            records=page_all(index,kind)
            assert len(records)==1
            assert 'support_observation_ids' not in records[0].metadata
        assert [q.object.value for q in index.publication.qualified_members(
            decision=p.iri(page_all(index,'relation')[0].id))]==[refs[0]]
        assert ExtractionRecords.from_fact_reference(store,'p',refs[1]).receipt() is not None
        store.close()
        store=OxigraphStore(tmp_path/'facts')
        index=QualifiedFactIndex(store,'p',generation)
        monkeypatch.setattr(index,'_reduce_partition',lambda *a,**k:pytest.fail('unchanged remainder reduced'))
        index.reconcile_and_stage(input_key='after')
        assert index.publication.fact_stage_status(generation,'after')
    finally:
        store.close()


def test_generation_change_interrupts_before_final_import(tmp_path,monkeypatch):
    store,generation,refs,index=prepared(tmp_path)
    p=index.publication
    original=p.import_batches
    try:
        def changed(generation,batches):
            store.begin_publication('p',expected_generation=generation,source_count=2,canonical_count=2)
            original(generation,batches)
        monkeypatch.setattr(p,'import_batches',changed)
        with pytest.raises(ProcessingError,match='generation'):
            index.reconcile_and_stage(input_key='input')
        assert not p.values(p.head,'factStageInput')
    finally:
        store.close()


def test_physical_projection_uses_indexed_endpoint_membership_not_graph_joins(tmp_path):
    store,generation,refs,index=prepared(tmp_path,70)
    try:
        query=store.store.query
        calls=[]
        def bounded_query(text,*args,**kwargs):
            if 'SELECT ?reference' in text:
                calls.append(text)
                assert '?targetDecisionGraph' not in text
                assert '?otherDecisionGraph' not in text
                assert '?sourceDecisionGraph' not in text
            return query(text,*args,**kwargs)
        original=store.store
        class ObservedStore:
            def __getattr__(self,name):
                return bounded_query if name=='query' else getattr(original,name)
        store.store=ObservedStore()
        rows=list(index._physical_rows())
        assert len(rows)==len(refs) and not calls
        assert {row['target'] for _,row in rows}=={'urn:canonical:1'}
    finally:
        store.close()


def test_physical_read_many_operations_and_decision_graphs_has_bounded_index_work(tmp_path):
    from time import perf_counter
    store,generation,refs,_=stage_duplicate_observations(tmp_path,
        source_ids=tuple('source:'+str(i) for i in range(64)))
    projections(store,refs)
    index=QualifiedFactIndex(store,'p',generation)
    p=index.publication
    graph,head=p.stage_graph('identity'),p.stage_head('identity')
    try:
        old=list(store.store.quads_for_pattern(head,p.iri(P+'canonical'),None,graph))
        members=[q.object for canonical in old for q in store.store.quads_for_pattern(
            canonical.object,p.iri(P+'member'),None,graph)]
        for quad in old:
            store.store.remove(quad)
        for number,member in enumerate(members):
            node=p.iri('urn:canonical:isolated:'+str(number))
            location=p.iri('urn:decision:isolated:'+str(number))
            for quad in (p.ox.Quad(head,p.iri(P+'canonical'),node,graph),
                         p.ox.Quad(node,p.iri(P+'canonicalGraph'),location,graph),
                         p.ox.Quad(node,p.iri(P+'member'),member,location)):
                store.store.add(quad)
        original=store.store
        calls=[]
        class ObservedStore:
            def __getattr__(self,name):
                return getattr(original,name)
            def query(self,*args,**kwargs):
                pytest.fail('physical reader reintroduced cross-graph SPARQL')
            def quads_for_pattern(self,*args):
                calls.append(args)
                return original.quads_for_pattern(*args)
        store.store=ObservedStore()
        started=perf_counter()
        rows=list(index._physical_rows())
        elapsed=perf_counter()-started
        assert {reference for reference,_ in rows}==set(refs)
        assert len({row['source'] for _,row in rows})==64
        assert len(calls)<len(refs)*80+256
        assert elapsed<5, dict(seconds=elapsed,index_seeks=len(calls))
    finally:
        store.close()
