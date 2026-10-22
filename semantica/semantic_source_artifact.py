"""Native parsed-source artifacts shared by the worker and semantic builder."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from .semantic_artifact_errors import DocumentQualityError, SemanticArtifactError
from .semantic_artifact_schema import (BindParsedSourceRequest, ParseSourceRequest,
    ParsedSourceRef, SourceBuildInput, stable_digest)
from .source import (SourceQualityError, UnsupportedSourceFormatError, parse_source,
    source_content_revision, source_processing_revision)
from .project_checkpoint import active_checkpoint


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _safe_id(value: str) -> str:
    return value.replace(" ", "_").replace("/", "_")[:100]


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return _digest_bytes(encoded)


def _parse_source(source: Any, force_ocr: bool, document_processing: dict | None = None,
                  *, admit_quality: bool = True) -> tuple[str, dict[str, Any], str, str, str, str]:
    path = Path(source.file_path).resolve()
    if not path.is_file():
        raise SemanticArtifactError(f"source is not a file: {source.source_id}")
    content_hash = source_content_revision(path)
    if source.material_revision != content_hash:
        raise SemanticArtifactError(f"source material revision does not match immutable bytes: {source.source_id}")
    checkpoint = active_checkpoint.get()
    cache_key = {"sourceId": source.source_id, "contentHash": content_hash, "forceOcr": force_ocr, "documentProcessing": document_processing}
    cached = checkpoint.read("document", cache_key) if checkpoint else None
    if cached is not None:
        if admit_quality:
            _admit_document_quality(source.source_id, cached[1], force_ocr)
        return tuple(cached)
    try:
        parsed = parse_source(
            path,
            name=source.name,
            mime_type=source.mime_type,
            force_ocr=force_ocr,
            document_processing=document_processing,
        )
    except SourceQualityError as exc:
        raise DocumentQualityError(str(exc), code="DOCUMENT_QUALITY_ERROR") from exc
    except UnsupportedSourceFormatError as exc:
        raise SemanticArtifactError(str(exc)) from exc
    document = {**parsed.document, "text": parsed.text, "content_hash": content_hash, "mime_type": source.mime_type}
    document["representation_revision"] = _representation_revision(source, force_ocr, content_hash, parsed.parser, parsed.parser_version, parsed.origin, document)
    result = (parsed.text, document, parsed.origin, content_hash, parsed.parser, parsed.parser_version)
    if checkpoint:
        checkpoint.write("document", cache_key, result)
    if admit_quality:
        _admit_document_quality(source.source_id, document, force_ocr)
    return result


def _admit_document_quality(document: dict, force_ocr: bool) -> None:
    quality = document.get("quality", {})
    if quality.get("status") == "needs_review":
        safe_codes = {"formula_transcription_missing", "fragmented_cjk_encoding", "unmapped_characters"}
        codes = sorted({item["code"] for item in quality["issues"] if item.get("code") in safe_codes})
        action = "OCR repair did not satisfy document quality admission" if force_ocr else "explicit OCR repair or source correction required"
        raise DocumentQualityError("Document quality admission failed; " + action, code="DOCUMENT_QUALITY_ERROR",
            diagnostic={"origin": "document_quality", "qualityIssueCodes": codes, "forceOcr": force_ocr})


def _representation_revision(source: Any, force_ocr: bool, content_hash: str, parser: str, parser_version: str, origin: str, document: dict) -> str:
    return stable_digest({"sourceRevision": source.material_revision, "contentHash": content_hash,
        "parser": parser, "parserVersion": parser_version, "forceOcr": force_ocr, "origin": origin,
        "document": {key: value for key, value in document.items() if key not in {"metadata", "representation_revision"}}})


def parse_source_artifact(request: ParseSourceRequest) -> dict[str, str]:
    """Materialize one source revision before any semantic/model work."""
    profile = request.document_processing.model_dump(mode="json", by_alias=True)
    text, document, origin, content_hash, parser, parser_version = _parse_source(
        request.source, request.force_ocr, profile, admit_quality=False)
    payload = {
        "protocol": "semantica.parsed-source.v2",
        "sourceId": request.source.source_id,
        "materialRevision": content_hash,
        "name": request.source.name,
        "mimeType": request.source.mime_type,
        "forceOcr": request.force_ocr,
        "documentProcessing": profile,
        "processingRevision": source_processing_revision(Path(request.source.file_path),
            mime_type=request.source.mime_type, force_ocr=request.force_ocr, document_processing=profile),
        "parser": parser,
        "parserVersion": parser_version,
        "origin": origin,
        "document": document,
    }
    return _write_parsed_source_artifact(request, payload)


def _write_parsed_source_artifact(request: ParseSourceRequest, payload: dict[str, Any]) -> dict[str, str]:
    document = payload["document"]
    content_hash = payload["materialRevision"]
    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"parsed-{_safe_id(request.source.source_id)}.json"
    digest = _write_json(path, payload)
    return {"artifactPath": str(path), "artifactDigest": digest, "sourceId": request.source.source_id,
            "materialRevision": content_hash, "representationRevision": document["representation_revision"],
            "processingRevision": payload["processingRevision"],
            "representationId": f"representation:{_safe_id(request.source.source_id)}:{document['representation_revision'][7:]}"}


def bind_parsed_source_artifact(request: BindParsedSourceRequest) -> dict[str, str]:
    """Bind a verified parse to another source identity without converting bytes again."""
    source = request.source
    path = Path(request.parsed_artifact_path).resolve()
    if not path.is_file() or _digest_file(path) != request.parsed_artifact_digest:
        raise SemanticArtifactError("parsed source artifact digest is invalid")
    if source_content_revision(Path(source.file_path).resolve()) != source.material_revision:
        raise SemanticArtifactError("target source material revision does not match immutable bytes")
    try:
        payload = json.loads(path.read_bytes())
    except ValueError as exc:
        raise SemanticArtifactError("parsed source artifact is invalid JSON") from exc
    profile = request.document_processing.model_dump(mode="json", by_alias=True)
    if not isinstance(payload, dict) or any((
        payload.get("protocol") != "semantica.parsed-source.v2",
        payload.get("materialRevision") != source.material_revision,
        payload.get("mimeType") != source.mime_type,
        payload.get("forceOcr") is not request.force_ocr,
        payload.get("documentProcessing") != profile,
        payload.get("processingRevision") != source_processing_revision(Path(source.file_path),
            mime_type=source.mime_type, force_ocr=request.force_ocr, document_processing=profile),
    )):
        raise SemanticArtifactError("parsed source content or processing profile changed")
    document = payload.get("document")
    origin, parser, version = payload.get("origin"), payload.get("parser"), payload.get("parserVersion")
    if (not isinstance(document, dict) or not isinstance(document.get("text"), str)
            or not all(isinstance(value, str) for value in (origin, parser, version))
            or document.get("content_hash") != source.material_revision
            or document.get("mime_type") != source.mime_type):
        raise SemanticArtifactError("parsed source document is invalid")
    original = SourceBuildInput.model_validate({
        "filePath": source.file_path,
        "materialRevision": source.material_revision,
        "mimeType": source.mime_type,
        "name": payload.get("name"),
        "sourceId": payload.get("sourceId"),
    })
    if (document.get("source") != original.name
            or document.get("representation_revision") != _representation_revision(
                original, request.force_ocr, source.material_revision, parser, version, origin, document)):
        raise SemanticArtifactError("parsed source representation revision is invalid")
    rebound_document = {**document, "source": source.name}
    rebound_document["representation_revision"] = _representation_revision(
        source, request.force_ocr, source.material_revision, parser, version, origin, rebound_document)
    rebound = {**payload, "sourceId": source.source_id, "name": source.name, "document": rebound_document}
    _admit_document_quality(source.source_id, rebound_document, request.force_ocr)
    return _write_parsed_source_artifact(request, rebound)


def _load_parsed_source(source: Any, ref: ParsedSourceRef, force_ocr: bool, profile: dict) -> tuple[str, dict, str, str, str, str]:
    path = Path(ref.artifact_path).resolve()
    if not path.is_file() or _digest_file(path) != ref.artifact_digest:
        raise SemanticArtifactError(f"parsed source artifact digest is invalid: {source.source_id}")
    if source_content_revision(Path(source.file_path).resolve()) != source.material_revision:
        raise SemanticArtifactError(f"source material revision does not match immutable bytes: {source.source_id}")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict) or any((
        payload.get("protocol") != "semantica.parsed-source.v2",
        payload.get("sourceId") != source.source_id or ref.source_id != source.source_id,
        payload.get("materialRevision") != source.material_revision,
        payload.get("name") != source.name,
        payload.get("mimeType") != source.mime_type,
        payload.get("forceOcr") is not force_ocr,
        payload.get("documentProcessing") != profile,
        payload.get("processingRevision") != source_processing_revision(Path(source.file_path),
            mime_type=source.mime_type, force_ocr=force_ocr, document_processing=profile),
    )):
        raise SemanticArtifactError(f"parsed source identity or processing profile changed: {source.source_id}")
    document = payload.get("document")
    origin, parser, version = payload.get("origin"), payload.get("parser"), payload.get("parserVersion")
    if not isinstance(document, dict) or not isinstance(document.get("text"), str) or not all(isinstance(value, str) for value in (origin, parser, version)):
        raise SemanticArtifactError(f"parsed source document is invalid: {source.source_id}")
    if (document.get("content_hash") != source.material_revision or document.get("mime_type") != source.mime_type
        or document.get("representation_revision") != _representation_revision(source, force_ocr, source.material_revision, parser, version, origin, document)):
        raise SemanticArtifactError(f"parsed source representation revision changed: {source.source_id}")
    _admit_document_quality(source.source_id, document, force_ocr)
    return document["text"], document, origin, source.material_revision, parser, version
