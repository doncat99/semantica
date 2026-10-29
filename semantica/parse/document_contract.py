"""Admission errors and media types shared by native document parsers."""
from ..project_office import OFFICE_SUFFIXES


class UnsupportedSourceFormatError(ValueError):
    """No admitted adapter or processing profile exists for this document."""


class SourceQualityError(ValueError):
    """Conversion produced no usable text and requires explicit repair."""


TEXT_SUFFIXES = {'.txt', '.text', '.md', '.markdown'}
STRUCTURED_SUFFIXES = {'.pdf', '.docx', '.pptx', '.xlsx', '.html', '.htm',
                       '.png', '.jpg', '.jpeg', '.xml', '.csv'}
MEDIA_TYPES_BY_SUFFIX = {
    '.txt': {'text/plain'}, '.text': {'text/plain'},
    '.md': {'text/markdown', 'text/plain'}, '.markdown': {'text/markdown', 'text/plain'},
    '.pdf': {'application/pdf'},
    '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    '.pptx': {'application/vnd.openxmlformats-officedocument.presentationml.presentation'},
    '.xlsx': {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
    '.html': {'text/html', 'application/xhtml+xml'}, '.htm': {'text/html', 'application/xhtml+xml'},
    '.png': {'image/png'}, '.jpg': {'image/jpeg'}, '.jpeg': {'image/jpeg'},
    '.xml': {'application/xml', 'text/xml'}, '.csv': {'text/csv'},
    '.epub': {'application/epub+zip'}, '.doc': {'application/msword'},
    '.ppt': {'application/vnd.ms-powerpoint'}, '.xls': {'application/vnd.ms-excel'},
    **{suffix: {'application/wordperfect', 'application/vnd.wordperfect', 'application/x-wordperfect'}
       for suffix in OFFICE_SUFFIXES if suffix.startswith('.wp')},
}


def admit_document(suffix, mime_type, force_ocr):
    if force_ocr and suffix not in STRUCTURED_SUFFIXES:
        raise UnsupportedSourceFormatError(f'force OCR is only supported by the Docling adapter, not {suffix}')
    expected = MEDIA_TYPES_BY_SUFFIX.get(suffix)
    if expected and mime_type is not None and mime_type not in expected:
        raise UnsupportedSourceFormatError(
            f'source mimeType {mime_type} does not match {suffix}; expected one of {sorted(expected)}')
