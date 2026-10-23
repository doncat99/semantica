from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from semantica import semantic_artifact_builder as builder
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_extract import grounded_window
from semantica.semantic_worker import _response
from semantica.utils.exceptions import ProcessingError


def test_local_relation_output_failure_keeps_entities(monkeypatch):
    from semantica.semantic_artifact_errors import ModelOutputError
    entity = object()
    monkeypatch.setattr(grounded_window, 'extract_entities_llm', lambda *a, **k: [entity])

    def fail(*args, **kwargs):
        raise ProcessingError('invalid relation output') from ModelOutputError('invalid', code='MODEL_OUTPUT_SCHEMA_INVALID')

    monkeypatch.setattr(grounded_window, 'extract_relations_llm', fail)
    provider = SimpleNamespace(rejections=[], receipts=[SimpleNamespace(metadata={})])
    entities, relations, _ = grounded_window.extract_grounded_window('source', model='test', provider_instance=provider)
    assert entities == [entity]
    assert relations == []
    assert provider.receipts[0].metadata['rejected_candidates'][0]['code'] == 'MODEL_OUTPUT_SCHEMA_INVALID'
    assert provider.rejections[0]['stage'] == 'relations'


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


def test_warning_page_mapping_ignores_locations_without_offsets(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(builder, '_text_windows', lambda _text: [(0, 2, 'ab')])
    monkeypatch.setattr(builder, '_docling_locations', lambda *_args: [
        {'page': 2, 'start': None, 'end': None},
        {'page': 3, 'start': 0, 'end': 2},
    ])
    def extract(*_args, **_kwargs):
        receipt = SimpleNamespace(metadata={'rejected_candidates': [
            {'code': 'MODEL_OUTPUT_EMPTY', 'stage': 'entities', 'action': 'skipped_extraction', 'diagnostic': {}}
        ]})
        return ({'entities': [], 'relations': []}, [receipt], False)
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    request = SimpleNamespace(parallelism=1, relays={'model': None, 'embedding': None}, recipe=SimpleNamespace(extraction_spec=None))
    events = []
    builder._extract_project_sources([(SimpleNamespace(source_id='source'), False, ('ab', {}))], request, events.append)
    warnings = [event['metadata']['warning'] for event in events if event['metadata'].get('warning')]
    assert warnings[0]['pages'] == [3]
