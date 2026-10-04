"""Generic source-grounded extraction for one caller-owned text window."""
from __future__ import annotations

from typing import Any, Callable

from ..utils.exceptions import ProcessingError
from .methods import extract_entities_llm, extract_relations_llm
from .schema import ExtractionSpecification
from .types import Entity, Relation


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
                grounding_retries=1, extraction_spec=specification,
            )
            relations = extract_relations_llm(
                text, entities, provider=provider_name, model=model,
                provider_instance=current_provider, grounding="strict",
                grounding_retries=1, extraction_spec=specification,
                confidence_threshold=0,
            )
            return entities, relations, current_provider
        except ProcessingError as exc:
            last_error = exc
            reject = getattr(current_provider, "reject_last", None)
            if callable(reject):
                reject()
            if attempt >= max(0, retries):
                raise
    raise last_error or ProcessingError("grounded extraction failed")
