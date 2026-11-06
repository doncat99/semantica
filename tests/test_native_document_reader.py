"""Production native reader: range fidelity, restart, no body index and bounds."""
import json
import sqlite3
import subprocess
import sys
import tracemalloc
from pathlib import Path
from threading import Event

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import BoundingBox, Size, CoordOrigin
from docling_core.types.doc.document import TableData, TableCell, RichTableCell, ProvenanceItem, RefItem

from semantica.semantic_document_reader import write_reader_artifact, read_document_reader, DocumentReaderBudgetError
from semantica.semantic_query_schema import DocumentReaderRequest


def request(path, digests, field='chunks', **selection):
    def ref(file, digest, kind):
        stat = file.stat()
        return dict(path=str(file), digest=digest, kind=kind, mediaType='application/json',
            installation=dict(digest=digest, identity=':'.join(map(str, (stat.st_dev, stat.st_ino,
                stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))))
    selected = dict(field=field, maxBytes=256*1024)
    selected.update(selection)
    return DocumentReaderRequest.model_validate(dict(id='reader:r', sourceId='source:authorized',
        materialRevision='material:m', representationRevision='representation:r',
        artifact=ref(path, digests[0], 'document-representation'),
        readerIndex=ref(path.with_suffix('.reader.sqlite'), digests[1], 'document-reader-index'),
        selection=selected))


def payload(document):
    return {'protocol': 'semantica.parsed-source.v3', 'materialRevision': 'material:m',
        'document': {**document, 'representation_revision': 'representation:r'}}


def test_exact_native_ranges_reuse_scalar_owner_and_keep_unicode_offsets(tmp_path):
    path = tmp_path / 'ranges.json'
    text = 'before😀漢' + 'value' * 4000
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': text}))
    selected = [{'nativeRef': '#/document/text', 'start': 6, 'end': 10},
        {'nativeRef': '#/document/text', 'start': 16380, 'end': 16390}]
    result = read_document_reader(request(path, digests, 'ranges', ranges=selected))
    assert [item['text'] for item in result['items']] == [text[6:10], text[16380:16390]]
    assert [item['locator'] for item in result['items']] == [
        {'nativeRef': item['nativeRef'], 'startChar': item['start'], 'endChar': item['end'],
         'coordinateSpace': 'native-scalar', 'locationState': 'coarse'}
        for item in selected]
    assert result['nextCursor'] is None and result['total'] == 2
    assert result['readBytes'] < 100000


def test_exact_ranges_resolve_pdf_page_from_index_without_guessing_native_ref(tmp_path):
    path = tmp_path / 'pdf-ranges.json'
    digests = write_reader_artifact(path, payload({'format': 'pdf-text', 'pages': [
        {'page_number': 7, 'text': 'Before😀evidence'}]}))
    selected = {'nativeRef': '#/document/pages/0/text', 'start': 6, 'end': 10}
    result = read_document_reader(request(path, digests, 'ranges', ranges=[selected]))
    assert result['items'][0]['text'] == '😀evi'
    assert result['items'][0]['locator']['page'] == 7
    assert result['items'][0]['locator']['startChar'] == 6
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        plan = ' '.join(str(row) for row in db.execute("""EXPLAIN QUERY PLAN SELECT descriptor FROM items
            WHERE field='pages' AND json_extract(descriptor,'$.ref')=?
            AND json_extract(descriptor,'$.start')>=? AND json_extract(descriptor,'$.start')<=?
            ORDER BY json_extract(descriptor,'$.start') DESC LIMIT 129""", (selected['nativeRef'], 0, 6)))
    assert 'items_native_range' in plan and 'SCAN' not in plan


def test_exact_native_ranges_reject_missing_scalar_and_incomplete_extent(tmp_path):
    path = tmp_path / 'ranges.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'evidence'}))
    for native_ref, end in [('#/document/missing', 1), ('#/document/text', 100)]:
        with pytest.raises(ValueError, match='incomplete'):
            read_document_reader(request(path, digests, 'ranges',
                ranges=[{'nativeRef': native_ref, 'start': 0, 'end': end}]))


def test_exact_native_ranges_reject_missing_location_index_instead_of_scanning(tmp_path):
    path = tmp_path / 'ranges.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'evidence'}))
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        db.execute('DROP INDEX items_native_range')
    with pytest.raises(ValueError, match='location index is missing; rebuild'):
        read_document_reader(request(path, digests, 'ranges', ranges=[{
            'nativeRef': '#/document/text', 'start': 0, 'end': 4}]))


def test_exact_native_ranges_never_return_partial_success_at_budget(tmp_path):
    path = tmp_path / 'ranges.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'value' * 10000}))
    ref = {'nativeRef': '#/document/text', 'start': 0, 'end': 100}
    raw = request(path, digests, 'ranges', ranges=[ref, ref]).model_dump(by_alias=True)
    raw['selection']['maxBytes'] = 20000
    with pytest.raises(DocumentReaderBudgetError, match='physical'):
        read_document_reader(DocumentReaderRequest.model_validate(raw))


def test_exact_native_ranges_reject_pagination_and_overbroad_input(tmp_path):
    from pydantic import ValidationError
    path = tmp_path / 'ranges.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'evidence'}))
    ref = {'nativeRef': '#/document/text', 'start': 0, 'end': 1}
    for selection in [dict(ranges=[ref], after=0), dict(ranges=[ref] * 129),
            dict(ranges=[dict(ref, end=65537)]), dict(ranges=None)]:
        with pytest.raises(ValidationError):
            request(path, digests, 'ranges', **selection)


@pytest.mark.parametrize('format,section,location', [
    ('epub', {'id':'chapter-one', 'href':'OPS/chapter.xhtml', 'media_type':'application/xhtml+xml'},
        {'kind':'epub-section', 'sectionId':'chapter-one', 'href':'OPS/chapter.xhtml'}),
    ('flat-odf', {'locator':{'kind':'paragraph', 'paragraph':2}}, {'kind':'paragraph', 'paragraph':2}),
    ('flat-odf', {'locator':{'kind':'slide-paragraph', 'slide':3, 'paragraph':1}},
        {'kind':'slide-paragraph', 'slide':3, 'paragraph':1}),
    ('flat-odf', {'locator':{'kind':'sheet-cell', 'sheet':'Evidence', 'row':4, 'column':2}},
        {'kind':'sheet-cell', 'sheet':'Evidence', 'row':4, 'column':2}),
])
def test_adapter_sections_are_unique_native_scalars_with_structural_locations(tmp_path, format, section, location):
    text = 'ONLY_NATIVE_SECTION😀漢' * 2000
    path = tmp_path / 'sections.json'
    digests = write_reader_artifact(path, payload({'format':format, 'sections':[{**section, 'text':text}]}))
    result = read_document_reader(request(path, digests, limit=1))
    assert result['items'][0]['text'] == text[:16384]
    assert result['readBytes'] <= 65536
    assert result['items'][0]['locator']['nativeRef'] == '#/document/sections/0/text'
    assert all(result['items'][0]['locator'][key] == value for key, value in location.items())
    cursor = result['nextCursor']
    second = read_document_reader(request(path, digests, limit=1, after=cursor))
    assert second['items'][0]['text'] == text[16384:32768]
    assert digests[2]['pageCount'] == 0
    assert path.read_bytes().count(b'ONLY_NATIVE_SECTION') == 2000
    script = '''import json,sys
from semantica.semantic_document_reader import read_document_reader
from semantica.semantic_query_schema import DocumentReaderRequest
print(json.dumps(read_document_reader(DocumentReaderRequest.model_validate_json(sys.argv[1]))))'''
    fresh = subprocess.run([sys.executable, '-c', script,
        request(path, digests, limit=1).model_dump_json(by_alias=True)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        timeout=30, check=True)
    restarted = json.loads(fresh.stdout)
    assert restarted['items'] == result['items']
    assert restarted['readBytes'] == result['readBytes'] <= 65536
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        assert not any('ONLY_NATIVE_SECTION' in row[0] for row in db.execute('SELECT descriptor FROM items'))


def test_native_scalar_cross_page_slices_keep_real_provenance_and_origin(tmp_path):
    native = DoclingDocument(name='cross-page')
    for number in (1, 2, 3):
        native.add_page(page_no=number, size=Size(width=600, height=800))
    value = 'First😀Second漢Third'
    item = native.add_text(label='text', text=value)
    for number, span in [(1, (0, 6)), (2, (6, 13)), (3, (13, len(value)))]:
        item.prov.append(ProvenanceItem(page_no=number, charspan=span,
            bbox=BoundingBox(l=10,t=20,r=200,b=40,coord_origin=CoordOrigin.TOPLEFT)))
    path = tmp_path/'cross-page.json'
    digests = write_reader_artifact(path, payload({'format':'docling','document':native.export_to_dict(),
        'pages':[{'page_number':1,'origin':'native'}, {'page_number':2,'origin':'ocr'},
                 {'page_number':3,'origin':'mixed'}]}))
    chunks = read_document_reader(request(path, digests))
    assert [row['text'] for row in chunks['items']] == [value]
    for start, end, number in [(0, 13, 1), (6, 13, 2), (13, len(value), 3)]:
        exact = read_document_reader(request(path, digests, 'ranges', ranges=[{
            'nativeRef': '#/document/document/texts/0/text', 'start': start, 'end': end}]))
        assert exact['items'][0]['text'] == value[start:end]
        assert exact['items'][0]['locator']['page'] == number
    for number, expected, state in [(1,value[:6],'native_text'), (2,value[6:13],'ocr_text'),
                                     (3,value[13:],'mixed_text')]:
        page = read_document_reader(request(path,digests,'pages',pageNumber=number))
        assert [row['text'] for row in page['items']] == [expected]
        assert page['items'][0]['state'] == state
        assert page['items'][0]['blocks'][0]['locator']['nativeRef'].endswith('/texts/0/text')
    assert {state: count for state, count in digests[2]['pageStateCounts'].items() if count} == {
        'native_text':1,'ocr_text':1,'mixed_text':1}


def test_native_docling_tables_unicode_pages_restart_and_no_formatter(tmp_path, monkeypatch):
    native = DoclingDocument(name='native')
    native.add_page(page_no=1, size=Size(width=600, height=800))
    def prov(start, end):
        return ProvenanceItem(page_no=1, charspan=(start, end),
            bbox=BoundingBox(l=10,t=20,r=200,b=40,coord_origin=CoordOrigin.TOPLEFT))
    body = 'Before😀漢'
    native.add_text(label='text', text=body, prov=prov(0,len(body)))
    native.add_table(data=TableData(num_rows=1,num_cols=2,table_cells=[
        TableCell(text='NATIVE_CELL_1', start_row_offset_idx=0,end_row_offset_idx=1,
            start_col_offset_idx=0,end_col_offset_idx=1,column_header=True),
        TableCell(text='NATIVE_CELL_2', start_row_offset_idx=0,end_row_offset_idx=1,
            start_col_offset_idx=1,end_col_offset_idx=2,
            bbox=BoundingBox(l=20,t=50,r=100,b=70,coord_origin=CoordOrigin.TOPLEFT))]),prov=prov(0,0))
    native.add_text(label='text',text='A😀B',prov=prov(1,2))
    data = payload({'format':'docling','document':native.export_to_dict()})
    def forbidden(*args, **kwargs):
        raise AssertionError('reader must not invoke a text/table serializer')
    monkeypatch.setattr(DoclingDocument,'export_to_text',forbidden)
    path = tmp_path/'native.json'
    digests = write_reader_artifact(path,data)
    assert json.loads(path.read_bytes()) == data
    result = read_document_reader(request(path,digests))
    assert [item['text'] for item in result['items']] == [body,'NATIVE_CELL_1','NATIVE_CELL_2','A😀B']
    assert result['items'][1]['locator']['locationState'] == 'coarse'
    assert result['items'][2]['locator']['locationState'] == 'located'
    assert result['items'][1]['locator']['tableCell']['columnHeader'] is True
    pages = read_document_reader(request(path,digests,'pages'))
    assert [item['text'] for item in pages['items']] == [body,'NATIVE_CELL_2','😀']
    assert pages['items'][1]['blocks'][0]['y'] == 50
    assert digests[2]['textCharCount'] == len(body)+len('NATIVE_CELL_1NATIVE_CELL_2A😀B')
    assert digests[2]['pageStateCounts']['invalid_layout'] == 1
    assert digests[2]['status'] == 'partial'
    assert pages['items'][-1]['hasMoreParts'] is False
    assert all(item['hasMoreParts'] for item in pages['items'][:-1])
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        descriptors = ' '.join(row[0] for row in db.execute('SELECT descriptor FROM items'))
        assert body not in descriptors and 'NATIVE_CELL' not in descriptors
    script = '''import json,sys
from semantica.semantic_document_reader import read_document_reader
from semantica.semantic_query_schema import DocumentReaderRequest
print(json.dumps(read_document_reader(DocumentReaderRequest.model_validate_json(sys.argv[1]))))'''
    fresh = subprocess.run([sys.executable,'-c',script,request(path,digests).model_dump_json(by_alias=True)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30,check=True)
    assert json.loads(fresh.stdout)['items'] == result['items']


def test_cross_page_table_retains_cells_without_inventing_page_membership(tmp_path):
    native = DoclingDocument(name='cross-page-table')
    for number in (1, 2):
        native.add_page(page_no=number, size=Size(width=600, height=800))
    table = native.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[
        TableCell(text='Cell😀漢', start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=1,
                  bbox=BoundingBox(l=10,t=20,r=100,b=40))]))
    for number in (1, 2):
        table.prov.append(ProvenanceItem(page_no=number, charspan=(0,0),
                         bbox=BoundingBox(l=10,t=20,r=100,b=40)))
    path = tmp_path/'cross-table.json'
    digests = write_reader_artifact(path,payload({'format':'docling','document':native.export_to_dict()}))
    chunks = read_document_reader(request(path,digests))
    assert [item['text'] for item in chunks['items']] == ['Cell😀漢']
    assert chunks['items'][0]['locator']['locationState'] == 'coarse'
    for number in (1,2):
        page = read_document_reader(request(path,digests,'pages',pageNumber=number))
        assert page['items'][0]['state'] == 'invalid_layout'
        assert page['items'][0]['text'] == ''
    assert digests[2]['status'] == 'partial'


def test_escape_heavy_unicode_paging_is_complete_and_physically_bounded(tmp_path):
    text = ('\x00\\"\n😀漢' * 40000)
    path = tmp_path/'text.json'
    digests = write_reader_artifact(path,payload({'format':'text','text':text}))
    after, values, reads = -1, [], []
    while True:
        result = read_document_reader(request(path,digests,after=after))
        reads.append(result['readBytes'])
        values.extend(item['text'] for item in result['items'])
        if result['nextCursor'] is None:
            break
        assert result['nextCursor'] > after
        after = result['nextCursor']
    assert ''.join(values) == text
    assert max(reads) <= 256*1024
    assert all(len(value) <= 64*1024 for value in values)


def test_large_native_scalar_publication_does_not_allocate_full_text_or_address_list(tmp_path):
    peaks=[]
    for size in (160000,8000000):
        data=payload({'format':'text','text':'x'*size})
        path=tmp_path/f'{size}.json'
        tracemalloc.start()
        digests=write_reader_artifact(path,data)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        result=read_document_reader(request(path,digests,limit=1,after=1))
        assert result['items'][0]['text'] == 'x'*16384 and result['readBytes']==16384
    print('native_reader_publication_peak_bytes',peaks)
    assert peaks[1] < peaks[0]+512*1024


def test_reader_cancellation_and_old_carrier_rejection_are_explicit(tmp_path):
    from semantica.semantic_worker_context import query_cancellation
    from semantica.utils.exceptions import ProcessingError
    data=payload({'format':'text','text':'native'})
    path=tmp_path/'source.json'
    digests=write_reader_artifact(path,data)
    event=Event(); event.set()
    token=query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError,match='canceled'):
            read_document_reader(request(path,digests))
        with pytest.raises(ProcessingError,match='canceled'):
            write_reader_artifact(tmp_path/'canceled.json',data)
    finally:
        query_cancellation.reset(token)
    with pytest.raises(ValueError,match='current parsed-source'):
        write_reader_artifact(tmp_path/'old.json',{**data,'protocol':'semantica.parsed-source.v2'})
    with pytest.raises(ValueError,match='reader projection'):
        write_reader_artifact(tmp_path/'duplicate.json',payload({'format':'text','text':'native','reader':{'chunks':[],'pages':[]}}))


