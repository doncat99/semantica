"""Semantica-owned project snapshot build pipeline.

The worker receives only immutable local source files and release metadata. Every
semantic object in the snapshot is produced here; callers cannot provide graph
objects, evidence, or precomputed entities.
"""
from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from .project_source import UnsupportedSourceFormatError, parse_source
from .project_snapshot_schema import (
    ArtifactManifest,
    ChangeDelta,
    DocumentLocator,
    DocumentRepresentation,
    EvidenceSpan,
    IdentityDecision,
    KernelLineage,
    KnowledgeAssertion,
    KnowledgeCommunity,
    KnowledgeConflict,
    KnowledgeRelation,
    KnowledgeEntity,
    KnowledgeReport,
    KnowledgeTopic,
    ModelReceipt,
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    RetrievalArtifactManifest,
    stable_digest,
)
from .semantic_extract import NamedEntityRecognizer


class SnapshotBuildError(RuntimeError):
    """Raised when a source cannot be represented by the single Semantica chain."""


def _relay_json(relay: Any, payload: dict[str, Any], operation: str) -> tuple[dict[str, Any], ModelReceipt]:
    token = os.environ.get(relay.authorization_env)
    if not token:
        raise SnapshotBuildError(f"missing relay authorization environment: {relay.authorization_env}")
    request_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        relay.base_url,
        data=request_bytes,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_bytes = response.read()
            if response.status != 200:
                raise SnapshotBuildError(f"{operation} relay returned HTTP {response.status}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SnapshotBuildError(f"{operation} relay request failed") from exc
    try:
        decoded = json.loads(response_bytes)
    except json.JSONDecodeError as exc:
        raise SnapshotBuildError(f"{operation} relay returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise SnapshotBuildError(f"{operation} relay returned a non-object response")
    receipt_digest = sha256((operation + ":" + _digest_bytes(request_bytes) + ":" + _digest_bytes(response_bytes)).encode("utf-8")).hexdigest()[:32]
    receipt = ModelReceipt(
        id=f"receipt:{receipt_digest}",
        operation=operation,
        provider="bifrost-loopback",
        model=relay.model_id,
        input_digest=_digest_bytes(request_bytes),
        output_digest=_digest_bytes(response_bytes),
        parameters={"relay_url": relay.base_url},
    )
    return decoded, receipt


def _structured_extract(text: str, relay: Any) -> tuple[dict[str, Any], ModelReceipt]:
    payload = {
        "model": relay.model_id,
        "messages": [
            {"role": "system", "content": "Extract only facts explicitly supported by the source. Return strict JSON with entities [{name,type}] and relations [{subject,predicate,object,evidence}]. Do not invent facts."},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    response, receipt = _relay_json(relay, payload, "structured_extraction")
    if response.get("model") != relay.model_id:
        raise SnapshotBuildError("structured extraction response model does not match the admitted relay model")
    if isinstance(response.get("usage"), dict):
        receipt.metadata["usage"] = response["usage"]
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise SnapshotBuildError("structured extraction response has invalid choices")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise SnapshotBuildError("structured extraction response has no JSON content")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SnapshotBuildError("structured extraction content is not valid JSON") from exc
    if not isinstance(result, dict) or not isinstance(result.get("entities"), list) or not isinstance(result.get("relations"), list):
        raise SnapshotBuildError("structured extraction JSON must contain entities and relations arrays")
    return result, receipt


def _embed_text(text: str, relay: Any) -> tuple[list[float], ModelReceipt]:
    response, receipt = _relay_json(relay, {"input": [text], "model": relay.model_id}, "embedding")
    if response.get("model") != relay.model_id:
        raise SnapshotBuildError("embedding response model does not match the admitted relay model")
    if isinstance(response.get("usage"), dict):
        receipt.metadata["usage"] = response["usage"]
    data = response.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise SnapshotBuildError("embedding response has invalid data")
    vector = data[0].get("embedding")
    if not isinstance(vector, list) or not vector or not all(isinstance(value, (int, float)) and value == value for value in vector):
        raise SnapshotBuildError("embedding response has invalid vector")
    return [float(value) for value in vector], receipt


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _safe_id(value: str) -> str:
    return value.replace(" ", "_").replace("/", "_")[:100]


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return _digest_bytes(encoded)


def _parse_source(source: Any, force_ocr: bool) -> tuple[str, dict[str, Any], str, str, str, str]:
    path = Path(source.file_path).resolve()
    if not path.is_file():
        raise SnapshotBuildError(f"source is not a file: {source.source_id}")
    content_hash = _digest_file(path)
    try:
        parsed = parse_source(
            path,
            name=source.name,
            mime_type=source.mime_type,
            force_ocr=force_ocr,
        )
    except UnsupportedSourceFormatError as exc:
        raise SnapshotBuildError(str(exc)) from exc
    document = {**parsed.document, "content_hash": content_hash, "mime_type": source.mime_type}
    return parsed.text, document, parsed.origin, content_hash, parsed.parser, parsed.parser_version


def _span_id(source_id: str, start: int, end: int) -> str:
    return f"evidence:{_safe_id(source_id)}:{start}:{end}"


def _entity_id(source_id: str, name: str, entity_type: str) -> str:
    """Keep extracted candidates source-scoped until identity is proven."""
    key = f"{source_id}:{entity_type}:{name.casefold()}"
    return f"entity:{sha256(key.encode()).hexdigest()[:24]}"


def _find_span(text: str, quote: str, start: int = 0) -> tuple[int, int]:
    position = text.find(quote, max(0, start))
    if position < 0:
        position = text.casefold().find(quote.casefold(), max(0, start))
    if position < 0:
        return 0, max(1, min(len(text), len(quote)))
    return position, position + len(quote)


def _build_source(source: Any, force_ocr: bool, model_result: dict[str, Any] | None = None, parsed: tuple[str, dict[str, Any], str, str, str, str] | None = None) -> dict[str, Any]:
    text, document, origin, content_hash, parser, parser_version = parsed or _parse_source(source, force_ocr)
    representation_id = f"representation:{_safe_id(source.source_id)}"
    representation_artifact_id = f"artifact:representation:{_safe_id(source.source_id)}"
    entities: dict[str, KnowledgeEntity] = {}
    evidence: dict[str, EvidenceSpan] = {}
    if model_result is None:
        entities_raw = [
            {"name": item.text, "type": "MENTION", "detected_label": item.label, "confidence": item.confidence}
            for item in NamedEntityRecognizer(method="pattern").extract_entities(text)
        ]
    else:
        entities_raw = model_result["entities"]
    for item in entities_raw:
        if not isinstance(item, dict):
            raise SnapshotBuildError("entity extraction result must contain objects")
        name = item.get("name")
        entity_type = item.get("type")
        if not isinstance(name, str) or not name.strip() or not isinstance(entity_type, str) or not entity_type.strip():
            raise SnapshotBuildError("entity extraction result has an invalid name or type")
        name = name.strip()
        entity_type = entity_type.strip()
        start, end = _find_span(text, name)
        if text[start:end].casefold() != name.casefold():
            raise SnapshotBuildError(f"entity is not present in source text: {name}")
        evidence_id = _span_id(source.source_id, start, end)
        evidence[evidence_id] = EvidenceSpan(
            id=evidence_id,
            representation_id=representation_id,
            locator=DocumentLocator(
                representation_id=representation_id,
                origin=origin,
                quote=text[start:end],
                start_char=start,
                end_char=end,
                quality="precise",
            ),
            quote=text[start:end],
            confidence=item.get("confidence"),
        )
        entity_id = _entity_id(source.source_id, name, entity_type)
        current = entities.get(entity_id)
        if current is None:
            entities[entity_id] = KnowledgeEntity(
                id=entity_id,
                canonical_name=name,
                type=entity_type,
                aliases=[],
                evidence_ids=[evidence_id],
                status="candidate",
                metadata={"extraction_method": "model" if model_result is not None else "pattern", "source_ids": [source.source_id], **({"detected_label": item["detected_label"]} if item.get("detected_label") else {})},
            )
        elif evidence_id not in current.evidence_ids:
            current.evidence_ids.append(evidence_id)
    assertions: list[KnowledgeAssertion] = []
    relations: list[KnowledgeRelation] = []
    if model_result is not None:
        entity_by_name = {entity.canonical_name.casefold(): entity for entity in entities.values()}
        for index, item in enumerate(model_result["relations"]):
            if not isinstance(item, dict):
                raise SnapshotBuildError("relation extraction result must contain objects")
            subject = item.get("subject")
            predicate = item.get("predicate")
            object_name = item.get("object")
            quote = item.get("evidence")
            if not all(isinstance(value, str) and value.strip() for value in (subject, predicate, object_name, quote)):
                raise SnapshotBuildError("relation extraction result has invalid fields")
            subject_entity = entity_by_name.get(subject.strip().casefold())
            object_entity = entity_by_name.get(object_name.strip().casefold())
            if not subject_entity or not object_entity:
                raise SnapshotBuildError("relation endpoint is absent from extracted entities")
            if subject_entity.id == object_entity.id:
                raise SnapshotBuildError("self relations are not accepted")
            start, end = _find_span(text, quote.strip())
            if text[start:end] != quote.strip():
                raise SnapshotBuildError("relation evidence is not an exact source quote")
            evidence_id = _span_id(source.source_id, start, end)
            evidence[evidence_id] = EvidenceSpan(
                id=evidence_id,
                representation_id=representation_id,
                locator=DocumentLocator(representation_id=representation_id, origin=origin, quote=quote.strip(), start_char=start, end_char=end, quality="precise"),
                quote=quote.strip(),
            )
            relation_id = f"relation:{_safe_id(source.source_id)}:{index}"
            assertion_id = f"assertion:{_safe_id(source.source_id)}:{index}"
            relations.append(KnowledgeRelation(id=relation_id, source_entity_id=subject_entity.id, target_entity_id=object_entity.id, type=predicate.strip(), evidence_ids=[evidence_id], status="candidate"))
            assertions.append(KnowledgeAssertion(id=assertion_id, subject_id=subject_entity.id, predicate=predicate.strip(), object=object_name.strip(), object_entity_id=object_entity.id, evidence_ids=[evidence_id], status="candidate"))
    representation = DocumentRepresentation(
        id=representation_id,
        source_id=source.source_id,
        material_revision_id=source.material_revision,
        input_revision=content_hash,
        media_type=source.mime_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        content_hash=content_hash,
        parser=parser,
        parser_version=parser_version,
        recipe_id="model" if model_result is not None else "deterministic",
        recipe_digest=stable_digest({"parser": document.get("format"), "ocr": force_ocr}),
        origin="mixed" if force_ocr else origin,
        artifact_ref_id=representation_artifact_id,
        metadata={"text_length": len(text), "source_name": source.name, "document": document},
    )
    return {"source": source, "text": text, "representation": representation, "evidence": list(evidence.values()), "entities": list(entities.values()), "assertions": assertions, "relations": relations, "artifact_id": representation_artifact_id, "document": document}


def _canonical_graph_projection(
    entities: list[KnowledgeEntity],
    relations: list[KnowledgeRelation],
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Validate one snapshot graph through Semantica's canonical graph owners.

    The project snapshot schema remains the stable interchange contract. The
    graph components receive explicit candidates produced by this pipeline;
    they never receive source text and therefore cannot open a second
    extraction path or silently replace evidence IDs.
    """
    from .context import ContextGraph
    from .kg import GraphBuilder

    graph = GraphBuilder(
        merge_entities=False,
        resolve_conflicts=False,
        fail_closed=True,
    ).build({
        "entities": [
            {
                "id": entity.id,
                "text": entity.canonical_name,
                "type": entity.type,
                "metadata": entity.metadata,
            }
            for entity in entities
        ],
        "relationships": [
            {
                "id": relation.id,
                "source": relation.source_entity_id,
                "target": relation.target_entity_id,
                "type": relation.type,
                "metadata": {
                    **relation.metadata,
                    "evidence_ids": relation.evidence_ids,
                },
            }
            for relation in relations
        ],
    })
    graph_entities = graph.get("entities")
    graph_relationships = graph.get("relationships")
    if not isinstance(graph_entities, list) or not isinstance(graph_relationships, list):
        raise SnapshotBuildError("Semantica GraphBuilder returned an invalid graph")
    expected_entity_ids = {entity.id for entity in entities}
    expected_relation_ids = {relation.id for relation in relations}
    actual_entity_ids = {item.get("id") for item in graph_entities if isinstance(item, dict)}
    actual_relation_ids = {item.get("id") for item in graph_relationships if isinstance(item, dict)}
    if actual_entity_ids != expected_entity_ids or actual_relation_ids != expected_relation_ids:
        raise SnapshotBuildError("Semantica graph components changed snapshot identities")

    context = ContextGraph(
        extract_entities=False,
        extract_relationships=False,
        advanced_analytics=False,
    )
    added_nodes = context.add_nodes([
        {"id": item["id"], "type": item.get("type", "entity"), "content": item.get("text", item["id"])}
        for item in graph_entities
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ])
    added_edges = context.add_edges([
        {
            "id": item["id"],
            "source": item["source"],
            "target": item["target"],
            "type": item.get("type", "related_to"),
            "metadata": item.get("metadata", {}),
        }
        for item in graph_relationships
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("source"), str)
        and isinstance(item.get("target"), str)
    ])
    if added_nodes != len(expected_entity_ids) or added_edges != len(expected_relation_ids):
        raise SnapshotBuildError("Semantica ContextGraph rejected a snapshot graph candidate")
    return graph_relationships, list(context.edges)


def _provenance_projection(
    representations: list[DocumentRepresentation],
    evidence: list[EvidenceSpan],
    entities: list[KnowledgeEntity],
    relations: list[KnowledgeRelation],
) -> dict[str, Any]:
    """Materialize source lineage with the canonical provenance manager."""
    from .provenance import ProvenanceManager

    representation_by_id = {item.id: item for item in representations}
    with tempfile.TemporaryDirectory(prefix="semantica-provenance-") as directory:
        manager = ProvenanceManager(storage_path=str(Path(directory) / "provenance.db"))
        for span in evidence:
            representation = representation_by_id.get(span.representation_id)
            if not representation:
                raise SnapshotBuildError(f"evidence references unknown representation: {span.id}")
            locator = span.locator
            location = (
                f"char:{locator.start_char}-{locator.end_char}"
                if locator.start_char is not None and locator.end_char is not None
                else f"page:{locator.page}"
                if locator.page is not None
                else "structural"
            )
            if manager.track_entity(
                span.id,
                representation.source_id,
                entity_type="evidence",
                source_location=location,
                source_quote=span.quote,
                confidence=span.confidence if span.confidence is not None else 1.0,
                metadata={"origin": locator.origin, "evidence_kind": span.origin, "quality": locator.quality},
            ) is None:
                raise SnapshotBuildError(f"failed to persist provenance for evidence: {span.id}")
        for entity in entities:
            source_ids = entity.metadata.get("source_ids", [])
            source = source_ids[0] if isinstance(source_ids, list) and source_ids and isinstance(source_ids[0], str) else "snapshot"
            if manager.track_entity(entity.id, source, entity_type=entity.type, metadata={"evidence_ids": entity.evidence_ids}) is None:
                raise SnapshotBuildError(f"failed to persist provenance for entity: {entity.id}")
        for relation in relations:
            source = "snapshot"
            if relation.evidence_ids:
                evidence_entry = manager.get_lineage(relation.evidence_ids[0])
                source_documents = evidence_entry.get("source_documents", []) if isinstance(evidence_entry, dict) else []
                if source_documents and isinstance(source_documents[0], str):
                    source = source_documents[0]
            if manager.track_relationship(
                relation.id,
                source,
                metadata={"evidence_ids": relation.evidence_ids},
            ) is None:
                raise SnapshotBuildError(f"failed to persist provenance for relation: {relation.id}")
        return {
            "evidence": {span.id: manager.get_lineage(span.id) for span in evidence},
            "entities": {entity.id: manager.get_lineage(entity.id) for entity in entities},
            "relations": {relation.id: manager.get_lineage(relation.id) for relation in relations},
        }


def _validate_embedding_projection(source_builds: list[dict[str, Any]]) -> None:
    """Exercise the canonical vector runtime without replacing stable IDs."""
    vectors = [item.get("embedding") for item in source_builds if item.get("embedding") is not None]
    if not vectors:
        return
    import numpy as np
    from .vector_store import VectorStore

    if any(not isinstance(vector, list) or not vector for vector in vectors):
        raise SnapshotBuildError("embedding projection contains an invalid vector")
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise SnapshotBuildError("embedding projection contains inconsistent dimensions")
    store = VectorStore(backend="inmemory", config={"dimension": dimension}, max_workers=1)
    stored_ids = store.store_vectors(
        [np.asarray(vector, dtype=np.float32) for vector in vectors],
        metadata=[{"source_id": item["source"].source_id} for item in source_builds if item.get("embedding") is not None],
    )
    if len(stored_ids) != len(vectors):
        raise SnapshotBuildError("vector runtime projection stored an incomplete embedding set")
    for vector in vectors:
        if not store.search_vectors(np.asarray(vector, dtype=np.float32), k=1):
            raise SnapshotBuildError("vector runtime projection cannot retrieve its stored embedding")


def _semantic_organization(
    entities: list[KnowledgeEntity],
    assertions: list[KnowledgeAssertion],
    relations: list[KnowledgeRelation],
    evidence: list[EvidenceSpan],
    model_receipts: list[ModelReceipt],
) -> tuple[list[IdentityDecision], list[KnowledgeCommunity], list[KnowledgeTopic], list[KnowledgeReport], list[KnowledgeConflict]]:
    """Create the project-level organization owned by the Semantica kernel.

    This is deliberately graph-native and deterministic. It does not invent
    facts or use a second extractor: every output points back to the candidate
    entities, assertions, relations, and evidence produced above.
    """
    evidence_by_id = {item.id: item for item in evidence}
    canonical_relationships, context_edges = _canonical_graph_projection(entities, relations)
    relation_by_id = {relation.id: relation for relation in relations}
    if {item.get("id") for item in canonical_relationships if isinstance(item, dict)} != set(relation_by_id):
        raise SnapshotBuildError("Semantica graph projection lost a relation candidate")
    # Source-scoped candidates are intentionally left unresolved. A durable
    # cross-source merge requires an identity model decision or human evidence;
    # a matching label alone is not sufficient.
    identities: list[IdentityDecision] = []

    # Connected components are the stable project graph communities. Isolated
    # entities remain visible as singleton communities instead of disappearing.
    adjacency: dict[str, set[str]] = {entity.id: set() for entity in entities}
    for edge in context_edges:
        adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        adjacency.setdefault(edge.target_id, set()).add(edge.source_id)

    components: list[list[str]] = []
    unseen = set(adjacency)
    while unseen:
        root = min(unseen)
        queue = [root]
        unseen.remove(root)
        component: list[str] = []
        while queue:
            current = queue.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, ())):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))

    entity_by_id = {entity.id: entity for entity in entities}
    communities: list[KnowledgeCommunity] = []
    topics: list[KnowledgeTopic] = []
    reports: list[KnowledgeReport] = []
    for component in components:
        member_set = set(component)
        internal_relations = [
            relation_by_id[edge.edge_id]
            for edge in context_edges
            if edge.edge_id in relation_by_id
            and edge.source_id in member_set
            and edge.target_id in member_set
        ]
        member_assertions = [
            assertion
            for assertion in assertions
            if assertion.subject_id in member_set or assertion.object_entity_id in member_set
        ]
        evidence_ids = sorted(
            {
                evidence_id
                for item in [*member_assertions, *internal_relations]
                for evidence_id in item.evidence_ids
                if evidence_id in evidence_by_id
            }
        )
        community_digest = sha256("|".join(component).encode("utf-8")).hexdigest()[:24]
        community_id = f"community:{community_digest}"
        names = [entity_by_id[item].canonical_name for item in component]
        title = " / ".join(names[:3])
        if len(names) > 3:
            title += f" +{len(names) - 3}"
        communities.append(
            KnowledgeCommunity(
                id=community_id,
                level=0,
                title=title,
                entity_ids=component,
                relation_ids=[relation.id for relation in internal_relations],
                metrics={"entity_count": len(component), "relation_count": len(internal_relations)},
            )
        )
        topic_id = f"topic:{community_digest}"
        topics.append(
            KnowledgeTopic(
                id=topic_id,
                title=title,
                community_ids=[community_id],
                entity_ids=component,
                assertion_ids=[assertion.id for assertion in member_assertions],
                evidence_ids=evidence_ids,
            )
        )
        relation_text = ", ".join(
            f"{entity_by_id[item.source_entity_id].canonical_name} {item.type} {entity_by_id[item.target_entity_id].canonical_name}"
            for item in internal_relations[:8]
        )
        summary = f"{len(component)} entities form one connected knowledge community."
        if relation_text:
            summary += f" Supported relations: {relation_text}."
        reports.append(
            KnowledgeReport(
                id=f"report:community:{community_digest}",
                report_type="community",
                title=title,
                summary=summary,
                community_id=community_id,
                topic_id=topic_id,
                evidence_ids=evidence_ids,
                model_receipt_ids=[receipt.id for receipt in model_receipts],
                content_hash=stable_digest({"title": title, "summary": summary, "evidence": evidence_ids}),
                metadata={"producer": "semantica", "assertion_count": len(member_assertions)},
            )
        )

    conflicts: list[KnowledgeConflict] = []
    by_normalized_name: dict[str, list[KnowledgeEntity]] = defaultdict(list)
    for entity in entities:
        by_normalized_name[" ".join(entity.canonical_name.casefold().split())].append(entity)
    for normalized_name, same_name in by_normalized_name.items():
        source_ids = {
            source_id
            for entity in same_name
            for source_id in entity.metadata.get("source_ids", [])
        }
        if len(source_ids) < 2:
            continue
        entity_ids = sorted(entity.id for entity in same_name)
        evidence_ids = sorted({evidence_id for entity in same_name for evidence_id in entity.evidence_ids if evidence_id in evidence_by_id})
        conflict_digest = sha256(normalized_name.encode("utf-8")).hexdigest()[:24]
        conflicts.append(
            KnowledgeConflict(
                id=f"conflict:identity:{conflict_digest}",
                conflict_type="identity",
                status="open",
                entity_ids=entity_ids,
                evidence_ids=evidence_ids,
                reason="same normalized mention appears in multiple sources; identity is unresolved",
            )
        )
    return identities, communities, topics, reports, conflicts


def _change_delta(
    base_snapshot: ProjectSnapshot | None,
    snapshot_id: str,
    representations: list[DocumentRepresentation],
    entities: list[KnowledgeEntity],
    assertions: list[KnowledgeAssertion],
    relations: list[KnowledgeRelation],
    reports: list[KnowledgeReport],
    retrieval_manifest_ids: list[str],
) -> ChangeDelta:
    if base_snapshot is None:
        return ChangeDelta(
            changed_representation_ids=[item.id for item in representations],
            added_ids=[item.id for item in [*entities, *assertions, *relations, *reports]],
            affected_report_ids=[item.id for item in reports],
            affected_retrieval_manifest_ids=retrieval_manifest_ids,
            reason="initial Semantica project build",
        )

    def keyed(items: list[Any]) -> dict[str, str]:
        return {item.id: stable_digest(item.model_dump(mode="json", by_alias=True)) for item in items}

    current = {"representation": keyed(representations), "entity": keyed(entities), "assertion": keyed(assertions), "relation": keyed(relations), "report": keyed(reports)}
    previous = {"representation": keyed(base_snapshot.document_representations), "entity": keyed(base_snapshot.entities), "assertion": keyed(base_snapshot.assertions), "relation": keyed(base_snapshot.relations), "report": keyed(base_snapshot.reports)}
    added: list[str] = []
    updated: list[str] = []
    retracted: list[str] = []
    for kind in current:
        current_ids = set(current[kind])
        previous_ids = set(previous[kind])
        added.extend(sorted(current_ids - previous_ids))
        retracted.extend(sorted(previous_ids - current_ids))
        updated.extend(sorted(item_id for item_id in current_ids & previous_ids if current[kind][item_id] != previous[kind][item_id]))
    representation_ids = set(current["representation"]) | set(previous["representation"])
    changed_representation_ids = sorted(set(added + updated + retracted) & representation_ids)
    affected_report_ids = sorted({item.id for item in reports if item.id in set(added + updated) or item.id in set(retracted)})
    if changed_representation_ids:
        affected_report_ids = sorted(set(affected_report_ids) | {item.id for item in reports})
    return ChangeDelta(
        base_snapshot_id=base_snapshot.id,
        changed_representation_ids=changed_representation_ids,
        added_ids=sorted(set(added)),
        updated_ids=sorted(set(updated)),
        retracted_ids=sorted(set(retracted)),
        affected_report_ids=affected_report_ids,
        affected_retrieval_manifest_ids=retrieval_manifest_ids if (added or updated or retracted) else [],
        reason=f"diff from Semantica snapshot {base_snapshot.id} to {snapshot_id}",
    )


def build_project_snapshot(request: ProjectSnapshotBuildRequest) -> dict[str, Any]:
    """Build, validate, and materialize one immutable snapshot and its artifacts."""
    if request.recipe.id not in {"deterministic", "model"}:
        raise SnapshotBuildError(
            f"unsupported project snapshot recipe: {request.recipe.id}; "
            "supported recipes are deterministic and model"
        )
    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base_snapshot: ProjectSnapshot | None = None
    if request.base_snapshot:
        base_path = Path(request.base_snapshot.snapshot_path).resolve()
        if not base_path.is_file():
            raise SnapshotBuildError("base snapshot is not a file")
        if _digest_file(base_path) != request.base_snapshot.artifact_digest:
            raise SnapshotBuildError("base snapshot digest does not match its reference")
        if request.base_snapshot.schema_digest != request.release.schema_digest:
            raise SnapshotBuildError("base snapshot schema does not match the selected release")
        try:
            base_snapshot = ProjectSnapshot.model_validate_json(base_path.read_bytes())
        except Exception as exc:
            raise SnapshotBuildError("base snapshot is not a valid Semantica snapshot") from exc
        if base_snapshot.id != request.base_snapshot.snapshot_id:
            raise SnapshotBuildError("base snapshot id does not match its reference")
    source_builds = []
    model_receipts: list[ModelReceipt] = []
    for source in request.sources:
        force_ocr = source.source_id in request.recipe.force_ocr_source_ids
        parsed = _parse_source(source, force_ocr)
        if request.recipe.id == "model":
            model_result, extraction_receipt = _structured_extract(parsed[0], request.relays["model"])
            embedding, embedding_receipt = _embed_text(parsed[0], request.relays["embedding"])
            built_source = _build_source(source, force_ocr, model_result, parsed)
            built_source["embedding"] = embedding
            model_receipts.extend([extraction_receipt, embedding_receipt])
        else:
            built_source = _build_source(source, force_ocr, parsed=parsed)
        source_builds.append(built_source)
    representations = [item["representation"] for item in source_builds]
    evidence = [ev for item in source_builds for ev in item["evidence"]]
    entities_by_id = {entity.id: entity for item in source_builds for entity in item["entities"]}
    assertions = [assertion for item in source_builds for assertion in item["assertions"]]
    relations = [relation for item in source_builds for relation in item["relations"]]
    for item in source_builds:
        path = output_dir / f"representation-{_safe_id(item['source'].source_id)}.json"
        item["artifact_digest"] = _write_json(path, item["document"])
        item["artifact_path"] = path
    snapshot_id = f"snapshot:{_safe_id(request.project_id)}:{request.input_revision.split(':')[-1][:16]}"
    entities = list(entities_by_id.values())
    identity_decisions, communities, topics, reports, conflicts = _semantic_organization(
        entities,
        assertions,
        relations,
        evidence,
        model_receipts,
    )
    _validate_embedding_projection(source_builds)
    provenance = _provenance_projection(representations, evidence, entities, relations)
    retrieval_payload = {
        "snapshot_id": snapshot_id,
        "entities": [entity.model_dump(mode="json", by_alias=True) for entity in entities],
        "assertions": [assertion.model_dump(mode="json", by_alias=True) for assertion in assertions],
        "relations": [relation.model_dump(mode="json", by_alias=True) for relation in relations],
        "evidence": [span.model_dump(mode="json", by_alias=True) for span in evidence],
        "communities": [community.model_dump(mode="json", by_alias=True) for community in communities],
        "topics": [topic.model_dump(mode="json", by_alias=True) for topic in topics],
        "reports": [report.model_dump(mode="json", by_alias=True) for report in reports],
        "embeddings": [{"source_id": item["source"].source_id, "vector": item["embedding"]} for item in source_builds if "embedding" in item],
        "model_receipt_ids": [receipt.id for receipt in model_receipts],
        "provenance": provenance,
    }
    retrieval_path = output_dir / "retrieval.json"
    retrieval_digest = _write_json(retrieval_path, retrieval_payload)
    retrieval_artifact_id = "artifact:retrieval"
    representation_artifacts = [ArtifactManifest(id=item["artifact_id"], artifact_type="representation", artifact_ref=str(item["artifact_path"]), artifact_hash=item["artifact_digest"]) for item in source_builds]
    # The snapshot bytes are self-referential: putting their own digest inside
    # the bytes would require a fixed-point hash. The external worker manifest
    # carries the snapshot artifact; this immutable in-snapshot manifest lists
    # only its upstream artifacts.
    retrieval_artifact = ArtifactManifest(id=retrieval_artifact_id, artifact_type="retrieval", artifact_ref=str(retrieval_path), artifact_hash=retrieval_digest, depends_on=[item.id for item in representation_artifacts])
    receipt_ids = [receipt.id for receipt in model_receipts]
    lineage = KernelLineage(schema_digest=request.release.schema_digest, recipe_id=request.recipe.id, recipe_digest=stable_digest(request.recipe.model_dump(mode="json", by_alias=True)), rule_version="semantica-project-snapshot-v1", rule_digest=stable_digest({"pipeline": request.recipe.id}), ontology_version="semantica-default", ontology_digest=stable_digest({"ontology": "default"}), model_receipt_ids=receipt_ids)
    retrieval_manifests = [
        RetrievalArtifactManifest(
            id="retrieval:graph",
            retrieval_type="graph",
            artifact_hash=retrieval_digest,
            artifact_ref_id=retrieval_artifact_id,
            source_snapshot_id=snapshot_id,
            record_count=len(entities) + len(assertions) + len(relations),
            entity_ids=[entity.id for entity in entities],
            relation_ids=[relation.id for relation in relations],
            community_ids=[community.id for community in communities],
            evidence_ids=[item.id for item in evidence],
            model_receipt_ids=receipt_ids,
        ),
        RetrievalArtifactManifest(
            id="retrieval:source",
            retrieval_type="source",
            artifact_hash=retrieval_digest,
            artifact_ref_id=retrieval_artifact_id,
            source_snapshot_id=snapshot_id,
            record_count=len(representations) + len(evidence),
            entity_ids=[],
            relation_ids=[],
            community_ids=[],
            evidence_ids=[item.id for item in evidence],
            model_receipt_ids=receipt_ids,
        ),
    ]
    change_delta = _change_delta(
        base_snapshot,
        snapshot_id,
        representations,
        entities,
        assertions,
        relations,
        reports,
        [item.id for item in retrieval_manifests],
    )
    snapshot = ProjectSnapshot(snapshot_id=snapshot_id, project_id=request.project_id, base_snapshot_id=request.base_snapshot.snapshot_id if request.base_snapshot else None, lineage=lineage, artifact_manifest=representation_artifacts + [retrieval_artifact], document_representations=representations, evidence_spans=evidence, entities=entities, assertions=assertions, relations=relations, identity_decisions=identity_decisions, communities=communities, topics=topics, reports=reports, conflicts=conflicts, retrieval_manifests=retrieval_manifests, change_delta=change_delta, model_receipts=model_receipts, metadata={"pipeline": "semantica", "recipe": request.recipe.id, "source_count": len(source_builds), "stages": ["document", "evidence", "identity", "knowledge", "organization", "retrieval", "change"]})
    snapshot_path = output_dir / "snapshot.json"
    snapshot_digest = _write_json(snapshot_path, snapshot.model_dump(mode="json", by_alias=True))
    return {"snapshot": snapshot, "snapshot_path": snapshot_path, "snapshot_digest": snapshot_digest, "representation_artifacts": source_builds, "retrieval_path": retrieval_path, "retrieval_digest": retrieval_digest, "model_receipts": model_receipts}
