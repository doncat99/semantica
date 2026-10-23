"""Generic source-grounded extraction for one caller-owned text window."""
from __future__ import annotations

from typing import Any, Callable

from ..utils.exceptions import ProcessingError
from ..semantic_artifact_errors import model_output_cause
from .methods import extract_entities_llm, extract_relations_llm
from .schema import ExtractionSpecification
from .types import Entity, Relation
from .providers import BaseProvider


def _retryable_failure(error: BaseException) -> bool:
    """Retry only transport/gateway failures, never deterministic validation errors."""
    return BaseProvider._is_transport_failure(error)


def _record_rejections(provider):
    if getattr(provider, "rejections", None) and getattr(provider, "receipts", None):
        receipt = provider.receipts[-1]
        metadata = receipt.setdefault("metadata", {}) if isinstance(receipt, dict) else receipt.metadata
        metadata["rejected_candidates"] = list(provider.rejections)


def extract_grounded_window(
    text: str,
    *,
    model: str,
    provider_instance: Any,
    extraction_spec: ExtractionSpecification | dict[str, Any] | None = None,
    provider: str = "bifrost",
    retries: int = 1,
    provider_factory: Callable[[], Any] | None = None,
    grounding_context: list[dict[str, Any]] | None = None,
    formula_semantics: bool = False,
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
        entities = []
        stage = "entities"
        current_provider = provider_instance if attempt == 0 else (provider_factory() if provider_factory else provider_instance)
        if current_provider is None:
            raise ProcessingError("grounded extraction requires a provider instance")
        try:
            entities = extract_entities_llm(
                text, provider=provider_name, model=model,
                provider_instance=current_provider, grounding="strict",
                max_retries=1, grounding_retries=1, extraction_spec=specification,
                rejection_receipts=getattr(current_provider, "rejections", None),
                grounding_context=grounding_context,
                formula_semantics=formula_semantics,
            )
            if not entities:
                _record_rejections(current_provider)
                return entities, [], current_provider
            stage = "relations"
            relations = extract_relations_llm(
                text, entities, provider=provider_name, model=model,
                provider_instance=current_provider, grounding="strict",
                max_retries=1, grounding_retries=1, extraction_spec=specification,
                confidence_threshold=0,
                grounding_context=grounding_context,
                formula_semantics=formula_semantics,
                rejection_receipts=getattr(current_provider, "rejections", None),
            )
            _record_rejections(current_provider)
            return entities, relations, current_provider
        except ProcessingError as exc:
            last_error = exc
            reject = getattr(current_provider, "reject_last", None)
            if callable(reject) and not _retryable_failure(exc):
                reject()
            local = model_output_cause(exc)
            if local is not None and hasattr(current_provider, "rejections"):
                current_provider.rejections.append({
                    "code": local.code, "stage": stage,
                    "action": "skipped_relations" if stage == "relations" else "skipped_extraction",
                    "diagnostic": local.diagnostic or {},
                })
                _record_rejections(current_provider)
                return entities, [], current_provider
            if attempt >= max(0, retries) or not _retryable_failure(exc):
                raise
    raise last_error or ProcessingError("grounded extraction failed")
