"""Explanation point reads native evidence; no aggregate or copied source bodies."""
import json

import pytest
from pydantic import ValidationError

from semantica import semantic_worker, semantic_publication_builder
from semantica.semantic_document_reader import write_reader_artifact
from semantica.semantic_extract.types import Entity
from semantica.semantic_artifact_schema import ReportSection
from semantica.triplet_store.oxigraph_store import OxigraphStore


@pytest.fixture
def explanation(tmp_path):
    path = tmp_path / 'source.json'
    digests = write_reader_artifact(path, dict(protocol='semantica.parsed-source.v3',
        materialRevision='material', document=dict(format='pdf-text', representation_revision='representation',
            pages=[dict(text='Acme', page_number=1), dict(text='Corp', page_number=2)], metadata={})))
    def ref(file, digest, kind):
        stat = file.stat()
        return dict(path=str(file), digest=digest, kind=kind, mediaType='application/json',
            installation=dict(digest=digest, identity=':'.join(map(str,
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))))
    source = dict(sourceId='source', materialRevision='material', representationRevision='representation',
        artifact=ref(path, digests[0], 'document-representation'),
        readerIndex=ref(path.with_suffix('.reader.sqlite'), digests[1], 'document-reader-index'))
    owner = OxigraphStore(tmp_path / 'native')
    binding = dict(project='project', source='source', material='material', representation='representation',
        recipe='recipe', model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=9)
    entity = Entity('Acme\nCorp', 'ORG', 0, 9, .9, dict(mention_id='mention:0',
        span_occurrence=0, model='model', provider='fixture', extraction_method='llm_typed'))
    owner.adopt_extraction(binding, 'entities', [entity], text='Acme\nCorp', native_ranges=[
        dict(nativeRef='#/document/pages/0/text', start=0, end=4, windowStart=0, windowEnd=4),
        dict(nativeRef='#/document/pages/1/text', start=0, end=4, windowStart=5, windowEnd=9, joinBefore='\n')],
        accepted_digest='paid')
    operation = owner.extraction_operation_id(binding, 'entities')
    generation = owner.begin_publication('project', expected_generation=None, source_count=1, canonical_count=0)['generation']
    owner.stage_publication_sources('project', generation, [dict(source='source', material='material',
        representation='representation', recipe='recipe', operations=[operation], operation_count=1)])
    owner.activate_publication('project', generation, indexes={
        'keyword': dict(kind='native-keyword', store_id='keyword', recipe_digest='recipe'),
        'semantic': dict(kind='native-vector', store_id='vector', recipe_digest='recipe', space_id='space')})
    owner.close()
    return dict(projectId='project', semanticStore=dict(path=str(tmp_path / 'native'), project='project',
        generation=generation), sources=[source], target=dict(id='subject', type='source-scope', title='Company'),
        evidenceIds=[operation + ':mention:0'], outputDir=str(tmp_path), relay=dict(
            authorizationEnv='OPENAI_API_KEY', baseUrl='http://127.0.0.1:9999/v1/chat/completions',
            bindingId='binding:test', modelId='test/model', contextWindowTokens=10000,
            maxOutputTokens=1000, capability='knowledge.publication.generate', receipts='required'))


def test_explanation_reads_exact_native_source_ranges_and_persists_only_generated_sections(explanation, monkeypatch):
    seen = []
    def explain(context, relay):
        seen.append(context)
        return [ReportSection(title='Company', text='A supported explanation.',
            evidence_ids=explanation['evidenceIds'])], []
    monkeypatch.setattr(semantic_publication_builder, '_grounded_explanation', explain)
    result = semantic_worker._explain_evidence(explanation, None)
    assert seen == [dict(target=explanation['target'], entities=[], assertions=[], relations=[],
        evidence=[dict(id=explanation['evidenceIds'][0], quote='Acme\nCorp')])]
    from pathlib import Path
    payload = json.loads(Path(result['path']).read_text())
    assert payload['generation'] == explanation['semanticStore']['generation']
    assert payload['projectId'] == 'project' and payload['evidenceIds'] == explanation['evidenceIds']
    assert 'Acme' not in Path(result['path']).read_text()
    assert not any('snapshot' in key.lower() for key in payload)
    # The worker releases its store before returning, so a subsequent write can open it.
    owner = OxigraphStore(explanation['semanticStore']['path'])
    owner.close()


