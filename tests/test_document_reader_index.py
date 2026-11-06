import json
from pathlib import Path
import sqlite3
from hashlib import sha256

import pytest

from semantica.semantic_document_reader import write_reader_artifact, read_document_reader


def ref(path, digest, kind):
    stat = path.stat()
    return {'path': str(path), 'digest': digest, 'kind': kind, 'mediaType': 'application/json',
        'installation': {'digest': digest, 'identity': ':'.join(map(str, (
            stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))}}


def test_reader_seeks_only_requested_unicode_items_and_continues_by_bytes(tmp_path):
    text = ('正文😀\\"\n' * 100000)
    payload = {'protocol': 'semantica.parsed-source.v3', 'materialRevision': 'm',
        'document': {'representation_revision': 'r', 'format': 'text', 'text': text}}
    path = tmp_path / 'source.json'
    digest, index_digest, reader_header = write_reader_artifact(path, payload)
    assert reader_header['indexFormat'] == 'semantica.document-reader-index.v3'
    assert 'chunksDigest' not in reader_header and 'pagesDigest' not in reader_header
    from semantica.semantic_query_schema import DocumentReaderRequest
    request = DocumentReaderRequest.model_validate({'id': 'reader:test', 'sourceId': 'source:test', 'materialRevision': 'm',
        'representationRevision': 'r', 'artifact': ref(path, digest, 'document-representation'),
        'readerIndex': ref(path.with_suffix('.reader.sqlite'), index_digest, 'document-reader-index'),
        'selection': {'field': 'chunks', 'after': reader_header['chunkCount'] - 2,
            'limit': 1, 'maxBytes': 256*1024}})
    result = read_document_reader(request)
    assert result['items'][0]['text'] == text[(reader_header['chunkCount']-1)*16384:]
    assert result['total'] == reader_header['chunkCount'] and result['nextCursor'] is None
    assert result['readBytes'] <= 256*1024
    assert result['header']['sourceId'] == 'source:test'
    assert json.loads(path.read_bytes()) == payload
    request.selection.after = -1
    request.selection.limit = 128
    request.selection.max_bytes = 256*1024
    result = read_document_reader(request)
    assert result['nextCursor'] is not None and result['readBytes'] <= 256*1024
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        stored = ' '.join(row[0] for row in db.execute('SELECT descriptor FROM items'))
        assert '正文😀' not in stored and 'text' not in {row[1] for row in db.execute('PRAGMA table_info(segments)')}
    # Source authorization is host-owned; identical content is reusable by a
    # different authorized source without another content/index write.
    request.source_id = 'source:second'
    assert read_document_reader(request)['header']['sourceId'] == 'source:second'


def test_reader_rejects_changed_installation_and_oversize_single_item(tmp_path):
    payload = {'protocol': 'semantica.parsed-source.v3', 'materialRevision': 'm',
        'document': {'representation_revision': 'r', 'format': 'text', 'text': 'x' * 200}}
    path = tmp_path / 'source.json'
    digest, index_digest, _ = write_reader_artifact(path, payload)
    from semantica.semantic_query_schema import DocumentReaderRequest
    request = DocumentReaderRequest.model_validate({'id': 'reader:test', 'sourceId': 'source:test', 'materialRevision': 'm',
        'representationRevision': 'r', 'artifact': ref(path, digest, 'document-representation'),
        'readerIndex': ref(path.with_suffix('.reader.sqlite'), index_digest, 'document-reader-index'),
        'selection': {'field': 'chunks', 'maxBytes': 100}})
    from semantica.semantic_document_reader import DocumentReaderBudgetError
    with pytest.raises(DocumentReaderBudgetError, match='budget'):
        read_document_reader(request)
    path.touch()
    with pytest.raises(ValueError, match='installation changed'):
        read_document_reader(request)


def test_reader_projection_adds_no_second_copy_of_native_content():
    """G0 red specification: reader records contain addresses, not native bodies."""
    from docling_core.types.doc import DoclingDocument
    from docling_core.types.doc.document import ProvenanceItem
    from docling_core.types.doc.base import BoundingBox, Size
    from semantica.parse.document_reader import project_document_reader

    body = 'G0 unique content 漢😀 ' * 512
    native = DoclingDocument(name='source')
    native.add_page(page_no=1, size=Size(width=600, height=800))
    native.add_text(label='text', text=body, prov=ProvenanceItem(page_no=1,
        charspan=(0, len(body)), bbox=BoundingBox(l=1, t=1, r=100, b=20)))
    projection = project_document_reader({'format': 'docling', 'document': native.export_to_dict()})

    def copied_bytes(value):
        if isinstance(value, str):
            return value.count(body) * len(body.encode('utf-8'))
        if isinstance(value, dict):
            return sum(copied_bytes(item) for item in value.values())
        if isinstance(value, list):
            return sum(copied_bytes(item) for item in value)
        return 0

    duplicated = copied_bytes(projection)
    print(f'G0 native_body_bytes={len(body.encode("utf-8"))} reader_duplicated_body_bytes={duplicated}')
    assert duplicated == 0, 'reader projection must reference the unique native content'


@pytest.mark.parametrize('quality', [False, True])
def test_same_content_rebinding_adds_zero_parsed_content_bytes(tmp_path, monkeypatch, quality):
    """G0 red specification: a new source binding must reuse existing content."""
    from semantica.semantic_artifact_schema import BindParsedSourceRequest, ParseSourceRequest
    from semantica.semantic_source_artifact import parse_source_artifact, bind_parsed_source_artifact
    from semantica.source import source_content_revision
    if quality:
        from semantica import semantic_source_artifact as owner
        parse = owner._parse_source
        def with_quality(*args, **kwargs):
            text, document, *rest = parse(*args, **kwargs)
            document['quality'] = dict(version='1', status='needs_review', issues=[{'code':'PAGE_PARSE_FAILED'}])
            return text, document, *rest
        monkeypatch.setattr(owner, '_parse_source', with_quality)

    source = tmp_path / 'original.txt'
    body = 'G0 unique source content 漢😀 ' * 512
    source.write_text(body, encoding='utf-8')
    params = {'source': {'sourceId': 'source:first', 'filePath': str(source),
        'materialRevision': source_content_revision(source), 'name': source.name,
        'mimeType': 'text/plain'}, 'outputDir': str(tmp_path / 'parsed'),
        'forceOcr': False, 'documentProcessing': {'mode': 'local'}}
    original = parse_source_artifact(ParseSourceRequest.model_validate(params))
    target = tmp_path / 'rebound'
    original_reader = Path.read_bytes
    def bounded_reads(path):
        if str(path) == original['artifactPath']:
            raise AssertionError('rebinding must not load the canonical content')
        return original_reader(path)
    monkeypatch.setattr(Path, 'read_bytes', bounded_reads)
    rebound = bind_parsed_source_artifact(BindParsedSourceRequest.model_validate({**params,
        'source': {**params['source'], 'sourceId': 'source:second'}, 'outputDir': str(target),
        'parsedArtifactPath': original['artifactPath'],
        'parsedArtifactDigest': original['artifactDigest'],
        'parsedReaderIndexPath': original['readerIndexPath'],
        'parsedReaderIndexDigest': original['readerIndexDigest']}))
    body_bytes = len(body.encode('utf-8'))
    copies = sum(path.read_bytes().count(body.encode('utf-8')) for path in target.rglob('*') if path.is_file())
    added = sum(path.stat().st_size for path in target.rglob('*') if path.is_file())
    print(f'G0 source_body_bytes={body_bytes} rebound_output_bytes={added} rebound_content_bytes={copies * body_bytes}')
    assert copies == 0, 'rebinding must store identity only, without another parsed-content body'
    assert added == 0
    assert rebound['artifactPath'] == original['artifactPath']
    assert rebound['readerIndexPath'] == original['readerIndexPath']
    assert rebound['sourceHeader']['parser'] == original['sourceHeader']['parser']
    assert set(original['sourceHeader']) == {'protocol', 'sourceId', 'materialRevision', 'contentHash',
        'representationRevision', 'forceOcr', 'mimeType', 'parser', 'parserVersion', 'origin',
        'documentProcessing', 'processingRevision', 'quality'}
    assert rebound['sourceHeader'] == {**original['sourceHeader'], 'sourceId': 'source:second'}
    if quality:
        assert rebound['sourceHeader']['quality'] == dict(version='1', status='needs_review', issueCount=1)


@pytest.mark.parametrize('change', [
    {'mode': 'native'}, {'pdfTextOrder': 'content'},
    {'endpoint': 'https://other.invalid'}, {'bindingId': 'other'},
    {'mode': 'remote', 'endpoint': 'https://remote.invalid', 'bindingId': 'one'},
])
def test_reuse_rejects_actual_processing_profile_changes(tmp_path, change):
    from semantica.semantic_artifact_schema import BindParsedSourceRequest, ParseSourceRequest, ParsedSourceRef, SourceBuildInput
    from semantica.semantic_source_artifact import parse_source_artifact, bind_parsed_source_artifact, _load_parsed_source
    from semantica.semantic_artifact_errors import SemanticArtifactError
    from semantica.source import source_content_revision
    source = tmp_path / 'source.txt'
    source.write_text('Unique native source content')
    params = {'source': {'sourceId': 'one', 'filePath': str(source), 'name': source.name,
        'materialRevision': source_content_revision(source), 'mimeType': 'text/plain'},
        'outputDir': str(tmp_path / 'parsed'), 'forceOcr': False, 'documentProcessing': {'mode': 'local'}}
    parsed = parse_source_artifact(ParseSourceRequest.model_validate(params))
    changed = {'mode': 'local', **change}
    with pytest.raises(SemanticArtifactError, match='processing profile changed'):
        bind_parsed_source_artifact(BindParsedSourceRequest.model_validate({**params,
            'documentProcessing': changed, 'parsedArtifactPath': parsed['artifactPath'],
            'parsedArtifactDigest': parsed['artifactDigest'], 'parsedReaderIndexPath': parsed['readerIndexPath'],
            'parsedReaderIndexDigest': parsed['readerIndexDigest']}))
    ref = ParsedSourceRef.model_validate({key: parsed[key] for key in
        ('artifactPath', 'artifactDigest', 'sourceId', 'representationRevision', 'readerIndexPath', 'readerIndexDigest')})
    with pytest.raises(SemanticArtifactError, match='processing profile changed'):
        _load_parsed_source(SourceBuildInput.model_validate(params['source']), ref, False, changed)


def test_processing_recipe_binds_native_implementation_without_importing_it(tmp_path, monkeypatch):
    import semantica.source as owner
    path = tmp_path / 'source.txt'
    base = owner.source_processing_revision(path, mime_type='text/plain', force_ocr=False)
    assert base == owner.source_processing_revision(path, mime_type='text/plain', force_ocr=False,
        document_processing={'mode': 'local'})
    assert base != owner.source_processing_revision(path.with_suffix('.md'), mime_type='text/plain', force_ocr=False)
    assert base != owner.source_processing_revision(path, mime_type='text/plain', force_ocr=True)
    monkeypatch.setattr(owner, '_processing_implementation', lambda *args: {'owners': {'native': 'changed'}})
    assert base != owner.source_processing_revision(path, mime_type='text/plain', force_ocr=False)


@pytest.mark.parametrize('suffix,mime,mode,parser_owner', [
    ('.pdf', 'application/pdf', 'native', 'parse/pdf_parser.py'),
    ('.pdf', 'application/pdf', 'local', 'parse/docling_parser.py'),
    ('.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'local', 'parse/docling_parser.py'),
])
def test_managed_recipe_binds_actual_native_parser_owner(tmp_path, monkeypatch, suffix, mime, mode, parser_owner):
    import semantica.source as owner
    original = owner._processing_implementation
    seen = []
    def implementation(admitted_suffix, processing_mode):
        recipe = original(admitted_suffix, processing_mode)
        seen.append(recipe)
        return recipe
    monkeypatch.setattr(owner, '_processing_implementation', implementation)
    owner.source_processing_revision(tmp_path / 'b3-material', mime_type=mime, force_ocr=False,
        document_processing={'mode': mode})
    assert parser_owner in seen[0]['owners']


@pytest.mark.parametrize('suffix,mime', [('.pdf', 'application/pdf'), ('.md', 'text/plain')])
def test_logical_and_physical_format_have_identical_recipe(tmp_path, suffix, mime):
    from semantica.source import source_processing_revision
    expected = source_processing_revision(tmp_path / ('report' + suffix), mime_type=mime, force_ocr=False)
    assert source_processing_revision(tmp_path / 'b3-material', name='report' + suffix,
        mime_type=mime, force_ocr=False) == expected


def test_managed_office_recipe_binds_immutable_runtime_receipt(tmp_path, monkeypatch):
    import json
    from semantica.source import source_processing_revision
    root = tmp_path / 'office'
    root.mkdir()
    monkeypatch.setenv('SEMANTICA_OFFICE_ROOT', str(root))
    receipt = root / 'office-release.json'
    def revision():
        return source_processing_revision(tmp_path / 'b3-material', mime_type='application/vnd.ms-excel',
            force_ocr=False)
    receipt.write_text(json.dumps({'version': '26.2.6', 'executable': 'soffice', 'digest': 'one'}))
    first = revision()
    receipt.write_text(json.dumps({'version': '26.2.6', 'executable': 'soffice', 'digest': 'two'}))
    assert revision() != first
