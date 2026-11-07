"""Paid semantic recipes follow their actual producers, not publication code."""
from functools import lru_cache
from importlib.metadata import version
from inspect import getsource

from .semantic_artifact_schema import stable_digest


@lru_cache(maxsize=32)
def _producer_digest(producers):
    # Positive dependency closure. Preserve complete callable bodies: no AST
    # exclusions that could silently discard prompt/validation changes. Native
    # storage/cache/publication/query modules are not semantic producers.
    return stable_digest({
        'producers': [getsource(producer) for producer in producers],
        'pydantic': version('pydantic'),
        'pydantic-core': version('pydantic-core'),
    })


def extraction_recipe(request) -> str:
    """Bind the actual prompt, grounding, schema and admitted generation model.

    Source bytes/revisions, windows, scalar ranges and hydrated grounding values
    are bound separately by the native operation. Publication/classification
    profiles and the embedding producer do not change paid extraction identity.
    Runtime dispatch and offline migration must call this same owner.
    """
    from . import semantic_publication_builder as builder
    from .semantic_extract import methods, schema, schemas, types, providers
    from .semantic_extract.grounded_window import _produce_grounded_entities, _produce_grounded_relations

    producers = (
        _produce_grounded_entities, _produce_grounded_relations,
        methods.extract_entities_llm, methods.extract_relations_llm,
        methods._prompt_grounding_context, methods._exact_occurrence,
        methods._grounded_qualifiers, methods.filter_entities_for_text,
        methods._parse_grounded_relation_result,
        schema.ExtractionAttribute, schema.ExtractionEntityType, schema.ExtractionRelationType,
        schema.ExtractionExampleEntity, schema.ExtractionExampleRelation, schema.ExtractionExample,
        schema.ExtractionSpecification, schema.Predicate, schema.ExtractionSchema,
        schema._as_name_set, schema._drop_thing, schema._constraint_set,
        schemas.validate_fact_qualifiers, schemas.IdentityProfileWire, schemas.IdentityProfileOut,
        schemas.EntityOut, schemas.RelationOut, schemas.GroundedEntityOut,
        schemas.GroundedEntitiesResponse, schemas.GroundedRelationOut,
        schemas.GroundedRelationsResponse, schemas.GroundedQualifiersWire,
        schemas.GroundedRelationWire, schemas.GroundedRelationsWire, schemas.grounded_entities_wire,
        types.Entity, types.Relation, types.normalize_fact_predicate,
        providers._extract_first_json_value, providers.ResponseText,
        providers.BaseProvider._parse_json, providers.BaseProvider.generate_structured,
        providers.BaseProvider.generate_typed, providers.BaseProvider._reject_last_typed_attempt,
        builder._input_token_budget, builder._generation_payload, builder._request_size,
        builder._context_size, builder._extraction_context_batches,
        builder._validate_generation_model, builder._generation_content,
    )
    relay = request.relays['model']
    return stable_digest({
        'producer': _producer_digest(producers),
        'generationBinding': relay.binding_id,
        'model': relay.model_id,
        'contextWindowTokens': relay.context_window_tokens,
        'maxOutputTokens': relay.max_output_tokens,
        'specification': request.recipe.extraction_spec.digest if request.recipe.extraction_spec else 'none',
    })


def classification_recipe(relay) -> str:
    """Bind paid classification, independently of extraction and publication.

    The native classification operation separately binds taxonomy/profile and
    exact evidence context. Read, reduction and publication code do not invoke
    paid generation and therefore do not belong to this computation identity.
    """
    from . import semantic_publication_builder as builder
    from . import semantic_artifact_schema as schema
    from .semantic_extract import providers

    # The instruction is a value, rather than a callable, so hash it separately.
    return stable_digest({
        'instruction': builder._CLASSIFICATION_INSTRUCTION,
        'producer': _producer_digest((
            builder._produce_source_classification, builder._product_json,
            builder._model_evidence_context, builder._ProductOutput, builder._SemanticCitation,
            builder._ClassificationOutputItem, builder._ClassificationOutput,
            schema.StrictModel, schema._unique, schema.ClassificationVocabularyItem,
            schema.ClassificationDimension, schema.ClassificationProfile,
            schema.ClassificationAssignment, schema.SourceClassification,
            providers._extract_first_json_value, providers.ResponseText,
            providers.BaseProvider._parse_json, providers.BaseProvider.generate_structured,
            providers.BaseProvider.generate_typed, providers.BaseProvider._reject_last_typed_attempt,
            builder._input_token_budget, builder._generation_payload,
            builder._request_size, builder._context_size, builder._context_batches,
            builder._validate_generation_model, builder._generation_content,
        )),
        'generationBinding': relay.binding_id, 'model': relay.model_id,
        'contextWindowTokens': relay.context_window_tokens,
        'maxOutputTokens': relay.max_output_tokens,
    })
