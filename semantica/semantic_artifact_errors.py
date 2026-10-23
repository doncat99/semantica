"""Shared semantic-artifact failures, independent of build dependencies."""
from __future__ import annotations

from typing import Any


class SemanticArtifactError(RuntimeError):
    """Raised when a source cannot be represented by the single Semantica chain."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None,
                 retryable: bool = False, retry_after_ms: int | None = None,
                 upstream_request_id: str | None = None, diagnostic: dict[str, Any] | None = None,
                 gateway: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
        self.upstream_request_id = upstream_request_id
        self.diagnostic = diagnostic
        self.gateway = gateway


class DocumentQualityError(SemanticArtifactError):
    """A parsed representation needs an explicit repair before knowledge production."""


class ModelOutputError(SemanticArtifactError):
    """A response-local defect; never a transport, authorization or integrity failure."""


def model_output_cause(error: BaseException) -> ModelOutputError | None:
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ModelOutputError):
            return error
        error = error.__cause__
    return None
