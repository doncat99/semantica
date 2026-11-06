from tests.artifact_helpers import build_source_fixture
from tests.artifact_helpers import extract_source, native_docling_fixture, docling_fixture_text
from tests.artifact_helpers import native_parsed_fixture
"""Structural citations remain queryable evidence in the existing fact contract."""
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as pipeline
from semantica.semantic_artifact_schema import SourceBuildInput
from semantica.source import source_content_revision
from semantica.utils.exceptions import ProcessingError


def document():
    return {'format': 'docling', 'document': native_docling_fixture({
        'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}, {'$ref': '#/texts/1'}]},
        'texts': [
            {'self_ref': '#/texts/0', 'label': 'text', 'text': 'F = ma', 'prov': [{'page_no': 2}]},
            {'self_ref': '#/texts/1', 'label': 'text', 'text': 'For constant mass.', 'prov': [{'page_no': 3}]}],
        'tables': [{'self_ref': '#/tables/0', 'label': 'table', 'prov': [{'page_no': 2}],
                    'data': {'table_cells': [
                        {'text': 'Variable unit', 'start_row_offset_idx': 0, 'start_col_offset_idx': 0,
                         'end_col_offset_idx': 2, 'col_span': 2, 'column_header': True},
                        {'text': 'm', 'start_row_offset_idx': 1, 'start_col_offset_idx': 0, 'row_header': True},
                        {'text': 'kg', 'start_row_offset_idx': 1, 'start_col_offset_idx': 1}]}}]})}


def result():
    return {'entities': [
        {'id': 'f', 'name': 'F', 'type': 'formula', 'occurrence': 0},
        {'id': 'm', 'name': 'm', 'type': 'variable', 'occurrence': 0}],
        'relations': [{'subject': 'f', 'object': 'm', 'predicate': 'uses_variable',
                       'evidence': 'F = ma', 'evidence_occurrence': 0,
                       'qualifiers': {'polarity': 'positive', 'unit': 'kg', 'condition': 'constant mass'},
                       'supporting_refs': ['#/tables/0/r0:c0', '#/tables/0/r1:c0', '#/tables/0/r1:c1', '#/texts/1']}]}


def test_formula_binding_persists_all_locators_headers_and_conditions(tmp_path):
    text = docling_fixture_text(document())
    path = tmp_path / 'source.txt'
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId='source-1', name=path.name,
        materialRevision=source_content_revision(path), mimeType='text/plain')
    parsed = (text, document(), 'native', source.material_revision, 'docling', 'test')
    built = build_source_fixture(source, False, result(), parsed)
    assertion, relation = built['assertions'][0], built['relations'][0]
    assert assertion.evidence_ids == relation.evidence_ids == assertion.support_ids
    spans = {item.id: item for item in built['evidence']}
    supports = [spans[ref] for ref in assertion.support_ids]
    assert [item.quote for item in supports] == ['F = ma', 'Variable unit', 'm', 'kg', 'For constant mass.']
    assert supports[1].locator.cell == 'r0:c0'
    assert supports[1].metadata['structure']['col_span'] == 2
    assert supports[1].metadata['structure']['column_header'] is True
    assert supports[-1].locator.page == 3
    assert assertion.qualifiers == {'polarity': 'positive', 'unit': 'kg', 'condition': 'constant mass'}
    bad = result()
    bad['relations'][0]['supporting_refs'] = []
    with pytest.raises(ProcessingError, match='exact evidence substring'):
        build_source_fixture(source, False, bad, parsed)
    bad['relations'][0]['supporting_refs'] = ['invented']
    with pytest.raises(pipeline.SemanticArtifactError, match='supporting reference'):
        build_source_fixture(source, False, bad, parsed)


def indexed_document(tmp_path, doc):
    text = docling_fixture_text(doc)
    path = tmp_path / 'indexed-source.txt'
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId='indexed-source', name=path.name,
        materialRevision=source_content_revision(path), mimeType='text/plain')
    return native_parsed_fixture(source, parsed=(text, doc, 'native', source.material_revision, 'docling', 'test'))


