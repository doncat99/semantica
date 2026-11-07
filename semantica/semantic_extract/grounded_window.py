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
        metadata["rejected_count"] = len(provider.rejections)


def _produce_grounded_entities(text, provider_name, model, current_provider, specification,
                               grounding_context, formula_semantics):
    return extract_entities_llm(
        text, provider=provider_name, model=model,
        provider_instance=current_provider, grounding="strict",
        max_retries=1, grounding_retries=1, extraction_spec=specification,
        rejection_receipts=getattr(current_provider, "rejections", None),
        grounding_context=grounding_context, formula_semantics=formula_semantics,
    )


def _produce_grounded_relations(text, entities, provider_name, model, current_provider,
                                specification, grounding_context, formula_semantics):
    return extract_relations_llm(
        text, entities, provider=provider_name, model=model,
        provider_instance=current_provider, grounding="strict",
        max_retries=1, grounding_retries=1, extraction_spec=specification,
        confidence_threshold=0, grounding_context=grounding_context,
        formula_semantics=formula_semantics,
        rejection_receipts=getattr(current_provider, "rejections", None),
    )


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
    native_store: Any = None,
    accepted_cache: Any = None,
    extraction_binding: dict[str, Any] | None = None,
    native_ranges: list[dict[str, Any]] | None = None,
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
    durable = any(value is not None for value in (native_store, accepted_cache, extraction_binding))
    if durable:
        if native_store is None or accepted_cache is None or extraction_binding is None or native_ranges is None:
            raise ProcessingError("Native extraction requires store, acceptance owner and complete binding")
        native_store.extraction_operation_id(extraction_binding, "entities")
        if extraction_binding["model"] != model:
            raise ProcessingError("Native extraction model binding mismatch")

    def restore_receipts(current_provider, receipts):
        if not hasattr(current_provider, "receipts"):
            return
        for receipt in receipts:
            identity = receipt.get("id") if isinstance(receipt, dict) else receipt.id
            existing = [item for item in current_provider.receipts
                        if (item.get("id") if isinstance(item, dict) else item.id) == identity]
            if existing:
                value = existing[0].model_dump(mode="json") if hasattr(existing[0], "model_dump") else existing[0]
                if value != receipt:
                    raise ProcessingError("Restored native model receipt conflicts with current receipt")
            else:
                current_provider.receipts.append(receipt)

    def run_stage(stage, operation, current_provider, entities=None):
        if not durable:
            return operation()
        # The persistent cache owns only a short-lived accepted handoff. Ordinary
        # LLM caching would retain a second durable copy after native adoption.
        current_provider.extraction_cache = None
        cache_params = {"native_operation": native_store.extraction_operation_id(extraction_binding, stage)}
        digest = accepted_cache.accepted_digest(stage, text, **cache_params)
        receipt = native_store.extraction_receipt(extraction_binding, stage)
        if receipt is not None:
            if digest != receipt["accepted_digest"]:
                raise ProcessingError("Native receipt and paid acceptance identity differ")
            values = native_store.read_extraction(extraction_binding, stage, text=text, native_ranges=native_ranges, entities=entities, extraction_spec=specification)
            # A released body is absent by design. Its durable acceptance digest
            # remains; only a verified native receipt makes that absence safe.
            if accepted_cache.has_accepted_body(stage, text, digest, **cache_params):
                native_store.flush()
                accepted_cache.release_accepted(stage, text, digest, **cache_params)
            recovered = native_store.read_extraction_receipts(extraction_binding, stage)
            restore_receipts(current_provider, recovered)
            return values
        if digest is None:
            before = len(getattr(current_provider, "receipts", []))
            values = operation()
            _record_rejections(current_provider)
            receipts = getattr(current_provider, "receipts", [])[before:]
            envelope = {"values": values, "receipts": [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in receipts]}
            digest = accepted_cache.accept(stage, text, envelope, **cache_params)
        else:
            envelope = accepted_cache.get_accepted(stage, text, **cache_params)
            if not isinstance(envelope, dict) or set(envelope) != {"values", "receipts"}:
                raise ProcessingError("Accepted native extraction envelope is invalid")
            values, receipts = envelope["values"], envelope["receipts"]
            restore_receipts(current_provider, receipts)
        native_store.adopt_extraction(extraction_binding, stage, values, text=text,
                                     native_ranges=native_ranges,
                                     accepted_digest=digest, receipts=receipts,
                                     extraction_spec=specification)
        accepted_cache.release_accepted(stage, text, digest, **cache_params)
        return values
    provider_name = provider
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        entities = []
        stage = "entities"
        current_provider = provider_instance if attempt == 0 else (provider_factory() if provider_factory else provider_instance)
        if current_provider is None:
            raise ProcessingError("grounded extraction requires a provider instance")
        try:
            entities = run_stage("entities", lambda: _produce_grounded_entities(
                text, provider_name, model, current_provider, specification,
                grounding_context, formula_semantics,
            ), current_provider)
            if not entities:
                _record_rejections(current_provider)
                return entities, [], current_provider
            stage = "relations"
            relations = run_stage("relations", lambda: _produce_grounded_relations(
                text, entities, provider_name, model, current_provider, specification,
                grounding_context, formula_semantics,
            ), current_provider, entities)
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
                    "action": "failed_extraction",
                    "diagnostic": local.diagnostic or {},
                })
                _record_rejections(current_provider)
                raise
            if attempt >= max(0, retries) or not _retryable_failure(exc):
                raise
    raise last_error or ProcessingError("grounded extraction failed")
