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


def _validated_records(value: Any, field: str, snapshot_items: Iterable[Any], evidence_ids: set[str]) -> list[dict[str, Any]]:
    records = _records(value, field)
    expected = {item.id: item.model_dump(mode="json", by_alias=True) for item in snapshot_items}
    seen: set[str] = set()
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or record_id in seen or record_id not in expected:
            raise QueryError(f"retrieval artifact contains an unknown or duplicate {field} record")
        if record != expected[record_id]:
            raise QueryError(f"retrieval artifact {field} record does not match the snapshot")
        evidence = _string_list(record.get("evidence_ids"), f"{field}.evidence_ids")
        if not evidence or not set(evidence).issubset(evidence_ids):
            raise QueryError(f"retrieval artifact contains an ungrounded {field} record")
        seen.add(record_id)
    if seen != set(expected):
        raise QueryError(f"retrieval artifact does not cover snapshot {field} records")
    return records


def _validated_evidence_records(value: Any, snapshot: ProjectSnapshot) -> list[dict[str, Any]]:
    records = _records(value, "evidence")
    expected = {item.id: item.model_dump(mode="json", by_alias=True) for item in snapshot.evidence_spans}
    seen: set[str] = set()
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or record_id in seen or record_id not in expected:
            raise QueryError("retrieval artifact contains an unknown or duplicate evidence record")
        if record != expected[record_id]:
            raise QueryError("retrieval artifact evidence record does not match the snapshot")
        seen.add(record_id)
    if seen != set(expected):
        raise QueryError("retrieval artifact does not cover snapshot evidence records")
    return records


def _fact_text(subject: str, predicate: Any, object_value: Any, qualifiers: Any, status: Any) -> tuple[str, str]:
    if not isinstance(qualifiers, dict) or qualifiers.get("polarity", "positive") not in {"positive", "negative"}:
        raise QueryError("retrieval artifact fact has invalid polarity")
    polarity = qualifiers.get("polarity", "positive")
    object_text = json.dumps(object_value, ensure_ascii=False, sort_keys=True) if isinstance(object_value, dict) else str(object_value)
    text = f"{subject} {'does not ' if polarity == 'negative' else ''}{predicate} {object_text}"
    context = [f"{key}={qualifiers[key]}" for key in ("condition", "time", "unit", "value") if qualifiers.get(key) is not None]
    if context:
        text += f" ({'; '.join(context)})"
    if status == "contradicted":
        text = f"Contradicted {'negative ' if polarity == 'negative' else ''}fact: {text}"
    elif status == "retracted":
        text = f"Retracted fact: {text}"
    elif status == "rejected":
        text = f"Rejected fact: {text}"
    return text, polarity


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

    evidence_ids = {item.id for item in snapshot.evidence_spans}
    evidence_records = _validated_evidence_records(retrieval_payload.get("evidence"), snapshot)
    entity_records = _validated_records(retrieval_payload.get("entities"), "entities", snapshot.entities, evidence_ids)
    assertion_records = _validated_records(retrieval_payload.get("assertions"), "assertions", snapshot.assertions, evidence_ids)
    relation_records = _validated_records(retrieval_payload.get("relations"), "relations", snapshot.relations, evidence_ids)
    identity_records = _validated_records(retrieval_payload.get("identity_decisions", []), "identity_decisions", snapshot.identity_decisions, evidence_ids)
    conflict_records = _validated_records(retrieval_payload.get("conflicts", []), "conflicts", snapshot.conflicts, evidence_ids)
    topic_records = _validated_records(retrieval_payload.get("topics"), "topics", snapshot.topics, evidence_ids)
    report_records = _validated_records(retrieval_payload.get("reports"), "reports", snapshot.reports, evidence_ids)
    evidence_by_id = {item.get("id"): item for item in evidence_records if isinstance(item.get("id"), str)}
    representation_by_id = {item.id: item.model_dump(mode="json", by_alias=True) for item in snapshot.document_representations}
    entity_by_id = {item.get("id"): item for item in entity_records if isinstance(item.get("id"), str)}

    candidates: list[tuple[str, str, str, list[str], str | None, str | None]] = []
    for entity in entity_records:
        evidence = _string_list(entity.get("evidence_ids", []), "entity.evidence_ids")
        candidates.append((str(entity["id"]), "entity", f"{entity.get('canonical_name', '')} ({entity.get('type', '')})", evidence, entity.get("status"), None))
    for assertion in assertion_records:
        subject = entity_by_id.get(assertion.get("subject_id"), {})
        text, polarity = _fact_text(subject.get("canonical_name", assertion.get("subject_id", "")), assertion.get("predicate", ""), assertion.get("object"), assertion.get("qualifiers"), assertion.get("status"))
        candidates.append((str(assertion["id"]), "assertion", text, _string_list(assertion.get("evidence_ids", []), "assertion.evidence_ids"), assertion.get("status"), polarity))
    for relation in relation_records:
        source = entity_by_id.get(relation.get("source_entity_id"), {})
        target = entity_by_id.get(relation.get("target_entity_id"), {})
        text, polarity = _fact_text(source.get("canonical_name", relation.get("source_entity_id", "")), relation.get("type", ""), target.get("canonical_name", relation.get("target_entity_id", "")), relation.get("qualifiers"), relation.get("status"))
        candidates.append((str(relation["id"]), "relation", text, _string_list(relation.get("evidence_ids", []), "relation.evidence_ids"), relation.get("status"), polarity))
    for decision in identity_records:
        names = [entity_by_id.get(item, {}).get("canonical_name", item) for item in decision.get("from_entity_ids", [])]
        text = f"{decision.get('decision_type', '')} identity: {', '.join(names)}; {decision.get('reason', '')}"
        candidates.append((str(decision["id"]), "identity_decision", text, _string_list(decision.get("evidence_ids", []), "identity_decision.evidence_ids"), decision.get("decision_type"), None))
    for conflict in conflict_records:
        text = f"{conflict.get('conflict_type', '')} conflict ({conflict.get('status', '')}): {conflict.get('reason', '')}"
        candidates.append((str(conflict["id"]), "conflict", text, _string_list(conflict.get("evidence_ids", []), "conflict.evidence_ids"), conflict.get("status"), None))
    for topic in topic_records:
        candidates.append((str(topic["id"]), "topic", str(topic.get("title", "")), _string_list(topic.get("evidence_ids", []), "topic.evidence_ids"), None, None))
    for report in report_records:
        candidates.append((str(report["id"]), "report", f"{report.get('title', '')} {report.get('summary', '')}", _string_list(report.get("evidence_ids", []), "report.evidence_ids"), None, None))
    for evidence in evidence_records:
        candidates.append((str(evidence["id"]), "evidence", str(evidence.get("quote", "")), [str(evidence["id"])], evidence.get("origin"), None))

    allowed_sources = set(request.source_ids) if request.source_ids is not None else None
    evidence_scores = _semantic_evidence_scores(request, retrieval_payload, evidence_by_id, representation_by_id) if request.mode == "semantic" else None
    hits = []
    for item_id, kind, text, evidence, status, polarity in candidates:
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
            status=status,
            polarity=polarity,
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
