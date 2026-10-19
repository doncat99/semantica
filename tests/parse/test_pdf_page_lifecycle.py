"""Native PDF reader contracts, including real documents and resource failures."""
from unittest.mock import MagicMock, patch

import pymupdf
import pytest

from semantica.parse.pdf_parser import PDFParser
from semantica.utils.exceptions import ProcessingError


@pytest.fixture
def original(tmp_path):
    path = tmp_path / "original.pdf"
    with pymupdf.open() as pdf:
        for text in ("First page", "Second page"):
            pdf.new_page().insert_text((30, 50), text)
        pdf.set_metadata({"title": "Native PDF", "author": "Author"})
        pdf.save(path)
    return path


def test_native_entrypoints_and_page_selection(original):
    from semantica.parse.methods import parse_pdf
    from semantica.parse.document_parser import DocumentParser

    parser = PDFParser()
    expected = parser.parse(original, extract_tables=False)
    assert parse_pdf(original, extract_tables=False) == expected
    assert DocumentParser().parse(original, extract_tables=False) == expected
    assert expected["total_pages"] == expected["metadata"]["page_count"] == 2
    assert expected["metadata"]["title"] == "Native PDF"
    assert [p["page_number"] for p in expected["pages"]] == [1, 2]
    assert parser.extract_text(original) == expected["full_text"]
    assert parser.extract_text(original, pages=[1]).strip() == "Second page"
    assert parser.extract_text(original, pages=[]) == ""
    for index in (-1, 2, True, "1"):
        with pytest.raises(ProcessingError, match="page index"):
            parser.parse(original, pages=[index])


def test_metadata_only_never_extracts_pages(original):
    with patch.object(PDFParser, "_parse_page", side_effect=AssertionError("unexpected extraction")):
        assert PDFParser().extract_metadata(original)["page_count"] == 2


def test_document_closed_when_extraction_fails(original):
    module = MagicMock()
    pdf = module.open.return_value.__enter__.return_value
    pdf.needs_pass = False
    pdf.__len__.return_value = 2
    pdf.metadata = {}
    module.open.return_value.__exit__.return_value = False
    with patch.dict("sys.modules", {"pymupdf": module}), patch.object(
        PDFParser, "_parse_page", side_effect=ValueError("broken page")
    ):
        with pytest.raises(ProcessingError, match="broken page"):
            PDFParser().parse(original)
    module.open.return_value.__exit__.assert_called_once()
    pdf.load_page.assert_called_once_with(0)


def test_corrupt_and_encrypted_documents_fail_explicitly(tmp_path):
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a PDF")
    with pytest.raises(ProcessingError):
        PDFParser().parse(corrupt)
    encrypted = tmp_path / "encrypted.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((30, 50), "Secret")
        pdf.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 owner_pw="owner", user_pw="reader")
    with pytest.raises(ProcessingError, match="requires a password"):
        PDFParser().parse(encrypted)


def test_real_tables_and_image_geometry(tmp_path):
    path = tmp_path / "table-image.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=300, height=400)
        for y in (50, 80, 110):
            page.draw_line((30, y), (230, y))
        for x in (30, 130, 230):
            page.draw_line((x, 50), (x, 110))
        for point, text in (((40, 70), "A"), ((140, 70), "B"),
                            ((40, 100), "C"), ((140, 100), "D")):
            page.insert_text(point, text)
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
        image.clear_with(128)
        page.insert_image(pymupdf.Rect(30, 150, 50, 170), pixmap=image)
        pdf.save(path)
    parser = PDFParser()
    assert parser.extract_tables(path) == [{
        "data": [["A", "B"], ["C", "D"]],
        "bbox": [30.0, 50.0, 230.0, 110.0], "page_number": 1,
    }]
    assert parser.extract_images(path) == [{
        "x0": 30.0, "y0": 230.0, "x1": 50.0, "y1": 250.0,
        "width": 20.0, "height": 20.0, "page_number": 1,
    }]
    with patch.object(pymupdf.Page, "find_tables", side_effect=AssertionError), \
         patch.object(pymupdf.Page, "get_image_info", side_effect=AssertionError):
        assert "A" in parser.extract_text(path)


def test_default_text_sort_and_explicit_override(original):
    page = MagicMock()
    page.get_text.return_value = "text"
    parser = PDFParser()
    parser._parse_page(page, 1, {"extract_tables": False})
    page.get_text.assert_called_once_with("text", sort=True)
    with patch.object(pymupdf.Page, "get_text", return_value="unsorted") as get_text:
        assert PDFParser(sort=False).extract_text(original) == "unsorted\n\nunsorted"
        assert all(call.kwargs == {"sort": False} for call in get_text.call_args_list)
