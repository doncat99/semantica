import unittest
import gc
import weakref
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
from semantica.parse.docling_parser import DoclingParser, DoclingMetadata

class TestDoclingParser(unittest.TestCase):
    def test_source_conversions_share_converter_without_retaining_document_results(self):
        from docling_core.types.doc import DoclingDocument, DocItemLabel
        from semantica.source import parse_source

        class Result:
            pass

        references = []
        def convert(path):
            document = DoclingDocument(name=Path(path).name)
            document.add_text(label=DocItemLabel.TEXT, text=Path(path).name)
            result = Result()
            result.document, result.status, result.pages = document, "success", []
            references.append(weakref.ref(result))
            return result

        self.mock_converter.convert.side_effect = convert
        with patch.object(Path, 'exists', return_value=True):
            first = parse_source(Path("first.pdf"), name="first.pdf", mime_type="application/pdf", force_ocr=False)
            second = parse_source(Path("second.pdf"), name="second.pdf", mime_type="application/pdf", force_ocr=False)
        self.mock_converter_cls.assert_called_once()
        self.assertEqual(self.mock_converter.convert.call_count, 2)
        self.assertEqual(first.text, "first.pdf")
        self.assertEqual(second.text, "second.pdf")
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))

    def test_source_failure_discards_converter_before_next_conversion(self):
        from docling_core.types.doc import DoclingDocument, DocItemLabel
        from semantica.source import parse_source
        from semantica.utils.exceptions import ProcessingError

        document = DoclingDocument(name="recovered")
        document.add_text(label=DocItemLabel.TEXT, text="Recovered content")
        self.mock_converter.convert.side_effect = [RuntimeError("broken pipeline"), SimpleNamespace(
            document=document, status="success", pages=[])]
        with patch.object(Path, 'exists', return_value=True):
            with self.assertRaisesRegex(ProcessingError, "broken pipeline"):
                parse_source(Path("broken.pdf"), name="broken.pdf", mime_type="application/pdf", force_ocr=False)
            result = parse_source(Path("recovered.pdf"), name="recovered.pdf", mime_type="application/pdf", force_ocr=False)
        self.assertEqual(self.mock_converter_cls.call_count, 2)
        self.assertEqual(result.text, "Recovered content")

    def test_source_ocr_change_replaces_converter_configuration(self):
        from docling_core.types.doc import DoclingDocument, DocItemLabel
        from docling.datamodel.base_models import InputFormat
        from semantica.source import parse_source

        document = DoclingDocument(name="ocr")
        document.add_text(label=DocItemLabel.TEXT, text="Content")
        self.mock_converter.convert.return_value = SimpleNamespace(document=document, status="success", pages=[
            SimpleNamespace(cells=[SimpleNamespace(text="Content", from_ocr=True)])])
        with patch.object(Path, 'exists', return_value=True):
            for force in [False, True]:
                parse_source(Path("source.pdf"), name="source.pdf", mime_type="application/pdf", force_ocr=force)
        self.assertEqual(self.mock_converter_cls.call_count, 2)
        options = [call.kwargs["format_options"][InputFormat.PDF].pipeline_options
                   for call in self.mock_converter_cls.call_args_list]
        self.assertFalse(options[0].do_ocr)
        self.assertTrue(options[1].do_ocr)

    def test_explicit_formula_enrichment_reaches_docling_pipeline(self):
        with patch.object(Path, 'exists', return_value=True):
            DoclingParser(do_formula_enrichment=True, do_code_enrichment=True).parse('fixture.pdf')
        from docling.datamodel.base_models import InputFormat
        options = self.mock_converter_cls.call_args.kwargs['format_options'][InputFormat.PDF].pipeline_options
        self.assertTrue(options.do_formula_enrichment)
        self.assertTrue(options.do_code_enrichment)
        self.assertTrue(options.layout_options.recover_formula_regions)
        self.assertTrue(options.do_native_formula_enrichment)

    def test_native_pdf_keeps_words_across_font_fragments_without_ocr(self):
        from docling.datamodel.backend_options import PdfBackendOptions
        if "enforce_same_font" not in PdfBackendOptions.model_fields:
            self.skipTest("Docling before the locked native release does not expose font segmentation")
        with patch.object(Path, 'exists', return_value=True):
            self.parser.parse("fixture.pdf")
        from docling.datamodel.base_models import InputFormat
        option = self.mock_converter_cls.call_args.kwargs["format_options"][InputFormat.PDF]
        self.assertFalse(option.backend_options.enforce_same_font)
        self.assertFalse(option.pipeline_options.do_ocr)
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        self.assertIsNot(option.backend, PyPdfiumDocumentBackend)
        self.assertEqual(option.backend.__module__, "docling.backend.docling_parse_backend")

    def test_page_projection_uses_all_docling_provenance_entries(self):
        first = SimpleNamespace(text="First page", prov=[SimpleNamespace(page_no=1)])
        second = SimpleNamespace(text="Second page", prov=[SimpleNamespace(page_no=2)])
        shared = SimpleNamespace(text="Spanning item", prov=[SimpleNamespace(page_no=1), SimpleNamespace(page_no=2)])
        visits = []
        def items():
            visits.append(True)
            return iter([(first, 0), (second, 0), (shared, 0)])
        document = SimpleNamespace(
            pages={number: SimpleNamespace(size=SimpleNamespace(width=100, height=200)) for number in [1, 2]},
            iterate_items=items,
        )
        pages = self.parser._extract_pages(SimpleNamespace(document=document), {})
        self.assertEqual(len(visits), 1)
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
        from docling.datamodel.base_models import InputFormat
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        pdf = self.mock_converter_cls.call_args.kwargs["format_options"][InputFormat.PDF]
        self.assertIs(pdf.backend, PyPdfiumDocumentBackend)
        options = pdf.pipeline_options
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

    def test_missing_cells_do_not_mislabel_ocr_output_as_native(self):
        document = MagicMock()
        document.tables = []
        document.pages = []
        document.export_to_text.return_value = "Recovered text"
        self.mock_converter.convert.return_value = SimpleNamespace(
            document=document, status="success", pages=[]
        )
        with patch.object(Path, 'exists', return_value=True):
            result = DoclingParser(enable_ocr=True).parse("fixture.pdf", include_document=True)
        self.assertIsNone(result["origin"])

    def test_native_only_conversion_can_use_assembled_text_without_cells(self):
        document = MagicMock()
        document.tables = []
        document.pages = []
        document.export_to_text.return_value = "Native text"
        self.mock_converter.convert.return_value = SimpleNamespace(
            document=document, status="success", pages=[]
        )
        with patch.object(Path, 'exists', return_value=True):
            result = DoclingParser(enable_ocr=False).parse("fixture.pdf", include_document=True)
        self.assertEqual(result["origin"], "native")

    def test_complete_document_uses_one_conversion_and_survives_reload(self):
        from docling_core.types.doc import DoclingDocument, DocItemLabel
        document = DoclingDocument(name="one-conversion")
        document.add_text(label=DocItemLabel.TEXT, text="北京大学位于北京。")
        converter = MagicMock()
        converter.convert.return_value = SimpleNamespace(document=document, status="success")
        parser = DoclingParser(converter=converter)
        with patch.dict('sys.modules', {'pymupdf': None, 'fitz': None}), patch.object(Path, 'exists', return_value=True):
            result = parser.parse("fixture.pdf", include_document=True, export_format="doctags")
        converter.convert.assert_called_once_with("fixture.pdf")
        restored = DoclingDocument.model_validate(result["document"])
        self.assertEqual(result["doctags"], restored.export_to_doctags())
        self.assertEqual(result["full_text"], result["doctags"])
        self.assertEqual(restored.texts[0].text, "北京大学位于北京。")

    def test_doctags_are_exported_once_for_complete_document(self):
        document = MagicMock()
        document.pages = {}
        document.tables = []
        document.export_to_doctags.return_value = "<doctag>text</doctag>"
        document.export_to_text.return_value = "text"
        document.export_to_dict.return_value = {"name": "document"}
        self.mock_converter.convert.return_value = SimpleNamespace(document=document, status="success", pages=[])
        with patch.object(Path, 'exists', return_value=True):
            result = DoclingParser(converter=self.mock_converter).parse(
                "fixture.pdf", include_document=True, export_format="doctags")
        self.assertEqual(result["doctags"], result["full_text"])
        document.export_to_doctags.assert_called_once_with()

    def setUp(self):
        DoclingParser.clear_shared()
        # Patch DOCLING_AVAILABLE to True for testing logic
        self.available_patcher = patch('semantica.parse.docling_parser.DOCLING_AVAILABLE', True)
        self.available_patcher.start()
        
        # Mock the DocumentConverter
        self.mock_converter_cls = patch('semantica.parse.docling_parser.DocumentConverter').start()
        self.mock_converter = self.mock_converter_cls.return_value
        
        self.parser = DoclingParser()

    def tearDown(self):
        DoclingParser.clear_shared()
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
