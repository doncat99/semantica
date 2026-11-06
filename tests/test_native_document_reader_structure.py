"""Production structural closure: original refs, address-only indexes, bounded reads."""
import json
import sqlite3
from pathlib import Path
from hashlib import sha256

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import TableData, TableCell, RichTableCell

from semantica.semantic_document_reader import write_reader_artifact, read_document_reader, DocumentReaderBudgetError
from tests.test_native_document_reader import request, payload


def fixture(tmp_path, unrelated=1500):
    native = DoclingDocument(name='structure')
    for _ in range(unrelated):
        native.add_text(label='text', text='unselected body ' * 30)
    caption = native.add_text(label='caption', text='Caption 😀')
    note = native.add_text(label='footnote', text='Footnote 漢')
    def cell(text, row, col, **kwargs):
        return TableCell(text=text, start_row_offset_idx=row, end_row_offset_idx=row+1,
            start_col_offset_idx=col, end_col_offset_idx=col+1, **kwargs)
    cells = [cell('Merged header', 0, 0, column_header=True),
        cell('Row header', 2, 0, row_header=True), cell('rich fallback is retained', 2, 1),
        cell('wrong column header', 0, 4, column_header=True),
        cell('wrong row header', 8, 0, row_header=True),
        cell('unselected huge cell ' * 20000, 9, 4)]
    cells[0].end_col_offset_idx = 3
    cells[0].col_span = 3
    table = native.add_table(data=TableData(num_rows=10, num_cols=5, table_cells=cells), caption=caption)
    table.footnotes.append(note.get_ref())
    rich = native.add_text(label='text', text='Rich 😀\\"\n', parent=table)
    table.data.table_cells[2] = RichTableCell(**cells[2].model_dump(), ref=rich.get_ref())
    picture = native.add_picture()
    ocr = native.add_text(label='text', text='OCR 🧪', parent=picture)
    path = tmp_path / 'structure.json'
    digests = write_reader_artifact(path, payload({'format':'docling', 'document':native.export_to_dict(), 'pages':[]}))
    return path, digests, native, table, caption, note, rich, picture, ocr


def structure(path, digests, roots, **bounds):
    selection = dict(roots=roots, **bounds)
    selection.setdefault('maxBytes', 256*1024)
    return read_document_reader(request(path, digests, 'structure', **selection))


def test_structure_selects_span_headers_and_native_dependencies_without_siblings(tmp_path):
    path, digests, native, table, caption, note, rich, picture, ocr = fixture(tmp_path)
    root = table.self_ref + '/data/table_cells/2'
    result = structure(path, digests, [root, ocr.self_ref])
    closure = result['structure']
    assert set(closure['cells']) == {table.self_ref + '/data/table_cells/' + str(i) for i in (0,1,2)}
    assert set(closure['nodes']) == {caption.self_ref, note.self_ref, rich.self_ref, ocr.self_ref}
    assert set(closure['containers']) == {table.self_ref, picture.self_ref}
    assert closure['cells'][root] == table.data.table_cells[2].model_dump(mode='json', by_alias=True, exclude_none=True)
    assert closure['cells'][table.self_ref + '/data/table_cells/0']['col_span'] == 3
    assert closure['nodes'][rich.self_ref]['text'] == rich.text
    assert closure['nodes'][ocr.self_ref]['parent']['$ref'] == picture.self_ref
    assert closure['containers'][table.self_ref]['data'] == {'num_rows':10, 'num_cols':5}
    assert result['readBytes'] < 16000 < path.stat().st_size // 20
    assert result['objectsRead'] <= 64 and result['nextCursor'] is None
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        assert [row[1] for row in db.execute('PRAGMA table_info(native_addresses)')] == ['ref','offset','length','digest']


def test_caption_parent_back_reference_is_not_a_dependency_cycle(tmp_path):
    path, digests, native, table, caption, note, rich, picture, ocr = fixture(tmp_path, 0)
    caption.parent = table.get_ref()
    digests = write_reader_artifact(path, payload({'format':'docling', 'document':native.export_to_dict(), 'pages':[]}))
    result = structure(path, digests, [caption.self_ref])
    assert result['structure']['nodes'][caption.self_ref]['text'] == caption.text
    assert result['structure']['containers'][table.self_ref]['captions'][0]['$ref'] == caption.self_ref


def test_real_dependency_cycle_in_index_fails_closed(tmp_path):
    native = DoclingDocument(name='cycle-index')
    parent = native.add_text(label='text', text='parent')
    child = native.add_text(label='text', text='child', parent=parent)
    path = tmp_path / 'cycle.json'
    digests = write_reader_artifact(path, payload({'format':'docling', 'document':native.export_to_dict(), 'pages':[]}))
    index = path.with_suffix('.reader.sqlite')
    forged = parent.model_dump(mode='json', by_alias=True, exclude_none=True)
    forged['children'] = [{'$ref': parent.self_ref}]
    raw = json.dumps(forged, ensure_ascii=False, separators=(',', ':')).encode()
    with path.open('ab') as stream:
        offset = stream.tell()
        stream.write(raw)
    with sqlite3.connect(index) as db:
        db.execute('UPDATE native_addresses SET offset=?,length=?,digest=? WHERE ref=?',
            (offset, len(raw), sha256(raw).digest(), parent.self_ref))
    with pytest.raises(ValueError, match='cycle'):
        structure(path, digests, [parent.self_ref])


def test_structure_never_silently_truncates_and_rejects_missing_and_cycles(tmp_path):
    path, digests, native, table, caption, note, rich, picture, ocr = fixture(tmp_path, 0)
    root = table.self_ref + '/data/table_cells/2'
    for bounds in ({'maxObjects':2}, {'maxBytes':32}, {'maxDepth':0}):
        with pytest.raises(DocumentReaderBudgetError):
            structure(path, digests, [root], **bounds)
    with pytest.raises(DocumentReaderBudgetError):
        structure(path, digests, [table.self_ref + '/data/table_cells/5'])
    index = path.with_suffix('.reader.sqlite')
    with sqlite3.connect(index) as db:
        db.execute('DELETE FROM native_addresses WHERE ref=?', (note.self_ref,))
    # The request helper binds the changed installation identity after index corruption.
    with pytest.raises(ValueError, match='missing'):
        structure(path, digests, [root])
