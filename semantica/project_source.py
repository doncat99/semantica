"""The single source-to-document boundary used by ProjectSnapshot builds."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
from typing import Any, Literal
from urllib.parse import unquote
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

class UnsupportedSourceFormatError(ValueError):
    """A source has no admitted adapter in the canonical document chain."""


@dataclass(frozen=True)
class SourceDocument:
    """One adapter result consumed by the semantic snapshot pipeline."""

    text: str
    document: dict[str, Any]
    origin: Literal["native", "ocr", "mixed", "adapter"]
    parser: str
    parser_version: str


_TEXT_SUFFIXES = {".txt", ".text", ".md", ".markdown"}
_DOCLING_SUFFIXES = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".xml",
    ".csv",
}
_ADAPTER_PENDING_SUFFIXES = {".doc", ".wpd", ".wp", ".wp4", ".wp5", ".wp6"}
_MEDIA_TYPES_BY_SUFFIX = {
    ".txt": {"text/plain"},
    ".text": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".html": {"text/html", "application/xhtml+xml"},
    ".htm": {"text/html", "application/xhtml+xml"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".xml": {"application/xml", "text/xml"},
    ".csv": {"text/csv"},
    ".epub": {"application/epub+zip"},
}


class _EpubTextExtractor(HTMLParser):
    _BLOCK_TAGS = {"address", "article", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "pre", "section", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg"}:
            self._ignored_depth += 1
        if not self._ignored_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if not self._ignored_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _epub_member(root: str, href: str) -> str:
    path = posixpath.normpath(posixpath.join(posixpath.dirname(root), unquote(href.split("#", 1)[0])))
    if path.startswith("../") or path == ".." or path.startswith("/"):
        raise UnsupportedSourceFormatError("EPUB contains an unsafe package path")
    return path


def _parse_epub(path: Path, name: str) -> SourceDocument:
    try:
        with ZipFile(path) as archive:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next((node for node in container.iter() if _xml_local_name(node.tag) == "rootfile"), None)
            opf_path = rootfile.attrib.get("full-path", "") if rootfile is not None else ""
            if not opf_path:
                raise UnsupportedSourceFormatError("EPUB container has no OPF package")
            opf_path = posixpath.normpath(unquote(opf_path))
            if opf_path.startswith("../") or opf_path.startswith("/"):
                raise UnsupportedSourceFormatError("EPUB package path is unsafe")
            package = ElementTree.fromstring(archive.read(opf_path))
            items = {}
            for node in package.iter():
                if _xml_local_name(node.tag) == "item":
                    item_id = node.attrib.get("id", "")
                    href = node.attrib.get("href", "")
                    if item_id and href:
                        items[item_id] = {
                            "href": _epub_member(opf_path, href),
                            "media_type": node.attrib.get("media-type", ""),
                        }
            spine_ids = [node.attrib.get("idref", "") for node in package.iter() if _xml_local_name(node.tag) == "itemref"]
            sections: list[dict[str, str]] = []
            for item_id in spine_ids:
                item = items.get(item_id)
                if not item:
                    raise UnsupportedSourceFormatError(f"EPUB spine references missing item: {item_id}")
                parser = _EpubTextExtractor()
                parser.feed(archive.read(item["href"]).decode("utf-8", errors="replace"))
                parser.close()
                text = parser.text()
                if text:
                    sections.append({"id": item_id, "href": item["href"], "media_type": item["media_type"], "text": text})
            full_text = "\n\n".join(section["text"] for section in sections)
            if not full_text:
                raise UnsupportedSourceFormatError("EPUB has no readable spine text")
            return SourceDocument(
                text=full_text,
                document={"format": "epub", "source": name, "package": opf_path, "sections": sections},
                origin="adapter",
                parser="semantica.epub",
                parser_version="1",
            )
    except (BadZipFile, KeyError, ElementTree.ParseError, UnicodeDecodeError) as exc:
        raise UnsupportedSourceFormatError(f"invalid EPUB source: {name}") from exc


def parse_source(path: Path, *, name: str, mime_type: str, force_ocr: bool) -> SourceDocument:
    """Parse one source exactly once through its admitted format adapter.

    Text files use the standard library. Structured formats use the single
    Docling adapter. Special formats require a future dedicated adapter that
    must return ``SourceDocument`` directly; they are never routed through
    ``DocumentParser`` or converted a second time by Docling.
    """

    suffix = path.suffix.lower()
    if force_ocr and suffix not in _DOCLING_SUFFIXES:
        raise UnsupportedSourceFormatError(
            f"force OCR is only supported by the Docling adapter, not {suffix}"
        )
    expected_media_types = _MEDIA_TYPES_BY_SUFFIX.get(suffix)
    if expected_media_types and mime_type not in expected_media_types:
        raise UnsupportedSourceFormatError(
            f"source mimeType {mime_type} does not match {suffix}; expected one of "
            f"{sorted(expected_media_types)}"
        )
    if suffix in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        return SourceDocument(
            text=text,
            document={"format": "plain-text" if suffix != ".md" else "markdown", "text": text, "source": name},
            origin="native",
            parser="semantica.text",
            parser_version="1",
        )
    if suffix in _DOCLING_SUFFIXES:
        # Keep the worker protocol and text-only builds independent from the
        # legacy parse package's eager imports; load Docling only for this adapter.
        from .parse.docling_parser import DoclingParser

        result = DoclingParser(enable_ocr=True, force_full_page_ocr=force_ocr, export_format="doctags").parse(
            path,
            export_format="doctags",
            include_document=True,
        )
        origin = result.get("origin")
        if origin not in {"native", "ocr", "mixed"}:
            raise UnsupportedSourceFormatError("Docling conversion did not retain text-cell provenance")
        return SourceDocument(
            text=result["plain_text"],
            document={
                "format": "docling",
                "document": result.get("document"),
                "doctags": result.get("doctags"),
                "pages": result.get("pages", []),
                "conversion_status": result.get("conversion_status", "unknown"),
                "metadata": result.get("metadata", {}),
                "source": name,
            },
            origin=origin,
            parser="docling",
            parser_version="2",
        )
    if suffix == ".epub":
        return _parse_epub(path, name)
    if suffix in _ADAPTER_PENDING_SUFFIXES:
        raise UnsupportedSourceFormatError(
            f"source format {suffix} requires a dedicated adapter that emits "
            "SourceDocument; legacy DocumentParser and second-pass Docling are not allowed"
        )
    raise UnsupportedSourceFormatError(f"unsupported source format for Semantica: {name}")
