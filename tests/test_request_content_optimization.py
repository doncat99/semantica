"""Model request economy must preserve source support and cached paid results."""
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from semantica import semantic_artifact_builder as b


def block(ref, page, start=None, **fields):
    return dict(ref=ref, page=page, start=start, end=start + 10 if start is not None else None,
                quote=ref, structure={}, **fields)


def test_context_uses_current_pages_and_explicit_table_dependencies_not_adjacent_pages():
    rows = [block('body', 2, 100), block('unrelated', 1, 0),
            block('cell', 2, table_id='t', cell='r1:c1'),
            block('header', 1, table_id='t', cell='r0:c1'),
            block('other-table', 1, table_id='other', cell='r0:c0'), block('note', 4)]
    rows[2]['structure'] = {'footnotes': [{'$ref': 'note'}]}
    assert {r['ref'] for r in b._window_grounding_context(rows, 100, 110)} == {'body', 'cell', 'header', 'note'}


def test_id_only_citation_is_rehydrated_but_wrong_or_unknown_quote_is_rejected():
    context = {'evidence': [{'id': 'e1', 'quote': 'Canonical full evidence'}]}
    result = b._SemanticCitation.model_validate({'evidence_id': 'e1'}, context=context)
    assert result.quote == 'Canonical full evidence'
    for value in ({'evidence_id': 'unknown'}, {'evidence_id': 'e1', 'quote': 'invented'}):
        with pytest.raises(ValidationError):
            b._SemanticCitation.model_validate(value, context=context)
    assert 'quote' not in b._SemanticCitation.model_json_schema()['properties']


def test_product_typed_output_sends_schema_on_first_request(monkeypatch):
    from semantica.semantic_artifact_schema import ModelReceipt
    requests = []
    def relay(_relay, payload, operation):
        requests.append(payload)
        return {'model': 'test', 'choices': [{'message': {'content': '{"assignments":[]}'}}]}, ModelReceipt(
            id='receipt:test', operation=operation, provider='test', model='test', input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64)
    monkeypatch.setattr(b, '_relay_json', relay)
    provider = b._ProjectModelProvider(SimpleNamespace(model_id='test', max_output_tokens=100), 'source_classification')
    provider.generate_typed('Return JSON', b._ClassificationOutput, validation_context={})
    assert len(requests) == 1
    fmt = requests[0]['response_format']
    assert fmt['type'] == 'json_schema'
    assert fmt['json_schema']['schema'] == b._ClassificationOutput.model_json_schema()
    assert fmt['json_schema']['strict'] is False  # open qualifier dictionaries are validated locally


def test_extraction_uses_only_current_context(monkeypatch):
    rows = [block('a', 2, 100), block('unrelated', 1), block('c', 2)]
    narrow = [rows[0], rows[2]]
    monkeypatch.setattr(b, '_window_grounding_context', lambda *args: narrow)
    monkeypatch.setattr(b, '_extraction_context_batches', lambda window, context: [context])
    calls = []
    def extract(text, relay, spec, item, context):
        calls.append(context)
        return {'entities': [], 'relations': []}, [], False
    monkeypatch.setattr(b, '_extract_window_context', extract)
    result = b._extract_window('body', None, None, rows, (100, 110, 'body'))
    assert calls == [narrow]
    assert result[2] is False


def test_report_unknown_targets_fail_before_any_model_call():
    with pytest.raises(b.SemanticArtifactError, match='distinct known IDs'):
        b._explanation_reports('p', [], [], [], [], [], [], [], None, ['unknown'])
