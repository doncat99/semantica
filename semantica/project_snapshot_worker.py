"""JSONL worker for the Semantica project snapshot build protocol.

The host resolves source authorization and owns process lifecycle. This worker
receives host-granted absolute paths and relay references without bearer tokens;
cancellation is process-level termination rather than an in-band command.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Dict, Optional, TextIO

from pydantic import ValidationError as PydanticValidationError

from .project_snapshot_pipeline import SnapshotBuildError, build_project_snapshot, parse_source_artifact
from .project_snapshot_schema import (
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    ParseSourceRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
    project_snapshot_json_schema,
)
from .semantic_extract.schema import ExtractionSpecification


MODEL_RECEIPT_OPERATIONS = {
    "structured_extraction", "identity_resolution", "relationship_discovery",
    "knowledge_explanation", "knowledge_synthesis", "source_classification",
}


def _relay_receipts(receipts: list[Any]) -> Dict[str, list[str]]:
    return {
        "embedding": [receipt.id for receipt in receipts if receipt.operation == "embedding"],
        "model": [receipt.id for receipt in receipts if receipt.operation in MODEL_RECEIPT_OPERATIONS],
    }


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        payload["error"] = {
            "type": error.__class__.__name__ if error else "Error",
            "message": str(error) if error else "unknown error",
            **({"status": error.status} if isinstance(error, SnapshotBuildError) and error.status is not None else {}),
            **({"code": error.code} if isinstance(error, SnapshotBuildError) and error.code else {}),
            **({"retryable": True} if isinstance(error, SnapshotBuildError) and error.retryable else {}),
        }
    return WorkerResponse.model_validate(payload).model_dump(exclude_none=True)


def handle_request(raw: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    request = WorkerRequest.model_validate(raw)
    if request.method == "schema":
        return _response(request.id, True, result={"snapshot": project_snapshot_json_schema(), "build_request": build_request_json_schema()})
    if request.method == "validate_snapshot":
        snapshot = ProjectSnapshot.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "snapshot_id": snapshot.id})
    if request.method == "validate_extraction_spec":
        specification = ExtractionSpecification.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "digest": specification.digest})
    if request.method == "parse_source":
        return _response(request.id, True, result=parse_source_artifact(ParseSourceRequest.model_validate(request.params)))
    build_request = ProjectSnapshotBuildRequest.model_validate(request.params)
    built = build_project_snapshot(build_request, progress=progress)
    snapshot: ProjectSnapshot = built["snapshot"]
    artifacts = []
    for item in built["representation_artifacts"]:
        artifacts.append({
            "digest": item["artifact_digest"],
            "kind": "document-representation",
            "mediaType": build_request.release.media_types["document-representation"],
            "path": str(item["artifact_path"]),
            "revision": item["representation"].metadata["representation_revision"],
            "sourceId": item["source"].source_id,
        })
    artifacts.append({
        "digest": built["retrieval_digest"],
        "kind": "retrieval-index",
        "mediaType": build_request.release.media_types["retrieval-index"],
        "path": str(built["retrieval_path"]),
        "revision": f"retrieval:{snapshot.id}",
    })
    artifacts.append({
        "digest": built["snapshot_digest"],
        "kind": "semantic-graph",
        "mediaType": build_request.release.media_types["semantic-graph"],
        "path": str(built["snapshot_path"]),
        "revision": snapshot.id,
    })
    receipts = built["model_receipts"]
    return _response(request.id, True, result={
        "artifacts": artifacts,
        "relayReceipts": _relay_receipts(receipts),
        "semanticGraph": {
            "artifactRevision": snapshot.id,
            "inputRevision": build_request.input_revision,
            "releaseDigest": build_request.release.artifact_digest,
            "schemaDigest": build_request.release.schema_digest,
        },
    })


def serve(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    for line in stdin:
        if not line.strip():
            continue
        request_id: Optional[str] = None
        try:
            raw = json.loads(line)
            if isinstance(raw, dict):
                request_id = raw.get("id")
            def emit_progress(event: Dict[str, Any]) -> None:
                stdout.write(json.dumps({
                    "protocol": "semantica.project-worker.v1",
                    "id": request_id,
                    "type": "progress",
                    **event,
                }, ensure_ascii=False, sort_keys=True) + "\n")
                stdout.flush()
            response = handle_request(raw, progress=emit_progress)
        except (json.JSONDecodeError, PydanticValidationError, ValueError, TypeError, SnapshotBuildError, OSError) as exc:
            response = _response(request_id, False, error=exc)
        stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
    return 0


def main() -> None:
    protocol_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with os.fdopen(protocol_fd, "w", encoding="utf-8") as protocol_stdout:
        raise SystemExit(serve(stdout=protocol_stdout))


if __name__ == "__main__":
    main()
