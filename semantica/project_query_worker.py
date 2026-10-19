"""JSONL worker for Semantica snapshot queries."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional, TextIO

from pydantic import ValidationError

from .project_query import QueryError, query_project_snapshot
from .project_query_schema import (
    ProjectQueryRequest,
    QueryWorkerRequest,
    QueryWorkerResponse,
)
from .project_snapshot_schema import project_snapshot_json_schema


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        payload["error"] = {"type": error.__class__.__name__ if error else "Error", "message": str(error) if error else "unknown error"}
    return QueryWorkerResponse.model_validate(payload).model_dump(exclude_none=True)


def handle_request(raw: Dict[str, Any]) -> Dict[str, Any]:
    request = QueryWorkerRequest.model_validate(raw)
    if request.method == "schema":
        return _response(request.id, True, result={"snapshot": project_snapshot_json_schema()})
    query = ProjectQueryRequest.model_validate({
        **request.params,
        "protocol": request.protocol,
        "id": request.id,
        "method": request.method,
    })
    result = query_project_snapshot(query)
    return _response(request.id, True, result=result.model_dump(mode="json", by_alias=True))


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
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError, QueryError, OSError) as exc:
            response = _response(request_id, False, error=exc)
        stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
    return 0


def main() -> None:
    raise SystemExit(serve())


if __name__ == "__main__":
    main()
