"""Semantica-owned project snapshot and worker protocol schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

SNAPSHOT_PROTOCOL = "semantica.project-snapshot.v1"
WORKER_PROTOCOL = "semantica.project-worker.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_digest(value: Any) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentLocator(StrictModel):
    representation_id: str
    origin: Literal["native", "ocr", "derived", "external", "unknown"]
    quote: Optional[str] = None
    start_char: Optional[int] = Field(default=None, ge=0)
    end_char: Optional[int] = Field(default=None, ge=0)
    page: Optional[int] = Field(default=None, ge=1)
    bbox: Optional[List[float]] = Field(default=None, min_length=4, max_length=4)
    table_id: Optional[str] = None
    cell: Optional[str] = None
    slide: Optional[int] = Field(default=None, ge=1)
    section_path: List[str] = Field(default_factory=list)
    quality: Literal["precise", "coarse", "unavailable"] = "unavailable"

    @model_validator(mode="after")
    def validate_span(self) -> "DocumentLocator":
        if self.start_char is not None or self.end_char is not None:
            if self.start_char is None or self.end_char is None or self.end_char <= self.start_char:
                raise ValueError("character locator requires start_char < end_char")
        return self


class DocumentRepresentation(StrictModel):
    id: str
    source_id: str
    material_revision_id: str
    media_type: str
    content_hash: str
    parser: str
    parser_version: Optional[str] = None
    origin: Literal["native", "ocr", "mixed", "adapter"]
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSpan(StrictModel):
    id: str
    representation_id: str
    locator: DocumentLocator
    quote: str
    origin: Literal["observed", "derived", "imported"] = "observed"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntity(StrictModel):
    id: str
    canonical_name: str
    type: str
    aliases: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeAssertion(StrictModel):
    id: str
    subject_id: str
    predicate: str
    object: Union[str, int, float, bool, Dict[str, Any]]
    object_entity_id: Optional[str] = None
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    support_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "contradicted", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeRelation(StrictModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    support_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IdentityDecision(StrictModel):
    id: str
    decision_type: Literal["accept", "merge", "split", "reject", "retract"]
    from_entity_ids: List[str] = Field(default_factory=list)
    to_entity_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    reason: str
    decided_by: Literal["system", "human", "import"] = "system"
    decided_at: str = Field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeCommunity(StrictModel):
    id: str
    level: int = Field(ge=0)
    title: str
    entity_ids: List[str] = Field(default_factory=list)
    relation_ids: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeTopic(StrictModel):
    id: str
    title: str
    community_ids: List[str] = Field(default_factory=list)
    entity_ids: List[str] = Field(default_factory=list)
    assertion_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class KnowledgeReport(StrictModel):
    id: str
    report_type: Literal["community", "topic", "conflict", "retrieval", "change"]
    title: str
    summary: str
    community_id: Optional[str] = None
    topic_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    model_receipt_ids: List[str] = Field(default_factory=list)
    content_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeConflict(StrictModel):
    id: str
    conflict_type: Literal["identity", "assertion", "relation", "evidence", "schema"]
    status: Literal["open", "resolved", "ignored"] = "open"
    entity_ids: List[str] = Field(default_factory=list)
    assertion_ids: List[str] = Field(default_factory=list)
    relation_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    reason: str
    resolution: Optional[str] = None


class RetrievalArtifactManifest(StrictModel):
    id: str
    retrieval_type: Literal["source", "entity", "relation", "community", "graph"]
    artifact_hash: str
    index_id: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    record_count: int = Field(ge=0)
    evidence_ids: List[str] = Field(default_factory=list)
    model_receipt_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChangeDelta(StrictModel):
    base_snapshot_id: Optional[str] = None
    changed_representation_ids: List[str] = Field(default_factory=list)
    added_ids: List[str] = Field(default_factory=list)
    updated_ids: List[str] = Field(default_factory=list)
    retracted_ids: List[str] = Field(default_factory=list)
    affected_report_ids: List[str] = Field(default_factory=list)
    affected_retrieval_manifest_ids: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class ModelReceipt(StrictModel):
    id: str
    operation: str
    provider: str
    model: str
    input_digest: str
    output_digest: str
    created_at: str = Field(default_factory=utc_now_iso)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectSnapshot(StrictModel):
    protocol: Literal[SNAPSHOT_PROTOCOL] = SNAPSHOT_PROTOCOL
    snapshot_version: int = Field(default=1, ge=1)
    snapshot_id: str
    project_id: str
    base_snapshot_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    document_representations: List[DocumentRepresentation] = Field(default_factory=list)
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list)
    entities: List[KnowledgeEntity] = Field(default_factory=list)
    assertions: List[KnowledgeAssertion] = Field(default_factory=list)
    relations: List[KnowledgeRelation] = Field(default_factory=list)
    identity_decisions: List[IdentityDecision] = Field(default_factory=list)
    communities: List[KnowledgeCommunity] = Field(default_factory=list)
    topics: List[KnowledgeTopic] = Field(default_factory=list)
    reports: List[KnowledgeReport] = Field(default_factory=list)
    conflicts: List[KnowledgeConflict] = Field(default_factory=list)
    retrieval_manifests: List[RetrievalArtifactManifest] = Field(default_factory=list)
    change_delta: ChangeDelta = Field(default_factory=ChangeDelta)
    model_receipts: List[ModelReceipt] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "ProjectSnapshot":
        representation_ids = {item.id for item in self.document_representations}
        evidence_ids = {item.id for item in self.evidence_spans}
        entity_ids = {item.id for item in self.entities}
        model_receipt_ids = {item.id for item in self.model_receipts}

        for evidence in self.evidence_spans:
            if evidence.representation_id not in representation_ids:
                raise ValueError(f"unknown evidence representation_id: {evidence.representation_id}")
            if evidence.locator.representation_id != evidence.representation_id:
                raise ValueError("evidence locator representation_id must match evidence representation_id")
        for entity in self.entities:
            missing = set(entity.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"entity {entity.id} references unknown evidence ids: {sorted(missing)}")
        for assertion in self.assertions:
            if assertion.subject_id not in entity_ids:
                raise ValueError(f"assertion {assertion.id} references unknown subject_id: {assertion.subject_id}")
            if assertion.object_entity_id and assertion.object_entity_id not in entity_ids:
                raise ValueError(f"assertion {assertion.id} references unknown object_entity_id: {assertion.object_entity_id}")
            missing = set(assertion.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"assertion {assertion.id} references unknown evidence ids: {sorted(missing)}")
        for relation in self.relations:
            if relation.source_entity_id not in entity_ids or relation.target_entity_id not in entity_ids:
                raise ValueError(f"relation {relation.id} references unknown entity endpoint")
            missing = set(relation.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"relation {relation.id} references unknown evidence ids: {sorted(missing)}")
        for report in self.reports:
            missing = set(report.model_receipt_ids) - model_receipt_ids
            if missing:
                raise ValueError(f"report {report.id} references unknown model receipt ids: {sorted(missing)}")
        return self


class ProjectSnapshotBuildParams(ProjectSnapshot):
    snapshot_id: Optional[str] = None  # type: ignore[assignment]

    def to_snapshot(self) -> ProjectSnapshot:
        data = self.model_dump()
        if not data.get("snapshot_id"):
            data["snapshot_id"] = f"snapshot:{stable_digest(data)[:16]}"
        return ProjectSnapshot.model_validate(data)


class WorkerRequest(StrictModel):
    protocol: Literal[WORKER_PROTOCOL] = WORKER_PROTOCOL
    id: str
    method: Literal["build_project_snapshot", "schema"]
    params: Dict[str, Any] = Field(default_factory=dict)


class WorkerError(StrictModel):
    type: str
    message: str


class WorkerResponse(StrictModel):
    protocol: Literal[WORKER_PROTOCOL] = WORKER_PROTOCOL
    id: Optional[str] = None
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[WorkerError] = None


def project_snapshot_json_schema() -> Dict[str, Any]:
    return ProjectSnapshot.model_json_schema()
