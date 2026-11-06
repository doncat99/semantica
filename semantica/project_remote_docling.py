"""Docling Serve conversion; the host job owns durable task identity."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from time import monotonic
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .semantic_worker_context import document_processing_token
from .semantic_artifact_errors import SemanticArtifactError

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_REQUEST_BYTES = 90 * 1024 * 1024
MAX_RESULT_BYTES = 128 * 1024 * 1024
MAX_TASK_RESPONSE_BYTES = 64 * 1024


class RemoteDoclingError(SemanticArtifactError):
    """Remote conversion failed; no alternate parser may be invoked."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_remote_document(result: dict) -> dict:
    """Only complete Serve documents can become accepted immutable results."""
    document = result.get("document") if isinstance(result, dict) else None
    if not isinstance(result, dict) or result.get("status") != "success" or not isinstance(document, dict):
        raise RemoteDoclingError("remote Docling result is not a successful document")
    if not isinstance(document.get("json_content"), dict):
        raise RemoteDoclingError("remote Docling result omitted native document JSON")
    if any(document.get(field) is not None for field in ("text_content", "doctags_content")):
        raise RemoteDoclingError("remote Docling returned unrequested duplicate content")
    return document


def parse_remote_docling(path: Path, *, name: str, force_ocr: bool, profile: dict,
                         wait_timeout_seconds: float = 1800,
                         cancelled: Callable[[], bool] | None = None,
                         remote_task: dict | None = None,
                         on_remote_task: Callable[[dict], None] | None = None) -> dict:
    if not math.isfinite(wait_timeout_seconds) or wait_timeout_seconds <= 0:
        raise RemoteDoclingError("remote Docling wait deadline must be positive and finite")
    deadline = monotonic() + wait_timeout_seconds
    endpoint = profile.get("endpoint", "").rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteDoclingError("remote Docling endpoint must be an absolute HTTP(S) URL without credentials, query or fragment")
    token = document_processing_token()
    if not token:
        raise RemoteDoclingError("remote Docling credential is unavailable")
    if not isinstance(remote_task, dict) or set(remote_task) - {"taskId"}:
        raise RemoteDoclingError("remote Docling requires host-owned task control; submission outcome unknown",
                                 code="REMOTE_PARSE_SUBMISSION_UNKNOWN")
    task_id = remote_task.get("taskId")
    if task_id is not None and (not isinstance(task_id, str) or not task_id.strip() or len(task_id.encode('utf-8')) > 1024):
        raise RemoteDoclingError("remote Docling task identity is invalid")
    if task_id is None and on_remote_task is None:
        raise RemoteDoclingError("remote Docling submission requires host task progress persistence")
    opener = build_opener(_NoRedirect())

    def remaining() -> float:
        if cancelled is not None and cancelled():
            raise RemoteDoclingError("remote Docling wait cancelled; task state retained")
        budget = deadline - monotonic()
        if budget <= 0:
            raise RemoteDoclingError(f"remote Docling wait deadline exceeded; task {task_id or 'unknown'} retained for resume")
        return budget

    def request(route: str, body: dict | None = None) -> dict:
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        if encoded is not None and len(encoded) > MAX_REQUEST_BYTES:
            raise RemoteDoclingError('remote Docling request exceeded byte budget')
        timeout = min(75, remaining())
        try:
            headers = {"Content-Type": "application/json", **({"X-OntoScience-Auth-Token": token} if token else {})}
            with opener.open(Request(endpoint + route, data=encoded, headers=headers), timeout=timeout) as response:
                limit = MAX_RESULT_BYTES if route.startswith('/v1/result/') else MAX_TASK_RESPONSE_BYTES
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise RemoteDoclingError('remote Docling response exceeded byte budget; task state retained')
                result = json.loads(payload)
        except RemoteDoclingError:
            raise
        except HTTPError as exc:
            raise RemoteDoclingError(f"remote Docling HTTP {exc.code}; task state retained") from None
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise RemoteDoclingError("remote Docling transport or JSON response failed; task state retained") from None
        if not isinstance(result, dict):
            raise RemoteDoclingError("remote Docling returned a non-object response")
        return result

    # {} is a one-time submission grant after the existing host job persisted
    # its submitting state. A resumed job must supply its accepted task ID.
    if task_id is None:
        remaining()
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise RemoteDoclingError('remote Docling source exceeded upload byte budget')
        with path.open('rb') as stream:
            content = stream.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise RemoteDoclingError('remote Docling source exceeded upload byte budget')
        submitted = request("/v1/convert/source/async", {
            "sources": [{"kind": "file", "filename": name,
                         "base64_string": base64.b64encode(content).decode("ascii")}],
            "options": {"to_formats": ["json"], "pipeline": "standard", "do_ocr": True,
                        "force_ocr": force_ocr, "abort_on_error": True},
            "target": {"kind": "inbody"},
        })
        del content
        task_id = submitted.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip() or len(task_id.encode('utf-8')) > 1024:
            raise RemoteDoclingError("remote Docling submit outcome unknown: invalid task_id")
        on_remote_task({"taskId": task_id})
    encoded_id = quote(task_id, safe="")
    while True:
        status = request(f"/v1/status/poll/{encoded_id}?wait=30")
        if status.get("task_id") != task_id:
            raise RemoteDoclingError("remote Docling task identity changed")
        value = status.get("task_status")
        if value == "success":
            break
        if value not in {"pending", "started"}:
            raise RemoteDoclingError(f"remote Docling task ended without complete conversion: {value}")
    result = request(f"/v1/result/{encoded_id}")
    document = validate_remote_document(result)
    from docling_core.types.doc import DoclingDocument
    try:
        text = DoclingDocument.model_validate(document["json_content"]).export_to_text()
    except Exception as exc:
        raise RemoteDoclingError("remote Docling returned invalid native document JSON") from exc
    return {"text": text, "document": {
        "format": "docling", "document": document["json_content"],
        "pages": [], "conversion_status": "success", "source": name,
        "metadata": {"text_origin": "unreported", "remote_task_id": task_id, "remote_cancellation": "unsupported"},
    }}
