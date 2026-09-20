"""Semantica-owned project snapshot build pipeline.

The worker receives only immutable local source files and release metadata. Every
semantic object in the snapshot is produced here; callers cannot provide graph
objects, evidence, or precomputed entities.
"""
from __future__ import annotations

import json
import mimetypes
from hashlib import sha256
from pathlib import Path
from typing import Any

from .parse import DoclingParser
from .project_snapshot_schema import (
    ArtifactManifest,
    ChangeDelta,
    DocumentLocator,
    DocumentRepresentation,
    EvidenceSpan,
    KernelLineage,
    KnowledgeEntity,
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    RetrievalArtifactManifest,
    stable_digest,
)
from .semantic_extract import NamedEntityRecognizer


class SnapshotBuildError(RuntimeError):
    """Raised when a source cannot be represented by the single Semantica chain."""


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


def _parse_source(source: Any, force_ocr: bool) -> tuple[str, dict[str, Any], str, str]:
    path = Path(source.file_path).resolve()
    if not path.is_file():
        raise SnapshotBuildError(f"source is not a file: {source.source_id}")
    suffix = path.suffix.lower()
    content_hash = _digest_file(path)
    if suffix in {".txt", ".text"}:
        text = path.read_text(encoding="utf-8")
        document = {"format": "plain-text", "text": text, "source": source.name}
        return text, document, "native", content_hash
    if suffix == ".md":
        text = path.read_text(encoding="utf-8")
        document = {"format": "markdown", "text": text, "source": source.name}
        return text, document, "native", content_hash
    # Docling is the only structured-document implementation. Unsupported
    # formats fail closed instead of being sent through a second parser.
    supported = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".xml", ".csv"}
    if suffix not in supported:
        raise SnapshotBuildError(f"unsupported source format for Semantica: {source.name}")
    result = DoclingParser(enable_ocr=force_ocr, export_format="doctags").parse(
        path, export_format="doctags", include_document=True,
    )
    text = result.get("full_text", "")
    document = {
        "format": "docling",
        "document": result.get("document"),
        "doctags": result.get("doctags"),
        "pages": result.get("pages", []),
        "conversion_status": result.get("conversion_status", "unknown"),
        "metadata": result.get("metadata", {}),
        "source": source.name,
        "content_hash": content_hash,
    }
    return text, document, "ocr" if force_ocr else "native", content_hash


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


def _build_source(source: Any, force_ocr: bool) -> dict[str, Any]:
    text, document, origin, content_hash = _parse_source(source, force_ocr)
    representation_id = f"representation:{_safe_id(source.source_id)}"
    representation_artifact_id = f"artifact:representation:{_safe_id(source.source_id)}"
    entities_raw = NamedEntityRecognizer(method="pattern").extract_entities(text)
    entities: dict[str, KnowledgeEntity] = {}
    evidence: dict[str, EvidenceSpan] = {}
    cursor = 0
    for item in entities_raw:
        start, end = _find_span(text, item.text, cursor)
        cursor = end
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
            confidence=item.confidence,
        )
        entity_id = _entity_id(item.text, item.label)
        current = entities.get(entity_id)
        if current is None:
            entities[entity_id] = KnowledgeEntity(
                id=entity_id,
                canonical_name=item.text,
                type="MENTION",
                aliases=[],
                evidence_ids=[evidence_id],
                status="candidate",
                metadata={"detected_label": item.label, "extraction_method": "pattern", "source_ids": [source.source_id]},
            )
        elif evidence_id not in current.evidence_ids:
            current.evidence_ids.append(evidence_id)
    representation = DocumentRepresentation(
        id=representation_id,
        source_id=source.source_id,
        material_revision_id=source.material_revision,
        input_revision=content_hash,
        media_type=source.mime_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        content_hash=content_hash,
        parser="docling" if document.get("format") == "docling" else "semantica.text",
        parser_version="2" if document.get("format") == "docling" else "1",
        recipe_id="deterministic",
        recipe_digest=stable_digest({"parser": document.get("format"), "ocr": force_ocr}),
        origin="mixed" if force_ocr else origin,
        artifact_ref_id=representation_artifact_id,
        metadata={"text_length": len(text), "source_name": source.name, "document": document},
    )
    return {"source": source, "text": text, "representation": representation, "evidence": list(evidence.values()), "entities": list(entities.values()), "assertions": [], "relations": [], "artifact_id": representation_artifact_id, "document": document}


