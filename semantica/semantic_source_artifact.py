"""Native parsed-source artifacts shared by the worker and semantic builder."""
from __future__ import annotations

import json
import logging
import re
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from .semantic_artifact_errors import DocumentQualityError, SemanticArtifactError
from .semantic_artifact_schema import (BindParsedSourceRequest, ParseSourceRequest,
    ParsedSourceRef, SourceBuildInput, stable_digest)
from .source import (SourceQualityError, UnsupportedSourceFormatError, parse_source,
    source_content_revision, source_processing_revision, normalized_processing_profile)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_file(path: Path) -> str:
    from .semantic_worker_context import check_query_cancellation
    digest = sha256()
    check_query_cancellation()
    buffer = bytearray(1024 * 1024)
    view = memoryview(buffer)
    with path.open('rb') as stream:
        while True:
            check_query_cancellation()
            count = stream.readinto(buffer)
            if not count:
                break
            digest.update(view[:count])
        check_query_cancellation()
    return 'sha256:' + digest.hexdigest()


def _native_text(document: dict) -> str:
    """Build-time text is transient; the parser's native representation owns content."""
    if document.get('format') == 'docling':
        from .parse.document_reader import native_scalar_projection
        return native_scalar_projection(document)[0]
    if document.get('format') == 'pdf-text':
        return '\n'.join(page['text'] for page in document['pages'])
    if document.get('format') == 'text':
        return document['text']
    if document.get('format') in {'epub', 'flat-odf'}:
        return '\n\n'.join(section['text'] for section in document['sections'])
    raise SemanticArtifactError('unsupported native parsed source format')


def _native_grounding_ranges(document: dict, text: str) -> list[dict]:
    """Prove transient text offsets against the reader's native scalar addresses.

    Native addresses, never reverse substring search, establish correspondence.
    """
    kind = document.get('format')
    if kind == 'text':
        parts, separator = [(document['text'], '#/document/text')], ''
    elif kind == 'pdf-text':
        parts, separator = [(p['text'], f'#/document/pages/{i}/text')
                            for i, p in enumerate(document['pages'])], '\n'
    elif kind in {'epub', 'flat-odf'}:
        parts, separator = [(s['text'], f'#/document/sections/{i}/text')
                            for i, s in enumerate(document['sections'])], '\n\n'
    elif kind == 'docling':
        from .parse.document_reader import native_scalar_projection
        projected, ranges, _, _ = native_scalar_projection(document)
        if projected != text:
            raise SemanticArtifactError('native scalar view differs from extraction text', code='NATIVE_GROUNDING_UNSUPPORTED')
        return ranges
    else:
        raise SemanticArtifactError('unsupported native grounding format', code='NATIVE_GROUNDING_UNSUPPORTED')
    if separator.join(value for value, _ in parts) != text:
        raise SemanticArtifactError('native serialization differs from extraction text', code='NATIVE_GROUNDING_UNSUPPORTED')
    ranges, offset = [], 0
    for value, ref in parts:
        if ref and value:
            ranges.append(dict(nativeRef=ref, start=0, end=len(value),
                               windowStart=offset, windowEnd=offset + len(value),
                               **({'joinBefore': separator} if ranges and ranges[-1]['windowEnd'] + len(separator) == offset else {})))
        offset += len(value) + len(separator)
    return ranges


def _window_native_ranges(ranges: list[dict], start: int, end: int) -> list[dict]:
    """Clip structural proof to one bounded extraction window; no body copies."""
    result = []
    if isinstance(ranges, _NativeSourceRanges):
        selected = ranges.window(start, end)
    else:
        index = bisect_right(ranges, start, key=lambda value: value['windowEnd'])
        selected = (ranges[position] for position in range(index, len(ranges)))
    for value in selected:
        if value['windowStart'] >= end:
            break
        lo, hi = max(start, value['windowStart']), min(end, value['windowEnd'])
        if lo < hi:
            result.append(dict(nativeRef=value['nativeRef'],
                start=value['start'] + lo - value['windowStart'],
                end=value['start'] + hi - value['windowStart'],
                windowStart=lo - start, windowEnd=hi - start,
                **({'joinBefore': value['joinBefore']} if result and lo == value['windowStart']
                   and 'joinBefore' in value
                   and result[-1]['windowEnd'] + len(value['joinBefore']) == lo - start else {})))
            if len(result) > 128:
                raise SemanticArtifactError('native grounding range budget exceeded', code='NATIVE_GROUNDING_UNSUPPORTED')
    return result


