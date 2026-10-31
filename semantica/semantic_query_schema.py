"""Strict protocol types for querying one immutable Semantica snapshot."""

from __future__ import annotations

from os.path import isabs
import math
from typing import Dict, List, Literal, Optional

from pydantic import Field, field_validator, model_validator

from .semantic_artifact_schema import DigestModel, StrictModel, MATERIAL_REVISION_PATTERN, _validate_media_type

QUERY_PROTOCOL = "semantica.semantic-query.v1"


class QueryArtifactRef(DigestModel):
    path: str
    digest: str
    kind: Literal["semantic-graph", "retrieval-index", "keyword-index"]
    media_type: str = Field(alias="mediaType")

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


class QuerySource(StrictModel):
    source_id: str = Field(alias="sourceId", min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=MATERIAL_REVISION_PATTERN)


class SemanticQueryRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["query", "schema"]
    project_id: str = Field(alias="projectId")
    snapshot_id: str = Field(alias="snapshotId")
    snapshot: QueryArtifactRef
    retrieval: Optional[QueryArtifactRef] = None
    keyword_index: Optional[QueryArtifactRef] = Field(default=None, alias="keywordIndex")
    query: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=1000)
    mode: Literal["keyword", "semantic"] = "keyword"
    embedding: Optional[QueryEmbedding] = None
    source_ids: Optional[List[str]] = Field(default=None, alias="sourceIds")
    sources: List[QuerySource]

    @model_validator(mode="after")
    def validate_mode(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("query source identities must be unique")
        if self.source_ids is not None and not set(self.source_ids).issubset(source.source_id for source in self.sources):
            raise ValueError("query source scope is outside the authorized project")
        if (self.mode == "semantic") != (self.embedding is not None):
            raise ValueError("semantic mode requires a query embedding; keyword mode does not accept one")
        if self.mode == "semantic" and self.retrieval is None:
            raise ValueError("semantic mode requires the retrieval artifact")
        if self.mode == "keyword" and (self.keyword_index is None or self.keyword_index.kind != "keyword-index"):
            raise ValueError("keyword mode requires the published keyword index; rebuild is required")
        return self

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("query must not be empty")
        return value.strip() if value is not None else value


class QueryHit(StrictModel):
    id: str
    kind: Literal["entity", "assertion", "relation", "conflict", "topic", "report", "evidence"]
    title: str
    text: str
    score: float = Field(allow_inf_nan=False)
    status: Optional[str] = None
    polarity: Optional[Literal["positive", "negative"]] = None
    evidence_ids: List[str] = Field(default_factory=list, alias="evidenceIds")
    source_ids: List[str] = Field(default_factory=list, alias="sourceIds")


class SemanticQueryResult(StrictModel):
    project_id: str = Field(alias="projectId")
    snapshot_id: str = Field(alias="snapshotId")
    query: str
    contexts: List[QueryHit]
    retrieval_manifest_id: str = Field(alias="retrievalManifestId")


class QueryWorkerRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["query", "schema"]
    params: Dict[str, object] = Field(default_factory=dict)


class QueryWorkerError(StrictModel):
    type: str
    message: str


class QueryWorkerResponse(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: Optional[str] = None
    ok: bool
    result: Optional[Dict[str, object]] = None
    error: Optional[QueryWorkerError] = None
