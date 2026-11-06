"""Search offsets must come from the canonical native serialization."""
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem, TableData, TableCell
from docling_core.types.doc.base import BoundingBox
import pytest
from types import SimpleNamespace

from semantica.semantic_publication_builder import _located_document_fields, _structural_evidence
from semantica.semantic_source_artifact import _native_text, _native_grounding_ranges
from semantica.semantic_artifact_errors import SemanticArtifactError
from tests.artifact_helpers import native_parsed_fixture


def admitted_document(tmp_path, document):
    text = _native_text(document)
    source = SimpleNamespace(file_path=str(tmp_path/'source.txt'), source_id='source',
        mime_type='text/plain', name='source.txt')
    return native_parsed_fixture(source, parsed=(text, document, 'native', '', 'docling', 'test'))


def provenance(page, start, end):
    return ProvenanceItem(page_no=page, charspan=(start, end),
                          bbox=BoundingBox(l=1, t=1, r=10, b=10))


def test_native_table_serialization_and_multipage_charspans(tmp_path):
    doc = DoclingDocument(name='source')
    doc.add_text(label='text', text='Repeated', prov=provenance(1, 0, 8))
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[
        TableCell(text='ESG ESG', start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=1)]), prov=provenance(2, 0, 0))
    doc.add_group(name='table cell structure', parent=table)
    item = doc.add_text(label='text', text='Governance ESG report', prov=provenance(3, 0, 10))
    item.prov.append(provenance(4, 11, 21))
    doc.add_text(label='text', text='Repeated', prov=provenance(5, 0, 8))
    document = {'format': 'docling', 'document': doc.export_to_dict()}
    text = _native_text(document)
    admitted = admitted_document(tmp_path, document)
    locations = admitted.locations
    # Native scalar addresses establish cell offsets without formatted tables.
    # A single table provenance establishes the page, never a whole-table box.
    for offset in (text.index('ESG'), text.index('ESG') + 4):
        fields, _ = _located_document_fields(locations, offset, offset + 3)
        assert fields['page'] == 2
        assert 'bbox' not in fields
    for offset, page in [(text.rindex('ESG'), 4), (text.rindex('Repeated'), 5)]:
        fields, _ = _located_document_fields(locations, offset, offset + 3)
        assert fields['page'] == page
    assert all(text[x['start']:x['end']] == x['quote'] for x in locations if x['start'] is not None)
    # Paid extraction cites the whole native item, not the per-page range suffix.
    whole = next(x for x in locations if x['ref'] == item.self_ref)
    evidence = _structural_evidence(whole, 'representation:test', 'native')
    assert evidence.quote == item.text
    assert text[evidence.locator.start_char:evidence.locator.end_char] == item.text
    assert evidence.locator.page is None
    with pytest.raises(SemanticArtifactError, match='differs'):
        _native_grounding_ranges(document, text + 'changed')


@pytest.mark.parametrize('start,end,expected_page', [(6, 11, 2), (10, 11, None)])
def test_native_charspan_clips_to_scalar_or_stays_unknown_without_losing_other_locations(tmp_path, start, end, expected_page):
    doc = DoclingDocument(name='source')
    item = doc.add_text(label='text', text='First ESG', prov=provenance(1, 0, 5))
    item.prov.append(provenance(2, start, end))  # Partially or wholly beyond the native scalar.
    doc.add_text(label='text', text='Other ESG', prov=provenance(3, 0, 9))
    document = {'format': 'docling', 'document': doc.export_to_dict()}
    text = _native_text(document)
    admitted = admitted_document(tmp_path, document)
    locations = admitted.locations
    fields, _ = _located_document_fields(locations, text.index('ESG'), text.index('ESG') + 3)
    assert fields.get('page') == expected_page
    fields, _ = _located_document_fields(locations, text.rindex('ESG'), text.rindex('ESG') + 3)
    assert fields['page'] == 3
