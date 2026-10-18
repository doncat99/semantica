"""Exercise the production project queue with one in-memory source."""
from types import SimpleNamespace

from semantica.semantic_artifact_builder import _extract_project_sources


def extract_source(text, model, embedding, *, extraction_spec=None, progress=None,
                   parallelism=1, document=None):
    request = SimpleNamespace(parallelism=parallelism,
        recipe=SimpleNamespace(extraction_spec=extraction_spec),
        relays={"model": model, "embedding": embedding})
    source = SimpleNamespace(source_id="source")
    return _extract_project_sources([(source, False, (text, document or {}))], request, progress)[0]


def stub_native_provider(monkeypatch, respond):
    """Stub only generation; retain native schemas, grounding and extraction cache."""
    from semantica import semantic_artifact_builder as pipeline
    from semantica.semantic_artifact_schema import ModelReceipt

    class Provider:
        def __init__(self):
            self.receipts, self.rejections = [], []

        def is_available(self):
            return True

        def generate_typed(self, prompt, schema, **kwargs):
            stage = kwargs['extraction_stage']
            result = respond(stage, prompt)
            digest = pipeline.stable_digest([stage, prompt, result])
            self.receipts.append(ModelReceipt(id='receipt:' + digest, operation='structured_extraction',
                provider='test', model='test', input_digest=pipeline.stable_digest(prompt),
                output_digest=pipeline.stable_digest(result), metadata={'extraction_stage': stage}))
            return schema.model_validate(result)

    monkeypatch.setattr(pipeline, '_project_model_provider', lambda _: Provider())
