"""Normal conversion exports one native content carrier, no parallel DocTags."""
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from docling_core.types.doc import DoclingDocument, DocItemLabel, TableCell, TableData

from semantica.parse.docling_parser import DoclingParser
from semantica.project_remote_docling import validate_remote_document, RemoteDoclingError


def test_include_native_json_does_not_export_doctags_or_duplicate_pages():
    native = DoclingDocument(name="single-content")
    native.add_text(label=DocItemLabel.TEXT, text="Unique native content")
    native.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[TableCell(
        text="Native table cell", start_row_offset_idx=0, end_row_offset_idx=1,
        start_col_offset_idx=0, end_col_offset_idx=1)]))
    document = MagicMock(wraps=native)
    document.pages = native.pages
    document.tables = native.tables
    converter = MagicMock()
    converter.convert.return_value = SimpleNamespace(document=document, status="success", pages=[])
    parser = DoclingParser(converter=converter, enable_ocr=False)
    with patch.object(Path, "exists", return_value=True), patch("semantica.parse.docling_parser.DOCLING_AVAILABLE", True):
        result = parser.parse("fixture.pdf", include_document=True, export_format="json", extract_tables=False)
    assert result["document"] == native.export_to_dict()
    assert result["plain_text"] == native.export_to_text()
    assert result["full_text"] == result["plain_text"]
    assert "doctags" not in result
    document.export_to_doctags.assert_not_called()
    document.export_to_text.assert_called_once_with()
    assert all(not any(key in page for key in ("text", "tables", "images", "items")) for page in result["pages"])


def test_remote_accepts_json_only_and_rejects_parallel_content():
    native = DoclingDocument(name="remote")
    native.add_text(label=DocItemLabel.TEXT, text="Remote evidence.")
    document = {"json_content": native.export_to_dict()}
    assert validate_remote_document({"status": "success", "document": document}) == document
    for field in ("text_content", "doctags_content"):
        with pytest.raises(RemoteDoclingError, match="duplicate"):
            validate_remote_document({"status": "success", "document": {**document, field: "redundant"}})


def test_normal_document_conversion_requests_only_native_json():
    from semantica.parse.document_parser import DocumentParser
    native = DoclingDocument(name="normal")
    native.add_text(label=DocItemLabel.TEXT, text="Native content")
    parser = MagicMock()
    parser.parse.return_value = {"plain_text": native.export_to_text(),
        "document": native.export_to_dict(), "origin": "native", "pages": [],
        "metadata": {}, "conversion_status": "success"}
    with patch.object(DoclingParser, "lease", return_value=nullcontext(parser)) as lease:
        result = DocumentParser()._parse_conversion(Path("fixture.pdf"), "fixture.pdf", False, {"mode": "local"})
    assert lease.call_args.kwargs["export_format"] == "json"
    assert parser.parse.call_args.kwargs == {"export_format": "json", "include_document": True, "extract_tables": False}
    assert result["document"]["document"] == native.export_to_dict()
    assert "doctags" not in result["document"]


@pytest.mark.parametrize("suffix", [".txt", ".md"])
def test_native_text_has_one_current_content_contract(tmp_path, suffix):
    from semantica.parse.document_parser import DocumentParser
    source = tmp_path / ("source" + suffix)
    source.write_text("Text content.", encoding="utf-8")
    result = DocumentParser().parse_document(source, document_processing={"mode": "local"})
    assert result["document"] == {"format": "text", "text": "Text content.", "source": source.name}


def test_explicit_doctags_library_export_remains_available():
    native = DoclingDocument(name="explicit")
    native.add_text(label=DocItemLabel.TEXT, text="Explicit content")
    document = MagicMock(wraps=native)
    document.pages = native.pages
    document.tables = native.tables
    converter = MagicMock()
    converter.convert.return_value = SimpleNamespace(document=document, status="success", pages=[])
    with patch.object(Path, "exists", return_value=True), patch("semantica.parse.docling_parser.DOCLING_AVAILABLE", True):
        result = DoclingParser(converter=converter, enable_ocr=False).parse(
            "fixture.pdf", include_document=True, export_format="doctags", extract_tables=False)
    assert result["doctags"] == native.export_to_doctags()
    document.export_to_doctags.assert_called_once_with()


def test_page_origins_use_native_converter_cells_without_copying_text():
    from docling_core.types.doc.base import Size
    native = DoclingDocument(name="origins")
    for number in range(1, 5):
        native.add_page(page_no=number, size=Size(width=600, height=800))
    native.add_text(label=DocItemLabel.TEXT, text="Content")
    converter = MagicMock()
    converter.convert.return_value = SimpleNamespace(document=native, status="success", pages=[
        SimpleNamespace(page_no=number, cells=[SimpleNamespace(text="Content", from_ocr=flag) for flag in flags])
        for number, flags in [(1, [False]), (2, [True]), (3, [False, True]), (4, [])]])
    with patch.object(Path, "exists", return_value=True), patch("semantica.parse.docling_parser.DOCLING_AVAILABLE", True):
        result = DoclingParser(converter=converter, enable_ocr=True).parse(
            "fixture.pdf", include_document=True, export_format="json", extract_tables=False)
    assert [page.get('origin') for page in result['pages']] == ['native', 'ocr', 'mixed', None]
    assert result['origin'] == 'mixed'
    assert all(set(page) <= {'page_number', 'width', 'height', 'origin'} for page in result['pages'])


def test_managed_pdf_ocr_without_cell_provenance_stays_unknown(tmp_path):
    native = DoclingDocument(name='managed')
    native.add_text(label=DocItemLabel.TEXT, text='Unattributed text')
    converter = MagicMock()
    converter.convert.return_value = SimpleNamespace(document=native, status='success', pages=[])
    path = tmp_path / 'b3-contenthash'
    path.write_bytes(b'fixture')
    parser = DoclingParser(converter=converter, enable_ocr=True)
    with patch('semantica.parse.docling_parser.DOCLING_AVAILABLE', True):
        result = parser.parse(path, source_suffix='.pdf', include_document=True,
            export_format='json', extract_tables=False)
    assert result['origin'] is None
    assert result['metadata']['format'] == 'pdf'
    converter.convert.assert_called_once_with(str(path))
