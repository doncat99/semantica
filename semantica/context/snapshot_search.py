"""Grounded artifact projection for ContextRetriever (no independent scoring)."""

import json
from typing import Any, Iterable

from ..vector_store.vector_store import VectorRetriever


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"retrieval artifact field {field} is invalid")
    return value


def _fact_text(subject: str, predicate: Any, object_value: Any, qualifiers: Any, status: Any) -> tuple[str, str]:
    if not isinstance(qualifiers, dict) or qualifiers.get("polarity", "positive") not in {"positive", "negative"}:
        raise ValueError("retrieval artifact fact has invalid polarity")
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


def rank_evidence(embedding, retrieval, evidence_by_id, representations):
    space = retrieval.get("embedding_space")
    if not isinstance(space, dict) or embedding is None:
        raise ValueError("snapshot has no compatible embedding space; rebuild is required")
    if space.get("model_id") != embedding.model_id or space.get("binding_id") != embedding.binding_id:
        raise ValueError("query embedding model does not match the snapshot embedding space")
    vector = embedding.vector
    dimension = space.get("dimensions")
    if not isinstance(dimension, int) or dimension < 1 or len(vector) != dimension:
        raise ValueError("query embedding dimensions do not match the snapshot")

    chunks = retrieval.get("embeddings")
    if not isinstance(chunks, list) or any(not isinstance(chunk, dict) for chunk in chunks):
        raise ValueError("retrieval artifact field embeddings is invalid")
    if not chunks:
        raise ValueError("snapshot contains no embedding vectors; rebuild is required")
    for chunk in chunks:
        start, end = chunk.get("start_char"), chunk.get("end_char")
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                or not isinstance(end, int) or start < 0 or end <= start):
            raise ValueError("snapshot embedding has invalid evidence coordinates")
    try:
        ranked = VectorRetriever().search_similar(vector, [chunk.get("vector") for chunk in chunks],
                                                   [str(index) for index in range(len(chunks))], k=len(chunks))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"snapshot embedding space is invalid: {exc}") from exc
    source_evidence = {}
    for evidence_id, evidence in evidence_by_id.items():
        representation = representations.get(evidence.get("representation_id"), {})
        locator = evidence.get("locator", {})
        start, end = locator.get("start_char"), locator.get("end_char")
        if isinstance(start, int) and isinstance(end, int):
            source_evidence.setdefault(representation.get("source_id"), []).append((evidence_id, start, end))
    scores = {}
    for hit in ranked:
        chunk = chunks[int(hit["id"])]
        for evidence_id, start, end in source_evidence.get(chunk.get("source_id"), []):
            if chunk["start_char"] < end and chunk["end_char"] > start:
                scores.setdefault(evidence_id, hit["score"])
    return scores


def prepare_snapshot(snapshot):
    """Project admitted artifact records for the native retriever; never copy artifacts to disk."""
    def records(items):
        return [item.model_dump(mode="json", by_alias=True) for item in items]
    evidence_records = records(snapshot.evidence_spans)
    entity_records = records(snapshot.entities)
    assertion_records = records(snapshot.assertions)
    relation_records = records(snapshot.relations)
    conflict_records = records(snapshot.conflicts)
    topic_records = records(snapshot.topics)
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
    for conflict in conflict_records:
        text = f"{conflict.get('conflict_type', '')} conflict ({conflict.get('status', '')}): {conflict.get('reason', '')}"
        candidates.append((str(conflict["id"]), "conflict", text, _string_list(conflict.get("evidence_ids", []), "conflict.evidence_ids"), conflict.get("status"), None))
    for topic in topic_records:
        candidates.append((str(topic["id"]), "topic", str(topic.get("title", "")), _string_list(topic.get("evidence_ids", []), "topic.evidence_ids"), None, None))
    for evidence in evidence_records:
        candidates.append((str(evidence["id"]), "evidence", str(evidence.get("quote", "")), [str(evidence["id"])], evidence.get("origin"), None))

    prepared = []
    for item_id, kind, text, evidence, status, polarity in candidates:
        sources = _source_ids(evidence, evidence_by_id, representation_by_id)
        if evidence and sources:
            prepared.append((item_id, kind, text, evidence, status, polarity, sources))
    return evidence_by_id, representation_by_id, prepared
