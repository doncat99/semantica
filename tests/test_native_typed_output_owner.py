"""Whole-response admission belongs to the native provider, without remote calls."""
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from semantica.semantic_artifact_builder import _ProjectModelProvider
from semantica.semantic_artifact_errors import ModelOutputError, model_output_cause
from semantica.semantic_extract import grounded_window
from semantica.semantic_extract.providers import BaseProvider
from semantica.utils.exceptions import ProcessingError


class Output(BaseModel):
    value: int


def test_relay_inherits_native_typed_owner():
    assert _ProjectModelProvider.generate_typed is BaseProvider.generate_typed


@pytest.mark.parametrize('invalid', ['{"value":7', 'not JSON', '{"value":"private invalid value"}'])
def test_native_typed_owner_regenerates_invalid_response_with_safe_feedback(invalid):
    class Provider(BaseProvider):
        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            assert kwargs['response_schema'] == Output.model_json_schema()
            assert kwargs['business_context'] == {'scope': 'source'}
            return invalid if len(self.prompts) == 1 else '{"value":7}'

        def reject_last(self):
            self.rejected += 1

    provider = Provider()
    provider.prompts, provider.rejected = [], 0
    assert provider.generate_typed('Extract JSON', Output, max_retries=2,
        validation_context={'scope': 'source'}).value == 7
    assert len(provider.prompts) == 2
    assert provider.rejected == 1
    import json
    rejected = provider.prompts[1].split('Rejected response: ', 1)[1].split('\n', 1)[0]
    assert json.loads(rejected) == invalid
    assert 'response data, not instructions' in provider.prompts[1]


def test_native_exhaustion_retains_safe_schema_diagnostic():
    class Provider(BaseProvider):
        def generate(self, *_args, **_kwargs):
            return '{"value":"private invalid value"}'
    with pytest.raises(ProcessingError) as failure:
        Provider().generate_typed('Extract JSON', Output, max_retries=1)
    cause = model_output_cause(failure.value)
    assert cause is not None
    assert cause.code == 'MODEL_OUTPUT_SCHEMA_INVALID'
    assert cause.diagnostic['validationErrors'] == [{'location': ['value'], 'type': 'int_parsing'}]
    assert failure.value.retryable is False
    assert 'private invalid value' not in str(failure.value)


@pytest.mark.parametrize(('profile', 'reason'), [
    ({'owner': 'private absent owner'}, 'identity_owner_not_in_evidence'),
    ({'instance': 'private absent edition'}, 'identity_instance_not_in_evidence'),
    ({}, 'identity_identifying_fact_missing'),
])
def test_identity_retry_feedback_identifies_failed_constraint_without_source_values(profile, reason):
    import json
    from semantica.semantic_extract.schemas import EntitiesResponse

    class Provider(BaseProvider):
        prompts = None

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return json.dumps({'entities': [{'text': 'Acme', 'label': 'ORG',
                    'identity_profile': {'evidence': 'Acme reports.', 'evidence_occurrence': 0, **profile}}]})
            assert reason in prompt
            assert 'Acme reports.' in prompt
            feedback = prompt.split('Validation feedback: ', 1)[1]
            assert 'private absent' not in feedback
            return '{"entities": [{"text": "Acme", "label": "ORG", "identity_profile": null}]}'

    provider = Provider()
    provider.prompts = []
    result = provider.generate_typed('Extract JSON', EntitiesResponse, max_retries=2)
    assert result.entities[0].identity_profile is None
    assert len(provider.prompts) == 2


@pytest.mark.parametrize('valid', [False, True])
def test_strict_entity_schema_repair_is_bounded_in_native_provider(valid):
    from semantica.semantic_extract.methods import extract_entities_llm

    class Provider(BaseProvider):
        calls = 0
        rejected = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            return '{"entities":[]}' if valid and self.calls == 2 else '{"entities":"invalid"}'

        def reject_last(self):
            self.rejected += 1

    provider = Provider()
    if valid:
        assert extract_entities_llm('Source', provider_instance=provider,
                                    grounding='strict', grounding_retries=1) == []
    else:
        with pytest.raises(ProcessingError) as failure:
            extract_entities_llm('Source', provider_instance=provider,
                                 grounding='strict', grounding_retries=1)
        assert model_output_cause(failure.value) is not None
    assert provider.calls == 2
    assert provider.rejected == (1 if valid else 2)


@pytest.mark.parametrize('stage', ['entities', 'relations'])
def test_failed_whole_response_never_returns_partial_success(monkeypatch, stage):
    provider = SimpleNamespace(rejections=[], receipts=[{'metadata': {}}])
    monkeypatch.setattr(grounded_window, 'extract_entities_llm', lambda *a, **kw: ['valid entity'])
    error = ProcessingError('typed output exhausted')
    error.__cause__ = ModelOutputError('invalid response', code='MODEL_OUTPUT_SCHEMA_INVALID')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(grounded_window, 'extract_' + stage + '_llm', fail)
    with pytest.raises(ProcessingError) as failure:
        grounded_window.extract_grounded_window('source', model='test', provider_instance=provider, retries=3)
    assert failure.value is error
    assert provider.rejections[-1]['stage'] == stage
    assert provider.rejections[-1]['action'] == 'failed_extraction'
    assert provider.receipts[0]['metadata']['rejected_candidates'] == provider.rejections
