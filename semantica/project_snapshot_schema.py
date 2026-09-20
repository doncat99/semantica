"""Semantica-owned project snapshot and worker protocol schemas."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SNAPSHOT_PROTOCOL = "semantica.project-snapshot.v1"
WORKER_PROTOCOL = "semantica.project-worker.v1"
SHA256_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{1,127}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_digest(value: Any) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _unique(items: List[Any], label: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = getattr(item, "id", None)
        if item_id in seen:
            raise ValueError(f"duplicate {label} id: {item_id}")
        seen.add(item_id)


def _missing(values: List[str], known: set[str]) -> List[str]:
    return sorted(set(values) - known)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    @model_validator(mode="after")
    def validate_id_like_fields(self) -> "StrictModel":
        for name in self.__class__.model_fields:
            value = getattr(self, name)
            if isinstance(value, str) and (name == "id" or name.endswith("_id")):
                if not ID_RE.match(value):
                    raise ValueError(f"invalid {name}: {value}")
            elif isinstance(value, list) and name.endswith("_ids"):
                for item in value:
                    if not isinstance(item, str) or not ID_RE.match(item):
                        raise ValueError(f"invalid {name} item: {item}")
        return self


class KernelModel(StrictModel):
    @field_validator("id", mode="after", check_fields=False)
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not ID_RE.match(value):
            raise ValueError(f"invalid id: {value}")
        return value


class DigestModel(StrictModel):
    @field_validator(
        "content_hash",
        "artifact_hash",
        "input_digest",
        "output_digest",
        "schema_digest",
        "recipe_digest",
        "rule_digest",
        "ontology_digest",
        "input_revision",
        mode="after",
        check_fields=False,
    )
    @classmethod
    def validate_sha256(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not SHA256_RE.match(value):
            raise ValueError(f"expected sha256 digest, got: {value}")
        return value


class DocumentLocator(StrictModel):
    representation_id: str
    origin: Literal["native", "ocr", "derived", "external"]
    quote: str
    start_char: Optional[int] = Field(default=None, ge=0)
    end_char: Optional[int] = Field(default=None, ge=0)
    page: Optional[int] = Field(default=None, ge=1)
    bbox: Optional[List[float]] = Field(default=None, min_length=4, max_length=4)
    table_id: Optional[str] = None
    cell: Optional[str] = None
    slide: Optional[int] = Field(default=None, ge=1)
    section_path: List[str] = Field(default_factory=list)
    quality: Literal["precise", "coarse"]

    @model_validator(mode="after")
    def validate_span(self) -> "DocumentLocator":
        has_char = self.start_char is not None or self.end_char is not None
        has_structural = (
            self.page is not None
            or self.cell is not None
            or self.slide is not None
            or bool(self.section_path)
        )
        if not has_char and not has_structural:
            raise ValueError("evidence locator requires character or structural coordinates")
        if has_char and (
            self.start_char is None
            or self.end_char is None
            or self.end_char <= self.start_char
        ):
            raise ValueError("character locator requires start_char < end_char")
        return self


class DocumentRepresentation(KernelModel, DigestModel):
    id: str
    source_id: str
    material_revision_id: str
    input_revision: str
    media_type: str
    content_hash: str
    parser: str
    parser_version: str
    recipe_id: str
    recipe_digest: str
    origin: Literal["native", "ocr", "mixed", "adapter"]
    artifact_ref_id: str
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSpan(KernelModel):
    id: str
    representation_id: str
    locator: DocumentLocator
    quote: str
    origin: Literal["observed", "derived", "imported"] = "observed"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntity(KernelModel):
    id: str
    canonical_name: str
    type: str
    aliases: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeAssertion(KernelModel):
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


class KnowledgeRelation(KernelModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    support_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IdentityDecision(KernelModel):
    id: str
    decision_type: Literal["accept", "merge", "split", "reject", "retract"]
    from_entity_ids: List[str] = Field(default_factory=list)
    to_entity_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    reason: str
    decided_by: Literal["semantica", "human", "import"] = "semantica"
    decided_at: str = Field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeCommunity(KernelModel):
    id: str
    level: int = Field(ge=0)
    title: str
    entity_ids: List[str] = Field(default_factory=list)
    relation_ids: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeTopic(KernelModel):
    id: str
    title: str
    community_ids: List[str] = Field(default_factory=list)
    entity_ids: List[str] = Field(default_factory=list)
    assertion_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class KnowledgeReport(KernelModel, DigestModel):
    id: str
    report_type: Literal["community", "topic", "conflict", "retrieval", "change"]
    title: str
    summary: str
    community_id: Optional[str] = None
    topic_id: Optional[str] = None
    conflict_id: Optional[str] = None
    retrieval_manifest_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    model_receipt_ids: List[str] = Field(default_factory=list)
    content_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeConflict(KernelModel):
    id: str
    conflict_type: Literal["identity", "assertion", "relation", "evidence", "schema"]
    status: Literal["open", "resolved", "ignored"] = "open"
    entity_ids: List[str] = Field(default_factory=list)
    assertion_ids: List[str] = Field(default_factory=list)
    relation_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    reason: str
    resolution: Optional[str] = None


class RetrievalArtifactManifest(KernelModel, DigestModel):
    id: str
    retrieval_type: Literal["source", "entity", "relation", "community", "graph"]
    artifact_hash: str
    artifact_ref_id: str
    index_id: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    record_count: int = Field(ge=0)
    entity_ids: List[str] = Field(default_factory=list)
    relation_ids: List[str] = Field(default_factory=list)
    community_ids: List[str] = Field(default_factory=list)
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


class ModelReceipt(KernelModel, DigestModel):
    id: str
    operation: str
    provider: str
    model: str
    input_digest: str
    output_digest: str
    created_at: str = Field(default_factory=utc_now_iso)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KernelLineage(DigestModel):
    schema_digest: str
    recipe_id: str
    recipe_digest: str
    rule_version: str
    rule_digest: str
    ontology_version: str
    ontology_digest: str
    model_receipt_ids: List[str] = Field(default_factory=list)


class ArtifactManifest(KernelModel, DigestModel):
    id: str
    artifact_type: Literal[
        "representation",
        "evidence",
        "graph",
        "community",
        "report",
        "retrieval",
        "change",
        "model-output",
    ]
    artifact_ref: str
    artifact_hash: str
    producer: str = "semantica"
    depends_on: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectSnapshot(KernelModel):
    protocol: Literal[SNAPSHOT_PROTOCOL] = SNAPSHOT_PROTOCOL
    snapshot_version: int = Field(default=1, ge=1)
    id: str = Field(alias="snapshot_id")
    project_id: str
    base_snapshot_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    lineage: KernelLineage
    artifact_manifest: List[ArtifactManifest]
    document_representations: List[DocumentRepresentation]
    evidence_spans: List[EvidenceSpan]
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
        lists = {
            "artifact": self.artifact_manifest,
            "representation": self.document_representations,
            "evidence": self.evidence_spans,
            "entity": self.entities,
            "assertion": self.assertions,
            "relation": self.relations,
            "identity_decision": self.identity_decisions,
            "community": self.communities,
            "topic": self.topics,
            "report": self.reports,
            "conflict": self.conflicts,
            "retrieval_manifest": self.retrieval_manifests,
            "model_receipt": self.model_receipts,
        }
        for label, items in lists.items():
            _unique(items, label)

        artifact_ids = {item.id for item in self.artifact_manifest}
        representation_ids = {item.id for item in self.document_representations}
        evidence_ids = {item.id for item in self.evidence_spans}
        entity_ids = {item.id for item in self.entities}
        assertion_ids = {item.id for item in self.assertions}
        relation_ids = {item.id for item in self.relations}
        community_ids = {item.id for item in self.communities}
        topic_ids = {item.id for item in self.topics}
        report_ids = {item.id for item in self.reports}
        conflict_ids = {item.id for item in self.conflicts}
        retrieval_ids = {item.id for item in self.retrieval_manifests}
        model_receipt_ids = {item.id for item in self.model_receipts}

        missing = _missing(self.lineage.model_receipt_ids, model_receipt_ids)
        if missing:
            raise ValueError(f"lineage references unknown model receipt ids: {missing}")
        for artifact in self.artifact_manifest:
            missing = _missing(artifact.depends_on, artifact_ids)
            if missing:
                raise ValueError(f"artifact {artifact.id} depends on unknown artifacts: {missing}")
        for representation in self.document_representations:
            if representation.artifact_ref_id not in artifact_ids:
                raise ValueError(f"representation {representation.id} references unknown artifact_ref_id")
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
            if report.community_id and report.community_id not in community_ids:
                raise ValueError(f"report {report.id} references unknown community_id")
            if report.topic_id and report.topic_id not in topic_ids:
                raise ValueError(f"report {report.id} references unknown topic_id")
            if report.conflict_id and report.conflict_id not in conflict_ids:
                raise ValueError(f"report {report.id} references unknown conflict_id")
            if report.retrieval_manifest_id and report.retrieval_manifest_id not in retrieval_ids:
                raise ValueError(f"report {report.id} references unknown retrieval_manifest_id")
            missing = _missing(report.evidence_ids, evidence_ids)
            if missing:
                raise ValueError(f"report {report.id} references unknown evidence ids: {missing}")
            missing = set(report.model_receipt_ids) - model_receipt_ids
            if missing:
                raise ValueError(f"report {report.id} references unknown model receipt ids: {sorted(missing)}")
        for decision in self.identity_decisions:
            missing = _missing(decision.from_entity_ids, entity_ids)
            if missing:
                raise ValueError(f"identity decision {decision.id} references unknown from_entity_ids: {missing}")
            if decision.to_entity_id and decision.to_entity_id not in entity_ids:
                raise ValueError(f"identity decision {decision.id} references unknown to_entity_id")
            missing = _missing(decision.evidence_ids, evidence_ids)
            if missing:
                raise ValueError(f"identity decision {decision.id} references unknown evidence ids: {missing}")
        for community in self.communities:
            missing = _missing(community.entity_ids, entity_ids)
            if missing:
                raise ValueError(f"community {community.id} references unknown entity ids: {missing}")
            missing = _missing(community.relation_ids, relation_ids)
            if missing:
                raise ValueError(f"community {community.id} references unknown relation ids: {missing}")
            if community.parent_id and community.parent_id not in community_ids:
                raise ValueError(f"community {community.id} references unknown parent_id")
        for topic in self.topics:
            for label, values, known in (
                ("community", topic.community_ids, community_ids),
                ("entity", topic.entity_ids, entity_ids),
                ("assertion", topic.assertion_ids, assertion_ids),
                ("evidence", topic.evidence_ids, evidence_ids),
            ):
                missing = _missing(values, known)
                if missing:
                    raise ValueError(f"topic {topic.id} references unknown {label} ids: {missing}")
        for conflict in self.conflicts:
            for label, values, known in (
                ("entity", conflict.entity_ids, entity_ids),
                ("assertion", conflict.assertion_ids, assertion_ids),
                ("relation", conflict.relation_ids, relation_ids),
                ("evidence", conflict.evidence_ids, evidence_ids),
            ):
                missing = _missing(values, known)
                if missing:
                    raise ValueError(f"conflict {conflict.id} references unknown {label} ids: {missing}")
        for retrieval in self.retrieval_manifests:
            if retrieval.artifact_ref_id not in artifact_ids:
                raise ValueError(f"retrieval {retrieval.id} references unknown artifact_ref_id")
            for label, values, known in (
                ("entity", retrieval.entity_ids, entity_ids),
                ("relation", retrieval.relation_ids, relation_ids),
                ("community", retrieval.community_ids, community_ids),
                ("evidence", retrieval.evidence_ids, evidence_ids),
                ("model receipt", retrieval.model_receipt_ids, model_receipt_ids),
            ):
                missing = _missing(values, known)
                if missing:
                    raise ValueError(f"retrieval {retrieval.id} references unknown {label} ids: {missing}")
        for label, values, known in (
            ("changed representation", self.change_delta.changed_representation_ids, representation_ids),
            ("affected report", self.change_delta.affected_report_ids, report_ids),
            ("affected retrieval manifest", self.change_delta.affected_retrieval_manifest_ids, retrieval_ids),
        ):
            missing = _missing(values, known)
            if missing:
                raise ValueError(f"change_delta references unknown {label} ids: {missing}")
        return self


class SourceBuildInput(KernelModel, DigestModel):
    id: str
    source_id: str
    material_revision_id: str
    input_revision: str
    media_type: str
    content_hash: str
    artifact_ref_id: str


class ExecutorRef(KernelModel, DigestModel):
    id: str
    executor_type: Literal["parser", "extractor", "reasoner", "community", "retriever", "model"]
    artifact_hash: str
    version: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SnapshotRef(KernelModel, DigestModel):
    id: str = Field(alias="snapshot_id")
    artifact_ref: str
    artifact_hash: str


class ProjectSnapshotBuildRequest(StrictModel):
    project_id: str
    base_snapshot: Optional[SnapshotRef] = None
    sources: List[SourceBuildInput]
    executors: List[ExecutorRef]
    artifact_manifest: List[ArtifactManifest]
    lineage: KernelLineage
    options: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_host_semantic_results(self) -> "ProjectSnapshotBuildRequest":
        forbidden = {
            "document_representations",
            "evidence_spans",
            "entities",
            "assertions",
            "relations",
            "identity_decisions",
            "communities",
            "topics",
            "reports",
            "conflicts",
            "retrieval_manifests",
            "change_delta",
            "model_receipts",
            "snapshot",
            "knowledge_graph",
        }
        present = sorted(forbidden & set(self.options))
        if present:
            raise ValueError(f"options cannot carry computed semantic results: {present}")
        return self


class WorkerRequest(StrictModel):
    protocol: Literal[WORKER_PROTOCOL] = WORKER_PROTOCOL
    id: str
    method: Literal["build_project_snapshot", "validate_snapshot", "schema"]
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


def build_request_json_schema() -> Dict[str, Any]:
    return ProjectSnapshotBuildRequest.model_json_schema()
