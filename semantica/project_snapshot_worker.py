"""JSONL worker for the Semantica project snapshot build protocol.

The host resolves source authorization and owns process lifecycle. This worker
receives host-granted absolute paths and relay references without bearer tokens;
cancellation is process-level termination rather than an in-band command.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional, TextIO

from pydantic import ValidationError as PydanticValidationError

from .project_snapshot_pipeline import SnapshotBuildError, build_project_snapshot
from .project_snapshot_schema import (
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
    project_snapshot_json_schema,
)


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        payload["error"] = {"type": error.__class__.__name__ if error else "Error", "message": str(error) if error else "unknown error"}
    return WorkerResponse.model_validate(payload).model_dump(exclude_none=True)


def handle_request(raw: Dict[str, Any]) -> Dict[str, Any]:
    request = WorkerRequest.model_validate(raw)
    if request.method == "schema":
        return _response(request.id, True, result={"snapshot": project_snapshot_json_schema(), "build_request": build_request_json_schema()})
    if request.method == "validate_snapshot":
        snapshot = ProjectSnapshot.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "snapshot_id": snapshot.id})
    build_request = ProjectSnapshotBuildRequest.model_validate(request.params)
    built = build_project_snapshot(build_request)
    snapshot: ProjectSnapshot = built["snapshot"]
    artifacts = []
    for item in built["representation_artifacts"]:
        artifacts.append({
            "digest": item["artifact_digest"],
            "kind": "document-representation",
            "mediaType": build_request.release.media_types["document-representation"],
            "path": str(item["artifact_path"]),
            "revision": item["representation"].material_revision_id,
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
        "kind": "snapshot",
        "mediaType": build_request.release.media_types["snapshot"],
        "path": str(built["snapshot_path"]),
        "revision": snapshot.id,
    })
    receipts = built["model_receipts"]
    return _response(request.id, True, result={
        "artifacts": artifacts,
        "relayReceipts": {
            "embedding": [receipt.id for receipt in receipts if receipt.operation == "embedding"],
            "model": [receipt.id for receipt in receipts if receipt.operation == "structured_extraction"],
        },
        "snapshot": {
            "baseSnapshotId": snapshot.base_snapshot_id,
            "inputRevision": build_request.input_revision,
            "projectId": snapshot.project_id,
            "schemaDigest": build_request.release.schema_digest,
            "semanticaArtifactDigest": build_request.release.artifact_digest,
            "snapshotId": snapshot.id,
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
            response = handle_request(raw)
        except (json.JSONDecodeError, PydanticValidationError, ValueError, TypeError, SnapshotBuildError, OSError) as exc:
            response = _response(request_id, False, error=exc)
        stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
    return 0


def main() -> None:
    raise SystemExit(serve())


if __name__ == "__main__":
    main()
