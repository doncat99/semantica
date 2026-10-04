"""JSONL worker for Semantica's generic semantic-artifact protocol.

The build implementation is intentionally shared with the existing semantic
pipeline.  This module owns the transport contract; product projections are
created by the host from the semantic graph artifact.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Dict, Optional, TextIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .project_snapshot_pipeline import SnapshotBuildError, build_semantic_artifacts, parse_source_artifact
from .project_snapshot_schema import (
    ParseSourceRequest,
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
    project_snapshot_json_schema,
)
from .semantic_extract.schema import ExtractionSpecification

PROTOCOL = "semantica.semantic-worker.v1"
METHOD = "build_semantic_artifacts"
MODEL_RECEIPT_OPERATIONS = {
    "structured_extraction", "identity_resolution", "relationship_discovery",
    "knowledge_explanation", "knowledge_synthesis", "source_classification",
}


class SemanticWorkerRequest(BaseModel):
    """Transport request for the generic worker; no project-worker rewrite."""

    model_config = ConfigDict(extra="forbid")
    protocol: str
    id: str
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)

    def validate_protocol(self) -> None:
        if self.protocol != PROTOCOL:
            raise ValueError(f"unsupported semantic worker protocol: {self.protocol}")


def _relay_receipts(receipts: list[Any]) -> Dict[str, list[str]]:
    return {
        "embedding": [item.id for item in receipts if item.operation == "embedding"],
        "model": [item.id for item in receipts if item.operation in MODEL_RECEIPT_OPERATIONS],
    }


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None,
              error: Optional[Exception] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"protocol": PROTOCOL, "id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        payload["error"] = {"type": error.__class__.__name__ if error else "Error",
                             "message": str(error) if error else "unknown error"}
        if isinstance(error, SnapshotBuildError):
            if error.status is not None:
                payload["error"]["status"] = error.status
            if error.code:
                payload["error"]["code"] = error.code
            if error.retryable:
                payload["error"]["retryable"] = True
    return payload


def handle_request(raw: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    request = SemanticWorkerRequest.model_validate(raw)
    request.validate_protocol()
    if request.method == "schema":
        return _response(request.id, True, result={"semantic_graph": project_snapshot_json_schema(),
                                                    "build_request": build_request_json_schema()})
    if request.method == "validate_extraction_spec":
        spec = ExtractionSpecification.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "digest": spec.digest})
    if request.method == "parse_source":
        return _response(request.id, True, result=parse_source_artifact(ParseSourceRequest.model_validate(request.params)))
    if request.method != METHOD:
        raise ValueError(f"unsupported semantic worker method: {request.method}")
    build_request = ProjectSnapshotBuildRequest.model_validate(request.params)
    built = build_semantic_artifacts(build_request, progress=progress)
    snapshot: ProjectSnapshot = built["snapshot"]
    artifacts = [{
        "digest": item["artifact_digest"],
        "kind": "document-representation",
        "mediaType": build_request.release.media_types["document-representation"],
        "path": str(item["artifact_path"]),
        "revision": item["representation"].metadata["representation_revision"],
        "sourceId": item["source"].source_id,
    } for item in built["representation_artifacts"]]
    graph = snapshot.model_dump(mode="json", by_alias=True)
    graph.pop("protocol", None)
    graph.pop("snapshot_id", None)
    graph.pop("project_id", None)
    graph.pop("base_snapshot_id", None)
    graph = {
        "protocol": "semantica.semantic-graph.v1",
        "artifact_revision": snapshot.id,
        "input_revision": build_request.input_revision,
        "release_digest": build_request.release.artifact_digest,
        "schema_digest": build_request.release.schema_digest,
        **graph,
    }
    graph_path = build_request.output_dir
    graph_file = os.path.join(graph_path, "semantic-graph.json")
    with open(graph_file, "w", encoding="utf-8") as stream:
        json.dump(graph, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    import hashlib
    graph_digest = "sha256:" + hashlib.sha256(open(graph_file, "rb").read()).hexdigest()
    artifacts.extend([
        {"digest": built["retrieval_digest"], "kind": "retrieval-index",
         "mediaType": build_request.release.media_types["retrieval-index"],
         "path": str(built["retrieval_path"]), "revision": f"retrieval:{snapshot.id}"},
        {"digest": graph_digest, "kind": "semantic-graph",
         "mediaType": build_request.release.media_types["semantic-graph"],
         "path": graph_file, "revision": snapshot.id},
    ])
    return _response(request.id, True, result={
        "artifacts": artifacts,
        "relayReceipts": _relay_receipts(built["model_receipts"]),
        "semanticGraph": {"inputRevision": build_request.input_revision,
                     "releaseDigest": build_request.release.artifact_digest,
                     "schemaDigest": build_request.release.schema_digest,
                     "artifactRevision": snapshot.id},
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
                stdout.write(json.dumps({"protocol": PROTOCOL, "id": request_id,
                                         "type": "progress", **event}, ensure_ascii=False, sort_keys=True) + "\n")
                stdout.flush()
            response = handle_request(raw, progress=emit_progress)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError, SnapshotBuildError, OSError) as exc:
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
