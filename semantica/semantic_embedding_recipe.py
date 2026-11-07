"""Identity of the actual embedding producer, independent of publication code."""
from importlib.metadata import version
from inspect import getsource
from functools import lru_cache

from .semantic_artifact_schema import stable_digest


@lru_cache(maxsize=1)
def _producer_digest(request, validation, encoding):
    return stable_digest({
        'request': getsource(request),
        'validation': getsource(validation),
        'encoding': getsource(encoding),
        'numpy': version('numpy'),
    })


def embedding_recipe(relay) -> str:
    """Return the current vector recipe for runtime and offline identity migration.

    Only the actual request/vector conversion and float32 encoder participate.
    Input text and source addresses are bound separately by the native operation.
    """
    from .semantic_publication_builder import _embedding_payload, _embedding_values
    from .vector_store.sqlite_vec_store import SQLiteVecStore

    return stable_digest({
        'binding': relay.binding_id,
        'model': relay.model_id,
        'parameters': {},
        'producer': _producer_digest(_embedding_payload, _embedding_values, SQLiteVecStore.pack_embedding_vectors),
    })
