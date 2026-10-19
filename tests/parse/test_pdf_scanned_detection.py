"""
Tests for scanned-PDF (empty text layer) detection in PDFParser.

Covers:
    - Warning when all parsed pages lack a text layer (scanned PDFs)
    - No warning when text is present or text extraction is disabled
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from semantica.parse.pdf_parser import PDFParser


class TestScannedPdfWarning(unittest.TestCase):
    """PDFParser warns when a PDF has pages but no extractable text."""

    def setUp(self):
        self.mock_logger = MagicMock()
        logger_patcher = patch(
            "semantica.parse.pdf_parser.get_logger", return_value=self.mock_logger
        )
        tracker_patcher = patch("semantica.parse.pdf_parser.get_progress_tracker")
        logger_patcher.start()
        tracker_patcher.start()
        self.addCleanup(logger_patcher.stop)
        self.addCleanup(tracker_patcher.stop)

    def _make_pdf_path(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pdf") as tmp:
            tmp.write(b"dummy pdf content")
            return tmp.name

    def _mock_pymupdf(self, page_text):
        """Build a fake PyMuPDF module whose single page yields page_text."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = page_text
        mock_page.find_tables.return_value.tables = []
        mock_page.rect.width = 612
        mock_page.rect.height = 792

        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 1
        mock_pdf.load_page.return_value = mock_page
        mock_pdf.needs_pass = False
        mock_pdf.metadata = {}

        mock_pymupdf = MagicMock()
        context_manager = MagicMock()
        context_manager.__enter__.return_value = mock_pdf
        mock_pymupdf.open.return_value = context_manager
        return mock_pymupdf

    def test_warns_when_no_text_layer(self):
        mock_pymupdf = self._mock_pymupdf(page_text=None)  # scanned page
        parser = PDFParser()
        path = self._make_pdf_path()
        try:
            with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
                result = parser.parse(path)
            self.assertEqual(result["full_text"], "")
            self.mock_logger.warning.assert_called_once()
            message = self.mock_logger.warning.call_args[0][0]
            self.assertIn("scanned", message)
            self.assertIn("enable_ocr", message)
        finally:
            os.unlink(path)

    def test_no_warning_when_text_present(self):
        mock_pymupdf = self._mock_pymupdf(page_text="Real digital text")
        parser = PDFParser()
        path = self._make_pdf_path()
        try:
            with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
                result = parser.parse(path)
            self.assertIn("Real digital text", result["full_text"])
            self.mock_logger.warning.assert_not_called()
        finally:
            os.unlink(path)

    def test_no_warning_when_extract_text_disabled(self):
        mock_pymupdf = self._mock_pymupdf(page_text=None)
        parser = PDFParser()
        path = self._make_pdf_path()
        try:
            with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
                result = parser.parse(path, extract_text=False, extract_tables=False)
            self.assertEqual(result["full_text"], "")
            self.mock_logger.warning.assert_not_called()
        finally:
            os.unlink(path)

    def test_warns_when_pages_have_only_whitespace(self):
        """Pages that return only whitespace count as no extractable text."""
        mock_pymupdf = self._mock_pymupdf(page_text="   \n\t  ")
        parser = PDFParser()
        path = self._make_pdf_path()
        try:
            with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
                parser.parse(path)
            self.mock_logger.warning.assert_called_once()
            message = self.mock_logger.warning.call_args[0][0]
            self.assertIn("scanned", message)
            self.assertIn("enable_ocr", message)
        finally:
            os.unlink(path)

    def test_no_warning_for_mixed_pdf(self):
        """A PDF where at least one page has real text must not warn."""
        # Build a two-page PDF: page 1 has text, page 2 is image-only
        mock_page_text = MagicMock()
        mock_page_text.get_text.return_value = "Actual content"
        mock_page_text.find_tables.return_value.tables = []
        mock_page_text.rect.width = 612
        mock_page_text.rect.height = 792

        mock_page_image = MagicMock()
        mock_page_image.get_text.return_value = None
        mock_page_image.find_tables.return_value.tables = []
        mock_page_image.rect.width = 612
        mock_page_image.rect.height = 792

        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 2
        mock_pdf.load_page.side_effect = [mock_page_text, mock_page_image]
        mock_pdf.needs_pass = False
        mock_pdf.metadata = {}

        mock_pymupdf = MagicMock()
        context_manager = MagicMock()
        context_manager.__enter__.return_value = mock_pdf
        mock_pymupdf.open.return_value = context_manager

        parser = PDFParser()
        path = self._make_pdf_path()
        try:
            with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
                result = parser.parse(path)
            self.assertIn("Actual content", result["full_text"])
            self.mock_logger.warning.assert_not_called()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
