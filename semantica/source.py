"""Source identity and quality boundary; parsing belongs to DocumentParser."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from .project_document_quality import assess_document_quality
from .parse.document_contract import SourceQualityError, UnsupportedSourceFormatError

def source_content_revision(path: Path) -> str:
    """Hash immutable material bytes using the shared source identity contract."""
    from blake3 import blake3

    digest = blake3()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "b3-" + digest.hexdigest()


def source_processing_revision(path: Path, *, mime_type: str, force_ocr: bool,
                               document_processing: dict | None = None) -> str:
    """Return the explicitly configured processing identity for this profile.

    Implementation source is deliberately excluded. Behavior changes require an
    explicit processingRevision change in the published processing profile.
    """
    suffix = path.suffix.lower()
    profile = document_processing or {"mode": "local"}
    revision = profile.get("processingRevision", "semantica-document-processing-v1")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("document processing requires an explicit processingRevision")
    return revision.strip()


@dataclass(frozen=True)
class SourceDocument:
    """One adapter result consumed by the semantic snapshot pipeline."""

    text: str
    document: dict[str, Any]
    origin: Literal["native", "ocr", "mixed", "adapter", "external"]
    parser: str
    parser_version: str

    def __post_init__(self) -> None:
        self.document["quality"] = assess_document_quality(self.text, self.document)


def parse_source(path: Path, *, name: str, mime_type: str, force_ocr: bool,
                 document_processing: dict | None = None,
                 progress_callback: Callable[[Any], None] | None = None) -> SourceDocument:
    """Translate the native parsed document into the product quality contract."""
    from .parse.document_parser import DocumentParser

    result = DocumentParser().parse_document(
        path, name=name, mime_type=mime_type, force_ocr=force_ocr,
        document_processing=document_processing or {"mode": "local"},
        progress_callback=progress_callback,
    )
    return SourceDocument(**result)
