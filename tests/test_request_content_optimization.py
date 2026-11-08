"""Model request economy must preserve source support and cached paid results."""
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from semantica import semantic_publication_builder as b


def test_context_uses_current_pages_and_explicit_table_dependencies_not_adjacent_pages(tmp_path):
    from tests.artifact_helpers import native_docling_fixture, native_parsed_fixture, docling_fixture_text
    raw = native_docling_fixture({'body': {'children': [{'$ref':'#/texts/0'}, {'$ref':'#/tables/0'}, {'$ref':'#/tables/1'}, {'$ref':'#/texts/2'}]},
        'texts': [{'self_ref':'#/texts/0','label':'text','text':'body', 'prov':[{'page_no':2}]}, {'self_ref':'#/texts/1','label':'text','text':'note', 'prov':[{'page_no':4}]},
                  {'self_ref':'#/texts/2','label':'text','text':'unrelated', 'prov':[{'page_no':1}]}, {'self_ref':'#/texts/3','parent':{'$ref':'#/tables/0'},'label':'text','text':'header','prov':[{'page_no':1}]},
                  {'self_ref':'#/texts/4','parent':{'$ref':'#/tables/0'},'label':'text','text':'cell','prov':[{'page_no':2}]}],
        'tables': [{'self_ref':'#/tables/0','label':'table','children':[{'$ref':'#/texts/3'}, {'$ref':'#/texts/4'}],'prov':[{'page_no':2}, {'page_no':1}], 'footnotes':[{'$ref':'#/texts/1'}],
            'data':{'table_cells':[{'text':'header','ref':{'$ref':'#/texts/3'},'start_row_offset_idx':0,'start_col_offset_idx':0},
                                  {'text':'cell','ref':{'$ref':'#/texts/4'},'start_row_offset_idx':1,'start_col_offset_idx':0}]}},
            {'self_ref':'#/tables/1','label':'table','prov':[{'page_no':1}], 'data':{'table_cells':[{'text':'other-table',
                'start_row_offset_idx':0,'start_col_offset_idx':0}]}}]})
    # The body belongs to the first table's page; the table crosses page 1/2.
    document = dict(format='docling', document=raw)
    text = docling_fixture_text(document)
    source = SimpleNamespace(file_path=str(tmp_path/'source.txt'), source_id='source', name='source.txt', mime_type='text/plain')
    admitted = native_parsed_fixture(source, parsed=(text, document, 'native', '', 'docling', 'test'))
    refs = {r['ref'] for r in b._window_grounding_context(admitted.locations, 0, 4)}
    assert refs == {'#/texts/0', '#/texts/3/r0:c0/texts/3', '#/texts/4/r1:c0/texts/4', '#/texts/4', '#/texts/1'}


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
    def relay(_relay, payload, operation, *, business_context):
        requests.append(payload)
        assert business_context == {}
        return {'model': 'test', 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"assignments":[]}'}}]}, ModelReceipt(
            id='receipt:test', operation=operation, provider='test', model='test', input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64)
    monkeypatch.setattr(b, '_relay_json', relay)
    provider = b._ProjectModelProvider(SimpleNamespace(model_id='test', context_window_tokens=8192, max_output_tokens=100), 'source_classification')
    provider.generate_typed('Return JSON', b._ClassificationOutput, validation_context={})
    assert len(requests) == 1
    fmt = requests[0]['response_format']
    assert fmt == {'type': 'json_object'}
    schema_text = requests[0]['messages'][0]['content'].split('Return one JSON object matching this JSON Schema:\n', 1)[1]
    assert json.loads(schema_text) == b._ClassificationOutput.model_json_schema()


def test_extraction_uses_only_current_context(tmp_path, monkeypatch):
    from tests.artifact_helpers import native_docling_fixture, native_parsed_fixture, docling_fixture_text
    document = dict(format='docling', document=native_docling_fixture({
        'body': {'children': [{'$ref':f'#/texts/{i}'} for i in range(3)]},
        'texts': [dict(self_ref=f'#/texts/{i}', label='text', text=quote, prov=[{'page_no':page}])
            for i, (quote, page) in enumerate([('body', 2), ('unrelated', 1), ('context', 2)])]}))
    source = SimpleNamespace(file_path=str(tmp_path/'source.txt'), source_id='source', name='source.txt', mime_type='text/plain')
    admitted = native_parsed_fixture(source, parsed=(docling_fixture_text(document), document, 'native', '', 'docling', 'test'))
    calls = []
    def extract(text, relay, spec, item, context, formula_semantics, **kwargs):
        calls.append(context)
        return {'entities': [], 'relations': []}, [], False
    monkeypatch.setattr(b, '_extract_window_context', extract)
    model = SimpleNamespace(context_window_tokens=8192, max_output_tokens=100)
    result = b._extract_window(admitted.text, model, None, admitted.locations, (0, 4, 'body'))
    assert len(calls) == 1
    assert {item['quote'] for item in calls[0]} == {'body', 'context'}
    assert result[2] is False


def test_report_unknown_targets_fail_before_any_model_call():
    with pytest.raises(b.SemanticArtifactError, match='distinct known IDs'):
        b._explanation_reports('p', [], [], [], [], [], [], [], None, ['unknown'])
