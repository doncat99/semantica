"""Snapshot-bound keyword and vector retrieval with grounded evidence."""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from .project_query_schema import ProjectQueryRequest, ProjectQueryResult, QueryHit
from .project_snapshot_schema import ProjectSnapshot


class QueryError(RuntimeError):
    """Raised when an artifact cannot be queried safely."""


def _digest_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load_json(path: Path, digest: str) -> Any:
    if not path.is_file():
        raise QueryError(f"query artifact is not a file: {path}")
    if _digest_file(path) != digest:
        raise QueryError(f"query artifact digest does not match: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueryError(f"query artifact is not valid UTF-8 JSON: {path}") from exc


def _tokens(value: str) -> list[str]:
    return re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE)


def _score(query: str, text: str) -> float:
    query_tokens = set(_tokens(query))
    text_tokens = set(_tokens(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens) / len(query_tokens)
    normalized_query = " ".join(_tokens(query))
    normalized_text = " ".join(_tokens(text))
    phrase_bonus = 0.25 if normalized_query in normalized_text else 0.0
    return overlap + phrase_bonus


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise QueryError(f"retrieval artifact field {field} is invalid")
    return value


def _records(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise QueryError(f"retrieval artifact field {field} is invalid")
    return value


def _source_ids(evidence_ids: Iterable[str], evidence_by_id: dict[str, Any], representation_by_id: dict[str, Any]) -> list[str]:
    source_ids: set[str] = set()
    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if not evidence:
            continue
        representation = representation_by_id.get(evidence.get("representation_id"))
        if representation and isinstance(representation.get("source_id"), str):
            source_ids.add(representation["source_id"])
    return sorted(source_ids)


def _semantic_evidence_scores(request, retrieval, evidence_by_id, representations):
    embedding = request.embedding
    space = retrieval.get("embedding_space")
    if not isinstance(space, dict) or embedding is None:
        raise QueryError("snapshot has no compatible embedding space; rebuild is required")
    if space.get("model_id") != embedding.model_id or space.get("binding_id") != embedding.binding_id:
        raise QueryError("query embedding model does not match the snapshot embedding space")
    vector = embedding.vector
    dimension = space.get("dimensions")
    if not isinstance(dimension, int) or dimension < 1 or len(vector) != dimension:
        raise QueryError("query embedding dimensions do not match the snapshot")

    def norm(values):
        if not all(isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) for value in values):
            raise QueryError("embedding vector contains invalid values")
        length = math.sqrt(math.fsum(value * value for value in values))
        if not math.isfinite(length) or length <= 0:
            raise QueryError("embedding vector has no valid norm")
        return length

    query_norm = norm(vector)
    chunks = _records(retrieval.get("embeddings"), "embeddings")
    if not chunks:
        raise QueryError("snapshot contains no embedding vectors; rebuild is required")
    source_scores = {}
    for chunk in chunks:
        values = chunk.get("vector")
        start, end = chunk.get("start_char"), chunk.get("end_char")
        if not isinstance(values, list) or len(values) != dimension:
            raise QueryError("snapshot embedding dimensions are inconsistent")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise QueryError("snapshot embedding has invalid evidence coordinates")
        cosine = math.fsum(a * b for a, b in zip(vector, values)) / (query_norm * norm(values))
        score = (max(-1.0, min(1.0, cosine)) + 1.0) / 2.0
        source_scores.setdefault(chunk.get("source_id"), []).append((start, end, score))
    scores = {}
    for evidence_id, evidence in evidence_by_id.items():
        representation = representations.get(evidence.get("representation_id"), {})
        locator = evidence.get("locator", {})
        start, end = locator.get("start_char"), locator.get("end_char")
        if isinstance(start, int) and isinstance(end, int):
            matches = [score for lo, hi, score in source_scores.get(representation.get("source_id"), []) if lo < end and hi > start]
            if matches:
                scores[evidence_id] = max(matches)
    return scores


def query_project_snapshot(request: ProjectQueryRequest) -> ProjectQueryResult:
    if request.method != "query":
        raise QueryError("query_project_snapshot requires method=query")
    snapshot_payload = _load_json(Path(request.snapshot.path), request.snapshot.digest)
    retrieval_payload = _load_json(Path(request.retrieval.path), request.retrieval.digest)
    snapshot = ProjectSnapshot.model_validate(snapshot_payload)
    if snapshot.project_id != request.project_id or snapshot.id != request.snapshot_id:
        raise QueryError("query artifacts do not match the requested project snapshot")
    if not isinstance(retrieval_payload, dict) or retrieval_payload.get("snapshot_id") != snapshot.id:
        raise QueryError("retrieval artifact does not belong to the requested snapshot")
    manifest_id = "retrieval:graph"
    manifests = {item.id: item for item in snapshot.retrieval_manifests}
    graph_manifest = manifests.get(manifest_id)
    if graph_manifest is None or graph_manifest.artifact_hash != request.retrieval.digest:
        raise QueryError("retrieval artifact is not the snapshot graph manifest")

    entity_records = _records(retrieval_payload.get("entities"), "entities")
    assertion_records = _records(retrieval_payload.get("assertions"), "assertions")
    relation_records = _records(retrieval_payload.get("relations"), "relations")
    topic_records = _records(retrieval_payload.get("topics"), "topics")
    report_records = _records(retrieval_payload.get("reports"), "reports")
    evidence_records = _records(retrieval_payload.get("evidence"), "evidence")
    evidence_by_id = {item.get("id"): item for item in evidence_records if isinstance(item.get("id"), str)}
    representation_by_id = {item.id: item.model_dump(mode="json", by_alias=True) for item in snapshot.document_representations}
    entity_by_id = {item.get("id"): item for item in entity_records if isinstance(item.get("id"), str)}
    entity_ids = {item.id for item in snapshot.entities}
    evidence_ids = {item.id for item in snapshot.evidence_spans}
    for entity in entity_records:
        if entity.get("id") not in entity_ids:
            raise QueryError("retrieval artifact contains an unknown entity")
        for evidence_id in _string_list(entity.get("evidence_ids", []), "entity.evidence_ids"):
            if evidence_id not in evidence_ids:
                raise QueryError("retrieval artifact contains an unknown entity evidence")

    candidates: list[tuple[str, str, str, list[str]]] = []
    for entity in entity_records:
        evidence = _string_list(entity.get("evidence_ids", []), "entity.evidence_ids")
        candidates.append((str(entity["id"]), "entity", f"{entity.get('canonical_name', '')} ({entity.get('type', '')})", evidence))
    for assertion in assertion_records:
        subject = entity_by_id.get(assertion.get("subject_id"), {})
        object_name = assertion.get("object")
        text = f"{subject.get('canonical_name', assertion.get('subject_id', ''))} {assertion.get('predicate', '')} {object_name}"
        candidates.append((str(assertion["id"]), "assertion", text, _string_list(assertion.get("evidence_ids", []), "assertion.evidence_ids")))
    for relation in relation_records:
        source = entity_by_id.get(relation.get("source_entity_id"), {})
        target = entity_by_id.get(relation.get("target_entity_id"), {})
        text = f"{source.get('canonical_name', relation.get('source_entity_id', ''))} {relation.get('type', '')} {target.get('canonical_name', relation.get('target_entity_id', ''))}"
        candidates.append((str(relation["id"]), "relation", text, _string_list(relation.get("evidence_ids", []), "relation.evidence_ids")))
    for topic in topic_records:
        candidates.append((str(topic["id"]), "topic", str(topic.get("title", "")), _string_list(topic.get("evidence_ids", []), "topic.evidence_ids")))
    for report in report_records:
        candidates.append((str(report["id"]), "report", f"{report.get('title', '')} {report.get('summary', '')}", _string_list(report.get("evidence_ids", []), "report.evidence_ids")))
    for evidence in evidence_records:
        candidates.append((str(evidence["id"]), "evidence", str(evidence.get("quote", "")), [str(evidence["id"])]))

    allowed_sources = set(request.source_ids) if request.source_ids is not None else None
    evidence_scores = _semantic_evidence_scores(request, retrieval_payload, evidence_by_id, representation_by_id) if request.mode == "semantic" else None
    hits = []
    for item_id, kind, text, evidence in candidates:
        sources = _source_ids(evidence, evidence_by_id, representation_by_id)
        if not evidence or not sources:
            continue
        if allowed_sources is not None and not set(sources).issubset(allowed_sources):
            continue
        if evidence_scores is not None:
            matches = [evidence_scores[item] for item in evidence if item in evidence_scores]
            if not matches:
                continue
            score = max(matches)
        else:
            score = _score(request.query or "", text)
            if score <= 0:
                continue
        hits.append(QueryHit(
            id=item_id,
            kind=kind,
            title=text.split(" ", 1)[0] if kind == "evidence" else text[:160],
            text=text,
            score=score,
            evidence_ids=evidence,
            source_ids=sources,
        ))
    hits.sort(key=lambda item: (-item.score, item.kind, item.id))
    return ProjectQueryResult(
        project_id=snapshot.project_id,
        snapshot_id=snapshot.id,
        query=request.query or "",
        contexts=hits[:request.limit],
        retrieval_manifest_id=manifest_id,
    )
