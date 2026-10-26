"""Model capacity comes from the admitted relay, not a global byte ceiling."""
import json
from types import SimpleNamespace

import pytest
from semantica import semantic_artifact_builder as builder


def relay(context=500_000, output=32768):
    return SimpleNamespace(authorization_env='TEST_CAPACITY_TOKEN', base_url='http://localhost/model',
                          context_window_tokens=context, max_output_tokens=output)


def test_large_valid_request_passes_old_byte_ceiling(monkeypatch):
    monkeypatch.setenv('TEST_CAPACITY_TOKEN', 'offline')
    class Sent(Exception): pass
    def send(request, **kwargs):
        assert len(request.data) > 80_000
        raise Sent()
    monkeypatch.setattr(builder.urllib.request, 'urlopen', send)
    with pytest.raises(Sent):
        builder._relay_uncached(relay(), {'messages': [{'role': 'user', 'content': '汉' * 30_000}]},
                                'structured_extraction', None, None)


def test_output_reserve_and_complete_payload_are_counted_before_send(monkeypatch):
    monkeypatch.setenv('TEST_CAPACITY_TOKEN', 'offline')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('must not send'))
    payload = {'messages': [{'role': 'user', 'content': '汉' * 200}],
               'response_format': {'schema': {'description': 'schema' * 100}}}
    with pytest.raises(builder.SemanticArtifactError) as failure:
        builder._relay_uncached(relay(2000, 1000), payload, 'structured_extraction', None, None)
    assert failure.value.code == 'MODEL_CONTEXT_BUDGET_EXCEEDED'
    assert failure.value.diagnostic['inputTokenBudget'] == 1000
    assert failure.value.diagnostic['upstreamRequestSent'] is False
    assert failure.value.diagnostic['tokenCounting'] == 'utf8-byte-upper-bound'


def test_embedding_is_not_subject_to_generation_output_budget(monkeypatch):
    monkeypatch.setenv('TEST_CAPACITY_TOKEN', 'offline')
    class Sent(Exception): pass
    def send(*args, **kwargs): raise Sent()
    monkeypatch.setattr(builder.urllib.request, 'urlopen', send)
    with pytest.raises(Sent):
        builder._relay_uncached(SimpleNamespace(authorization_env='TEST_CAPACITY_TOKEN', base_url='http://localhost/embed'),
                                {'input': ['x' * 81_000]}, 'embedding', None, None)
