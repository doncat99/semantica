"""JSONL transport for native semantic publication and document processing."""
from __future__ import annotations

import json
import os
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, Optional, TextIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .semantic_artifact_errors import SemanticArtifactError, model_output_cause
from .semantic_source_artifact import bind_parsed_source_artifact, parse_source_artifact
from .semantic_artifact_schema import (
    ParseSourceRequest,
    SemanticArtifactBuildRequest,
    WorkerRequest,
    WorkerResponse,
    build_request_json_schema,
)
from .semantic_extract.schema import ExtractionSpecification
from .semantic_query_schema import NativeStoreRef, QueryArtifactRef
from .semantic_artifact_schema import BindParsedSourceRequest, RelayRef
from . import semantic_artifact_schema as _artifact_schema
from .semantic_extract import schema as _extraction_schema

PROTOCOL = "semantica.semantic-worker.v1"
METHOD = "build_semantic_artifacts"
MODEL_RECEIPT_OPERATIONS = {
    "structured_extraction",
    "identity_resolution", "relationship_discovery",  # Historical receipts only; new builds do not run these stages.
    "knowledge_explanation", "knowledge_synthesis", "source_classification",
}
_SAFE_VALIDATION_TYPES = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def _safe_validation_details(error: ValidationError) -> Dict[str, Any]:
    field_names = set()
    for module in (_artifact_schema, _extraction_schema):
        for candidate in vars(module).values():
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                for name, field in candidate.model_fields.items():
                    field_names.add(name)
                    if isinstance(field.alias, str):
                        field_names.add(field.alias)

    errors = []
    for item in error.errors(include_input=False, include_context=False, include_url=False)[:32]:
        location = []
        for part in item.get("loc", ()):
            if isinstance(part, int) and part >= 0:
                location.append(part)
            elif isinstance(part, str) and part in field_names:
                location.append(part)
        error_type = item.get("type")
        if not isinstance(error_type, str) or not _SAFE_VALIDATION_TYPES.fullmatch(error_type):
            error_type = "validation_error"
        errors.append({"location": location, "type": error_type})
    return {"validationErrorCount": error.error_count(), "validationErrors": errors}


class ExplanationSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source_id: str = Field(alias='sourceId', min_length=1, max_length=1024)
    material_revision: str = Field(alias='materialRevision', min_length=1, max_length=4096)
    representation_revision: str = Field(alias='representationRevision', min_length=1, max_length=4096)
    artifact: QueryArtifactRef
    reader_index: QueryArtifactRef = Field(alias='readerIndex')


class EvidenceExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    project_id: str = Field(alias="projectId", min_length=1, max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    sources: list[ExplanationSource] = Field(min_length=1, max_length=32)
    output_dir: str = Field(alias="outputDir")
    relay: RelayRef
    target: Dict[str, str]
    evidence_ids: list[Annotated[str, Field(min_length=1, max_length=4096)]] = Field(
        alias="evidenceIds", min_length=1, max_length=32)


def _native_explanation_context(request):
    """Hydrate only caller-selected native evidence and its proven scalar ranges."""
    from time import monotonic
    from .semantic_query import NativeQueryStore, QueryError
    from .utils.exceptions import ProcessingError
    from .semantic_query_schema import DocumentReaderRequest
    from .semantic_document_reader import read_document_reader
    from .semantic_worker_context import check_query_cancellation
    from .triplet_store.extraction_records import F, RDF_TYPE

    sources = {source.source_id: source for source in request.sources}
    if len(sources) != len(request.sources) or len(set(request.evidence_ids)) != len(request.evidence_ids):
        raise SemanticArtifactError('explanation requires distinct sources and evidence IDs')
    deadline, used_bytes, range_count = monotonic() + 30, 0, 0
    def charge(value=0):
        nonlocal used_bytes
        used_bytes += value
        check_query_cancellation()
        if used_bytes > 262144 or monotonic() > deadline:
            raise SemanticArtifactError('explanation native evidence exceeds its 256KiB/30s budget')
    def one(record, field, kind='literal'):
        values = record['fields'].get(field if field == RDF_TYPE else F + field, [])
        if len(values) != 1 or values[0]['type'] != kind:
            raise SemanticArtifactError('explanation native evidence field is missing or ambiguous: ' + field)
        return values[0]['value']
    session = NativeQueryStore()
    try:
        session.acquire(request.semantic_store)
        owner = session.borrow(request.semantic_store, request.project_id)
        evidence = []
        for identity in request.evidence_ids:
            charge()
            records = owner.read_native_records(request.project_id, request.semantic_store.generation,
                [identity], source_ids=list(sources))
            charge(len(json.dumps(records, ensure_ascii=False).encode()))
            record = records[0]
            if one(record, RDF_TYPE, 'iri') not in {F + 'Evidence', F + 'Mention', F + 'IdentityProfile'}:
                raise SemanticArtifactError('explanation requires exact native evidence spans')
            binding = owner.read_record_binding(request.project_id, request.semantic_store.generation, identity)
            source = sources.get(binding['source'])
            if source is None or (source.material_revision, source.representation_revision) != (binding['material'], binding['representation']):
                raise SemanticArtifactError('explanation source revision differs from native evidence binding')
            refs = record['fields'].get(F + 'nativeRange', [])
            range_count += len(refs)
            if not refs or range_count > 128 or any(ref['type'] != 'iri' for ref in refs):
                raise SemanticArtifactError('explanation requires at most 128 proven native scalar ranges')
            ranges = owner.read_native_records(request.project_id, request.semantic_store.generation,
                [ref['value'] for ref in refs], source_ids=[source.source_id])
            charge(len(json.dumps(ranges, ensure_ascii=False).encode()))
            ranges.sort(key=lambda row: int(one(row, 'position')))
            cursor, joins, selected = int(one(record, 'start')), [], []
            for position, row in enumerate(ranges):
                if one(row, RDF_TYPE, 'iri') != F + 'NativeRange' or int(one(row, 'position')) != position:
                    raise SemanticArtifactError('explanation native range order is invalid')
                joins_raw = row['fields'].get(F + 'joinBefore', [])
                join = one(row, 'joinBefore') if joins_raw else ''
                start, end = int(one(row, 'start')), int(one(row, 'end'))
                lo, hi = int(one(row, 'windowStart')), int(one(row, 'windowEnd'))
                if join not in {'', '\n', '\n\n'} or lo != cursor + len(join) or hi - lo != end - start:
                    raise SemanticArtifactError('explanation native evidence extent is invalid')
                joins.append(join)
                selected.append(dict(nativeRef=one(row, 'nativeRef'), start=start, end=end))
                cursor = hi
            if cursor != int(one(record, 'end')):
                raise SemanticArtifactError('explanation native evidence extent is incomplete')
            reader = DocumentReaderRequest.model_validate(dict(id='explanation',
                **source.model_dump(by_alias=True), selection=dict(field='ranges', ranges=selected,
                    maxBytes=max(1, 262144 - used_bytes))))
            hydrated = read_document_reader(reader)
            charge(hydrated['readBytes'])
            quote = ''.join(join + item['text'] for join, item in zip(joins, hydrated['items']))
            charge(len(quote.encode()))
            evidence.append(dict(id=identity, quote=quote))
        session.borrow(request.semantic_store, request.project_id)
        return dict(target=request.target, entities=[], assertions=[], relations=[], evidence=evidence)
    except (ProcessingError, QueryError) as exc:
        raise SemanticArtifactError(str(exc), code='NATIVE_EVIDENCE_INVALID', retryable=False,
            diagnostic={'upstreamRequestSent': False}) from exc
    finally:
        session.close()


def _explain_evidence(params: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]]) -> Dict[str, Any]:
    from .semantic_publication_builder import _grounded_explanation

    request = EvidenceExplanationRequest.model_validate(params)
    if set(request.target) != {"id", "type", "title"} or not all(
            value and len(value.encode()) <= 2048 for value in request.target.values()):
        raise SemanticArtifactError("explanation target requires id, type and title")
    output_dir = Path(request.output_dir)
    if not output_dir.is_absolute() or not output_dir.is_dir():
        raise SemanticArtifactError("explanation output directory must exist")
    if request.relay.capability != "knowledge.publication.generate":
        raise SemanticArtifactError("explanation requires the model generation relay")
    context = _native_explanation_context(request)
    if progress:
        progress({"stage": "explaining_evidence", "percent": 1, "detail": "Explaining selected evidence"})
    sections, receipts = _grounded_explanation(context, request.relay)
    payload = {"protocol": "semantica.evidence-explanation.v1", "projectId": request.project_id,
               "generation": request.semantic_store.generation, "target": request.target,
               "sections": [item.model_dump(mode="json") for item in sections],
               "evidenceIds": sorted({ref for section in sections for ref in section.evidence_ids}),
               "modelReceipts": [item.model_dump(mode="json", by_alias=True) for item in receipts]}
    output = output_dir / "evidence-explanation.json"
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > 262144:
        raise SemanticArtifactError('explanation output exceeds 256KiB')
    output.write_bytes(data)
    if progress:
        progress({"stage": "explaining_evidence", "percent": 100, "detail": "Evidence explanation completed"})
    return {"path": str(output), "digest": f"sha256:{sha256(data).hexdigest()}",
            "sectionCount": len(sections), "receiptCount": len(receipts)}


def _relay_receipts(receipts: list[Any]) -> Dict[str, list[str]]:
    return {
        "embedding": [item.id for item in receipts if item.operation == "embedding"],
        "model": [item.id for item in receipts if item.operation in MODEL_RECEIPT_OPERATIONS],
    }


