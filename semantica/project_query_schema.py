"""Strict protocol types for querying one immutable Semantica snapshot."""

from __future__ import annotations

from os.path import isabs
from typing import Dict, List, Literal, Optional

from pydantic import Field, field_validator

from .project_snapshot_schema import DigestModel, StrictModel, _validate_media_type

QUERY_PROTOCOL = "semantica.project-query.v1"


class QueryArtifactRef(DigestModel):
    path: str
    digest: str
    kind: Literal["snapshot", "retrieval-index"]
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


class ProjectQueryRequest(StrictModel):
    protocol: Literal[QUERY_PROTOCOL] = QUERY_PROTOCOL
    id: str
    method: Literal["query", "schema"]
    project_id: str = Field(alias="projectId")
    snapshot_id: str = Field(alias="snapshotId")
    snapshot: QueryArtifactRef
    retrieval: QueryArtifactRef
    query: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("query must not be empty")
        return value.strip() if value is not None else value


class QueryHit(StrictModel):
    id: str
    kind: str
    title: str
    text: str
    score: float = Field(ge=0)
    evidence_ids: List[str] = Field(default_factory=list, alias="evidenceIds")
    source_ids: List[str] = Field(default_factory=list, alias="sourceIds")


class ProjectQueryResult(StrictModel):
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

