"""Source identity and quality boundary; parsing belongs to DocumentParser."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from hashlib import sha256
import json
from .project_document_quality import assess_document_quality
from .parse.document_contract import SourceQualityError, UnsupportedSourceFormatError

def source_content_revision(path: Path) -> str:
    """Hash immutable material bytes using the shared source identity contract."""
    from blake3 import blake3
    from .semantic_worker_context import check_query_cancellation

    digest = blake3()
    check_query_cancellation()
    buffer = bytearray(1024 * 1024)
    view = memoryview(buffer)
    with path.open("rb") as stream:
        while True:
            check_query_cancellation()
            count = stream.readinto(buffer)
            if not count:
                break
            digest.update(view[:count])
        check_query_cancellation()
    return "b3-" + digest.hexdigest()


def normalized_processing_profile(profile: dict | None) -> dict:
    from .semantic_artifact_schema import DocumentProcessingProfile
    return DocumentProcessingProfile.model_validate(profile or {}).model_dump(mode='json', by_alias=True)


def source_processing_revision(path: Path, *, mime_type: str, force_ocr: bool,
                               document_processing: dict | None = None, name: str | None = None) -> str:
    """Bind parsing inputs and the representation contract, never implementation bytes."""
    profile = normalized_processing_profile(document_processing)
    from .parse.document_contract import document_suffix
    suffix = document_suffix(path, name if name is not None else path.name, mime_type, False)
    recipe = {'profile': profile,
        'mimeType': mime_type, 'suffix': suffix, 'forceOcr': force_ocr,
        'representationContract': 'semantica.parsed-source.v3'}
    return 'sha256:' + sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class SourceDocument:
    """One native parser result with transient text for computation."""

    text: str
    document: dict[str, Any]
    origin: Literal["native", "ocr", "mixed", "adapter", "external"]
    parser: str
    parser_version: str

    def __post_init__(self) -> None:
        self.document["quality"] = assess_document_quality(self.text, self.document)


def parse_source(path: Path, *, name: str, mime_type: str, force_ocr: bool,
                 document_processing: dict | None = None,
                 progress_callback: Callable[[Any], None] | None = None,
                 remote_task: dict | None = None,
                 on_remote_task: Callable[[dict], None] | None = None) -> SourceDocument:
    """Translate the native parsed document into the product quality contract."""
    from .parse.document_parser import DocumentParser

    result = DocumentParser().parse_document(
        path, name=name, mime_type=mime_type, force_ocr=force_ocr,
        document_processing=document_processing or {"mode": "local"},
        progress_callback=progress_callback,
        remote_task=remote_task, on_remote_task=on_remote_task,
    )
    return SourceDocument(**result)
