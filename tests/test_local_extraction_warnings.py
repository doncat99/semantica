from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_extract import grounded_window
from semantica.semantic_worker import _response
from semantica.utils.exceptions import ProcessingError


def test_local_relation_output_failure_propagates_typed_failure(monkeypatch):
    from semantica.semantic_artifact_errors import ModelOutputError
    entity = object()
    monkeypatch.setattr(grounded_window, 'extract_entities_llm', lambda *a, **k: [entity])

    def fail(*args, **kwargs):
        raise ProcessingError('invalid relation output') from ModelOutputError('invalid', code='MODEL_OUTPUT_SCHEMA_INVALID')

    monkeypatch.setattr(grounded_window, 'extract_relations_llm', fail)
    provider = SimpleNamespace(rejections=[], receipts=[SimpleNamespace(metadata={})])
    with pytest.raises(ProcessingError) as raised:
        grounded_window.extract_grounded_window('source', model='test', provider_instance=provider)
    assert isinstance(raised.value.__cause__, ModelOutputError)
    assert raised.value.__cause__.code == 'MODEL_OUTPUT_SCHEMA_INVALID'
    assert provider.receipts[0].metadata['rejected_count'] == 1
    assert provider.rejections[0]['stage'] == 'relations'
    assert provider.rejections[0]['action'] == 'failed_extraction'


def test_transport_failure_is_not_discarded(monkeypatch):
    def fail(*args, **kwargs):
        raise ProcessingError('offline') from builder.SemanticArtifactError('offline', retryable=True)
    monkeypatch.setattr(grounded_window, 'extract_entities_llm', fail)
    with pytest.raises(ProcessingError):
        grounded_window.extract_grounded_window('source', model='test', provider_instance=SimpleNamespace())


def test_parallel_context_does_not_hide_causal_validation():
    try:
        SemanticArtifactBuildRequest.model_validate({'privateDocumentText': 'confidential'})
    except ValidationError as cause:
        try:
            raise builder.SemanticArtifactError('failed', diagnostic={'parallelTask': {'taskId': '47'}}) from cause
        except builder.SemanticArtifactError as error:
            result = _response('request', False, error=error)['error']['diagnostic']
    assert result['parallelTask']['taskId'] == '47'
    assert result['validationErrorCount'] > 0
    assert 'confidential' not in str(result)
    assert 'privateDocumentText' not in str(result)


def test_all_malformed_relations_are_discarded_when_rejecting_candidates():
    from types import SimpleNamespace
    from semantica.semantic_extract.methods import _parse_grounded_relation_result

    result = _parse_grounded_relation_result(
        SimpleNamespace(relations=[object()]), [], 'source', 'bifrost', 'model',
        reject_invalid=True, rejections=[],
    )
    assert result == []


def test_warning_page_mapping_ignores_locations_without_offsets(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests.artifact_helpers import native_docling_fixture, native_parsed_fixture, docling_fixture_text
    from semantica.semantic_artifact_schema import RecipeRef, DocumentProcessingProfile
    document = dict(format='docling', document=native_docling_fixture({
        'body':{'children':[{'$ref':'#/texts/0'}, {'$ref':'#/tables/0'}]},
        'texts':[{'self_ref':'#/texts/0','label':'text','text':'ab','prov':[{'page_no':3}]}, {'self_ref':'#/texts/1','label':'text','text':'note','prov':[{'page_no':2}]}],
        'tables':[{'self_ref':'#/tables/0','label':'table','footnotes':[{'$ref':'#/texts/1'}], 'data':{'table_cells':[{'text':'',
            'start_row_offset_idx':0,'start_col_offset_idx':0}]}}]}))
    source = SimpleNamespace(source_id='source',file_path=str(tmp_path/'source.txt'), name='source.txt',mime_type='text/plain')
    parsed = native_parsed_fixture(source, parsed=(docling_fixture_text(document),document,'native','','docling','test'))
    assert any(item['page'] == 2 and item['start'] is None for item in parsed.locations)
    def extract(*_args, **_kwargs):
        receipt = SimpleNamespace(metadata={'rejected_count': 1})
        return ({'entities': [], 'relations': []}, [receipt], False)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    model = SimpleNamespace(binding_id=None, context_window_tokens=500000, max_output_tokens=32768)
    request = SimpleNamespace(parallelism=1, project_id='p', relays={'model': model, 'embedding': None},
        document_processing=DocumentProcessingProfile(mode='local'), recipe=RecipeRef(id='recipe:test',version='1'),
        parsed_sources=[SimpleNamespace(source_id='source',representation_revision=parsed.document['representation_revision'])])
    events = []
    builder._extract_project_sources([(source, False, parsed)], request, events.append)
    warnings = [event['metadata']['warning'] for event in events if event['metadata'].get('warning')]
    assert warnings[0]['pages'] == [3]