def _relay_receipt_manifest(receipts):
    """Transport identity attestations only; paid output remains in its owner."""
    result, size = [], 0
    for receipt in receipts:
        item = {key: getattr(receipt, key) for key in
            ("id", "operation", "provider", "model", "input_digest", "output_digest")}
        size += len(json.dumps(item, ensure_ascii=False).encode()) + 1
        if size > 4 * 1024 * 1024:
            raise SemanticArtifactError('Relay receipt attestations exceed the build response budget')
        result.append(item)
    return result


def _response(request_id: Optional[str], ok: bool, *, result: Optional[Dict[str, Any]] = None,
              error: Optional[Exception] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"protocol": PROTOCOL, "id": request_id, "ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        validation_error = isinstance(error, ValidationError)
        payload["error"] = {"type": error.__class__.__name__ if error else "Error",
                             "message": "Semantica request validation failed" if validation_error else str(error) if error else "unknown error"}
        if validation_error:
            payload["error"]["diagnostic"] = {"origin": "protocol_error", "code": "SEMANTIC_WORKER_INTERNAL_ERROR",
                                                **_safe_validation_details(error)}
        # Model-output classification comes from the innermost cause, while
        # the scheduler attaches the failed window identity to an outer error.
        # Keep that identity across unwrapping; it is required to resume only
        # the rejected operation instead of repeating accepted paid results.
        parallel_context = None
        context_error, context_seen = error, set()
        while context_error is not None and id(context_error) not in context_seen:
            context_seen.add(id(context_error))
            candidate = getattr(context_error, "parallel_context", None)
            diagnostic_candidate = getattr(context_error, "diagnostic", None)
            if candidate is None and isinstance(diagnostic_candidate, dict):
                candidate = diagnostic_candidate.get("parallelTask")
            if isinstance(candidate, dict):
                parallel_context = candidate
                break
            context_error = context_error.__cause__
        output_error = model_output_cause(error) if error is not None else None
        if output_error is not None:
            error = output_error
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
        if error is not None:
            code = payload["error"].setdefault("code", "SEMANTIC_WORKER_INTERNAL_ERROR")
            diagnostic = {"origin": "protocol_error", "code": code, **payload["error"].get("diagnostic", {})}
            if parallel_context is not None:
                diagnostic["parallelTask"] = parallel_context
            cause = error
            seen = set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                if isinstance(cause, ValidationError):
                    diagnostic.update(_safe_validation_details(cause))
                deepest = cause
                cause = cause.__cause__
            frame = deepest.__traceback__
            if frame is not None:
                while frame.tb_next is not None:
                    frame = frame.tb_next
                diagnostic["fault"] = {"file": Path(frame.tb_frame.f_code.co_filename).name,
                    "function": frame.tb_frame.f_code.co_name, "line": frame.tb_lineno}
            payload["error"]["diagnostic"] = diagnostic
    return WorkerResponse.model_validate(payload).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)


def handle_request(raw: Dict[str, Any], progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    request = WorkerRequest.model_validate(raw)
    from .semantic_worker_context import document_processing_authorization, worker_authorization
    token = worker_authorization.set(request.authorization)
    document_token = document_processing_authorization.set(request.document_processing_authorization)
    try:
        return _dispatch(request, progress)
    finally:
        document_processing_authorization.reset(document_token)
        worker_authorization.reset(token)


def _dispatch(request: WorkerRequest, progress: Optional[Callable[[Dict[str, Any]], None]]) -> Dict[str, Any]:
    if request.method == "schema":
        return _response(request.id, True, result={"build_request": build_request_json_schema()})
    if request.method == "validate_extraction_spec":
        spec = ExtractionSpecification.model_validate(request.params)
        return _response(request.id, True, result={"valid": True, "digest": spec.digest})
    if request.method == "parse_source":
        return _response(request.id, True, result=parse_source_artifact(ParseSourceRequest.model_validate(request.params), progress=progress))
    if request.method == "bind_parsed_source":
        return _response(request.id, True, result=bind_parsed_source_artifact(BindParsedSourceRequest.model_validate(request.params)))
    if request.method == "explain_evidence":
        return _response(request.id, True, result=_explain_evidence(request.params, progress))
    if request.method != METHOD:
        raise ValueError(f"unsupported semantic worker method: {request.method}")
    build_request = SemanticArtifactBuildRequest.model_validate(request.params)
    from .semantic_publication_builder import build_semantic_artifacts

    built = build_semantic_artifacts(build_request, progress=progress)
    store = built["semantic_store"]
    return _response(request.id, True, result={
        "publication": built["publication"],
        "nativeIndexes": built["native_indexes"],
        "semanticStore": {"path": store["path"], "project": store["projectId"],
                          "generation": store["generationId"]},
        "relayReceipts": _relay_receipts(built["model_receipts"]),
        "relayReceiptManifest": _relay_receipt_manifest(built["model_receipts"]),
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
