"""Business identity follows semantic inputs, never executable source."""
from .semantic_artifact_schema import stable_digest


def extraction_recipe(request) -> str:
    from .semantic_extract.methods import entity_extraction_prompt, relation_extraction_prompt
    from .semantic_extract.schemas import grounded_entities_wire, GroundedRelationsWire
    relay = request.relays['model']
    spec = request.recipe.extraction_spec
    # Render the same prompt owners as production with symbolic data. Actual
    # source windows, mentions and grounding are independently bound by operations.
    context = [{'ref': 'structure', 'quote': 'source'}]
    return stable_digest({
        'prompts': [prompt for formula in (False, True) for prompt in (
            entity_extraction_prompt('source', spec, grounding_context=context, formula_semantics=formula),
            relation_extraction_prompt('source', [], spec, grounding_context=context, formula_semantics=formula))],
        'output': [grounded_entities_wire(spec).model_json_schema(), GroundedRelationsWire.model_json_schema()],
        'generationBinding': relay.binding_id, 'model': relay.model_id,
        'contextWindowTokens': relay.context_window_tokens, 'maxOutputTokens': relay.max_output_tokens,
        'specification': spec.digest if spec else 'none',
    })


def classification_recipe(relay) -> str:
    from . import semantic_publication_builder as builder
    return stable_digest({
        'instruction': builder._CLASSIFICATION_INSTRUCTION,
        'output': builder._ClassificationOutput.model_json_schema(),
        'generationBinding': relay.binding_id, 'model': relay.model_id,
        'contextWindowTokens': relay.context_window_tokens, 'maxOutputTokens': relay.max_output_tokens,
    })
