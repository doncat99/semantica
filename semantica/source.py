"""Source identity and quality boundary; parsing belongs to DocumentParser."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
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


@lru_cache(maxsize=64)
def _processing_implementation(suffix: str, mode: str) -> dict:
    """Small immutable parser/reader recipe; never import an engine or scan a runtime."""
    root = Path(__file__).parent
    from .parse.document_contract import OFFICE_SUFFIXES, STRUCTURED_SUFFIXES
    owners = ['source.py', 'parse/document_parser.py', 'parse/document_contract.py',
        'project_document_quality.py', 'parse/document_reader.py',
        'semantic_document_reader.py', 'semantic_source_artifact.py']
    packages = []
    if suffix == '.epub':
        owners.append('parse/epub_parser.py')
    elif suffix in OFFICE_SUFFIXES:
        owners.append('project_office.py')
    elif suffix in STRUCTURED_SUFFIXES:
        if mode == 'native':
            owners.append('parse/pdf_parser.py')
            packages.append('PyMuPDF')
        elif mode == 'remote':
            owners.append('project_remote_docling.py')
            packages.append('docling-core')
        elif mode == 'local':
            owners.append('parse/docling_parser.py')
            packages.extend(('docling', 'docling-slim', 'docling-core', 'docling-ibm-models',
                'docling-parse', 'pypdfium2', 'rapidocr', 'onnxruntime', 'Pillow'))
    dependencies = {}
    for name in packages:
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    return {'owners': {name: sha256((root / name).read_bytes()).hexdigest() for name in owners},
            'dependencies': dependencies}


def normalized_processing_profile(profile: dict | None) -> dict:
    from .semantic_artifact_schema import DocumentProcessingProfile
    return DocumentProcessingProfile.model_validate(profile or {}).model_dump(mode='json', by_alias=True)


def source_processing_revision(path: Path, *, mime_type: str, force_ocr: bool,
                               document_processing: dict | None = None, name: str | None = None) -> str:
    """Bind actual inputs and installed native implementation, without a manual salt."""
    profile = normalized_processing_profile(document_processing)
    from .parse.document_contract import OFFICE_SUFFIXES, document_suffix
    suffix = document_suffix(path, name if name is not None else path.name, mime_type, False)
    recipe = {'profile': profile,
        'mimeType': mime_type, 'suffix': suffix, 'forceOcr': force_ocr,
        'implementation': _processing_implementation(suffix, profile['mode'])}
    if suffix in OFFICE_SUFFIXES:
        from .project_office import office_runtime_identity
        recipe['officeRuntime'] = office_runtime_identity()
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
