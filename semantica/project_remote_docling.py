"""Durable Docling Serve async conversion inside the source parsing owner."""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .project_checkpoint import active_checkpoint


class RemoteDoclingError(ValueError):
    """Remote conversion failed; no alternate parser may be invoked."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_remote_docling(path: Path, *, name: str, force_ocr: bool, profile: dict) -> dict:
    endpoint = profile.get("endpoint", "").rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteDoclingError("remote Docling endpoint must be an absolute HTTP(S) URL without credentials, query or fragment")
    token = os.environ.get(profile.get("authorizationEnv", ""))
    if token is None:
        raise RemoteDoclingError("remote Docling credential is unavailable")
    checkpoint = active_checkpoint.get()
    if checkpoint is None:
        raise RemoteDoclingError("remote Docling requires a durable snapshot checkpoint")
    content = path.read_bytes()
    key = {"contentHash": sha256(content).hexdigest(), "name": name, "forceOcr": force_ocr, "profile": profile}
    state = checkpoint.read("remote-docling", key)
    opener = build_opener(_NoRedirect())

    def request(route: str, body: dict | None = None) -> dict:
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            headers = {"Content-Type": "application/json", **({"X-Api-Key": token} if token else {})}
            with opener.open(Request(endpoint + route, data=encoded, headers=headers), timeout=75) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise RemoteDoclingError(f"remote Docling HTTP {exc.code}; task state retained") from None
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise RemoteDoclingError("remote Docling transport or JSON response failed; task state retained") from None
        if not isinstance(result, dict):
            raise RemoteDoclingError("remote Docling returned a non-object response")
        return result

    if state is None:
        # Serve has no idempotency key. A lost submit response must never create
        # a second conversion on restart.
        checkpoint.write("remote-docling", key, {"phase": "submitting", "remoteCancellation": "unsupported"})
        submitted = request("/v1/convert/source/async", {
            "sources": [{"kind": "file", "filename": name, "base64_string": base64.b64encode(content).decode("ascii")}],
            "options": {"to_formats": ["json", "text", "doctags"], "pipeline": "standard", "do_ocr": True, "force_ocr": force_ocr, "abort_on_error": True},
            "target": {"kind": "inbody"},
        })
        task_id = submitted.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise RemoteDoclingError("remote Docling submit outcome unknown: response omitted task_id")
        state = {"phase": "running", "taskId": task_id, "remoteCancellation": "unsupported"}
        checkpoint.write("remote-docling", key, state)
    if state.get("phase") == "submitting":
        raise RemoteDoclingError("remote Docling submit outcome unknown; reconcile the server task before starting a new build")
    if state.get("phase") == "complete":
        result = state["result"]
    else:
        task_id = state.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise RemoteDoclingError("remote Docling checkpoint has no task identity")
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
        checkpoint.write("remote-docling", key, {**state, "phase": "complete", "result": result})
    document = result.get("document")
    if result.get("status") != "success" or not isinstance(document, dict):
        raise RemoteDoclingError("remote Docling result is not a successful document")
    if not isinstance(document.get("json_content"), dict) or not isinstance(document.get("text_content"), str) or not isinstance(document.get("doctags_content"), str):
        raise RemoteDoclingError("remote Docling result omitted full document, text or DocTags")
    return {"text": document["text_content"], "document": {
        "format": "docling", "document": document["json_content"], "doctags": document["doctags_content"],
        "pages": [], "conversion_status": "success", "source": name,
        "metadata": {"text_origin": "unreported", "remote_task_id": state["taskId"], "remote_cancellation": "unsupported"},
    }}
