"""Evidence resolves original native scalars, including after native restart."""
import gc
from types import SimpleNamespace

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import TableData, TableCell

from semantica.semantic_source_artifact import _native_text, _native_grounding_ranges, _window_native_ranges
from semantica.semantic_extract.types import Entity
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.extraction_records import F
from semantica.utils.exceptions import ProcessingError
from semantica.semantic_artifact_schema import DocumentLocator


def test_native_locator_requires_an_exact_scalar_span_and_preserves_address():
    value = dict(representation_id='representation:1', origin='native', nativeRef='#/document/text', start_char=2, end_char=5,
                 quote='abc', quality='precise')
    locator = DocumentLocator.model_validate(value)
    assert locator.model_dump(by_alias=True)['nativeRef'] == '#/document/text'
    for invalid in [dict(value, nativeRef='window:2'), dict(value, start_char=None), dict(value, end_char=2)]:
        with pytest.raises(ValueError):
            DocumentLocator.model_validate(invalid)


def scalar(document, ref):
    value = {'document': document}
    for key in ref[2:].split('/'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


@pytest.mark.parametrize('document', [
    dict(format='text', text='Acme😀 Acme😀'),
    dict(format='pdf-text', pages=[dict(page_number=1, text='Acme😀'), dict(page_number=2, text='Acme😀')]),
    dict(format='epub', sections=[dict(text='Acme😀'), dict(text='Acme😀')]),
    dict(format='flat-odf', sections=[dict(text='Acme😀'), dict(text='Acme😀')]),
])
def test_structural_proof_uses_each_exact_native_scalar_without_find(document):
    text = _native_text(document)
    values = _native_grounding_ranges(document, text)
    for value in values:
        assert scalar(document, value['nativeRef'])[value['start']:value['end']] == text[value['windowStart']:value['windowEnd']]
    clipped = _window_native_ranges(values, 2, len(text) - 1)
    for value in clipped:
        assert scalar(document, value['nativeRef'])[value['start']:value['end']] == text[2:len(text) - 1][value['windowStart']:value['windowEnd']]


def test_real_docling_repeated_text_has_distinct_reader_addresses():
    doc = DoclingDocument(name='repeated')
    doc.add_text(label='text', text='Acme😀')
    doc.add_text(label='text', text='Acme😀')
    document = dict(format='docling', document=doc.export_to_dict())
    text = _native_text(document)
    values = _native_grounding_ranges(document, text)
    assert [v['nativeRef'] for v in values] == ['#/document/document/texts/0/text', '#/document/document/texts/1/text']
    assert values[1]['windowStart'] == 7
    assert values[1]['joinBefore'] == '\n\n'
    assert '\n\n'.join(scalar(document, v['nativeRef']) for v in values) == text
    # Starting a window inside a serializer separator does not claim that a
    # shortened separator belongs to the following source scalar.
    clipped = _window_native_ranges(values, 6, len(text))
    assert len(clipped) == 1 and 'joinBefore' not in clipped[0]


def bound(text):
    return dict(project='p', source='s', material='m', representation='r', recipe='recipe', model='model',
        specification='none', parser='parser', grounding='scalar-proof', window_start=0, window_end=len(text))


def test_cross_scalar_evidence_preserves_ranges_and_resume_without_quote(tmp_path):
    document = dict(format='pdf-text', pages=[dict(text='Acme😀'), dict(text='Engine')])
    text = _native_text(document)
    ranges = _native_grounding_ranges(document, text)
    entity = Entity(text, 'ORG', 0, len(text), .7, {'mention_id':'mention'})
    owner = OxigraphStore(tmp_path / 'facts')
    owner.adopt_extraction(bound(text), 'entities', [entity], text=text, native_ranges=ranges, accepted_digest='paid')
    facts = list(owner.store)
    assert not any(q.predicate.value == F + 'itemRef' for q in facts)
    assert any(q.predicate.value == F + 'nativeRef' and q.object.value == '#/document/pages/1/text' for q in facts)
    assert any(q.predicate.value == F + 'joinBefore' and q.object.value == '\n' for q in facts)
    # Entity name is a semantic field; no separate evidence quote/body is stored.
    assert not any(q.predicate.value in {F + 'quote', F + 'text', F + 'body'} for q in facts)
    owner.close()
    del owner
    gc.collect()
    owner = OxigraphStore(tmp_path / 'facts')
    assert owner.read_extraction(bound(text), 'entities', text=text, native_ranges=ranges) == [entity]
    changed = [{**ranges[0], 'nativeRef':'#/document/pages/99/text'}, ranges[1]]
    with pytest.raises(ProcessingError, match='grounding differs'):
        owner.read_extraction(bound(text), 'entities', text=text, native_ranges=changed)


def test_docling_native_table_cells_prove_evidence_without_formatted_body(tmp_path):
    doc = DoclingDocument(name='table')
    doc.add_table(data=TableData(num_rows=1, num_cols=2, table_cells=[
        TableCell(text='Acme', start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text='Engine', start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=1, end_col_offset_idx=2)]))
    document = dict(format='docling', document=doc.export_to_dict())
    text = _native_text(document)
    ranges = _native_grounding_ranges(document, text)
    assert text == 'Acme\n\nEngine'
    assert [r['nativeRef'] for r in ranges] == [
        '#/document/document/tables/0/data/table_cells/0/text',
        '#/document/document/tables/0/data/table_cells/1/text']
    entity = Entity('Acme', 'ORG', text.index('Acme'), text.index('Acme') + 4, .7, {'mention_id':'mention'})
    owner = OxigraphStore(tmp_path / 'facts')
    owner.adopt_extraction(bound(text), 'entities', [entity], text=text, native_ranges=ranges, accepted_digest='paid')
    owner.close()
    del owner
    gc.collect()
    owner = OxigraphStore(tmp_path / 'facts')
    assert owner.read_extraction(bound(text), 'entities', text=text, native_ranges=ranges) == [entity]


def test_docling_formula_and_long_scalar_share_reader_coordinates():
    from semantica.parse.document_reader import project_document_reader
    doc = DoclingDocument(name='formula')
    doc.add_text(label='formula', text='x = y')
    doc.add_text(label='text', text='A' * 17000)
    document = dict(format='docling', document=doc.export_to_dict())
    text = _native_text(document)
    assert text == 'x = y\n\n' + 'A' * 17000
    proof = _native_grounding_ranges(document, text)
    chunks = project_document_reader(document)['chunks']
    assert [(p['nativeRef'], p['start'], p['end']) for p in proof] == [
        (c['ref'], c['start'], c['end']) for c in chunks]
    assert 'joinBefore' not in proof[-1]
    for p in proof:
        assert scalar(document, p['nativeRef'])[p['start']:p['end']] == text[p['windowStart']:p['windowEnd']]


def test_rich_table_cell_fidelity_uses_child_scalar_not_mirror(tmp_path):
    from docling_core.types.doc.document import RichTableCell, RefItem
    from tests.artifact_helpers import native_parsed_fixture
    doc = DoclingDocument(name='rich')
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[]))
    child = doc.add_text(label='formula', text='a = b', parent=table)
    doc.add_table_cell(table, RichTableCell(text='UNUSED_MIRROR', ref=RefItem(cref=child.self_ref),
        start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1))
    document = dict(format='docling', document=doc.export_to_dict())
    text = _native_text(document)
    assert text == 'a = b'
    proof = _native_grounding_ranges(document, text)
    assert len(proof) == 1 and proof[0]['nativeRef'] == '#/document/document/texts/0/text'
    source = SimpleNamespace(file_path=str(tmp_path/'rich.txt'), source_id='rich',
        mime_type='text/plain', name='rich.txt')
    admitted = native_parsed_fixture(source, parsed=(text, document, 'native', '', 'docling', 'test'))
    cells = [loc for loc in admitted.locations if loc.get('cell')]
    assert len(cells) == 1
    assert text[cells[0]['start']:cells[0]['end']] == 'a = b'


def test_unproven_whitespace_gap_is_rejected(tmp_path):
    text = 'Acme\nEngine'
    ranges = [dict(nativeRef='#/document/text', start=0, end=4, windowStart=0, windowEnd=4),
              dict(nativeRef='#/document/text', start=5, end=11, windowStart=5, windowEnd=11)]
    owner = OxigraphStore(tmp_path / 'facts')
    with pytest.raises(ProcessingError, match='unproven serializer'):
        owner.adopt_extraction(bound(text), 'entities', [Entity(text, 'ORG', 0, len(text), .7, {'mention_id':'m'})],
            text=text, native_ranges=ranges, accepted_digest='paid')
