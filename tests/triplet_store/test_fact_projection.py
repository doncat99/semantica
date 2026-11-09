import pytest
from semantica.triplet_store.extraction_records import ExtractionRecords
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation
from tests.test_native_extraction_handoff import build_child
from tests.test_semantic_artifact import _request
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest


def test_native_fact_projection_survives_restart_and_matches_builder(tmp_path):
    built = build_child(tmp_path, stop_before_publication=False)
    request = SemanticArtifactBuildRequest.model_validate(_request(tmp_path / 'source.txt', tmp_path / 'published')['params'])
    store = OxigraphStore(request.native_store_dir)
    try:
        generation = built['publication']['generation']
        scene = store.read_publication_scene(request.project_id, generation, {'kind':'nodes'})
        links = store.read_publication_scene(request.project_id,generation,{'kind':'links','visibleIds':[item['id'] for item in scene['nodes']]})
        assert links['links']
        for link in links['links']:
            members = store.read_publication_fact_members(request.project_id,generation,link['id'])
            for member in members['members']:
                ref = member if isinstance(member,str) else member['id']
                records = ExtractionRecords.from_fact_reference(store,request.project_id,ref)
                projections = records.read_fact_projections(ref)
                relation = KnowledgeRelation.model_validate(projections['relation'])
                assertion = KnowledgeAssertion.model_validate(projections['assertion'])
                assert projections['relation'] == records.read_fact_projection(ref,'relation')
                assert projections['assertion'] == records.read_fact_projection(ref,'assertion')
                assert relation.evidence_ids == assertion.evidence_ids
                assert relation.qualifiers == assertion.qualifiers
                assert relation.type == assertion.predicate
    finally:
        store.close()


def test_native_fact_projection_matches_source_observation_oracle(tmp_path, monkeypatch):
    from semantica import semantic_publication_builder as builder
    original=builder._build_source
    expected={}
    source_results=[]
    def capture(*args,**kwargs):
        result=original(*args,**kwargs)
        source_results.append(result)
        assert 'assertions' not in result and 'relations' not in result
        for fact in result['facts']:
            relation=KnowledgeRelation(id='relation:'+fact.id.split(':')[1],
                source_entity_id=fact.subject_id,target_entity_id=fact.object_entity_id,
                type=fact.predicate,qualifiers=fact.qualifiers,evidence_ids=fact.evidence_ids,
                support_ids=fact.evidence_ids,status='candidate')
            key=builder.stable_digest([relation.id,relation.evidence_ids])
            for ref in result['native_fact_refs'][key]:
                expected[ref]=(dict(id=fact.id, subject_id=fact.subject_id, object_entity_id=fact.object_entity_id,
                    predicate=fact.predicate, qualifiers=fact.qualifiers, evidence_ids=fact.evidence_ids),relation.model_dump())
        return result
    monkeypatch.setattr(builder,'_build_source',capture)
    from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
    original_index_build=QualifiedFactIndex.reconcile_and_stage
    def verify_released(index,**options):
        assert source_results
        assert all(not ({'facts','assertions','relations','native_fact_refs'} & result.keys()) for result in source_results)
        assert index.owner._build_plan_scope == (index.publication.publication_graph.value,index.generation)
        return original_index_build(index,**options)
    monkeypatch.setattr(QualifiedFactIndex,'reconcile_and_stage',verify_released)
    build_child(tmp_path,stop_before_publication=False)
    request=SemanticArtifactBuildRequest.model_validate(_request(tmp_path/'source.txt',tmp_path/'published')['params'])
    store=OxigraphStore(request.native_store_dir)
    try:
        assert expected
        for ref,(assertion,relation) in expected.items():
            records=ExtractionRecords.from_fact_reference(store,request.project_id,ref)
            actual = records.read_fact_projection(ref,'assertion')
            assert {key: actual[key] for key in assertion} == assertion
            assert actual['object'] == 'Analytical Engine'
            assert records.read_fact_projection(ref,'relation')==relation
            graph=records.fact_projection_graph
            node=store._oxigraph.NamedNode(ref)
            store.store.update('DELETE WHERE { GRAPH '+str(graph)+' { '+str(node)+' <urn:semantica:field:buildPredicate> ?v } }')
            import pytest
            from semantica.utils.exceptions import ProcessingError
            with pytest.raises(ProcessingError,match='corrupt'):
                records.read_fact_projection(ref,'relation')
    finally:
        store.close()