def _safe_id(value: str) -> str:
    return value.replace(" ", "_").replace("/", "_")[:100]


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return _digest_bytes(encoded)


def _parse_source(source: Any, force_ocr: bool, document_processing: dict | None = None,
                  *, admit_quality: bool = True,
                  progress_callback: Callable[[Any], None] | None = None,
                  remote_task: dict | None = None,
                  on_remote_task: Callable[[dict], None] | None = None) -> tuple[str, dict[str, Any], str, str, str, str]:
    path = Path(source.file_path).resolve()
    if not path.is_file():
        raise SemanticArtifactError(f"source is not a file: {source.source_id}")
    content_hash = source_content_revision(path)
    if source.material_revision != content_hash:
        raise SemanticArtifactError(f"source material revision does not match immutable bytes: {source.source_id}")
    profile = document_processing or {"mode": "local"}
    try:
        parsed = parse_source(
            path,
            name=source.name,
            mime_type=source.mime_type,
            force_ocr=force_ocr,
            document_processing=profile,
            **({"remote_task": remote_task, "on_remote_task": on_remote_task}
               if profile.get("mode") == "remote" else {}),
            **({"progress_callback": progress_callback} if progress_callback is not None else {}),
        )
    except SourceQualityError as exc:
        raise DocumentQualityError(str(exc), code="DOCUMENT_QUALITY_ERROR") from exc
    except UnsupportedSourceFormatError as exc:
        raise SemanticArtifactError(str(exc)) from exc
    document = {key: value for key, value in parsed.document.items() if key != 'source'}
    document.update(content_hash=content_hash, mime_type=source.mime_type)
    document["representation_revision"] = _representation_revision(source, force_ocr, content_hash, parsed.parser, parsed.parser_version, parsed.origin, document)
    result = (_native_text(document), document, parsed.origin, content_hash, parsed.parser, parsed.parser_version)
    if admit_quality:
        _admit_document_quality(document, force_ocr)
    return result


def _admit_document_quality(document: dict, force_ocr: bool) -> None:
    """Retain local transcription findings without rejecting readable source content."""
    quality = document.get("quality", {})
    if quality.get("status") == "needs_review":
        safe_codes = {"formula_transcription_missing", "fragmented_cjk_encoding", "unmapped_characters"}
        codes = sorted({item["code"] for item in quality["issues"] if item.get("code") in safe_codes})
        logging.getLogger(__name__).warning(
            "Document transcription needs review; qualityIssueCodes=%s forceOcr=%s; continuing with located findings retained",
            codes, force_ocr)


def _representation_revision(source: Any, force_ocr: bool, content_hash: str, parser: str, parser_version: str, origin: str, document: dict) -> str:
    return stable_digest({"sourceRevision": source.material_revision, "contentHash": content_hash,
        "forceOcr": force_ocr,
        "document": {key: value for key, value in document.items() if key not in {"metadata", "representation_revision"}}})


def _has_representation_identity(document: dict) -> bool:
    # The verified artifact digest protects persisted identity, not today's producer formula.
    revision = document.get("representation_revision")
    return (isinstance(revision, str) and revision.startswith("sha256:") and len(revision) == 71
            and all(c in "0123456789abcdef" for c in revision[7:]))


