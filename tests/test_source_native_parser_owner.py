"""Source boundaries delegate parsing; native parser owns format decisions."""
from pathlib import Path

import pytest

from semantica.source import parse_source


@pytest.mark.parametrize('suffix,mime', [('.txt', 'text/plain'), ('.pdf', 'application/pdf'),
    ('.epub', 'application/epub+zip'), ('.doc', 'application/msword')])
def test_source_delegates_once_to_document_parser(tmp_path, monkeypatch, suffix, mime):
    from semantica.parse.document_parser import DocumentParser
    calls = []
    def parse(self, path, **options):
        calls.append((path, options))
        return {'text': 'Exact source text', 'document': {'source': options['name']},
                'origin': 'native', 'parser': 'fixture', 'parser_version': '1'}
    monkeypatch.setattr(DocumentParser, 'parse_document', parse)
    path = tmp_path / ('source' + suffix)
    path.write_bytes(b'fixture')
    result = parse_source(path, name='Visible source', mime_type=mime, force_ocr=False,
                          document_processing={'mode': 'local'})
    assert result.text == 'Exact source text'
    assert len(calls) == 1
    assert calls[0] == (path, {'name': 'Visible source', 'mime_type': mime, 'force_ocr': False,
                            'document_processing': {'mode': 'local'}, 'progress_callback': None})
    assert 'quality' in result.document


def test_native_epub_uses_spine_order_and_rejects_traversal(tmp_path):
    from zipfile import ZipFile
    from semantica.parse.document_parser import DocumentParser
    from semantica.source import UnsupportedSourceFormatError
    path = tmp_path / 'source.epub'
    def package(href):
        with ZipFile(path, 'w') as archive:
            archive.writestr('META-INF/container.xml', '<container><rootfile full-path="OPS/book.opf"/></container>')
            archive.writestr('OPS/book.opf', '<package><manifest>'
                '<item id="a" href="a.html"/><item id="b" href="' + href + '"/>'
                '</manifest><spine><itemref idref="b"/><itemref idref="a"/></spine></package>')
            archive.writestr('OPS/a.html', '<p>Second</p>')
            archive.writestr('OPS/b.html', '<script>Hidden</script><p>First</p>')
    package('b.html')
    assert DocumentParser().extract_text(path) == 'First\n\nSecond'
    package('../../outside.html')
    with pytest.raises(UnsupportedSourceFormatError, match='unsafe'):
        DocumentParser().parse_document(path)


def test_native_processing_profile_rejects_unknown_mode_without_conversion(tmp_path):
    from semantica.parse.document_parser import DocumentParser
    from semantica.source import UnsupportedSourceFormatError
    path = tmp_path / 'source.pdf'
    path.write_bytes(b'fixture')
    with pytest.raises(UnsupportedSourceFormatError, match='unsupported document processing mode'):
        DocumentParser().parse_document(path, document_processing={'mode': 'invalid'})
