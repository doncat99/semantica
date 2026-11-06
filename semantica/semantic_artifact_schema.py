"""Semantica-owned semantic artifact and worker protocol schemas."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from os.path import isabs
from typing import Any, Dict, List, Literal, Optional, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .semantic_extract.schema import ExtractionSpecification
from .semantic_extract.schemas import validate_fact_qualifiers

WORKER_PROTOCOL = "semantica.semantic-worker.v1"
SHA256_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
MATERIAL_REVISION_PATTERN = r"^b3-[0-9a-f]{64}$"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,255}$")
MEDIA_TYPE_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


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




def _validate_media_type(value: str, field: str) -> str:
    if not MEDIA_TYPE_RE.fullmatch(value):
        raise ValueError(f"{field} must be a MIME type")
    return value.lower()


@lru_cache(maxsize=128)
def _identifier_fields(model: type[BaseModel]) -> tuple[str, ...]:
    return tuple(name for name in model.model_fields if name == "id" or name.endswith(("_id", "_ids")))


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    @model_validator(mode="after")
    def validate_id_like_fields(self) -> "StrictModel":
        for name in _identifier_fields(self.__class__):
            value = getattr(self, name)
            if isinstance(value, str) and (name == "id" or name.endswith("_id")):
                pattern = MODEL_ID_RE if name == "model_id" else ID_RE
                if not pattern.fullmatch(value):
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
        "artifact_digest",
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
    native_ref: Optional[str] = Field(default=None, alias="nativeRef", min_length=1, max_length=8192)
    origin: Literal["native", "ocr", "mixed", "derived", "external", "adapter"]
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
        if self.native_ref is not None and (not self.native_ref.startswith("#/")
                or self.start_char is None or self.end_char is None):
            raise ValueError("native locator requires a scalar reference and character range")
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


class DocumentRepresentation(KernelModel):
    id: str
    source_id: str
    material_revision_id: str = Field(pattern=MATERIAL_REVISION_PATTERN)
    input_revision: str = Field(pattern=MATERIAL_REVISION_PATTERN)
    media_type: str
    content_hash: str = Field(pattern=MATERIAL_REVISION_PATTERN)
    parser: str
    parser_version: str
    recipe_id: str
    recipe_digest: str = Field(pattern=SHA256_RE.pattern)
    origin: Literal["native", "ocr", "mixed", "adapter", "external"]
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
    description: str = ""
    context: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
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
    qualifiers: Dict[str, Any]
    evidence_ids: List[str] = Field(default_factory=list)
    support_ids: List[str] = Field(default_factory=list, description="Located evidence IDs supporting this canonical qualified assertion")
    status: Literal["candidate", "accepted", "contradicted", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("qualifiers")
    @classmethod
    def validate_qualifiers(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return validate_fact_qualifiers(value)


class KnowledgeRelation(KernelModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    qualifiers: Dict[str, Any]
    evidence_ids: List[str] = Field(default_factory=list)
    support_ids: List[str] = Field(default_factory=list, description="Located evidence IDs supporting this canonical qualified relation")
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("qualifiers")
    @classmethod
    def validate_qualifiers(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return validate_fact_qualifiers(value)


class SourceRelation(KernelModel):
    """A canonical relation between two source documents.

    Source relations are produced by Semantica from located knowledge support.
    Consumers may render them, but must not infer them by joining entity
    evidence at read time.
    """

    id: str
    source_id: str
    target_id: str
    type: str
    evidence_ids: List[str] = Field(default_factory=list)
    entity_relation_ids: List[str] = Field(default_factory=list)
    status: Literal["candidate", "accepted", "rejected", "retracted"] = "candidate"
    unresolved_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IdentityCandidateReview(StrictModel):
    entity_id: str
    reason: str = Field(min_length=1)


class IdentityRegistryEntry(StrictModel):
    mention_id: str
    entity_id: str
    canonical_name: str
    type: str
    source_ids: List[str] = Field(default_factory=list)
    unresolved_candidate_count: int = Field(default=0, ge=0)
    unresolved_candidates: List[IdentityCandidateReview] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_unresolved_candidates(self):
        pairs = [(item.entity_id, item.reason) for item in self.unresolved_candidates]
        if self.unresolved_candidate_count < len(pairs) or len(set(pairs)) != len(pairs):
            raise ValueError('identity review count must cover its unique sampled candidates')
        if any(entity_id == self.entity_id for entity_id, _ in pairs):
            raise ValueError('identity review must refer to another canonical entity')
        return self


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
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReportSection(StrictModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: List[str] = Field(min_length=1)


class KnowledgeReport(KernelModel, DigestModel):
    id: str
    report_type: Literal["overview", "concept", "community", "topic", "conflict", "retrieval", "change"]
    title: str
    entity_id: Optional[str] = None
    sections: List[ReportSection] = Field(default_factory=list)
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




class SourceBuildInput(KernelModel):
    """Immutable absolute-path source granted by the host for one build.

    The host resolves authorization, symlinks, and file existence before launch;
    this contract intentionally carries no bearer token or remote URL.
    """

    file_path: str = Field(alias="filePath")
    material_revision: str = Field(alias="materialRevision", pattern=MATERIAL_REVISION_PATTERN)
    mime_type: str = Field(alias="mimeType")
    name: str
    source_id: str = Field(alias="sourceId")

    @field_validator("file_path", mode="after")
    @classmethod
    def validate_absolute_file_path(cls, value: str) -> str:
        if not isabs(value):
            raise ValueError("source filePath must be absolute")
        return value

    @field_validator("mime_type", mode="after")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        return _validate_media_type(value, "source mimeType")




class ClassificationVocabularyItem(StrictModel):
    id: str
    label: str
    description: Optional[str] = None
    parent_id: Optional[str] = Field(default=None, alias="parentId")


class ClassificationDimension(StrictModel):
    id: str
    label: str
    cardinality: Literal["single", "multi"]
    vocabulary: List[ClassificationVocabularyItem]

    @model_validator(mode="after")
    def validate_vocabulary(self) -> "ClassificationDimension":
        _unique(self.vocabulary, "classification vocabulary")
        ids = {item.id for item in self.vocabulary}
        if any(item.parent_id and item.parent_id not in ids for item in self.vocabulary):
            raise ValueError("classification vocabulary references unknown parent")
        return self


class ClassificationProfile(StrictModel):
    id: str
    version: str
    label: str
    description: str
    dimensions: List[ClassificationDimension]

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ClassificationProfile":
        _unique(self.dimensions, "classification dimension")
        return self


class ClassificationAssignment(StrictModel):
    dimension_id: str
    item_id: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: List[str] = Field(min_length=1)


class SourceClassification(StrictModel):
    source_id: str
    profile_id: str
    profile_version: str
    assignments: List[ClassificationAssignment]
    unclassified_dimension_ids: List[str]
    model_receipt_ids: List[str]


class RecipeRef(StrictModel):
    force_ocr_source_ids: List[str] = Field(default_factory=list, alias="forceOcrSourceIds")
    formula_semantics_source_ids: List[str] = Field(default_factory=list, alias="formulaSemanticsSourceIds")
    classification_profile: Optional[ClassificationProfile] = Field(default=None, alias="classificationProfile")
    extraction_spec: Optional[ExtractionSpecification] = Field(default=None, alias="extractionSpec")
    id: str
    version: str

    def lineage_payload(self) -> Dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class RelayRef(StrictModel):
    authorization_env: str = Field(alias="authorizationEnv")
    base_url: str = Field(alias="baseUrl")
    capability: Literal["knowledge.publication.embed", "knowledge.publication.generate"]
    model_id: str = Field(alias="modelId")
    binding_id: Optional[str] = Field(default=None, alias="bindingId")
    context_window_tokens: Optional[int] = Field(default=None, alias="contextWindowTokens", gt=0)
    max_output_tokens: Optional[int] = Field(default=None, alias="maxOutputTokens", gt=0)
    receipts: Literal["required"]

    @field_validator("authorization_env", mode="after")
    @classmethod
    def validate_authorization_env(cls, value: str) -> str:
        if not ENV_VAR_RE.fullmatch(value):
            raise ValueError("authorizationEnv must be an environment variable name")
        return value

    @model_validator(mode="after")
    def validate_loopback_url(self) -> "RelayRef":
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("relay baseUrl must be an unauthenticated loopback HTTP URL")
        expected_path = {
            "knowledge.publication.embed": "/v1/embeddings",
            "knowledge.publication.generate": "/v1/chat/completions",
        }[self.capability]
        if parsed.path.rstrip("/") != expected_path:
            raise ValueError(f"relay baseUrl path must be {expected_path} for {self.capability}")
        if self.capability == "knowledge.publication.generate":
            if self.context_window_tokens is None or self.max_output_tokens is None:
                raise ValueError("model relay requires contextWindowTokens and maxOutputTokens")
            if self.max_output_tokens > self.context_window_tokens:
                raise ValueError("model relay maxOutputTokens cannot exceed contextWindowTokens")
        return self


class ReleaseRef(DigestModel):
    artifact_digest: str = Field(alias="artifactDigest")
    media_types: Dict[str, str] = Field(alias="mediaTypes")
    schema_digest: str = Field(alias="schemaDigest")

    @field_validator("media_types", mode="after")
    @classmethod
    def validate_media_types(cls, value: Dict[str, str]) -> Dict[str, str]:
        expected = {"document-representation": "application/vnd.semantica.document-representation+json"}
        if value != expected:
            raise ValueError("release mediaTypes must declare only the current document-representation MIME type")
        return value


class DocumentProcessingProfile(StrictModel):
    mode: Literal["disabled", "native", "local", "remote"] = "local"
    pdf_text_order: Literal["coordinates", "content"] = Field(default="coordinates", alias="pdfTextOrder")
    endpoint: Optional[str] = None
    binding_id: Optional[str] = Field(default=None, alias="bindingId")
    remote_cancellation: Literal["unsupported"] = Field(default="unsupported", alias="remoteCancellation")

    @model_validator(mode="after")
    def validate_remote(self) -> "DocumentProcessingProfile":
        if self.mode == "remote" and (not self.endpoint or not self.binding_id):
            raise ValueError("remote document processing requires endpoint and bindingId")
        return self


class ParsedSourceRef(DigestModel):
    reader_index_path: str = Field(alias="readerIndexPath")
    reader_index_digest: str = Field(alias="readerIndexDigest", pattern=SHA256_RE.pattern)
    artifact_digest: str = Field(alias="artifactDigest")
    artifact_path: str = Field(alias="artifactPath")
    source_id: str = Field(alias="sourceId")
    representation_revision: str = Field(alias="representationRevision", pattern=SHA256_RE.pattern)

    @field_validator("artifact_path", "reader_index_path", mode="after")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not isabs(value):
            raise ValueError("parsed source artifactPath and readerIndexPath must be absolute")
        return value


class OrganizationReportsRef(DigestModel):
    base_url: str = Field(alias="baseUrl")
    authorization_env: str = Field(alias="authorizationEnv", pattern=ENV_VAR_RE.pattern)
    recipe_digest: str = Field(alias="recipeDigest")

    @model_validator(mode="after")
    def validate_owner_url(self):
        parsed = urlsplit(self.base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip("/") != "/v1/products/semantic-organization"):
            raise ValueError("organizationReports must address the authenticated loopback product owner")
        return self


class SemanticArtifactBuildRequest(DigestModel):
    project_id: str = Field(alias="projectId")
    input_revision: str = Field(alias="inputRevision")
    parallelism: int = Field(default=1, ge=1, le=16)
    output_dir: str = Field(alias="outputDir")
    native_cache_dir: str = Field(alias="nativeCacheDir")
    native_store_dir: str = Field(alias="nativeStoreDir")
    organization_reports: OrganizationReportsRef = Field(alias="organizationReports")
    recipe: RecipeRef
    relays: Dict[str, RelayRef]
    release: ReleaseRef
    sources: List[SourceBuildInput]
    parsed_sources: List[ParsedSourceRef] = Field(alias="parsedSources")
    document_processing: DocumentProcessingProfile = Field(default_factory=DocumentProcessingProfile, alias="documentProcessing")
    # Caller-verified identity properties supply vetoes, not mandatory merge keys.
    identity_property_schema: Dict[str, Dict[str, Any]] = Field(default_factory=dict, alias="identityPropertySchema")

    @model_validator(mode="after")
    def validate_inputs(self) -> "SemanticArtifactBuildRequest":
        if not self.sources:
            raise ValueError("at least one source is required")
        if not isabs(self.output_dir):
            raise ValueError("outputDir must be absolute")
        if not isabs(self.native_cache_dir) or not isabs(self.native_store_dir):
            raise ValueError("nativeCacheDir and nativeStoreDir must be absolute")
        source_ids = {source.source_id for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("source ids must be unique")
        if set(self.recipe.force_ocr_source_ids) - source_ids:
            raise ValueError("OCR recipe references an unknown source")
        if len(set(self.recipe.formula_semantics_source_ids)) != len(self.recipe.formula_semantics_source_ids) or set(self.recipe.formula_semantics_source_ids) - source_ids:
            raise ValueError("formula semantics recipe requires unique known sources")
        selected_sources = [source for source in self.sources if source.source_id in self.recipe.formula_semantics_source_ids]
        if any(source.mime_type.lower() != "application/pdf" and not source.name.lower().endswith(".pdf") for source in selected_sources):
            raise ValueError("formula semantics recipe requires PDF sources")
        if self.recipe.formula_semantics_source_ids and self.recipe.id != "model":
            raise ValueError("formula semantics requires the model recipe")
        if self.recipe.classification_profile and self.recipe.id != "model":
            raise ValueError("classification requires the model recipe")
        if self.recipe.extraction_spec and self.recipe.id != "model":
            raise ValueError("typed extraction requires the model recipe")
        if set(self.relays) != {"embedding", "model"}:
            raise ValueError("relays must contain embedding and model")
        if {item.source_id for item in self.parsed_sources} != source_ids or len(self.parsed_sources) != len(source_ids):
            raise ValueError("parsed sources must match the source manifest exactly")
        if self.relays["embedding"].capability != "knowledge.publication.embed":
            raise ValueError("embedding relay capability is invalid")
        if self.relays["model"].capability != "knowledge.publication.generate":
            raise ValueError("model relay capability is invalid")
        return self


class RemoteConversionTask(StrictModel):
    task_id: str | None = Field(default=None, alias="taskId", min_length=1, max_length=1024)

    @field_validator("task_id")
    @classmethod
    def validate_task_identity(cls, value):
        if value is not None and (not value.strip() or len(value.encode('utf-8')) > 1024):
            raise ValueError('remote taskId must be nonblank and at most 1024 UTF-8 bytes')
        return value


class ParseSourceRequest(StrictModel):
    source: SourceBuildInput
    output_dir: str = Field(alias="outputDir")
    force_ocr: bool = Field(alias="forceOcr")
    document_processing: DocumentProcessingProfile = Field(alias="documentProcessing")
    remote_task: RemoteConversionTask | None = Field(default=None, alias="remoteTask")

    @field_validator("output_dir", mode="after")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        if not isabs(value):
            raise ValueError("parse outputDir must be absolute")
        return value


class BindParsedSourceRequest(ParseSourceRequest):
    parsed_artifact_path: str = Field(alias="parsedArtifactPath")
    parsed_artifact_digest: str = Field(alias="parsedArtifactDigest", pattern=r"^sha256:[a-f0-9]{64}$")
    parsed_reader_index_path: str = Field(alias="parsedReaderIndexPath")
    parsed_reader_index_digest: str = Field(alias="parsedReaderIndexDigest", pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("parsed_artifact_path", "parsed_reader_index_path", mode="after")
    @classmethod
    def validate_parsed_artifact_path(cls, value: str) -> str:
        if not isabs(value):
            raise ValueError("parsedArtifactPath must be absolute")
        return value


class WorkerRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, hide_input_in_errors=True)
    protocol: Literal[WORKER_PROTOCOL] = WORKER_PROTOCOL
    id: str
    method: Literal["parse_source", "bind_parsed_source", "build_semantic_artifacts", "validate_extraction_spec", "schema", "explain_evidence"]
    params: Dict[str, Any] = Field(default_factory=dict)
    authorization: Optional[Dict[str, str]] = Field(default=None, repr=False, exclude=True)
    document_processing_authorization: Optional[str] = Field(default=None, alias="documentProcessingAuthorization", repr=False, exclude=True)

    @field_validator("authorization", mode="after")
    @classmethod
    def validate_authorization(cls, value: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if value is None:
            return None
        for name, token in value.items():
            if not ENV_VAR_RE.fullmatch(name) or len(token) > 16384 or any(char in token for char in "\r\n\0"):
                raise ValueError("authorization contains an invalid environment name or credential")
        return value

    @field_validator("document_processing_authorization", mode="after")
    @classmethod
    def validate_document_processing_authorization(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (len(value) > 16384 or any(char in value for char in "\r\n\0")):
            raise ValueError("document processing authorization is invalid")
        return value


class WorkerError(StrictModel):
    type: str
    message: str
    status: Optional[int] = None
    code: Optional[str] = None
    retryable: bool = False
    retry_after_ms: Optional[int] = Field(default=None, alias="retryAfterMs")
    upstream_request_id: Optional[str] = Field(default=None, alias="upstreamRequestId")
    diagnostic: Optional[Dict[str, Any]] = None
    gateway: Optional[Dict[str, Any]] = None


class WorkerResponse(StrictModel):
    protocol: Literal[WORKER_PROTOCOL] = WORKER_PROTOCOL
    id: Optional[str] = None
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[WorkerError] = None




def build_request_json_schema() -> Dict[str, Any]:
    return SemanticArtifactBuildRequest.model_json_schema()
