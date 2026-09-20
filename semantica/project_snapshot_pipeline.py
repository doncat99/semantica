"""Semantica-owned project snapshot build pipeline.

The worker receives only immutable local source files and release metadata. Every
semantic object in the snapshot is produced here; callers cannot provide graph
objects, evidence, or precomputed entities.
"""
from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
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
    KernelLineage,
    KnowledgeAssertion,
    KnowledgeRelation,
    KnowledgeEntity,
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
    response, receipt = _relay_json(relay, {"input": [text]}, "embedding")
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


def _entity_id(name: str, entity_type: str) -> str:
    return f"entity:{sha256(f'{entity_type}:{name.casefold()}'.encode()).hexdigest()[:24]}"


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
        entity_id = _entity_id(name, entity_type)
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


def build_project_snapshot(request: ProjectSnapshotBuildRequest) -> dict[str, Any]:
    """Build, validate, and materialize one immutable snapshot and its artifacts."""
    if request.recipe.id not in {"deterministic", "model"}:
        raise SnapshotBuildError(
            f"unsupported project snapshot recipe: {request.recipe.id}; "
            "supported recipes are deterministic and model"
        )
    output_dir = Path(request.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
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
    communities: list[Any] = []
    topics: list[Any] = []
    identity_decisions: list[Any] = []
    reports: list[Any] = []
    retrieval_payload = {"entities": [entity.model_dump(mode="json", by_alias=True) for entity in entities_by_id.values()], "relations": [relation.model_dump(mode="json", by_alias=True) for relation in relations], "evidence": [span.model_dump(mode="json", by_alias=True) for span in evidence], "communities": [], "topics": [], "embeddings": [{"source_id": item["source"].source_id, "vector": item["embedding"]} for item in source_builds if "embedding" in item]}
    retrieval_path = output_dir / "retrieval.json"
    retrieval_digest = _write_json(retrieval_path, retrieval_payload)
    retrieval_artifact_id = "artifact:retrieval"
    snapshot_id = f"snapshot:{_safe_id(request.project_id)}:{request.input_revision.split(':')[-1][:16]}"
    representation_artifacts = [ArtifactManifest(id=item["artifact_id"], artifact_type="representation", artifact_ref=str(item["artifact_path"]), artifact_hash=item["artifact_digest"]) for item in source_builds]
    # The snapshot bytes are self-referential: putting their own digest inside
    # the bytes would require a fixed-point hash. The external worker manifest
    # carries the snapshot artifact; this immutable in-snapshot manifest lists
    # only its upstream artifacts.
    retrieval_artifact = ArtifactManifest(id=retrieval_artifact_id, artifact_type="retrieval", artifact_ref=str(retrieval_path), artifact_hash=retrieval_digest, depends_on=[item.id for item in representation_artifacts])
    receipt_ids = [receipt.id for receipt in model_receipts]
    lineage = KernelLineage(schema_digest=request.release.schema_digest, recipe_id=request.recipe.id, recipe_digest=stable_digest(request.recipe.model_dump(mode="json", by_alias=True)), rule_version="semantica-project-snapshot-v1", rule_digest=stable_digest({"pipeline": request.recipe.id}), ontology_version="semantica-default", ontology_digest=stable_digest({"ontology": "default"}), model_receipt_ids=receipt_ids)
    snapshot = ProjectSnapshot(snapshot_id=snapshot_id, project_id=request.project_id, base_snapshot_id=request.base_snapshot.snapshot_id if request.base_snapshot else None, lineage=lineage, artifact_manifest=representation_artifacts + [retrieval_artifact], document_representations=representations, evidence_spans=evidence, entities=list(entities_by_id.values()), assertions=assertions, relations=relations, identity_decisions=identity_decisions, communities=communities, topics=topics, reports=reports, conflicts=[], retrieval_manifests=[RetrievalArtifactManifest(id="retrieval:graph", retrieval_type="graph", artifact_hash=retrieval_digest, artifact_ref_id=retrieval_artifact_id, source_snapshot_id=snapshot_id, record_count=len(entities_by_id) + len(relations), entity_ids=list(entities_by_id), relation_ids=[r.id for r in relations], community_ids=[], evidence_ids=[e.id for e in evidence], model_receipt_ids=receipt_ids)], change_delta=ChangeDelta(base_snapshot_id=request.base_snapshot.snapshot_id if request.base_snapshot else None, changed_representation_ids=[r.id for r in representations], added_ids=[e.id for e in entities_by_id.values()], affected_report_ids=[], affected_retrieval_manifest_ids=["retrieval:graph"], reason=f"{request.recipe.id} Semantica build"), model_receipts=model_receipts, metadata={"pipeline": "semantica", "recipe": request.recipe.id, "source_count": len(source_builds)})
    snapshot_path = output_dir / "snapshot.json"
    snapshot_digest = _write_json(snapshot_path, snapshot.model_dump(mode="json", by_alias=True))
    return {"snapshot": snapshot, "snapshot_path": snapshot_path, "snapshot_digest": snapshot_digest, "representation_artifacts": source_builds, "retrieval_path": retrieval_path, "retrieval_digest": retrieval_digest, "model_receipts": model_receipts}