def build_project_snapshot(request: ProjectSnapshotBuildRequest) -> dict[str, Any]:
    """Build, validate, and materialize one immutable snapshot and its artifacts."""
    if request.recipe.id != "deterministic":
        raise SnapshotBuildError(
            f"unsupported project snapshot recipe: {request.recipe.id}; "
            "model recipes require a receipt-bearing relay implementation"
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
    source_builds = [_build_source(source, source.source_id in request.recipe.force_ocr_source_ids) for source in request.sources]
    representations = [item["representation"] for item in source_builds]
    evidence = [ev for item in source_builds for ev in item["evidence"]]
    entities_by_id = {entity.id: entity for item in source_builds for entity in item["entities"]}
    assertions = [assertion for item in source_builds for assertion in item["assertions"]]
    relations = [relation for item in source_builds for relation in item["relations"]]
    for item in source_builds:
        path = output_dir / f"representation-{_safe_id(item['source'].source_id)}.json"
        item["artifact_digest"] = _write_json(path, item["document"])
        item["artifact_path"] = path
    communities: list[KnowledgeCommunity] = []
    topics: list[KnowledgeTopic] = []
    identity_decisions: list[IdentityDecision] = []
    reports: list[KnowledgeReport] = []
    retrieval_payload = {"entities": [entity.model_dump(mode="json", by_alias=True) for entity in entities_by_id.values()], "relations": [], "evidence": [span.model_dump(mode="json", by_alias=True) for span in evidence], "communities": [], "topics": []}
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
    lineage = KernelLineage(schema_digest=request.release.schema_digest, recipe_id=request.recipe.id, recipe_digest=stable_digest(request.recipe.model_dump(mode="json", by_alias=True)), rule_version="semantica-project-snapshot-v1", rule_digest=stable_digest({"pipeline": "deterministic"}), ontology_version="semantica-default", ontology_digest=stable_digest({"ontology": "default"}), model_receipt_ids=[])
    snapshot = ProjectSnapshot(snapshot_id=snapshot_id, project_id=request.project_id, base_snapshot_id=request.base_snapshot.snapshot_id if request.base_snapshot else None, lineage=lineage, artifact_manifest=representation_artifacts + [retrieval_artifact], document_representations=representations, evidence_spans=evidence, entities=list(entities_by_id.values()), assertions=assertions, relations=relations, identity_decisions=identity_decisions, communities=communities, topics=topics, reports=reports, conflicts=[], retrieval_manifests=[RetrievalArtifactManifest(id="retrieval:graph", retrieval_type="graph", artifact_hash=retrieval_digest, artifact_ref_id=retrieval_artifact_id, source_snapshot_id=snapshot_id, record_count=len(entities_by_id) + len(relations), entity_ids=list(entities_by_id), relation_ids=[r.id for r in relations], community_ids=[c.id for c in communities], evidence_ids=[e.id for e in evidence], model_receipt_ids=[])], change_delta=ChangeDelta(base_snapshot_id=request.base_snapshot.snapshot_id if request.base_snapshot else None, changed_representation_ids=[r.id for r in representations], added_ids=[e.id for e in entities_by_id.values()], affected_report_ids=[r.id for r in reports], affected_retrieval_manifest_ids=["retrieval:graph"], reason="deterministic Semantica build"), model_receipts=[], metadata={"pipeline": "semantica", "recipe": request.recipe.id, "source_count": len(source_builds)})
    snapshot_path = output_dir / "snapshot.json"
    snapshot_digest = _write_json(snapshot_path, snapshot.model_dump(mode="json", by_alias=True))
    return {"snapshot": snapshot, "snapshot_path": snapshot_path, "snapshot_digest": snapshot_digest, "representation_artifacts": source_builds, "retrieval_path": retrieval_path, "retrieval_digest": retrieval_digest}
