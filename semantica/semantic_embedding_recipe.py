"""Embedding identity follows the model space and numeric contract."""
from .semantic_artifact_schema import stable_digest


def embedding_recipe(relay) -> str:
    return stable_digest({
        'binding': relay.binding_id,
        'model': relay.model_id,
        'parameters': {},
        'encoding': 'float32',
    })