def test_window_context_uses_page_and_not_repeated_short_cell_text(tmp_path):
    text = docling_fixture_text(document())
    admitted = indexed_document(tmp_path, document())
    locations = admitted.locations
    context = pipeline._window_grounding_context(locations, 0, 6)
    assert {item['ref'] for item in context} == {
        '#/texts/0', '#/tables/0/r0:c0', '#/tables/0/r1:c0', '#/tables/0/r1:c1'}
    cells = [item for item in context if item['cell']]
    assert len(cells) == 3
    assert all(text[item['start']:item['end']] == item['quote'] for item in cells)
    assert all(item['page'] == 2 and item['bbox'] is None for item in cells)
    from copy import deepcopy
    distant_doc = document()
    distant = deepcopy(distant_doc['document']['tables'][0])
    distant.update(self_ref='#/tables/1', prov=[{**distant['prov'][0], 'page_no':99}])
    distant_doc['document']['tables'].append(distant)
    distant_doc['document']['body']['children'].append({'$ref':'#/tables/1'})
    distant_source = indexed_document(tmp_path, distant_doc)
    assert not any(item['source_ref'] == '#/tables/1'
        for item in pipeline._window_grounding_context(distant_source.locations, 0, 6))
    referenced = document()
    referenced['document']['texts'][0].update(label='formula', references=[{'$ref':'#/texts/1'}])
    referenced_source = indexed_document(tmp_path, referenced)
    assert '#/texts/1' in {item['ref'] for item in pipeline._window_grounding_context(referenced_source.locations, 0, 6)}


def test_cell_scalar_does_not_guess_a_page_for_a_multipage_table(tmp_path):
    doc = document()
    table = doc['document']['tables'][0]
    table['prov'].append({**table['prov'][0], 'page_no': 3})
    text = docling_fixture_text(doc)
    admitted = indexed_document(tmp_path, doc)
    cells = [item for item in admitted.locations if item['cell']]
    assert len(cells) == 3
    assert all(item['page'] is None and item['bbox'] is None for item in cells)
    assert all(text[item['start']:item['end']] == item['quote'] for item in cells)
    context = pipeline._window_grounding_context(admitted.locations, cells[0]['start'], cells[0]['start']+1)
    assert {item['ref'] for item in context if item.get('table_id')} == {item['ref'] for item in cells}


