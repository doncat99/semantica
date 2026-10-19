"""
PDF Document Parser Module

This module handles PDF document parsing using PyMuPDF for text,
table, and image extraction, including metadata and page-level processing.

Key Features:
    - PDF text extraction
    - Table extraction from PDFs
    - Image extraction
    - Metadata extraction (title, author, dates)
    - Page-level processing
    - Multi-page document support

Main Classes:
    - PDFParser: PDF document parser
    - PDFPage: Dataclass for PDF page representation
    - PDFMetadata: Dataclass for PDF metadata representation

Example Usage:
    >>> from semantica.parse import PDFParser
    >>> parser = PDFParser()
    >>> text = parser.parse("document.pdf")
    >>> pages = parser.extract_pages("document.pdf")
    >>> metadata = parser.extract_metadata("document.pdf")

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class PDFPage:
    """PDF page representation."""

    page_number: int
    text: str
    width: float
    height: float
    images: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PDFMetadata:
    """PDF metadata representation."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    page_count: int = 0


class PDFParser:
    """PDF document parser."""

    def __init__(self, **config):
        """
        Initialize PDF parser.

        Args:
            **config: Parser configuration
        """
        self.logger = get_logger("pdf_parser")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def parse(self, file_path: Union[str, Path], pipeline_id: Optional[str] = None, **options) -> Dict[str, Any]:
        """
        Parse PDF document.

        Args:
            file_path: Path to PDF file
            pipeline_id: Optional pipeline ID for progress tracking
            **options: Parsing options:
                - extract_text: Whether to extract text (default: True)
                - extract_tables: Whether to extract tables (default: True)
                - extract_images: Whether to extract images (default: False)
                - pages: Specific page numbers to parse (None = all pages)
                - sort: Sort text by coordinates (default: True)

        Returns:
            dict: Parsed PDF data
        """
        file_path = Path(file_path)
        options = {**self.config, **options}

        # Track PDF parsing
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path),
            module="parse",
            submodule="PDFParser",
            message=f"PDF: {file_path.name}",
            pipeline_id=pipeline_id,
        )

        try:
            if not file_path.exists():
                raise ValidationError(f"PDF file not found: {file_path}")

            if not file_path.suffix.lower() == ".pdf":
                raise ValidationError(f"File is not a PDF: {file_path}")

            try:
                try:
                    import pymupdf
                except ImportError:
                    raise ProcessingError(
                        "PyMuPDF is required for PDF parsing. "
                        "Install with: pip install 'semantica[parse-pdf]'"
                    )
                with pymupdf.open(str(file_path)) as pdf:
                    if pdf.needs_pass:
                        raise ProcessingError("PDF requires a password")
                    # Extract metadata
                    metadata = self._extract_metadata(pdf)
                    metadata.page_count = len(pdf)

                    # Extract pages
                    pages = []
                    page_numbers = options.get("pages")
                    if page_numbers is None:
                        page_numbers = range(len(pdf))

                    self.progress_tracker.update_tracking(
                        tracking_id, message=f"Parsing {len(pdf)} pages"
                    )

                    for page_num in page_numbers:
                        if type(page_num) is not int or not 0 <= page_num < len(pdf):
                            raise ValidationError(f"Invalid zero-based PDF page index: {page_num}")
                        page = pdf.load_page(page_num)
                        try:
                            page_data = self._parse_page(page, page_num + 1, options)
                        finally:
                            # Do not retain native pages after their plain-data result is copied.
                            del page
                        pages.append(page_data)

                    full_text = "\n\n".join(page.text for page in pages)

                    # Scanned/image-only PDFs have no text layer; warn so the
                    # failure surfaces at parse time instead of downstream.
                    # Check any() over page texts to avoid a temporary stripped
                    # copy of the full concatenation for large documents.
                    no_text = (
                        options.get("extract_text", True)
                        and pages
                        and not any(page.text.strip() for page in pages)
                    )
                    if no_text:
                        self.logger.warning(
                            f"PDF {file_path.name}: parsed {len(pages)} page(s) but "
                            f"extracted no text. This is likely a scanned "
                            f"(image-only) PDF. Retry with "
                            f"parse_pdf(..., method='docling', enable_ocr=True) "
                            f"for OCR-based extraction."
                        )

                    self.progress_tracker.stop_tracking(
                        tracking_id,
                        status="completed",
                        message=(
                            f"Parsed {len(pages)} page(s) (no text layer detected)"
                            if no_text
                            else f"Parsed {len(pages)} page(s)"
                        ),
                    )
                    return {
                        "metadata": metadata.__dict__,
                        "pages": [page.__dict__ for page in pages],
                        "full_text": full_text,
                        "total_pages": len(pdf),
                    }

            except Exception as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                self.logger.error(f"Failed to parse PDF {file_path}: {e}")
                raise ProcessingError(f"Failed to parse PDF: {e}")

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def extract_text(
        self, file_path: Union[str, Path], pages: Optional[List[int]] = None
    ) -> str:
        """
        Extract text from PDF.

        Args:
            file_path: Path to PDF file
            pages: Specific page numbers (None = all pages)

        Returns:
            str: Extracted text
        """
        result = self.parse(
            file_path, extract_tables=False, extract_images=False, pages=pages
        )
        return result["full_text"]

    def extract_tables(
        self, file_path: Union[str, Path], pages: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from PDF.

        Args:
            file_path: Path to PDF file
            pages: Specific page numbers (None = all pages)

        Returns:
            list: Extracted tables
        """
        result = self.parse(
            file_path, extract_text=False, extract_images=False, pages=pages
        )

        all_tables = []
        for page in result["pages"]:
            for table in page.get("tables", []):
                table["page_number"] = page["page_number"]
                all_tables.append(table)

        return all_tables

    def extract_images(
        self, file_path: Union[str, Path], output_dir: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract images from PDF.

        Args:
            file_path: Path to PDF file
            output_dir: Directory to save extracted images

        Returns:
            list: Extracted image information
        """
        result = self.parse(
            file_path, extract_text=False, extract_tables=False, extract_images=True
        )

        all_images = []
        for page in result["pages"]:
            for img in page.get("images", []):
                img["page_number"] = page["page_number"]
                all_images.append(img)

        return all_images

    def extract_metadata(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Read metadata without extracting any pages."""
        return self.parse(file_path, pages=[], extract_text=False,
                          extract_tables=False, extract_images=False)["metadata"]

    def render_pages(self, file_path: Union[str, Path], pages: List[int], *, dpi: int = 150) -> Dict[int, bytes]:
        """Render selected zero-based pages without exposing the PDF reader to callers."""
        if not 72 <= dpi <= 600:
            raise ValidationError("PDF render dpi must be between 72 and 600")
        path = Path(file_path)
        try:
            import pymupdf
            with pymupdf.open(str(path)) as pdf:
                if pdf.needs_pass:
                    raise ProcessingError("PDF requires a password")
                rendered = {}
                for page_num in pages:
                    if type(page_num) is not int or not 0 <= page_num < len(pdf):
                        raise ValidationError(f"Invalid zero-based PDF page index: {page_num}")
                    page = pdf.load_page(page_num)
                    try:
                        rendered[page_num] = page.get_pixmap(dpi=dpi).tobytes("png")
                    finally:
                        del page
                return rendered
        except (ProcessingError, ValidationError):
            raise
        except Exception as exc:
            raise ProcessingError(f"Failed to render PDF: {exc}") from exc

    def _parse_page(self, page, page_number: int, options: Dict[str, Any]) -> PDFPage:
        """Parse individual PDF page."""
        page_data = PDFPage(
            page_number=page_number, text="", width=page.rect.width, height=page.rect.height
        )

        # Extract text
        if options.get("extract_text", True):
            page_data.text = page.get_text("text", sort=options.get("sort", True)) or ""

        # Extract tables
        if options.get("extract_tables", True):
            page_data.tables = [
                {"data": table.extract(), "bbox": list(table.bbox)}
                for table in page.find_tables().tables
            ]

        # Extract images
        if options.get("extract_images", False):
            for image in page.get_image_info():
                x0, top, x1, bottom = image["bbox"]
                page_data.images.append({
                    "x0": x0, "y0": page.rect.height - bottom,
                    "x1": x1, "y1": page.rect.height - top,
                    "width": x1 - x0, "height": bottom - top,
                })

        if options.get("extract_links", False):
            for link in page.get_links():
                uri = link.get("uri")
                rectangle = link.get("from")
                if uri:
                    page_data.links.append({"uri": uri,
                        "quote": page.get_textbox(rectangle).strip() if rectangle is not None else ""})

        return page_data

    def _extract_metadata(self, pdf) -> PDFMetadata:
        """Extract PDF metadata."""
        metadata = pdf.metadata or {}

        return PDFMetadata(
            title=metadata.get("title"),
            author=metadata.get("author"),
            subject=metadata.get("subject"),
            creator=metadata.get("creator"),
            producer=metadata.get("producer"),
            creation_date=str(metadata.get("creationDate", "")),
            modification_date=str(metadata.get("modDate", "")),
        )