def test_binding_metadata_is_small_body_free_and_reusable_without_opening_source(tmp_path):
    data = payload({'format':'text','text':'CANONICAL_BODY', 'content_hash':'hash:h',
        'quality':{'version':'1','status':'needs_review','issues':[
            {'code':'fragmented_cjk_encoding','quote':'QUALITY_BODY'*10000},
            {'code':'unmapped_characters'}, {'code':'formula_transcription_missing'}, {'code':'untrusted'}]}})
    data.update(mimeType='text/plain',forceOcr=False,processingRevision='processing:p',
        documentProcessing={'mode':'local'})
    path=tmp_path/'source.json'
    digests=write_reader_artifact(path,data)
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        metadata=dict(db.execute('SELECT key,value FROM metadata'))
    header=json.loads(metadata['header'])
    assert header['quality']=={'version':'1','status':'needs_review','issueCount':4,
        'issueCodes':['formula_transcription_missing','fragmented_cjk_encoding','unmapped_characters']}
    assert header['contentHash']=='hash:h' and header['documentProcessing']=={'mode':'local'}
    assert json.loads(metadata['readerHeader']) == digests[2]
    assert not any('BODY' in value for value in metadata.values())
    assert max(len(value.encode()) for value in metadata.values()) <= 4096
    with pytest.raises(DocumentReaderBudgetError,match='binding metadata'):
        write_reader_artifact(tmp_path/'oversized.json',{**data,'documentProcessing':{'mode':'x'*4096}})


