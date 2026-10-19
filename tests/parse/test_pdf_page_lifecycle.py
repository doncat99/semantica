"""Page resources must not survive into the next page or swallow parse errors."""
from unittest.mock import MagicMock, patch

import pytest

from semantica.parse.pdf_parser import PDFParser
from semantica.utils.exceptions import ProcessingError


def test_page_caches_released_after_all_extraction_before_next_page(tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(b"fixture")
    events = []
    pages = [MagicMock(width=100, height=100) for _ in range(2)]
    for index, page in enumerate(pages):
        page.extract_text.side_effect = lambda i=index, **kw: events.append((i, "text", kw)) or "text"
        page.extract_tables.side_effect = lambda i=index: events.append((i, "tables")) or []
        page.close.side_effect = lambda i=index: events.append((i, "close"))
    pdf = MagicMock(pages=pages, metadata={})
    module = MagicMock()
    module.open.return_value.__enter__.return_value = pdf
    with patch.dict("sys.modules", {"pdfplumber": module}):
        result = PDFParser().parse(path, use_text_flow=True)
    assert result["full_text"] == "text\n\ntext"
    assert events == [(0, "text", {"use_text_flow": True}), (0, "tables"), (0, "close"),
                      (1, "text", {"use_text_flow": True}), (1, "tables"), (1, "close")]


def test_page_released_when_extraction_fails(tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(b"fixture")
    page = MagicMock(width=100, height=100)
    page.extract_text.side_effect = ValueError("broken page")
    module = MagicMock()
    module.open.return_value.__enter__.return_value = MagicMock(pages=[page], metadata={})
    with patch.dict("sys.modules", {"pdfplumber": module}):
        with pytest.raises(ProcessingError, match="broken page"):
            PDFParser().parse(path)
    page.close.assert_called_once_with()


def test_default_text_extraction_keeps_native_defaults():
    page = MagicMock(width=100, height=100)
    page.extract_text.return_value = "text"
    PDFParser()._parse_page(page, 1, {"extract_tables": False})
    page.extract_text.assert_called_once_with()
