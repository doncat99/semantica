"""The native pipeline owns real build stages, failure and ordering."""
import pytest

from semantica import semantic_publication_builder as builder
from semantica.pipeline import ExecutionEngine, StepStatus
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


STAGES = ['prepare', 'source_processing', 'source_classification',
          'source_projection', 'entity_resolution', 'fact_reconciliation',
          'semantic_organization', 'artifact_writing']


def test_build_executes_real_native_dependency_stages(tmp_path, monkeypatch):
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    captured = []
    execute = ExecutionEngine.execute_pipeline
    def observe(self, pipeline, *args, **kwargs):
        captured.append(pipeline)
        assert [step.name for step in pipeline.steps] == STAGES
        assert [step.dependencies for step in pipeline.steps] == [[], *[[name] for name in STAGES[:-1]]]
        assert len({step.handler for step in pipeline.steps}) == len(STAGES)
        assert self.failure_handler.default_max_retries == 0
        return execute(self, pipeline, *args, **kwargs)
    monkeypatch.setattr(ExecutionEngine, 'execute_pipeline', observe)
    result = builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / 'out')['params']))
    assert result['publication']['state'] == 'pending'
    assert result['publication']['source_count'] == 1
    assert result['publication']['canonical_count'] > 0
    assert result['semantic_store']['path'] == str(tmp_path / 'native-store')
    assert not (tmp_path / 'out' / 'semantic-graph.json').exists()
    assert not (tmp_path / 'out' / 'snapshot.json').exists()
    assert len(captured) == 1
    assert all(step.status == StepStatus.COMPLETED for step in captured[0].steps)


def test_stage_failure_preserves_cause_and_never_publishes_or_retries(tmp_path, monkeypatch):
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    captured, calls = [], []
    execute = ExecutionEngine.execute_pipeline
    def observe(self, pipeline, *args, **kwargs):
        captured.append(pipeline)
        return execute(self, pipeline, *args, **kwargs)
    failure = ValueError('organization rejected')
    def reject(*args):
        calls.append('organization')
        raise failure
    monkeypatch.setattr(ExecutionEngine, 'execute_pipeline', observe)
    monkeypatch.setattr(builder, '_semantic_organization', reject)
    with pytest.raises(ValueError) as error:
        builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
            _request(source, tmp_path / 'out')['params']))
    assert error.value is failure
    assert calls == ['organization']
    assert len(captured) == 1
    assert captured[0].steps[-2].status == StepStatus.FAILED
    assert captured[0].steps[-1].status == StepStatus.PENDING
    assert not (tmp_path / 'out' / 'semantic-graph.json').exists()
    assert not (tmp_path / 'out' / 'snapshot.json').exists()


def test_complete_source_plan_is_available_before_project_computation(tmp_path, monkeypatch):
    """Pending native cursors require every source operation before computation."""
    from semantica.triplet_store.publication_records import PublicationRecords
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    organize = builder._semantic_organization
    observed = []

    def inspect_plan(*args):
        request, store, _ = builder._native_build.get()
        generation = store.publication_status(request.project_id)['generation']
        publication = PublicationRecords(store, request.project_id)
        publication._build_fence(generation)
        page = publication.build_page(generation, kind='Entity')
        assert page['records']
        observed.append(True)
        return organize(*args)

    monkeypatch.setattr(builder, '_semantic_organization', inspect_plan)
    builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / 'out')['params']))
    assert observed == [True]


def test_project_computation_reopens_native_identity_projection(tmp_path, monkeypatch):
    """Source DTOs must be released before the project resolver/organization."""
    import weakref
    from semantica.triplet_store.extraction_records import ExtractionRecords
    built_refs, hydrated = [], []
    original_build, original_read = builder._build_source, ExtractionRecords.read_identity_projection
    def capture(*args, **kwargs):
        result = original_build(*args, **kwargs)
        built_refs.extend(weakref.ref(entity) for entity in result['entities'])
        return result
    def read(self, *args, **kwargs):
        assert all(ref() is None for ref in built_refs)
        value = original_read(self, *args, **kwargs)
        hydrated.append(value['id'])
        return value
    monkeypatch.setattr(builder, '_build_source', capture)
    monkeypatch.setattr(ExtractionRecords, 'read_identity_projection', read)
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / 'out')['params']))
    assert hydrated


