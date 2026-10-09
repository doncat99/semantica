"""JSONL worker for Semantica's generic semantic-artifact protocol.

The build implementation is intentionally shared with the existing semantic
pipeline.  This module owns the transport contract; product projections are
created by the host from the semantic graph artifact.
"""
from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TextIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .semantic_artifact_builder import (
    SemanticArtifactError, _explanation_reports, _report_support_sources, explain_evidence,
    bind_parsed_source_artifact, build_semantic_artifacts, parse_source_artifact,
)
from .semantic_artifact_schema import (
    ParseSourceRequest,
    SemanticArtifact,
    SemanticArtifactBuildRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
    semantic_artifact_json_schema,
)
from .semantic_extract.schema import ExtractionSpecification
from .semantic_artifact_schema import BindParsedSourceRequest, RelayRef

PROTOCOL = "semantica.semantic-worker.v1"
METHOD = "build_semantic_artifacts"
MODEL_RECEIPT_OPERATIONS = {
    "structured_extraction", "identity_resolution", "relationship_discovery",
    "knowledge_explanation", "knowledge_synthesis", "source_classification",
}


class SemanticWorkerRequest(BaseModel):
    """Transport request for the generic semantic worker."""

    model_config = ConfigDict(extra="forbid")
    protocol: str
    id: str
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)

    def validate_protocol(self) -> None:
        if self.protocol != PROTOCOL:
            raise ValueError(f"unsupported semantic worker protocol: {self.protocol}")


class ReadingReportsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    snapshot_path: str = Field(alias="snapshotPath")
    snapshot_digest: str = Field(alias="snapshotDigest")
    snapshot_id: str = Field(alias="snapshotId")
    project_id: str = Field(alias="projectId")
    output_dir: str = Field(alias="outputDir")
    relay: RelayRef


class EvidenceExplanationRequest(ReadingReportsRequest):
    target: Dict[str, str]
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1)


def _verified_snapshot(request: ReadingReportsRequest) -> SemanticArtifact:
    path = Path(request.snapshot_path)
    if not path.is_absolute() or not path.is_file():
        raise SemanticArtifactError("explanation requires a local snapshot file")
    raw = path.read_bytes()
    if f"sha256:{sha256(raw).hexdigest()}" != request.snapshot_digest:
        raise SemanticArtifactError("explanation snapshot digest does not match")
    document = json.loads(raw)
    if document.get("protocol") != "semantica.semantic-graph.v1":
        raise SemanticArtifactError("explanation requires a semantic graph artifact")
    # The graph artifact is the transport representation; explanation consumes
    # the same bytes as a validated semantic-artifact view with explicit
    # identity fields. This is a format projection, not a second extraction path.
    document["protocol"] = "semantica.semantic-artifact.v1"
    document["snapshot_id"] = document.pop("artifact_revision")
    document["project_id"] = request.project_id
    for field in ("input_revision", "release_digest", "schema_digest"):
        document.pop(field, None)
    snapshot = SemanticArtifact.model_validate(document)
    if snapshot.id != request.snapshot_id or snapshot.project_id != request.project_id:
        raise SemanticArtifactError("explanation snapshot identity does not match")
    if request.relay.capability != "knowledge.snapshot.generate":
        raise SemanticArtifactError("explanation requires the model generation relay")
    return snapshot


def _explain_evidence(params: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]]) -> Dict[str, Any]:
    request = EvidenceExplanationRequest.model_validate(params)
    if set(request.target) != {"id", "type", "title"} or not all(request.target.values()):
        raise SemanticArtifactError("explanation target requires id, type and title")
    snapshot = _verified_snapshot(request)
    if progress:
        progress({"stage": "explaining_evidence", "percent": 1, "detail": "Explaining selected evidence"})
    sections, receipts = explain_evidence(snapshot, request.target, request.evidence_ids, request.relay)
    payload = {"protocol": "semantica.evidence-explanation.v1", "snapshotId": snapshot.id,
               "snapshotDigest": request.snapshot_digest, "target": request.target,
               "sections": [item.model_dump(mode="json") for item in sections],
               "evidenceIds": sorted({ref for section in sections for ref in section.evidence_ids}),
               "modelReceipts": [item.model_dump(mode="json", by_alias=True) for item in receipts]}
    output_dir = Path(request.output_dir)
    if not output_dir.is_absolute() or not output_dir.is_dir():
        raise SemanticArtifactError("explanation output directory must exist")
    output = output_dir / "evidence-explanation.json"
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    output.write_bytes(data)
    if progress:
        progress({"stage": "explaining_evidence", "percent": 100, "detail": "Evidence explanation completed"})
    return {"path": str(output), "digest": f"sha256:{sha256(data).hexdigest()}",
            "sectionCount": len(sections), "receiptCount": len(receipts)}


