"""EPUB parsing in package spine order, without extracting ZIP members to disk."""
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
from .document_contract import UnsupportedSourceFormatError

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


def parse_epub(path: Path, name: str) -> dict:
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
            return dict(
                text=full_text,
                document={"format": "epub", "source": name, "package": opf_path, "sections": sections},
                origin="adapter",
                parser="semantica.epub",
                parser_version="1",
            )
    except (BadZipFile, KeyError, ElementTree.ParseError, UnicodeDecodeError) as exc:
        raise UnsupportedSourceFormatError(f"invalid EPUB source: {name}") from exc
