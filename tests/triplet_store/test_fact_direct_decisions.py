"""The native fact owner never persists intermediate logical views."""
import pytest
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations


def projections(store, refs):
    from semantica.triplet_store.extraction_records import ExtractionRecords
    for number, ref in enumerate(refs):
        records = ExtractionRecords.from_fact_reference(store, 'p', ref)
        records.write_fact_projection(ref, assertion_id=f'a:{number}', relation_id=f'r:{number}',
            source_id='urn:canonical:0', target_id='urn:canonical:1', predicate='owns',
            qualifiers={'polarity': 'positive'}, evidence_ids=[f'e:{number}'])


def test_native_input_is_consumed_once_without_durable_view_entries(tmp_path,monkeypatch):
    store, generation, refs, _ = stage_duplicate_observations(tmp_path)
    try:
        projections(store, refs)
        index = QualifiedFactIndex(store, 'p', generation)
        import tempfile
        import sqlite3
        def forbidden(*args,**kwargs):
            pytest.fail('fact coordination created intermediate storage')
        for name in ('TemporaryDirectory','NamedTemporaryFile','TemporaryFile','mkstemp','mkdtemp'):
            monkeypatch.setattr(tempfile,name,forbidden)
        monkeypatch.setattr(sqlite3,'connect',forbidden)
        index.reconcile_and_stage(input_key='input')
        p = index.publication
        assert not any('qualified-entry:' in str(q) or 'qualifiedRecord' in str(q)
            for q in store.store.quads_for_pattern(None, None, None, p.graph))
        assert p.fact_stage_status(generation, 'input')
        assert len(index.canonical_page('relation')['records']) == 1
    finally:
        store.close()


def test_single_reduction_preserves_independent_public_representatives(tmp_path,monkeypatch):
    from semantica.conflicts.conflict_detector import ConflictDetector
    from semantica.triplet_store.extraction_records import ExtractionRecords
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        for reference,assertion,relation in zip(refs,('a:z','a:a'),('r:a','r:z'),strict=True):
            records=ExtractionRecords.from_fact_reference(store,'p',reference)
            records.write_fact_projection(reference,assertion_id=assertion,relation_id=relation,
                source_id='urn:canonical:0',target_id='urn:canonical:1',predicate='owns',
                qualifiers={'polarity':'positive'},evidence_ids=['shared'])
        original=ConflictDetector.reconcile_qualified_facts
        visited=[]
        def reconcile(project,**options):
            source=options['observations']
            def observations():
                for kind,item in source:
                    visited.append((kind,item['id']))
                    yield kind,item
            return original(project,**{**options,'observations':observations()})
        monkeypatch.setattr(ConflictDetector,'reconcile_qualified_facts',staticmethod(reconcile))
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='input')
        assert sorted(visited)==[('assertion','a:a'),('assertion','a:z')]
        assertion=index.canonical_page('assertion')['records'][0]
        relation=index.canonical_page('relation')['records'][0]
        assert assertion.metadata['representative_observation_id']=='a:a'
        assert relation.metadata['representative_observation_id']=='r:a'
        assert assertion.id.split(':')[1]==relation.id.split(':')[1]
        assert assertion.evidence_ids==relation.evidence_ids==['shared']
        assert len(visited)==2  # Neither public expression reruns coordination.
    finally:
        store.close()


@pytest.mark.parametrize('reverse',[False,True])
def test_distinct_native_supports_may_share_public_projection_ids(tmp_path,monkeypatch,reverse):
    from semantica.triplet_store.extraction_records import ExtractionRecords
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        for number,reference in enumerate(refs):
            records=ExtractionRecords.from_fact_reference(store,'p',reference)
            records.write_fact_projection(reference,assertion_id='a:shared',relation_id='r:shared',
                source_id='urn:canonical:0',target_id='urn:canonical:1',predicate='owns',
                qualifiers={'polarity':'positive'},evidence_ids=[f'e:{number}'])
        index=QualifiedFactIndex(store,'p',generation)
        if reverse:
            rows=list(index._physical_rows())
            monkeypatch.setattr(index,'_physical_rows',lambda:iter(reversed(rows)))
        index.reconcile_and_stage(input_key='input')
        for kind in ('assertion','relation'):
            item=index.canonical_page(kind)['records'][0]
            assert item.evidence_ids==['e:0','e:1']
            assert item.metadata['representative_observation_id']==('a:shared' if kind=='assertion' else 'r:shared')
        p=index.publication
        from semantica.triplet_store.publication_records import P
        decisions=list(store.store.quads_for_pattern(p.head,p.ox.NamedNode(P+'qualifiedDecision'),None,p.graph))
        assert len(decisions)==1
        assert {q.object.value for q in store.store.quads_for_pattern(decisions[0].object,p.ox.NamedNode(P+'member'),None,p.graph)}==set(refs)
    finally:
        store.close()


def test_single_reduction_rejects_duplicate_native_reference(tmp_path):
    from semantica.utils.exceptions import ProcessingError
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        projections(store,refs)
        index=QualifiedFactIndex(store,'p',generation)
        rows=list(index._physical_rows())
        rows[1]=(rows[0][0],rows[1][1])
        with pytest.raises(ProcessingError,match='Duplicate native observation'):
            index._reduce_partition(rows,())
    finally:
        store.close()


def test_entity_backed_fact_has_one_decision_and_one_support_membership(tmp_path):
    from semantica.triplet_store.publication_records import P
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        projections(store,refs)
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='input')
        p=index.publication
        decisions=list(store.store.quads_for_pattern(p.head,p.ox.NamedNode(P+'qualifiedDecision'),None,p.graph))
        assert len(decisions)==1
        assert all(not q.subject.value.startswith('assertion:') and q.predicate.value!=P+'qualifiedMember'
            for q in store.store.quads_for_pattern(None,None,None,p.graph))
        assert len(list(store.store.quads_for_pattern(decisions[0].object,p.ox.NamedNode(P+'member'),None,p.graph)))==len(refs)
        assert len(index.canonical_page('assertion')['records'])==1
        assert len(index.canonical_page('relation')['records'])==1
    finally:
        store.close()


def test_coordination_projects_native_fields_without_restoring_fact_objects(tmp_path,monkeypatch):
    from semantica.triplet_store.extraction_records import ExtractionRecords
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        projections(store,refs)
        def forbidden(*args,**kwargs):
            pytest.fail('coordination restored complete fact projections')
        monkeypatch.setattr(ExtractionRecords,'read_fact_projection_page',forbidden)
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='input')
        assert len(index.canonical_page('relation')['records'])==1
    finally:
        store.close()



def test_completion_is_committed_by_writer_and_reuse_does_no_work(tmp_path,monkeypatch):
    store,generation,refs,_=stage_duplicate_observations(tmp_path)
    try:
        projections(store,refs)
        index=QualifiedFactIndex(store,'p',generation)
        index.reconcile_and_stage(input_key='input')
        assert index.publication.fact_stage_status(generation,'input')
        def forbidden(*args,**kwargs):
            pytest.fail('completed coordination performed input reads, reduction or import')
        monkeypatch.setattr(index,'_physical_rows',forbidden)
        monkeypatch.setattr(index,'_reduce_partition',forbidden)
        monkeypatch.setattr(index.publication,'import_batches',forbidden)
        index.reconcile_and_stage(input_key='input')
        assert not hasattr(index.publication,'seal_fact_stage')
    finally:
        store.close()