def parse_source_artifact(request: ParseSourceRequest, *, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, str]:
    """Materialize one source revision before any semantic/model work."""
    failed_pages = 0

    def on_conversion_progress(event: Any) -> None:
        nonlocal failed_pages
        if event.kind != "page_completed":
            return
        # Docling counts completed work, including failed pages, not page order.
        failed_pages += int(not event.success)
        progress({"stage": "recognizing" if request.force_ocr else "document_parsing",
                  "percent": round(event.completed_pages / max(1, event.total_pages) * 70),
                  "metadata": {"sourceId": request.source.source_id,
                               "completedPages": event.completed_pages,
                               "totalPages": event.total_pages, "failedPages": failed_pages}})

    profile = request.document_processing.model_dump(mode="json", by_alias=True)
    def on_remote_task(task: dict) -> None:
        if progress is None:
            raise SemanticArtifactError('remote conversion requires host task progress persistence')
        progress({"stage": "document_parsing", "percent": 1,
                  "detail": "Remote conversion submitted", "remoteTask": task})
    text, document, origin, content_hash, parser, parser_version = _parse_source(
        request.source, request.force_ocr, profile, admit_quality=False,
        **({"remote_task": request.remote_task.model_dump(by_alias=True, exclude_none=True)
            if request.remote_task is not None else None, "on_remote_task": on_remote_task}
           if profile.get("mode") == "remote" else {}),
        **({"progress_callback": on_conversion_progress} if progress is not None else {}))
    payload = {
        "protocol": "semantica.parsed-source.v3",
        "materialRevision": content_hash,
        "mimeType": request.source.mime_type,
        "forceOcr": request.force_ocr,
        "documentProcessing": profile,
        "processingRevision": source_processing_revision(Path(request.source.file_path),
            name=request.source.name, mime_type=request.source.mime_type, force_ocr=request.force_ocr, document_processing=profile),
        "parser": parser,
        "parserVersion": parser_version,
        "origin": origin,
        "document": document,
    }
    return _write_parsed_source_artifact(request, payload)


def _source_header_receipt(header, source_id):
    """Expose only the current host receipt, never reader-private metadata."""
    result = {key: header[key] for key in ('protocol', 'materialRevision', 'contentHash',
        'representationRevision', 'forceOcr', 'mimeType', 'parser', 'parserVersion', 'origin',
        'documentProcessing', 'processingRevision') if key in header}
    result['sourceId'] = source_id
    if isinstance(header.get('quality'), dict):
        result['quality'] = {key: header['quality'][key] for key in ('version', 'status', 'issueCount')}
    return result


def _write_parsed_source_artifact(request: ParseSourceRequest, payload: dict[str, Any]) -> dict[str, str]:
    document = payload["document"]
    content_hash = payload["materialRevision"]
    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"parsed-{_safe_id(request.source.source_id)}.json"
    from .semantic_document_reader import write_reader_artifact
    digest, reader_digest, reader_header = write_reader_artifact(path, payload)
    return {"artifactPath": str(path), "artifactDigest": digest, "sourceId": request.source.source_id,
            "sourceHeader": _source_header_receipt({**payload, "contentHash": document['content_hash'],
                "representationRevision": document['representation_revision'],
                **({'quality': {'version': document['quality']['version'], 'status': document['quality']['status'],
                    'issueCount': len(document['quality']['issues'])}} if isinstance(document.get('quality'), dict) else {}),
                }, request.source.source_id),
            "readerIndexPath": str(path.with_suffix('.reader.sqlite')), "readerIndexDigest": reader_digest,
            "readerHeader": reader_header,
            "materialRevision": content_hash, "representationRevision": document["representation_revision"],
            **({"processingRevision": payload["processingRevision"]} if "processingRevision" in payload else {}),
            "representationId": f"representation:{_safe_id(request.source.source_id)}:{document['representation_revision'][7:]}"}


