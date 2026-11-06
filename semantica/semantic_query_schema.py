"""Strict native-owner query protocol; no aggregate knowledge carrier."""

from __future__ import annotations

from os.path import isabs
import math
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field, field_validator, model_validator

from .semantic_artifact_schema import DigestModel, StrictModel, DocumentLocator, _validate_media_type

QUERY_PROTOCOL = "semantica.semantic-query.v1"


class QueryInstallation(DigestModel):
    digest: str
    identity: str = Field(pattern=r'^\d+:\d+:\d+:\d+:\d+$', max_length=256)


class NativeStoreLocation(StrictModel):
    """Worker-only location and exact native publication fence."""
    path: str = Field(min_length=1, max_length=4096)
    project: str = Field(min_length=1, max_length=4096)

    @field_validator('path')
    @classmethod
    def validate_path(cls, value):
        if not isabs(value):
            raise ValueError('native store path must be absolute')
        return value


class NativeStoreRef(NativeStoreLocation):
    generation: str = Field(min_length=1, max_length=4096)


class QueryArtifactRef(DigestModel):
    path: str
    digest: str
    kind: Literal["document-representation", "document-reader-index"]
    media_type: str = Field(alias="mediaType")
    installation: Optional[QueryInstallation] = None

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not isabs(value):
            raise ValueError("query artifact path must be absolute")
        return value

    @field_validator("media_type", mode="after")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        return _validate_media_type(value, "query artifact mediaType")


class QueryEmbedding(StrictModel):
    binding_id: str = Field(alias="bindingId", min_length=1)
    model_id: str = Field(alias="modelId", min_length=1)
    vector: List[float] = Field(min_length=1)

    @field_validator("vector", mode="before")
    @classmethod
    def validate_vector(cls, value):
        if not isinstance(value, list) or not all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value):
            raise ValueError("query embedding must contain finite numbers")
        return value


class NativeIndexReceipt(StrictModel):
    kind: Literal['native-scalar-positions', 'native-sqlite-vec']
    store_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    recipe_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    space_id: Optional[str] = None


class NativeKeywordIndex(StrictModel):
    path: str = Field(min_length=1, max_length=4096)
    receipt: NativeIndexReceipt
    installation: QueryInstallation

    @model_validator(mode='after')
    def validate_index(self):
        if (not isabs(self.path) or self.receipt.kind != 'native-scalar-positions'
                or self.receipt.space_id is not None or self.installation.digest != self.receipt.store_id):
            raise ValueError('native keyword installation differs from its receipt')
        return self


class NativeEmbeddingSpace(StrictModel):
    binding_id: str = Field(alias='bindingId', min_length=1, max_length=4096)
    model_id: str = Field(alias='modelId', min_length=1, max_length=4096)
    dimensions: int = Field(ge=1, le=8192)
    space_id: str = Field(min_length=1, max_length=4096)
    recipe: str = Field(min_length=1, max_length=4096)


class NativeSemanticIndex(StrictModel):
    path: str = Field(min_length=1, max_length=4096)
    receipt: NativeIndexReceipt
    space: NativeEmbeddingSpace

    @model_validator(mode='after')
    def validate_index(self):
        if (not isabs(self.path) or self.receipt.kind != 'native-sqlite-vec'
                or self.receipt.space_id != self.space.space_id):
            raise ValueError('native vector space differs from its receipt')
        return self


class NativeIndexes(StrictModel):
    keyword: NativeKeywordIndex
    semantic: Optional[NativeSemanticIndex] = None


class SemanticQueryRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["query", "schema"]
    project_id: str = Field(alias="projectId")
    generation: str = Field(min_length=1, max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    native_indexes: NativeIndexes = Field(alias='nativeIndexes')
    query: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=128)
    top_k: Optional[int] = Field(default=None, alias='topK', ge=1, le=1000)
    mode: Literal["keyword", "semantic"] = "keyword"
    target: Literal["knowledge", "documents"] = "knowledge"
    offset: int = Field(default=0, ge=0)
    position: Optional[Tuple[str, str, int, int]] = None
    navigation: Literal['next', 'previous', 'next_source', 'previous_source', 'next_page', 'previous_page'] = 'next'
    embedding: Optional[QueryEmbedding] = None
    source_ids: Optional[List[str]] = Field(default=None, alias="sourceIds")
    source_artifacts: Optional[Dict[str, 'DocumentReaderRequest']] = Field(default=None, alias="sourceArtifacts")

    @model_validator(mode="after")
    def validate_mode(self):
        if self.semantic_store.project != self.project_id or self.semantic_store.generation != self.generation:
            raise ValueError('native query publication identity differs')
        if self.mode == 'semantic' and (self.position is not None or self.navigation != 'next'):
            raise ValueError('semantic top-k does not accept occurrence pagination')
        if self.top_k is not None and self.mode != 'semantic':
            raise ValueError('only semantic queries accept a top-k budget')
        if self.mode == 'semantic' and self.offset >= (self.top_k or self.limit):
            raise ValueError('semantic offset exceeds the requested top-k budget')
        if self.target == "knowledge" and self.mode == 'keyword' and self.offset:
            raise ValueError("knowledge queries do not accept document pagination")
        if self.position is not None and (self.target != 'documents' or not self.position[0]
                or not self.position[1].startswith('#/document/') or self.position[2] < 0 or self.position[3] < 0):
            raise ValueError('invalid document position cursor')
        if self.mode == 'keyword' and self.target == 'documents' and self.offset and self.position is None:
            raise ValueError('document continuation requires a stable position cursor')
        if self.navigation != 'next' and (self.target != 'documents' or self.position is None):
            raise ValueError('document navigation requires a position cursor')
        if self.method == 'query' and self.query is None:
            raise ValueError('query text is required')
        if self.source_ids is not None and (len(self.source_ids)>128 or len(set(self.source_ids)) != len(self.source_ids)
                or any(not source_id.strip() for source_id in self.source_ids)):
            raise ValueError("query source identities must be nonempty and unique")
        if (self.mode == "semantic") != (self.embedding is not None):
            raise ValueError("semantic mode requires a query embedding; keyword mode does not accept one")
        if self.mode == 'semantic' and self.native_indexes.semantic is None:
            raise ValueError('semantic query requires native vector publication')
        if self.source_artifacts is not None and (len(self.source_artifacts)>128
                or any(key != ref.source_id for key,ref in self.source_artifacts.items())):
            raise ValueError('source artifacts must contain selected native reader references')
        return self

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("query must not be empty")
        if value is not None and len(value.encode('utf-8')) > 1024:
            raise ValueError('query exceeds 1 KiB')
        return value.strip() if value is not None else value


class QueryHit(StrictModel):
    id: str
    kind: Literal["entity", "assertion", "relation", "conflict", "topic", "report", "evidence", "source_text"]
    title: str
    text: str
    score: float = Field(allow_inf_nan=False)
    status: Optional[str] = None
    polarity: Optional[Literal["positive", "negative"]] = None
    evidence_ids: List[str] = Field(default_factory=list, alias="evidenceIds")
    evidence_next_cursor: Optional[Tuple[str,str]] = Field(default=None,alias='evidenceNextCursor')
    source_ids: List[str] = Field(default_factory=list, alias="sourceIds")
    locator: Optional["DocumentLocator"] = None
    match_index: Optional[int] = Field(default=None, alias="matchIndex", ge=0)
    position: Optional[Tuple[str, str, int, int]] = None

    @model_validator(mode='after')
    def validate_id_like_fields(self):
        # Native RDF identities are not product-generated short record IDs.
        # Preserve the owner's exact identity rather than hashing a second ID.
        values = [self.id, *self.evidence_ids, *self.source_ids]
        if any(not isinstance(value,str) or not value or len(value.encode()) > 8192
               or any(char.isspace() for char in value) for value in values):
            raise ValueError('native query identities must be bounded nonempty identifiers')
        return self


class SemanticQueryResult(StrictModel):
    project_id: str = Field(alias="projectId")
    generation: str
    query: str
    contexts: List[QueryHit]
    total: Optional[int] = Field(default=None, ge=0)
    next_offset: Optional[int] = Field(default=None, alias="nextOffset", ge=0)
    next_position: Optional[Tuple[str, str, int, int]] = Field(default=None, alias='nextPosition')
    previous_position: Optional[Tuple[str, str, int, int]] = Field(default=None, alias='previousPosition')
    start_offset: Optional[int] = Field(default=None, alias='startOffset', ge=0)
    required_source_ids: Optional[List[str]] = Field(default=None, alias="requiredSourceIds")


class QueryWorkerRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["query", "schema", "records", "section", "scene", "classification", "bindings", "evidence", "reader", "acquire_store", "release_store"]
    params: Dict[str, object] = Field(default_factory=dict)


class NativeStoreControlRequest(StrictModel):
    semantic_store: NativeStoreRef = Field(alias='semanticStore')


class NativeStoreReleaseRequest(StrictModel):
    semantic_store: NativeStoreLocation = Field(alias='semanticStore')


class NativeSceneRequest(StrictModel):
    project_id: str = Field(alias='projectId', min_length=1, max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    selection: Dict[str, object]

    @model_validator(mode='after')
    def validate_scene(self):
        if self.project_id != self.semantic_store.project:
            raise ValueError('native scene project differs from request project')
        # The native storage owner validates its single selection contract.
        if len(self.selection) > 7:
            raise ValueError('native scene selection exceeds field budget')
        return self


class NativeClassificationSelection(StrictModel):
    source_id: str = Field(alias='sourceId', min_length=1, max_length=1024)
    dimension_id: Optional[str] = Field(default=None, alias='dimensionId', min_length=1, max_length=1024)
    after: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    limit: int = Field(default=128, ge=1, le=128)
    max_bytes: int = Field(default=262144, alias='maxBytes', ge=1, le=262144)

    @model_validator(mode='after')
    def validate_cursor(self):
        if self.dimension_id is None and self.after is not None:
            raise ValueError('classification header does not accept a cursor')
        return self


class NativeClassificationRequest(StrictModel):
    project_id: str = Field(alias='projectId', min_length=1, max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    selection: NativeClassificationSelection

    @model_validator(mode='after')
    def validate_project(self):
        if self.project_id != self.semantic_store.project:
            raise ValueError('native classification project differs from request project')
        return self


class NativeBindingRequest(StrictModel):
    project_id: str = Field(alias='projectId', min_length=1, max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    ids: List[str] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def validate_bindings(self):
        if self.project_id != self.semantic_store.project:
            raise ValueError('native binding project differs from request project')
        if len(set(self.ids)) != len(self.ids) or any(not value or len(value.encode()) > 4096 for value in self.ids):
            raise ValueError('native bindings require unique bounded identities')
        return self


class NativeEvidenceRequest(StrictModel):
    project_id: str = Field(alias='projectId',min_length=1,max_length=4096)
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    native_indexes: NativeIndexes = Field(alias='nativeIndexes')
    record_id: str = Field(alias='recordId',min_length=1,max_length=8192)
    source_ids: Optional[List[str]] = Field(default=None,alias='sourceIds',max_length=128)
    after: Optional[Tuple[str,str]] = None
    limit: int = Field(default=128,ge=1,le=128)

    @model_validator(mode='after')
    def validate_scope(self):
        if self.project_id != self.semantic_store.project or self.native_indexes.semantic is None:
            raise ValueError('Native evidence requires current scoped semantic index')
        if self.after is not None and any(not value or len(value.encode())>8192 for value in self.after):
            raise ValueError('Invalid native evidence cursor')
        return self


class CanonicalRecordSelection(StrictModel):
    ids: Optional[List[str]] = None
    source_ids: Optional[List[str]] = Field(default=None, alias="sourceIds")
    source_id: Optional[str] = Field(default=None, alias="sourceId", min_length=1, max_length=1024)
    after: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    limit: int = Field(default=128, ge=1, le=128)
    max_bytes: int = Field(default=262144, alias='maxBytes', ge=1, le=262144)

    @model_validator(mode="after")
    def validate_selection(self):
        if sum(value is not None for value in (self.ids, self.source_id)) != 1:
            raise ValueError("select exactly one canonical record selection")
        identities = self.ids
        if identities is not None and (not identities or len(identities) > 128 or len(set(identities)) != len(identities)):
            raise ValueError("canonical record selection must contain 1..128 unique identities")
        if self.source_ids is not None and (identities is None or not 1 <= len(self.source_ids) <= 128
                or any(not source or len(source.encode()) > 4096 for source in self.source_ids)
                or len(set(self.source_ids)) != len(self.source_ids)):
            raise ValueError("native source selection requires 1..128 unique sources and exact record IDs")
        if self.source_id is None and (self.after is not None or self.limit != 128):
            raise ValueError("canonical record cursor is only valid for source passages")
        return self


class CanonicalRecordRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["records"] = "records"
    project_id: str = Field(alias="projectId")
    semantic_store: NativeStoreRef = Field(alias='semanticStore')
    selection: CanonicalRecordSelection

    @model_validator(mode="after")
    def validate_store(self):
        if self.project_id != self.semantic_store.project:
            raise ValueError('native store project differs from request project')
        return self


class DocumentReaderRange(StrictModel):
    native_ref: str = Field(alias='nativeRef', min_length=1, max_length=4096, pattern=r'^#/document/')
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode='after')
    def validate_extent(self):
        if not self.start < self.end <= self.start + 64 * 1024:
            raise ValueError('native reader range must contain 1..65536 codepoints')
        return self


class DocumentReaderSelection(StrictModel):
    field: Literal['chunks', 'pages', 'ranges', 'structure', 'source_windows']
    ranges: List[DocumentReaderRange] | None = Field(default=None, min_length=1, max_length=128)
    roots: List[str] | None = Field(default=None, min_length=1, max_length=32)
    max_objects: int = Field(default=64, alias='maxObjects', ge=1, le=512)
    max_depth: int = Field(default=8, alias='maxDepth', ge=0, le=32)
    page_number: int | None = Field(default=None, alias='pageNumber', ge=1, le=100000)
    after: int = Field(default=-1, ge=-1)
    limit: int = Field(default=128, ge=1, le=128)
    max_bytes: int = Field(default=1024*1024, alias='maxBytes', ge=1, le=4*1024*1024)

    @model_validator(mode='after')
    def validate_page_selection(self):
        if self.page_number is not None and self.field != 'pages':
            raise ValueError('pageNumber is only valid for pages')
        if (self.field == 'ranges') != (self.ranges is not None):
            raise ValueError('exact native ranges require field=ranges and explicit ranges')
        if self.field == 'ranges' and (self.after != -1 or self.limit != 128 or self.max_bytes > 262144):
            raise ValueError('exact native ranges do not accept pagination and require at most 256KiB')
        if (self.field == 'structure') != (self.roots is not None):
            raise ValueError('native structure requires explicit roots and field=structure')
        if self.field == 'structure':
            import re
            if self.after != -1 or self.limit != 128 or self.max_bytes > 262144:
                raise ValueError('native structure does not accept pagination and requires at most 256KiB')
            if any(len(ref) > 128 or not re.fullmatch(
                    r'#/(?:(?:texts|pictures|groups)/\d+|tables/\d+/data/table_cells/\d+)', ref)
                    for ref in self.roots):
                raise ValueError('native structure roots must be original node or table cell references')
        elif self.max_objects != 64 or self.max_depth != 8:
            raise ValueError('structure bounds are only valid for structure selections')
        return self


class DocumentReaderRequest(StrictModel):
    id: str
    source_id: str = Field(alias='sourceId', min_length=1, max_length=1024)
    material_revision: str = Field(alias='materialRevision')
    representation_revision: str = Field(alias='representationRevision')
    artifact: QueryArtifactRef
    reader_index: QueryArtifactRef = Field(alias='readerIndex')
    selection: DocumentReaderSelection

    @model_validator(mode='after')
    def validate_installations(self):
        if self.artifact.kind != 'document-representation' or self.reader_index.kind != 'document-reader-index':
            raise ValueError('document reader requires canonical source and reader index')
        if any(ref.installation is None or ref.installation.digest != ref.digest for ref in (self.artifact, self.reader_index)):
            raise ValueError('document reader requires verified installations')
        return self


class QueryWorkerError(StrictModel):
    type: str
    message: str


class QueryMetrics(StrictModel):
    duration_ms: float = Field(alias='durationMs', ge=0, allow_inf_nan=False)
    retrieval_ms: float = Field(alias='retrievalMs', ge=0, allow_inf_nan=False)
    hydration_ms: float = Field(alias='hydrationMs', ge=0, allow_inf_nan=False)
    canonical_bytes: int = Field(alias='canonicalBytes', ge=0)
    record_bytes: int = Field(alias='recordBytes', ge=0)
    sqlite_vm_steps_lower_bound: int = Field(alias='sqliteVmStepsLowerBound', ge=0)


class QueryWorkerResponse(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: Optional[str] = None
    ok: bool
    result: Optional[Dict[str, object]] = None
    error: Optional[QueryWorkerError] = None
    metrics: Optional[QueryMetrics] = None
