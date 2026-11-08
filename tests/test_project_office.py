from pathlib import Path

import pytest

from semantica.project_office import flat_odf_document
from semantica.source import UnsupportedSourceFormatError, parse_source


def test_binary_office_routes_once_to_dedicated_owner(tmp_path, monkeypatch):
    calls = []
    def parse(path, *, name):
        calls.append(path)
        return {"format": "flat-odf", "source": name, "sections":[{'text':'Ada',
            'locator':{'kind':'paragraph', 'paragraph':0}}]}, "26.2.6"
    monkeypatch.setattr("semantica.project_office.parse_office", parse)
    (tmp_path / 'source.doc').write_bytes(b'fixture')
    result = parse_source(tmp_path / "source.doc", name="source.doc", mime_type="application/msword", force_ocr=False)
    assert result.text == "Ada" and result.parser == "semantica.libreoffice"
    assert len(calls) == 1


def test_binary_office_requires_explicit_optional_capability(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMANTICA_OFFICE_ROOT", raising=False)
    (tmp_path / 'source.doc').write_bytes(b'fixture')
    with pytest.raises(UnsupportedSourceFormatError, match="office-runtime-unavailable"):
        parse_source(tmp_path / "source.doc", name="source.doc", mime_type="application/msword", force_ocr=False)


def test_office_recipe_ignores_runtime_identity(tmp_path, monkeypatch):
    import json
    from semantica.source import source_processing_revision
    root = tmp_path/'office-runtime'
    root.mkdir()
    receipt = root/'office-release.json'
    monkeypatch.setenv('SEMANTICA_OFFICE_ROOT',str(root))
    def revision():
        return source_processing_revision(tmp_path/'source.doc',mime_type='application/msword',force_ocr=False)
    receipt.write_text(json.dumps({'version':'26.2.6','executable':'program/soffice','digest':'one'}))
    first = revision()
    receipt.write_text(json.dumps({'version':'26.2.6','executable':'program/soffice','digest':'two'}))
    assert revision() == first
    receipt.write_bytes(b'x'*65537)
    assert revision() == first


@pytest.mark.parametrize("body,expected,locator", [
    ('<office:text><text:h>Ada</text:h><text:p>A<text:s text:c="3"/>B<text:tab/>C</text:p></office:text>', 'Ada\n\nA   B\tC', {"kind": "paragraph", "paragraph": 1}),
    ('<office:presentation><draw:page><text:p>Ada</text:p></draw:page><draw:page><text:p>Engine</text:p></draw:page></office:presentation>', 'Ada\n\nEngine', {"kind": "slide-paragraph", "slide": 2, "paragraph": 0}),
    ('<office:spreadsheet><table:table table:name="Evidence"><table:table-row><table:table-cell table:number-columns-repeated="2"/><table:table-cell><text:p>Ada</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>', 'Ada', {"kind": "sheet-cell", "sheet": "Evidence", "row": 1, "column": 3, "row_repeat": 1, "column_repeat": 1}),
])
def test_flat_odf_preserves_unique_text_and_structural_locators(body, expected, locator):
    xml = ('<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"><office:body>' + body + '</office:body></office:document>').encode()
    result = flat_odf_document(xml, name="source")
    assert 'text' not in result and 'flat_odf' not in result
    assert '\n\n'.join(section['text'] for section in result['sections']) == expected
    assert result["sections"][-1]["locator"] == locator
    assert all('start_char' not in item and 'end_char' not in item for item in result['sections'])


@pytest.mark.parametrize('suffix,mime,body,texts,locators', [
    ('.doc', 'application/msword', '<office:text><text:p>Ada</text:p><text:p>Engine</text:p></office:text>',
        ['Ada', 'Engine'], [{'kind':'paragraph','paragraph':0}, {'kind':'paragraph','paragraph':1}]),
    ('.ppt', 'application/vnd.ms-powerpoint', '<office:presentation><draw:page><text:p>Ada</text:p></draw:page><draw:page><text:p>Engine</text:p></draw:page></office:presentation>',
        ['Ada', 'Engine'], [{'kind':'slide-paragraph','slide':1,'paragraph':0}, {'kind':'slide-paragraph','slide':2,'paragraph':0}]),
    ('.xls', 'application/vnd.ms-excel', '<office:spreadsheet><table:table table:name="Evidence"><table:table-row table:number-rows-repeated="3"><table:table-cell table:number-columns-repeated="2"><text:p>Ada</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>',
        ['Ada'], [{'kind':'sheet-cell','sheet':'Evidence','row':1,'column':1,'row_repeat':3,'column_repeat':2}]),
    ('.epub', 'application/epub+zip', None, ['Ada', 'Engine'],
        [{'kind':'epub-section','sectionId':'one','href':'OPS/one.xhtml'},
         {'kind':'epub-section','sectionId':'two','href':'OPS/two.xhtml'}]),
])
def test_adapter_parser_publication_build_reader_and_zero_copy_rebind(tmp_path, monkeypatch,
        suffix, mime, body, texts, locators):
    import json
    from zipfile import ZipFile
    from semantica.semantic_artifact_schema import ParseSourceRequest, BindParsedSourceRequest, ParsedSourceRef, SourceBuildInput
    from semantica.semantic_source_artifact import parse_source_artifact, bind_parsed_source_artifact, _load_parsed_source
    from semantica.source import source_content_revision
    from semantica.semantic_query_schema import DocumentReaderRequest
    from semantica.semantic_document_reader import read_document_reader
    source = tmp_path / ('source' + suffix)
    if suffix == '.epub':
        with ZipFile(source, 'w') as archive:
            archive.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>')
            archive.writestr('OPS/package.opf', '<package><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
            archive.writestr('OPS/one.xhtml', '<html><body><p>Ada</p></body></html>')
            archive.writestr('OPS/two.xhtml', '<html><body><p>Engine</p></body></html>')
    else:
        source.write_bytes(b'original Office bytes')
        xml = ('<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"><office:body>' + body + '</office:body></office:document>').encode()
        # Only the unavailable LibreOffice executable boundary is substituted.
        # Native ODF extraction, parser, writer, reader and build loader run.
        monkeypatch.setattr('semantica.project_office.parse_office',
            lambda path, name: (flat_odf_document(xml, name=name), '26.2.6'))
    params = {'source':{'sourceId':'source:one','filePath':str(source), 'name':source.name,
        'mimeType':mime, 'materialRevision':source_content_revision(source)},
        'outputDir':str(tmp_path/'parsed'), 'forceOcr':False,'documentProcessing':{'mode':'local'}}
    parsed = parse_source_artifact(ParseSourceRequest.model_validate(params))
    document = json.loads(Path(parsed['artifactPath']).read_bytes())['document']
    assert all(key not in document for key in ('text','plain_text','doctags','flat_odf'))
    assert [section['text'] for section in document['sections']] == texts
    ref = ParsedSourceRef.model_validate({key:parsed[key] for key in
        ('artifactPath','artifactDigest','sourceId','representationRevision','readerIndexPath','readerIndexDigest')})
    loaded = _load_parsed_source(SourceBuildInput.model_validate(params['source']),ref,False,{'mode':'local'})
    assert loaded.text[:] == '\n\n'.join(texts)
    def installed(path, digest, kind):
        path = Path(path)
        stat = path.stat()
        return {'path':str(path),'digest':digest,'kind':kind,'mediaType':'application/json',
            'installation':{'digest':digest,'identity':':'.join(map(str, (stat.st_dev,stat.st_ino,
                stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)))}}
    request = DocumentReaderRequest.model_validate({'id':'reader:adapter','sourceId':'source:one',
        'materialRevision':params['source']['materialRevision'],'representationRevision':parsed['representationRevision'],
        'artifact':installed(parsed['artifactPath'],parsed['artifactDigest'],'document-representation'),
        'readerIndex':installed(parsed['readerIndexPath'],parsed['readerIndexDigest'],'document-reader-index'),
        'selection':{'field':'chunks','limit':1,'maxBytes':65536}})
    chunks = []
    while True:
        page = read_document_reader(request)
        assert page['readBytes'] <= 65536
        chunks.extend(page['items'])
        if page['nextCursor'] is None:
            break
        request.selection.after = page['nextCursor']
    assert [item['text'] for item in chunks] == texts
    assert all(all(item['locator'][key] == value for key,value in locator.items())
        for item,locator in zip(chunks,locators,strict=True))
    assert parsed['readerHeader']['pageCount'] == 0
    rebound_dir = tmp_path/'rebound'
    rebound = bind_parsed_source_artifact(BindParsedSourceRequest.model_validate({**params,
        'source':{**params['source'],'sourceId':'source:two'},'outputDir':str(rebound_dir),
        'parsedArtifactPath':parsed['artifactPath'],'parsedArtifactDigest':parsed['artifactDigest'],
        'parsedReaderIndexPath':parsed['readerIndexPath'],'parsedReaderIndexDigest':parsed['readerIndexDigest']}))
    assert rebound['artifactPath'] == parsed['artifactPath']
    assert not rebound_dir.exists() or not list(rebound_dir.rglob('*'))
    assert rebound['processingRevision'] == parsed['processingRevision']


@pytest.mark.parametrize('suffix,target', [('.xls', 'fods'), ('.ppt', 'fodp'), ('.wpd', 'fodt')])
def test_managed_office_uses_admitted_format_and_preserves_original_path(tmp_path, monkeypatch, suffix, target):
    from semantica.project_office import parse_office
    source = tmp_path / 'b3-content-address'
    source.write_bytes(b'original immutable bytes')
    calls = []
    monkeypatch.setattr('semantica.project_office.bundled_office', lambda: (Path('/native/soffice'), '26.2.6'))
    def convert(path, output, profile, executable, selected_target):
        calls.append((path, selected_target))
        converted = output / ('converted.' + selected_target)
        converted.write_bytes(b'<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Ada</text:p></office:text></office:body></office:document>')
        return converted
    monkeypatch.setattr('semantica.project_office.convert_office', convert)
    document, version = parse_office(source, name='report' + suffix, source_suffix=suffix)
    assert calls == [(source, target)]
    assert source.read_bytes() == b'original immutable bytes'
    assert document['sections'][0]['text'] == 'Ada'
    assert document['source'] == 'report' + suffix and version == '26.2.6'
