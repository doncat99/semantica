"""Transport failures cannot invalidate already paid successful responses."""
from types import SimpleNamespace

import pytest

from semantica import semantic_artifact_builder as builder


def test_failed_generate_does_not_reject_previous_response(monkeypatch):
    provider = builder._ProjectModelProvider(SimpleNamespace(model_id='test', max_output_tokens=100))
    provider.last_checkpoint_entry = ('entity-key', {'response': 'valid'})
    def fail(*args):
        raise builder.SemanticArtifactError('unavailable', retryable=True)
    monkeypatch.setattr(builder, '_relay_json', fail)
    rejected = []
    token = builder.active_checkpoint.set(SimpleNamespace(reject=lambda *args: rejected.append(args)))
    try:
        with pytest.raises(builder.SemanticArtifactError):
            provider.generate('relations')
        provider.reject_last()
    finally:
        builder.active_checkpoint.reset(token)
    assert provider.last_checkpoint_entry is None
    assert rejected == []
