"""JSONL protocol worker for Semantica ProjectSnapshot validation.

This is not the legacy polling worker. The host owns process lifecycle and sends
one JSON request per line on stdin; this module validates Semantica's snapshot
contract and returns one JSON response per line on stdout.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional, TextIO

from pydantic import ValidationError as PydanticValidationError

from .project_snapshot_schema import (
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
    project_snapshot_json_schema,
)


class UnsupportedBuildError(RuntimeError):
    pass


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
        return _response(
            request.id,
            True,
            result={
                "snapshot": project_snapshot_json_schema(),
                "build_request": build_request_json_schema(),
            },
        )
    if request.method == "validate_snapshot":
        snapshot = ProjectSnapshot.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "snapshot_id": snapshot.id})

    ProjectSnapshotBuildRequest.model_validate(request.params)
    raise UnsupportedBuildError(
        "build_project_snapshot is not implemented until the Semantica kernel pipeline "
        "computes document representations, evidence, identities, graph, communities, "
        "retrieval artifacts, change deltas, and model receipts from source inputs"
    )


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
        except (json.JSONDecodeError, PydanticValidationError, ValueError, TypeError, UnsupportedBuildError) as exc:
            response = _response(request_id, False, error=exc)
        stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
    return 0


def main() -> None:
    raise SystemExit(serve())


if __name__ == "__main__":
    main()
