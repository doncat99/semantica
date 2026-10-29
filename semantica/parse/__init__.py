"""Native parsing exports, loaded only when their format is requested."""
from importlib import import_module

_MODULE_EXPORTS = {
    'document_parser': 'DocumentParser',
    'web_parser': 'WebParser HTMLContentParser JavaScriptRenderer',
    'structured_data_parser': 'StructuredDataParser',
    'email_parser': 'EmailParser EmailHeaders EmailBody EmailData MIMEParser EmailThreadAnalyzer',
    'code_parser': 'CodeParser CodeStructure CodeComment SyntaxTreeParser CommentExtractor DependencyAnalyzer',
    'media_parser': 'MediaParser',
    'pdf_parser': 'PDFParser PDFPage PDFMetadata',
    'docx_parser': 'DOCXParser DocxSection DocxMetadata',
    'pptx_parser': 'PPTXParser SlideContent PPTXData',
    'excel_parser': 'ExcelParser ExcelSheet ExcelData',
    'html_parser': 'HTMLParser HTMLMetadata HTMLElement',
    'json_parser': 'JSONParser JSONData',
    'csv_parser': 'CSVParser CSVData',
    'xml_parser': 'XMLParser XMLElement XMLData',
    'image_parser': 'ImageParser ImageMetadata OCRResult',
    'mcp_parser': 'MCPParser',
    'registry': 'MethodRegistry method_registry',
    'config': 'ParseConfig parse_config',
    'methods': ('parse_document parse_web_content parse_structured_data parse_email '
                'parse_code parse_media parse_pdf parse_docx parse_json parse_csv '
                'parse_xml parse_image get_parse_method list_available_methods'),
    'docling_parser': 'DoclingParser DoclingMetadata DOCLING_AVAILABLE DOCLING_IMPORT_ERROR',
}
_EXPORTS = {name: module for module, names in _MODULE_EXPORTS.items() for name in names.split()}
__all__ = [name for name in _EXPORTS if not name.startswith('DOCLING_')]


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module('.' + _EXPORTS[name], __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
