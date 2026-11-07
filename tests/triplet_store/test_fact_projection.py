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
                relation = KnowledgeRelation.model_validate(records.read_fact_projection(ref,'relation'))
                assertion = KnowledgeAssertion.model_validate(records.read_fact_projection(ref,'assertion'))
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
        for assertion,relation in zip(result['assertions'],result['relations'],strict=True):
            key=builder.stable_digest([relation.id,relation.evidence_ids])
            for ref in result['native_fact_refs'][key]:
                expected[ref]=(assertion.model_dump(),relation.model_dump())
        return result
    monkeypatch.setattr(builder,'_build_source',capture)
    from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
    original_index_build=QualifiedFactIndex.build
    def verify_released(index,rows):
        assert source_results
        assert all(not ({'assertions','relations','native_fact_refs'} & result.keys()) for result in source_results)
        assert index.owner._build_plan_scope == (index.publication.graph.value,index.generation)
        return original_index_build(index,rows)
    monkeypatch.setattr(QualifiedFactIndex,'build',verify_released)
    original_reconcile=QualifiedFactIndex.iter_reconciled
    def verify_reconcile(index,read,**options):
        def scoped_read(*args):
            assert index.owner._build_plan_scope == (index.publication.graph.value,index.generation)
            return read(*args)
        for group in original_reconcile(index,scoped_read,**options):
            yield group
            assert index.owner._build_plan_scope == (index.publication.graph.value,index.generation)
    monkeypatch.setattr(QualifiedFactIndex,'iter_reconciled',verify_reconcile)
    build_child(tmp_path,stop_before_publication=False)
    request=SemanticArtifactBuildRequest.model_validate(_request(tmp_path/'source.txt',tmp_path/'published')['params'])
    store=OxigraphStore(request.native_store_dir)
    try:
        assert expected
        for ref,(assertion,relation) in expected.items():
            records=ExtractionRecords.from_fact_reference(store,request.project_id,ref)
            assert records.read_fact_projection(ref,'assertion')==assertion
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
        assert index.owner._build_plan_scope == (index.publication.graph.value,index.generation)
        assert 0 < len(kwargs['subject_ids']) <= 128
        page = original_family(index, **kwargs)
        actual.update(value for row in page['records'] for value in row['representations'])
        return page
    monkeypatch.setattr(builder, '_build_source', capture_source)
    monkeypatch.setattr(QualifiedFactIndex, 'family_page', capture_family)
    build_child(tmp_path, stop_before_publication=False)
    assert expected and actual
    assert actual == expected