def bind_parsed_source_artifact(request: BindParsedSourceRequest) -> dict[str, str]:
    """Bind a verified parse to another source identity without converting bytes again."""
    source = request.source
    path = Path(request.parsed_artifact_path).resolve()
    if not path.is_file() or _digest_file(path) != request.parsed_artifact_digest:
        raise SemanticArtifactError("parsed source artifact digest is invalid")
    if source_content_revision(Path(source.file_path).resolve()) != source.material_revision:
        raise SemanticArtifactError("target source material revision does not match immutable bytes")
    import sqlite3
    from contextlib import closing
    from .semantic_document_reader import INDEX_FORMAT
    index = Path(request.parsed_reader_index_path).resolve()
    if not index.is_file() or _digest_file(index) != request.parsed_reader_index_digest:
        raise SemanticArtifactError('parsed source reader index digest is invalid')
    with closing(sqlite3.connect(index.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        metadata = dict(db.execute("SELECT key,value FROM metadata WHERE key IN ('format','artifactDigest','header','readerHeader') AND length(CAST(value AS BLOB))<=4096"))
    if metadata.get('format') != INDEX_FORMAT or metadata.get('artifactDigest') != request.parsed_artifact_digest:
        raise SemanticArtifactError('parsed source reader index is invalid')
    try:
        payload = json.loads(metadata['header'])
        reader_header = json.loads(metadata['readerHeader'])
    except (KeyError, ValueError) as exc:
        raise SemanticArtifactError('parsed source reader metadata is invalid') from exc
    profile = request.document_processing.model_dump(mode="json", by_alias=True)
    if not isinstance(payload, dict) or any((
        payload.get("protocol") != "semantica.parsed-source.v3",
        payload.get("materialRevision") != source.material_revision,
        payload.get("mimeType") != source.mime_type,
        payload.get("forceOcr") is not request.force_ocr,
        payload.get('documentProcessing') != profile,
        not isinstance(payload.get('processingRevision'), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', payload['processingRevision']),
    )):
        raise SemanticArtifactError("parsed source content or processing profile changed")
    if payload.get('contentHash') != source.material_revision or not _has_representation_identity(
            {'representation_revision': payload.get('representationRevision')}):
        raise SemanticArtifactError("parsed source representation revision is invalid")
    return {'artifactPath': str(path), 'artifactDigest': request.parsed_artifact_digest,
        'sourceId': source.source_id, 'materialRevision': source.material_revision,
        'representationRevision': payload['representationRevision'],
        'representationId': f"representation:{_safe_id(source.source_id)}:{payload['representationRevision'][7:]}",
        'processingRevision': payload['processingRevision'],
        'sourceHeader': _source_header_receipt(payload, source.source_id),
        'readerIndexPath': str(index), 'readerIndexDigest': _digest_file(index),
        'readerHeader': reader_header}


def _source_reader_request(source, reference, field='source_windows'):
    from .explorer.search_index import _file_identity
    from .semantic_query_schema import DocumentReaderRequest
    path = Path(reference.artifact_path).resolve()
    index = Path(reference.reader_index_path).resolve()
    if not index.is_file() or _digest_file(index) != reference.reader_index_digest:
        raise SemanticArtifactError(f'parsed source reader index digest is invalid: {source.source_id}')
    def installed(file, digest, kind):
        return dict(path=str(file), digest=digest, kind=kind, mediaType='application/json',
            installation=dict(digest=digest, identity=':'.join(map(str, _file_identity(file)))))
    return DocumentReaderRequest.model_validate(dict(id='build:'+source.source_id,
        sourceId=source.source_id, materialRevision=source.material_revision,
        representationRevision=reference.representation_revision,
        artifact=installed(path, reference.artifact_digest, 'document-representation'),
        readerIndex=installed(index, reference.reader_index_digest, 'document-reader-index'),
        selection=dict(field=field, maxBytes=262144)))


class _NativeSourceText:
    """An admitted native source's scalar range, never a complete body string."""
    def __init__(self, reader, length):
        self.reader, self.length = reader, length

    def __len__(self):
        return self.length

    def __getitem__(self, key):
        from .semantic_document_reader import read_source_text_range
        if isinstance(key, slice):
            start, end, step = key.indices(self.length)
            if step != 1:
                raise ValueError('native source ranges require a contiguous slice')
        else:
            start = key if key >= 0 else self.length + key
            if not 0 <= start < self.length:
                raise IndexError(key)
            end = start + 1
        if end <= start:
            return ''
        return read_source_text_range(self.reader, start=start, end=end)['item']['text']


class _NativeSourceWindows:
    def __init__(self, text, ranges):
        self.text, self.ranges = text, ranges

    def __len__(self):
        return len(self.ranges)

    def __getitem__(self, index):
        start, end = self.ranges[index]
        return start, end, self.text[start:end]


class _NativeWindowRanges:
    """Address only the requested window; admission retains no document-wide list."""
    def __init__(self, reader, count):
        self.reader, self.count = reader, count

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        from .semantic_document_reader import read_source_window_ranges
        if not isinstance(index, int):
            raise TypeError('native window addresses require an integer index')
        index = index if index >= 0 else self.count + index
        if not 0 <= index < self.count:
            raise IndexError(index)
        page = read_source_window_ranges(self.reader, after=index - 1, limit=1)
        item = page['items'][0]
        return item['start'], item['end']


class _NativeSourceRanges:
    """Stream only scalar address records intersecting the active window."""
    def __init__(self, reader):
        self.reader = reader

    def window(self, start, end):
        from .semantic_document_reader import read_source_native_ranges
        after = -1
        while True:
            page = read_source_native_ranges(self.reader, after=after, start=start, end=end)
            yield from page['items']
            after = page['nextCursor']
            if after is None:
                return


class _NativeSourceLocations:
    def __init__(self, reader):
        self.reader = reader

    def pages(self, **query):
        from .semantic_document_reader import read_source_locations
        after = -1
        while True:
            page = read_source_locations(self.reader, after=after,
                limit=128 if query.get('hydrate') is False else 1, **query)
            yield from page['items']
            after = page['nextCursor']
            if after is None:
                break

    def __iter__(self):
        return self.pages()

    def context(self, start, end):
        return self.pages(start=start, end=end, context=True)

    def context_addresses(self, start, end):
        return self.pages(start=start, end=end, context=True, hydrate=False)

    def hydrate(self, address):
        from .semantic_document_reader import read_source_locations
        result = read_source_locations(self.reader,
            after=address['sourceLocationOrdinal'] - 1, limit=1)
        if not result['items']:
            raise ValueError('native grounding location address is missing')
        return result['items'][0]

    def locate(self, start, end):
        from .semantic_document_reader import locate_source_range
        return locate_source_range(self.reader, start=start, end=end, include_quote=False)['item']

    def by_ref(self, ref):
        # Producer reference maps used the last original record on duplicate refs.
        selected = None
        for item in self.pages(ref=ref):
            selected = item
        return selected


@dataclass
class NativeParsedSource:
    text: _NativeSourceText
    document: dict
    origin: str
    content_hash: str
    parser: str
    parser_version: str
    locations: _NativeSourceLocations
    native_ranges: _NativeSourceRanges
    windows: _NativeSourceWindows
    reader: Any
    page_count: int | None


def _load_parsed_source(source: Any, ref: ParsedSourceRef, force_ocr: bool, profile: dict) -> NativeParsedSource:
    profile = normalized_processing_profile(profile)
    path = Path(ref.artifact_path).resolve()
    if not path.is_file() or _digest_file(path) != ref.artifact_digest:
        raise SemanticArtifactError(f"parsed source artifact digest is invalid: {source.source_id}")
    if source_content_revision(Path(source.file_path).resolve()) != source.material_revision:
        raise SemanticArtifactError(f"source material revision does not match immutable bytes: {source.source_id}")
    from .semantic_document_reader import read_source_header
    reader = _source_reader_request(source, ref)
    try:
        payload = read_source_header(reader)['header']
    except ValueError as error:
        raise SemanticArtifactError(f'parsed source identity or representation revision changed: {source.source_id}') from error
    if not isinstance(payload, dict) or any((
        payload.get("protocol") != "semantica.parsed-source.v3",
        ref.source_id != source.source_id,
        payload.get("materialRevision") != source.material_revision,
        payload.get("mimeType") != source.mime_type,
        payload.get("forceOcr") is not force_ocr,
        payload.get('documentProcessing') != profile,
        not isinstance(payload.get('processingRevision'), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', payload['processingRevision']),
    )):
        raise SemanticArtifactError(f"parsed source identity or processing profile changed: {source.source_id}")
    document = dict(format=payload.get('format'), content_hash=payload.get('contentHash'),
        mime_type=payload.get('documentMimeType'), representation_revision=payload.get('representationRevision'))
    if 'quality' in payload:
        quality = payload['quality']
        document['quality'] = {**quality, 'issues': [{'code': code} for code in quality.get('issueCodes', [])]}
    origin, parser, version = payload.get("origin"), payload.get("parser"), payload.get("parserVersion")
    if not isinstance(document, dict) or not all(isinstance(value, str) for value in (origin, parser, version)):
        raise SemanticArtifactError(f"parsed source document is invalid: {source.source_id}")
    if (document.get("content_hash") != source.material_revision or document.get("mime_type") != source.mime_type
        or not _has_representation_identity(document)
        or document.get("representation_revision") != ref.representation_revision):
        raise SemanticArtifactError(f"parsed source representation revision changed: {source.source_id}")
    _admit_document_quality(document, force_ocr)
    text = _NativeSourceText(reader, payload['sourceCharCount'])
    windows = _NativeWindowRanges(reader, payload['sourceWindowCount'])
    return NativeParsedSource(text, document, origin, source.material_revision, parser, version,
        _NativeSourceLocations(reader), _NativeSourceRanges(reader),
        _NativeSourceWindows(text, windows), reader, payload.get('documentPageCount'))
