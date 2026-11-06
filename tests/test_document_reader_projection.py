"""Reader publication stores addresses, not another serialization of content."""
import json
import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem, TableData, TableCell
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size

from semantica.parse.document_reader import project_document_reader, SCALAR_SEGMENT


@pytest.mark.parametrize('format', ['text', 'pdf-text'])
def test_unicode_ranges_reference_unique_native_scalar_without_copying(format):
    text = 'A😀漢\\"\n' * 10000
    document = {'format': format, 'text': text} if format == 'text' else {
        'format': format, 'pages': [{'page_number': 7, 'text': text}]}
    result = project_document_reader(document)
    assert text not in json.dumps(result, ensure_ascii=False)
    assert all('text' not in item for item in result['chunks'])
    assert ''.join(text[item['start']:item['end']] for item in result['chunks']) == text
    assert all(item['end'] - item['start'] <= SCALAR_SEGMENT for item in result['chunks'])
    assert all(item['locator']['coordinateSpace'] == 'native-scalar' for item in result['chunks'])


def native_document():
    doc = DoclingDocument(name='source')
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    def prov(start, end):
        return ProvenanceItem(page_no=1, charspan=(start, end),
            bbox=BoundingBox(l=10, t=20, r=210, b=40, coord_origin=CoordOrigin.TOPLEFT))
    doc.add_text(label='text', text='Before', prov=prov(0, 6))
    doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[
        TableCell(text='Metric', start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=1)]), prov=prov(0, 0))
    doc.add_text(label='text', text='A😀B', prov=prov(1, 2))
    return doc


def test_native_order_and_table_cells_are_references_not_custom_table_formatting():
    result = project_document_reader({'format': 'docling', 'document': native_document().export_to_dict()})
    chunks = result['chunks']
    assert [item['locator']['doclingRefs'] for item in chunks] == [['#/texts/0'], ['#/tables/0'], ['#/texts/1']]
    assert chunks[1]['locator']['tableCell']['rowStart'] == 0
    assert chunks[1]['locator']['locationState'] == 'coarse'
    assert 'Metric' not in json.dumps(result)
    # Missing cell boxes cannot become guessed table-wide overlays.
    assert len(result['pages']) == 2
    assert result['pages'][1]['start'] == 1 and result['pages'][1]['end'] == 2


def test_invalid_provenance_remains_explicit_without_hiding_native_content():
    doc = DoclingDocument(name='source')
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    doc.add_text(label='text', text='short', prov=ProvenanceItem(page_no=1,
        charspan=(0, 20), bbox=BoundingBox(l=1, t=1, r=10, b=10)))
    result = project_document_reader({'format': 'docling', 'document': doc.export_to_dict()})
    assert result['pages'][0]['state'] == 'invalid_layout'
    assert result['chunks'][0]['locator']['locationState'] == 'invalid'
    assert result['chunks'][0]['end'] == 5


def test_reader_does_not_accept_transient_extraction_text_as_native_content():
    with pytest.raises(KeyError, match='text'):
        project_document_reader({'format': 'text'})