def test_native_cache_restores_paid_context_plan_and_support_refs(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from tests.artifact_helpers import native_extraction_owner
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, ModelReceipt

    text = docling_fixture_text(document())
    path = tmp_path / "source.txt"
    path.write_text(text)
    calls = []
    def respond(stage, prompt):
        calls.append(stage)
        if stage == "entities":
            return {"entities": [{"text": "F", "label": "formula", "occurrence": 0,
                                  "confidence": 0.9, "attributes": {}},
                                 {"text": "m", "label": "variable", "occurrence": 0,
                                  "confidence": 0.9, "attributes": {}}]}
        return {"relations": [{"subject_id": "mention:0", "predicate": "uses_variable", "object_id": "mention:1",
            "evidence": "F = ma", "evidence_occurrence": 0, "confidence": 0.9,
            "qualifiers": {"polarity": "positive", "condition": "constant mass"},
            "supporting_refs": ["#/texts/1"]}]}
    stub_native_provider(monkeypatch, respond)
    receipt = ModelReceipt(id="receipt:embed", operation="embedding", provider="test", model="test",
        input_digest="sha256:" + "1" * 64, output_digest="sha256:" + "2" * 64)
    monkeypatch.setattr(pipeline, '_embed_texts', lambda *_: ([[0.1]], receipt))
    with native_extraction_owner(tmp_path / "native", text=text) as store:
        args = (text, SimpleNamespace(model_id='test'), None)
        first, _, _ = extract_source(*args, document=document())
        restored, _, _ = extract_source(*args, document=document())
        assert calls == ["entities", "relations"]
        assert first == restored
        assert restored['relations'][0]['supporting_refs'] == ['#/texts/1']
        changed = document()
        changed['document']['tables'][0]['data']['table_cells'][0]['column_header'] = False
        changed_source = indexed_document(tmp_path, changed)
        original_source = indexed_document(tmp_path, document())
        assert list(changed_source.locations) != list(original_source.locations)
        extract_source(*args, document=changed)
        # Changed structural grounding is a distinct actual extraction input.
        assert calls == ["entities", "relations", "entities", "relations"]


def test_real_sovereign_formula_annotations_survive_split_blocks(tmp_path):
    # Source excerpts: CFA Sustainable Investing 2026, physical page 431.
    # These are manually annotated expectations, not evidence of model accuracy.
    quotes = [
        'Attributed emissions = [ Exposure to sovereign bond (USD) ____________________________ PPP adjusted GDP (international USD) ] .',
        '× Sovereign Scope 1 emissions (tCO2e) .',
        'to be used for sovereign debt portfolios',
        'PPP = purchasing power parity.',
    ]
    text = '\n\n'.join(quotes)
    doc = {'format': 'docling', 'document': native_docling_fixture({
        'body': {'children': [{'$ref': f'#/texts/{i}'} for i in range(4)]},
        'texts': [{'self_ref': f'#/texts/{i}', 'text': quote,
                   'label': 'code' if i == 0 else 'text', 'prov': [{'page_no': 431}]}
                  for i, quote in enumerate(quotes)]})}
    names = ['Attributed emissions', 'Exposure to sovereign bond', 'PPP adjusted GDP',
             'Sovereign Scope 1 emissions', 'sovereign debt portfolios', 'PPP', 'purchasing power parity']
    entities = [{'id': str(i), 'name': name, 'type': 'formula' if i == 0 else 'variable',
                 'occurrence': 0} for i, name in enumerate(names)]
    relations = [{'subject': '0', 'object': str(i), 'predicate': 'has_operand',
        'evidence': quotes[0] if i < 3 else quotes[1], 'evidence_occurrence': 0,
        'qualifiers': {'polarity': 'positive', 'unit': unit, 'condition': quotes[2]},
        'supporting_refs': ['#/texts/0', '#/texts/1', '#/texts/2']}
        for i, unit in [(1, 'USD'), (2, 'international USD'), (3, 'tCO2e')]]
    relations.extend([
        {'subject': '0', 'object': '4', 'predicate': 'applies_to', 'evidence': quotes[2],
         'evidence_occurrence': 0, 'qualifiers': {'polarity': 'positive'}, 'supporting_refs': ['#/texts/0']},
        {'subject': '5', 'object': '6', 'predicate': 'means', 'evidence': quotes[3],
         'evidence_occurrence': 0, 'qualifiers': {'polarity': 'positive'}, 'supporting_refs': []},
    ])
    path = tmp_path / 'excerpt.txt'
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId='sovereign', name=path.name,
        materialRevision=source_content_revision(path), mimeType='text/plain')
    built = build_source_fixture(source, False, {'entities': entities, 'relations': relations},
        (text, doc, 'native', source.material_revision, 'docling', '2.135.0'))
    operands = [a for a in built['assertions'] if a.predicate == 'has_operand']
    assert {a.object: a.qualifiers['unit'] for a in operands} == dict(zip(names[1:4], ['USD', 'international USD', 'tCO2e']))
    assert {a.qualifiers['condition'] for a in operands} == {quotes[2]}
    assert all(a.status == 'candidate' for a in built['assertions'])
    evidence = {e.id: e for e in built['evidence']}
    assert all({evidence[ref].quote for ref in a.support_ids} >= set(quotes[:3]) for a in operands)
    assert all(evidence[ref].locator.page == 431 for a in operands for ref in a.support_ids)