def test_rich_cells_use_native_children_once_and_blank_cells_keep_coordinates(tmp_path):
    native=DoclingDocument(name='native')
    table=native.add_table(data=TableData(num_rows=1,num_cols=2,table_cells=[]))
    child=native.add_text(label='text',text='NATIVE_CHILD',parent=table)
    native.add_table_cell(table,RichTableCell(text='RICH_FORMATTED_MIRROR',ref=RefItem(cref=child.self_ref),
        start_row_offset_idx=0,end_row_offset_idx=1,start_col_offset_idx=0,end_col_offset_idx=1))
    native.add_table_cell(table,TableCell(text='',start_row_offset_idx=0,end_row_offset_idx=1,
        start_col_offset_idx=1,end_col_offset_idx=2))
    path=tmp_path/'rich.json'
    digests=write_reader_artifact(path,payload({'format':'docling','document':native.export_to_dict()}))
    result=read_document_reader(request(path,digests))
    assert [item['text'] for item in result['items']] == ['NATIVE_CHILD','']
    assert result['items'][0]['locator']['tableCell']['contentRef']==child.self_ref
    assert result['items'][1]['locator']['tableCell']['colStart']==1


def test_native_pdf_pages_keep_text_without_fabricating_layout_and_have_exact_summary(tmp_path):
    text='😀漢'*12000
    path=tmp_path/'pdf.json'
    digests=write_reader_artifact(path,payload({'format':'pdf-text','pages':[
        {'page_number':1,'text':text}, {'page_number':2,'text':''}]}))
    result=read_document_reader(request(path,digests,'pages'))
    assert ''.join(item['text'] for item in result['items']) == text
    assert all('width' not in item and 'height' not in item and item['blocks']==[] for item in result['items'])
    assert result['items'][0]['state']=='invalid_layout'
    assert result['items'][-1]['state']=='no_text_content'
    assert digests[2]['pageCount']==2 and digests[2]['pagePartCount']==3
    assert digests[2]['pageStateCounts']['invalid_layout']==1
    assert digests[2]['pageStateCounts']['no_text_content']==1
    assert digests[2]['textCharCount']==len(text)
    first=read_document_reader(request(path,digests,'pages',pageNumber=1,limit=1))
    assert first['total']==2 and first['nextCursor']==0
    second=read_document_reader(request(path,digests,'pages',pageNumber=1,after=0,limit=1))
    assert first['items'][0]['text']+second['items'][0]['text']==text
    assert second['nextCursor'] is None
    empty=read_document_reader(request(path,digests,'pages',pageNumber=2))
    assert empty['total']==1 and empty['items'][0]['pageNumber']==2
    with pytest.raises(ValueError,match='only valid for pages'):
        request(path,digests,'chunks',pageNumber=1)
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        plan=' '.join(str(row) for row in db.execute("EXPLAIN QUERY PLAN SELECT descriptor FROM items WHERE field='pages' AND page=1 AND json_extract(descriptor,'$.pagePart')>0 ORDER BY json_extract(descriptor,'$.pagePart') LIMIT 1"))
    assert 'items_page_part' in plan and 'SCAN' not in plan
