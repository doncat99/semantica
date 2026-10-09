"""Generic source-grounded extraction for one caller-owned text window."""
from __future__ import annotations

from typing import Any, Callable

from ..utils.exceptions import ProcessingError
from .methods import extract_entities_llm, extract_relations_llm
from .schema import ExtractionSpecification
from .types import Entity, Relation


def _retryable_failure(error: BaseException) -> bool:
    """Retry only transport/gateway failures, never deterministic validation errors."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if (
            getattr(current, "retryable", False) is True
            or getattr(current, "retry_after_ms", None) is not None
            or getattr(current, "retryAfterMs", None) is not None
        ):
            return True
        status = getattr(current, "status", getattr(current, "status_code", None))
        if isinstance(status, int) and (status == 429 or 500 <= status <= 599):
            return True
        current = current.__cause__ or current.__context__
    return False


def extract_grounded_window(
    text: str,
    *,
    model: str,
    provider_instance: Any,
    extraction_spec: ExtractionSpecification | dict[str, Any] | None = None,
    provider: str = "bifrost",
    retries: int = 1,
    provider_factory: Callable[[], Any] | None = None,
) -> tuple[list[Entity], list[Relation], Any]:
    """Run Semantica's native strict entity and relation extractors.

    The caller owns transport receipts and persistence. This function has no
    product or project schema and only returns Semantica domain objects.
    """
    if not text.strip():
        raise ProcessingError("grounded extraction requires non-empty text")
    specification = (
        extraction_spec
        if isinstance(extraction_spec, ExtractionSpecification)
        else ExtractionSpecification.model_validate(extraction_spec)
        if extraction_spec is not None
        else None
    )
    provider_name = provider
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        current_provider = provider_instance if attempt == 0 else (provider_factory() if provider_factory else provider_instance)
        if current_provider is None:
            raise ProcessingError("grounded extraction requires a provider instance")
        try:
            entities = extract_entities_llm(
                text, provider=provider_name, model=model,
                provider_instance=current_provider, grounding="strict",
                max_retries=1, grounding_retries=1, extraction_spec=specification,
                rejection_receipts=getattr(current_provider, "rejections", None),
            )
            if not entities:
                if getattr(current_provider, "rejections", None) and getattr(current_provider, "receipts", None):
                    current_provider.receipts[-1].metadata["rejected_candidates"] = current_provider.rejections
                return entities, [], current_provider
            relations = extract_relations_llm(
                text, entities, provider=provider_name, model=model,
                provider_instance=current_provider, grounding="strict",
                max_retries=1, grounding_retries=1, extraction_spec=specification,
                confidence_threshold=0,
                rejection_receipts=getattr(current_provider, "rejections", None),
            )
            if getattr(current_provider, "rejections", None) and getattr(current_provider, "receipts", None):
                current_provider.receipts[-1].metadata["rejected_candidates"] = current_provider.rejections
            return entities, relations, current_provider
        except ProcessingError as exc:
            last_error = exc
            reject = getattr(current_provider, "reject_last", None)
            if callable(reject):
                reject()
            if attempt >= max(0, retries) or not _retryable_failure(exc):
                raise
    raise last_error or ProcessingError("grounded extraction failed")