def test_source_projection_flushes_at_source_boundary_not_per_record(tmp_path, monkeypatch):
    from semantica.triplet_store.extraction_records import ExtractionRecords
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.publication_records import PublicationRecords
    state = dict(writing=False, pending=False, writes=0, fences=0)
    for name in ('write_identity_projection', 'write_fact_projection'):
        original = getattr(ExtractionRecords, name)
        def write(self, *args, _original=original, **kwargs):
            state['writing'] = True
            try:
                result = _original(self, *args, **kwargs)
                state['pending'] = True
                state['writes'] += 1
                return result
            finally:
                state['writing'] = False
        monkeypatch.setattr(ExtractionRecords, name, write)
    original_flush = OxigraphStore.flush
    def flush(self):
        assert not state['writing'], 'Derived projection must not force disk flush per record'
        result = original_flush(self)
        if state['pending']:
            state['fences'] += 1
            state['pending'] = False
        return result
    monkeypatch.setattr(OxigraphStore, 'flush', flush)
    original_stage = PublicationRecords.stage_sources
    def stage(self, *args, **kwargs):
        assert not state['pending'], 'Source must be durable before publication staging'
        return original_stage(self, *args, **kwargs)
    monkeypatch.setattr(PublicationRecords, 'stage_sources', stage)
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / 'out')['params']))
    assert state['writes'] > 1
    assert state['fences'] == 1


def test_native_identity_components_match_project_oracle_across_sources_and_restart(tmp_path, monkeypatch):
    """The full-context resolver's IDs and field provenance survive component reads."""
    from tests.test_semantic_artifact import _parsed_ref
    from semantica.triplet_store.publication_records import PublicationRecords
    source=tmp_path/'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    second=tmp_path/'second.txt'
    second.write_text('Ada Lovelace designed the Analytical Engine in London.')
    raw=_request(source,tmp_path/'out',recipe='model')['params']
    from semantica.source import source_content_revision
    other={**raw['sources'][0],'sourceId':'source-2','filePath':str(second),
           'name':second.name,'materialRevision':source_content_revision(second)}
    raw['sources'].append(other)
    raw['parsedSources'].append(_parsed_ref(raw,other))
    monkeypatch.setattr(builder,'_extract_project_sources',lambda *a,**kw:[(None,[],[])])
    monkeypatch.setattr(builder,'_explanation_reports',lambda *a,**kw:([],[]))
    monkeypatch.setattr(builder,'_grounded_topics',lambda *a,**kw:[])
    original=builder._build_source
    captured,refs=[],{}
    def capture(*args,**kwargs):
        result=original(*args,**kwargs)
        captured.extend(result['entities'])
        refs.update(result['native_entity_refs'])
        return result
    monkeypatch.setattr(builder,'_build_source',capture)
    original_organize=builder._semantic_organization
    observed=[]
    def verify(topology,*args):
        resolver=builder.EntityResolver(strategy='contextual',deduplication={'similarity':{'property_schema':{}}})
        oracle,_,_=builder._resolve_native_entities(captured,resolver=resolver)
        assert sorted(topology['entities'],key=lambda x:x['id']) == sorted(
            ({'id':x.id,'name':x.canonical_name} for x in oracle),key=lambda x:x['id'])
        request,store,_=builder._native_build.get()
        generation=store.publication_status(request.project_id)['generation']
        publication=PublicationRecords(store,request.project_id)
        for entity in oracle:
            selected=resolver.resolution_selections[entity.id]
            node=publication.iri(entity.id)
            members,selectors=publication._canonical_references(node)
            actual=dict(representative=publication.one(node,'representative'),members=members,selectors=selectors)
            assert actual['representative']==refs[selected['representative']][0]
            assert set(actual['members'])=={ref for member in selected['members'] for ref in refs[member]}
            expected={(field,refs[origin][0]) for field,origins in selected['field_sources'].items() for origin in origins}
            for name,origins in selected['property_sources'].items():
                for origin in origins:
                    expected.add(('properties.'+name,store.publication_attribute_reference(
                        request.project_id,generation,refs[origin][0],name)))
            assert {(item['field'],item['record']) for item in actual['selectors']}==expected
        observed.append(len(topology['entities']))
        return original_organize(topology,*args)
    monkeypatch.setattr(builder,'_semantic_organization',verify)
    request=SemanticArtifactBuildRequest.model_validate(raw)
    first=builder.build_semantic_artifacts(request)
    captured.clear()
    refs.clear()
    second_result=builder.build_semantic_artifacts(request)
    assert observed[0]==observed[1]>0
    assert first['publication']['canonical_count']==second_result['publication']['canonical_count']
