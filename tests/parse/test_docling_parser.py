import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
from semantica.parse.docling_parser import DoclingParser, DoclingMetadata

class TestDoclingParser(unittest.TestCase):
    def test_page_projection_uses_all_docling_provenance_entries(self):
        first = SimpleNamespace(text="First page", prov=[SimpleNamespace(page_no=1)])
        second = SimpleNamespace(text="Second page", prov=[SimpleNamespace(page_no=2)])
        shared = SimpleNamespace(text="Spanning item", prov=[SimpleNamespace(page_no=1), SimpleNamespace(page_no=2)])
        document = SimpleNamespace(
            pages={number: SimpleNamespace(size=SimpleNamespace(width=100, height=200)) for number in [1, 2]},
            iterate_items=lambda: iter([(first, 0), (second, 0), (shared, 0)]),
        )
        pages = self.parser._extract_pages(SimpleNamespace(document=document), {})
        self.assertEqual(pages[0]["text"], "First page\nSpanning item")
        self.assertEqual(pages[1]["text"], "Second page\nSpanning item")

    def test_force_ocr_configures_full_page_and_reports_actual_cell_origin(self):
        document = MagicMock()
        document.tables = []
        document.pages = []
        document.export_to_text.return_value = "Recovered text"
        self.mock_converter.convert.return_value = SimpleNamespace(
            document=document, status="success", pages=[SimpleNamespace(cells=[SimpleNamespace(text="Recovered text", from_ocr=True)])]
        )
        with patch.object(Path, 'exists', return_value=True):
            result = DoclingParser(enable_ocr=True, force_full_page_ocr=True).parse("fixture.pdf", include_document=True)
        options = next(iter(self.mock_converter_cls.call_args.kwargs["format_options"].values())).pipeline_options
        self.assertTrue(options.do_ocr)
        self.assertTrue(options.ocr_options.force_full_page_ocr)
        self.assertEqual(result["origin"], "ocr")
        self.assertEqual(result["plain_text"], "Recovered text")

    def test_mixed_origin_comes_from_cells_not_requested_ocr_setting(self):
        document = MagicMock()
        document.tables = []
        document.pages = []
        self.mock_converter.convert.return_value = SimpleNamespace(
            document=document, status="success", pages=[SimpleNamespace(cells=[
                SimpleNamespace(text="Native", from_ocr=False), SimpleNamespace(text="Scanned", from_ocr=True)
            ])]
        )
        with patch.object(Path, 'exists', return_value=True):
            result = DoclingParser(enable_ocr=True).parse("fixture.pdf", include_document=True)
        self.assertEqual(result["origin"], "mixed")

    def test_complete_document_uses_one_conversion_and_survives_reload(self):
        from docling_core.types.doc import DoclingDocument, DocItemLabel
        document = DoclingDocument(name="one-conversion")
        document.add_text(label=DocItemLabel.TEXT, text="北京大学位于北京。")
        converter = MagicMock()
        converter.convert.return_value = SimpleNamespace(document=document, status="success")
        parser = DoclingParser(converter=converter)
        with patch.object(Path, 'exists', return_value=True):
            result = parser.parse("fixture.pdf", include_document=True, export_format="doctags")
        converter.convert.assert_called_once_with("fixture.pdf")
        restored = DoclingDocument.model_validate(result["document"])
        self.assertEqual(result["doctags"], restored.export_to_doctags())
        self.assertEqual(result["full_text"], result["doctags"])
        self.assertEqual(restored.texts[0].text, "北京大学位于北京。")

    def setUp(self):
        # Patch DOCLING_AVAILABLE to True for testing logic
        self.available_patcher = patch('semantica.parse.docling_parser.DOCLING_AVAILABLE', True)
        self.available_patcher.start()
        
        # Mock the DocumentConverter
        self.mock_converter_cls = patch('semantica.parse.docling_parser.DocumentConverter').start()
        self.mock_converter = self.mock_converter_cls.return_value
        
        self.parser = DoclingParser()

    def tearDown(self):
        patch.stopall()

    def test_parse_returns_dict(self):
        # Mock the result of converter.convert
        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# Test Content"
        mock_result.document.tables = []
        mock_result.document.pages = []
        
        # Mock metadata
        mock_result.input.file.name = "test.pdf"
        mock_result.document.name = "test.pdf"
        
        self.mock_converter.convert.return_value = mock_result
        
        # Create a dummy file for Path.exists()
        with patch.object(Path, 'exists', return_value=True):
            result = self.parser.parse("test.pdf")
            
            # Verify result is a dict and has expected keys
            self.assertIsInstance(result, dict)
            self.assertIn("full_text", result)
            self.assertIn("tables", result)
            self.assertIn("metadata", result)
            self.assertIn("total_pages", result)
            
            # Verify we are using dict access for tables (as per our doc fix)
            self.assertIsInstance(result["tables"], list)
            self.assertEqual(result["full_text"], "# Test Content")

    def test_extract_text_uses_dict_access(self):
        # Mock parse to return a dict
        mock_parse_result = {
            "full_text": "Extracted Text",
            "tables": [],
            "metadata": {},
            "total_pages": 1
        }
        
        with patch.object(DoclingParser, 'parse', return_value=mock_parse_result):
            text = self.parser.extract_text("test.pdf")
            self.assertEqual(text, "Extracted Text")

    def test_extract_tables_uses_dict_access(self):
        # Mock parse to return a dict
        mock_tables = [{"headers": ["Col1"], "rows": [["Val1"]]}]
        mock_parse_result = {
            "full_text": "Text",
            "tables": mock_tables,
            "metadata": {},
            "total_pages": 1
        }
        
        with patch.object(DoclingParser, 'parse', return_value=mock_parse_result):
            tables = self.parser.extract_tables("test.pdf")
            self.assertEqual(tables, mock_tables)
            self.assertEqual(tables[0]["headers"], ["Col1"])

if __name__ == '__main__':
    unittest.main()