@pytest.mark.parametrize('mutation', ['project', 'generation', 'source', 'material', 'representation',
    'foreign_evidence', 'entity_instead_of_span', 'duplicate_evidence', 'duplicate_source', 'stale_installation'])
def test_explanation_rejects_wrong_binding_before_model_call(explanation, monkeypatch, mutation):
    monkeypatch.setattr(semantic_publication_builder, '_grounded_explanation',
        lambda *args: pytest.fail('must reject before model call'))
    if mutation == 'project':
        explanation['projectId'] = 'other'
    elif mutation == 'generation':
        explanation['semanticStore']['generation'] = 'stale'
    elif mutation in {'source', 'material', 'representation'}:
        field = dict(source='sourceId', material='materialRevision', representation='representationRevision')[mutation]
        explanation['sources'][0][field] = 'other'
    elif mutation == 'foreign_evidence':
        explanation['evidenceIds'] = ['urn:foreign']
    elif mutation == 'entity_instead_of_span':
        owner = OxigraphStore(explanation['semanticStore']['path'])
        explanation['evidenceIds'] = [next(q.subject.value for q in owner.store
            if q.predicate.value == 'urn:semantica:field:name')]
        owner.close()
    elif mutation == 'duplicate_evidence':
        explanation['evidenceIds'] *= 2
    elif mutation == 'duplicate_source':
        explanation['sources'] *= 2
    else:
        explanation['sources'][0]['artifact']['installation']['identity'] = '0:0:0:0:0'
    with pytest.raises((ValueError, RuntimeError)):
        semantic_worker._explain_evidence(explanation, None)


def test_explanation_rejects_snapshot_transport_and_unbounded_selection(explanation):
    for extra in ('snapshotPath', 'snapshotDigest', 'snapshotId'):
        with pytest.raises(ValidationError):
            semantic_worker.EvidenceExplanationRequest.model_validate(dict(explanation, **{extra: 'obsolete'}))
    for field in ('sources', 'evidenceIds'):
        with pytest.raises(ValidationError):
            semantic_worker.EvidenceExplanationRequest.model_validate(dict(explanation, **{field: explanation[field] * 33}))


def test_explanation_enforces_total_physical_read_budget_before_model(explanation, monkeypatch):
    from semantica import semantic_document_reader
    original = semantic_document_reader.read_document_reader
    def oversized(request):
        result = original(request)
        return dict(result, readBytes=262144)
    monkeypatch.setattr(semantic_document_reader, 'read_document_reader', oversized)
    monkeypatch.setattr(semantic_publication_builder, '_grounded_explanation',
        lambda *args: pytest.fail('oversized evidence must not call model'))
    with pytest.raises(semantic_worker.SemanticArtifactError, match='256KiB'):
        semantic_worker._explain_evidence(explanation, None)


def test_native_binding_lookup_rejects_missing_record_and_checks_generation(explanation):
    owner = OxigraphStore(explanation['semanticStore']['path'])
    try:
        generation = explanation['semanticStore']['generation']
        assert owner.read_record_binding('project', generation, explanation['evidenceIds'][0]) == dict(
            source='source', material='material', representation='representation')
        from semantica.utils.exceptions import ProcessingError
        with pytest.raises(ProcessingError, match='binding'):
            owner.read_record_binding('project', generation, 'urn:foreign')
        with pytest.raises(ProcessingError, match='stale'):
            owner.read_record_binding('project', 'stale', explanation['evidenceIds'][0])
    finally:
        owner.close()