def test_native_family_representation_matches_builder_evidence(tmp_path, monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
    original_source = builder._build_source
    original_family = QualifiedFactIndex.family_page
    expected, actual = set(), set()
    def capture_source(*args, **kwargs):
        result = original_source(*args, **kwargs)
        expected.update(item.representation_id for item in result['evidence'])
        return result
    def capture_family(index, **kwargs):
        assert index.owner._build_plan_scope == (index.publication.publication_graph.value,index.generation)
        assert 0 < len(kwargs['subject_ids']) <= 128
        page = original_family(index, **kwargs)
        actual.update(value for row in page['records'] for value in row['representations'])
        return page
    monkeypatch.setattr(builder, '_build_source', capture_source)
    monkeypatch.setattr(QualifiedFactIndex, 'family_page', capture_family)
    build_child(tmp_path, stop_before_publication=False)
    assert expected and actual
    assert actual == expected


def test_projection_field_access_is_linear_in_evidence_count(tmp_path, monkeypatch):
    from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations
    store, _, refs, _ = stage_duplicate_observations(tmp_path)
    records = ExtractionRecords.from_fact_reference(store, 'p', refs[0])
    evidence = ['e:' + str(i) for i in range(128)]
    records.write_fact_projection(refs[0], assertion_id='a', relation_id='r',
        source_id='a', target_id='b', predicate='owns',
        qualifiers={'polarity': 'positive'}, evidence_ids=evidence)
    original = store.store
    accesses = [0]

    class CountedQuad:
        def __init__(self, quad):
            self.quad = quad

        def __getattr__(self, name):
            accesses[0] += 1
            return getattr(self.quad, name)

        def __str__(self):
            return str(self.quad)

    class CountedStore:
        def quads_for_pattern(self, subject, predicate, obj, graph):
            for quad in original.quads_for_pattern(subject, predicate, obj, graph):
                yield CountedQuad(quad) if graph == records.fact_projection_graph else quad

        def __getattr__(self, name):
            return getattr(original, name)

    try:
        monkeypatch.setattr(store, 'store', CountedStore())
        result = records.read_fact_projections(refs[0])
        assert result['relation']['evidence_ids'] == evidence
        assert result['assertion']['evidence_ids'] == evidence
        assert accesses[0] < 128 * 40
    finally:
        monkeypatch.setattr(store, 'store', original)
        store.close()


def test_projection_page_admits_operation_once_and_rechecks_next_page(tmp_path, monkeypatch):
    import pytest
    from semantica.utils.exceptions import ProcessingError
    from semantica.triplet_store.extraction_records import F
    from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations
    store, _, refs, _ = stage_duplicate_observations(tmp_path, relations_per_source=3)
    try:
        for i, ref in enumerate(refs):
            records = ExtractionRecords.from_fact_reference(store, 'p', ref)
            records.write_fact_projection(ref, assertion_id='a'+str(i), relation_id='r'+str(i),
                source_id='a', target_id='b', predicate='owns',
                qualifiers={'polarity':'positive'}, evidence_ids=['e:'+str(i)])
        expected = {ref: ExtractionRecords.from_fact_reference(store, 'p', ref).read_fact_projections(ref)
            for ref in refs}
        calls = []
        original = ExtractionRecords.receipt
        def counted(records):
            calls.append(records.operation.value)
            return original(records)
        monkeypatch.setattr(ExtractionRecords, 'receipt', counted)
        assert physical_views(ExtractionRecords.read_fact_projection_page(store, 'p', refs)) == expected
        assert len(calls) == len(set(calls)) == 2
        calls.clear()
        repeated = ExtractionRecords.read_fact_projection_page(store, 'p', refs)
        assert len(calls) == len(set(calls)) == 2
        assert physical_views(repeated) == expected
        with pytest.raises(ProcessingError):
            ExtractionRecords.read_fact_projection_page(store, 'p', refs*30)
        node = store._oxigraph.NamedNode(refs[1])
        operation = store._oxigraph.NamedNode(refs[1].rsplit(':relation:', 1)[0])
        graph = records.graph
        store.store.remove(store._oxigraph.Quad(operation, store._oxigraph.NamedNode(F+'ownedRecord'), node, graph))
        with pytest.raises(ProcessingError, match='membership'):
            ExtractionRecords.read_fact_projection_page(store, 'p', refs)
    finally:
        store.close()


@pytest.mark.parametrize('damage', ['digest', 'receipt', 'foreign-project', 'invalid-reference', 'duplicate', 'bytes'])
def test_projection_page_rejects_damage_and_budget_overflow(tmp_path, monkeypatch, damage):
    from semantica.utils.exceptions import ProcessingError
    from semantica.triplet_store.extraction_records import F
    from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations
    store, _, refs, _ = stage_duplicate_observations(tmp_path)
    try:
        for i, ref in enumerate(refs):
            records = ExtractionRecords.from_fact_reference(store, 'p', ref)
            records.write_fact_projection(ref, assertion_id='a'+str(i), relation_id='r'+str(i),
                source_id='a', target_id='b', predicate='owns',
                qualifiers={'polarity':'positive'}, evidence_ids=['e:'+str(i)])
        ExtractionRecords.read_fact_projection_page(store, 'p', refs)
        project = 'p'
        if damage == 'digest':
            store.store.update('DELETE WHERE { GRAPH '+str(records.fact_projection_graph)+' { <'+refs[-1]+'> <'+F+'factProjectionDigest> ?v } }')
        elif damage == 'receipt':
            original = ExtractionRecords.receipt
            monkeypatch.setattr(ExtractionRecords, 'receipt', lambda self: None if self.operation == records.operation else original(self))
        elif damage == 'foreign-project':
            project = 'other'
        elif damage == 'invalid-reference':
            refs = [None]
        elif damage == 'duplicate':
            refs = [refs[0], refs[0]]
        elif damage == 'bytes':
            original = ExtractionRecords._read_fact_projection_node
            monkeypatch.setattr(ExtractionRecords, '_read_fact_projection_node',
                lambda self,*args,**kwargs: (original(self,*args,**kwargs)[0], 9*1024*1024))
        with pytest.raises(ProcessingError):
            ExtractionRecords.read_fact_projection_page(store, project, refs)
    finally:
        store.close()


@pytest.mark.parametrize('damaged', [False, True])
def test_offline_projection_metadata_migration_preserves_native_facts(tmp_path, damaged):
    from semantica.triplet_store.extraction_records import F, _hash
    from semantica.utils.exceptions import ProcessingError
    from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations
    store, _, refs, _ = stage_duplicate_observations(tmp_path)
    try:
        records = ExtractionRecords.from_fact_reference(store, 'p', refs[0])
        records.write_fact_projection(refs[0], assertion_id='a', relation_id='r',
            source_id='a', target_id='b', predicate='owns',
            qualifiers={'polarity':'positive'}, evidence_ids=['e'])
        expected = records.read_fact_projections(refs[0])
        native = set(store.store.quads_for_pattern(None, None, None, records.graph))
        node, graph, ox = records.ox.NamedNode(refs[0]), records.fact_projection_graph, records.ox
        old = next(store.store.quads_for_pattern(node, ox.NamedNode(F+'factProjectionDigest'), None, graph))
        store.store.remove(old)
        store.store.add(ox.Quad(node, ox.NamedNode(F+'buildQualifierPolarity'),
            ox.Literal('negative' if damaged else 'positive'), graph))
        body = list(store.store.quads_for_pattern(node, None, None, graph))
        for child in [q.object for q in body if q.predicate.value == F+'buildEvidence']:
            body.extend(store.store.quads_for_pattern(child, None, None, graph))
        store.store.add(ox.Quad(node, old.predicate, ox.Literal(_hash(body)), graph))
        with pytest.raises(ProcessingError, match='offline metadata migration'):
            records.read_fact_projections(refs[0])
        if damaged:
            before = set(store.store.quads_for_pattern(None, None, None, graph))
            with pytest.raises(ProcessingError, match='qualifiers differ'):
                records.migrate_fact_projection(refs[0])
            assert before == set(store.store.quads_for_pattern(None, None, None, graph))
        else:
            assert records.migrate_fact_projection(refs[0]) is True
            assert records.read_fact_projections(refs[0]) == expected
            assert records.migrate_fact_projection(refs[0]) is False
        assert native == set(store.store.quads_for_pattern(None, None, None, records.graph))
    finally:
        store.close()


def physical_views(rows):
    result={}
    for ref,row in rows.items():
        shared=dict(qualifiers=row['qualifiers'],evidence_ids=row['evidence'],
            support_ids=row['evidence'],status='candidate',metadata={})
        result[ref]=dict(
            assertion=dict(id=row['assertion'],subject_id=row['source'],object_entity_id=row['target'],
                predicate=row['predicate'],object=row['object'],**shared),
            relation=dict(id=row['id'],source_entity_id=row['source'],target_entity_id=row['target'],
                type=row['predicate'],**shared))
    return result
