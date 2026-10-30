"""Snapshot-bound keyword and vector retrieval with grounded evidence."""

from __future__ import annotations

import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from .semantic_query_schema import SemanticQueryRequest, SemanticQueryResult, QueryHit
from .semantic_artifact_schema import SemanticArtifact
from .context.context_retriever import ContextRetriever


class QueryError(RuntimeError):
    """Raised when an artifact cannot be queried safely."""


@lru_cache(maxsize=2)
def _load_admitted_json(path: Path, digest: str, identity: tuple[int, ...]) -> Any:
    payload = path.read_bytes()
    current = path.stat()
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != identity:
        raise QueryError(f"query artifact changed during admission: {path}")
    if f"sha256:{sha256(payload).hexdigest()}" != digest:
        raise QueryError(f"query artifact digest does not match: {path}")
    return json.loads(payload.decode("utf-8"))


def _load_json(path: Path, digest: str) -> Any:
    try:
        stat = path.stat()
        return _load_admitted_json(path.resolve(), digest,
            (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueryError(f"query artifact is not valid UTF-8 JSON: {path}") from exc


@lru_cache(maxsize=2)
def _load_snapshot(path: Path, digest: str, identity: tuple[int, ...]) -> SemanticArtifact:
    return SemanticArtifact.model_validate(_load_admitted_json(path, digest, identity))


@lru_cache(maxsize=2)
def _prepare_query_snapshot(path: Path, digest: str, identity: tuple[int, ...]):
    return ContextRetriever.prepare_snapshot_search(_load_snapshot(path, digest, identity))


def query_semantic_artifact(request: SemanticQueryRequest) -> SemanticQueryResult:
    if request.method != "query":
        raise QueryError("query_semantic_artifact requires method=query")
    retrieval_payload = _load_json(Path(request.retrieval.path), request.retrieval.digest)
    stat = Path(request.snapshot.path).stat()
    snapshot = _load_snapshot(Path(request.snapshot.path).resolve(), request.snapshot.digest,
        (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    if snapshot.project_id != request.project_id or snapshot.id != request.snapshot_id:
        raise QueryError("query artifacts do not match the requested semantic artifact")
    if not isinstance(retrieval_payload, dict):
        raise QueryError("retrieval artifact must be a JSON object")
    manifest_id = "retrieval:graph"
    manifests = {item.id: item for item in snapshot.retrieval_manifests}
    graph_manifest = manifests.get(manifest_id)
    if graph_manifest is None or graph_manifest.artifact_hash != request.retrieval.digest:
        raise QueryError("retrieval artifact is not the snapshot graph manifest")

    if retrieval_payload.get("format") != "semantica.retrieval-reference.v1":
        raise QueryError("unsupported retrieval artifact format; rebuild is required")
    duplicate_fields = {"entities", "assertions", "relations", "identity_decisions", "conflicts", "topics", "evidence"}
    if duplicate_fields.intersection(retrieval_payload):
        raise QueryError("reference retrieval artifact cannot duplicate snapshot records")
    prepared = _prepare_query_snapshot(
        Path(request.snapshot.path).resolve(), request.snapshot.digest,
        (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    try:
        contexts = ContextRetriever().search_snapshot(
            prepared, query=request.query or "", mode=request.mode,
            retrieval=retrieval_payload, embedding=request.embedding,
            source_ids=request.source_ids, max_results=request.limit)
    except (ValueError, TypeError) as exc:
        raise QueryError(str(exc)) from exc
    hits = [QueryHit(
        id=context.metadata["id"], kind=context.metadata["kind"],
        title=context.content.split(" ", 1)[0] if context.metadata["kind"] == "evidence" else context.content[:160],
        text=context.content, score=context.score,
        status=context.metadata["status"], polarity=context.metadata["polarity"],
        evidence_ids=context.metadata["evidence_ids"], source_ids=context.metadata["source_ids"],
    ) for context in contexts]
    return SemanticQueryResult(
        project_id=snapshot.project_id,
        snapshot_id=snapshot.id,
        query=request.query or "",
        contexts=hits[:request.limit],
        retrieval_manifest_id=manifest_id,
    )