def _reading_reports(params: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]]) -> Dict[str, Any]:
    request = ReadingReportsRequest.model_validate(params)
    snapshot = _verified_snapshot(request)
    if progress:
        progress({"stage": "reading_reports", "percent": 1, "detail": "Generating reading reports"})
    passages = [span for span in snapshot.evidence_spans if span.metadata.get("role") == "source-passage"]
    source_builds = [{"passages": [span for span in passages if span.representation_id == representation.id]}
                     for representation in snapshot.document_representations]
    reports, receipts = _explanation_reports(snapshot.project_id, source_builds, snapshot.entities,
        snapshot.assertions, snapshot.relations, snapshot.communities, snapshot.topics,
        snapshot.evidence_spans, request.relay)
    _report_support_sources(snapshot.document_representations, snapshot.evidence_spans,
        snapshot.entities, snapshot.assertions, snapshot.relations, snapshot.communities,
        snapshot.topics, reports)
    if progress:
        progress({"stage": "reading_reports", "percent": 100, "detail": f"Generated {len(reports)} reading reports"})
    payload = {"protocol": "semantica.reading-reports.v1", "snapshotId": snapshot.id,
            "snapshotDigest": request.snapshot_digest,
            "reports": [report.model_dump(mode="json", by_alias=True) for report in reports],
            "modelReceipts": [receipt.model_dump(mode="json", by_alias=True) for receipt in receipts]}
    output_dir = Path(request.output_dir)
    if not output_dir.is_absolute() or not output_dir.is_dir():
        raise SemanticArtifactError("reading report output directory must exist")
    output = output_dir / "reading-reports.json"
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    output.write_bytes(data)
    return {"path": str(output), "digest": f"sha256:{sha256(data).hexdigest()}",
            "reportCount": len(reports), "receiptCount": len(receipts)}


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
        if isinstance(error, SemanticArtifactError):
            if error.status is not None:
                payload["error"]["status"] = error.status
            if error.code:
                payload["error"]["code"] = error.code
            if error.retryable:
                payload["error"]["retryable"] = True
            if error.retry_after_ms is not None:
                payload["error"]["retryAfterMs"] = error.retry_after_ms
            if error.upstream_request_id:
                payload["error"]["upstreamRequestId"] = error.upstream_request_id
            if error.diagnostic:
                payload["error"]["diagnostic"] = error.diagnostic
            if error.gateway:
                payload["error"]["gateway"] = error.gateway
        if error is not None and "diagnostic" not in payload["error"]:
            code = payload["error"].setdefault("code", "SEMANTIC_WORKER_INTERNAL_ERROR")
            diagnostic = {"origin": "protocol_error", "code": code}
            parallel_context = getattr(error, "parallel_context", None)
            if parallel_context is not None:
                diagnostic["parallelTask"] = parallel_context
            frame = error.__traceback__
            if frame is not None:
                while frame.tb_next is not None:
                    frame = frame.tb_next
                diagnostic["fault"] = {"file": Path(frame.tb_frame.f_code.co_filename).name,
                    "function": frame.tb_frame.f_code.co_name, "line": frame.tb_lineno}
            payload["error"]["diagnostic"] = diagnostic
    return payload


def handle_request(raw: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    request = SemanticWorkerRequest.model_validate(raw)
    request.validate_protocol()
    if request.method == "schema":
        return _response(request.id, True, result={"semantic_graph": semantic_artifact_json_schema(),
                                                    "build_request": build_request_json_schema()})
    if request.method == "validate_extraction_spec":
        spec = ExtractionSpecification.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "digest": spec.digest})
    if request.method == "parse_source":
        return _response(request.id, True, result=parse_source_artifact(ParseSourceRequest.model_validate(request.params)))
    if request.method == "bind_parsed_source":
        return _response(request.id, True, result=bind_parsed_source_artifact(BindParsedSourceRequest.model_validate(request.params)))
    if request.method == "validate_artifact":
        snapshot = SemanticArtifact.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "snapshot_id": snapshot.id})
    if request.method == "generate_reading_reports":
        return _response(request.id, True, result=_reading_reports(request.params, progress))
    if request.method == "explain_evidence":
        return _response(request.id, True, result=_explain_evidence(request.params, progress))
    if request.method != METHOD:
        raise ValueError(f"unsupported semantic worker method: {request.method}")
    build_request = SemanticArtifactBuildRequest.model_validate(request.params)
    built = build_semantic_artifacts(build_request, progress=progress)
    snapshot: SemanticArtifact = built["snapshot"]
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
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError, SemanticArtifactError, OSError) as exc:
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
