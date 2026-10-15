import pytest

from semantica.semantic_extract.methods import _parse_grounded_relation_result
from semantica.semantic_extract.types import Entity
from semantica.utils.exceptions import ProcessingError


@pytest.mark.parametrize('stage', ['entities', 'relations'])
def test_output_limit_cannot_drop_caller_owned_structure(monkeypatch, stage):
    from semantica.semantic_extract import methods

    class Provider:
        def is_available(self):
            return True

        def generate_typed(self, *args, **kwargs):
            raise ProcessingError('max_tokens output limit')

    def forbidden_rechunk(*args, **kwargs):
        pytest.fail('caller-owned structure must not be discarded by rechunking')

    monkeypatch.setattr(methods, f'_extract_{stage}_chunked', forbidden_rechunk)
    kwargs = dict(provider_instance=Provider(), grounding='strict', silent_fail=False,
                  grounding_context=[{'ref': 'definition', 'quote': 'm is mass in kg.'}])
    if stage == 'relations':
        kwargs['entities'] = [Entity('m', 'variable', 0, 1, metadata={'mention_id': 'm'})]
    with pytest.raises(ProcessingError, match='max_tokens'):
        getattr(methods, f'extract_{stage}_llm')('m ' * 200, **kwargs)


def test_formula_condition_can_cite_a_separate_located_source_item():
    text = 'F = ma'
    entities = [Entity('F', 'formula', 0, 1, metadata={'mention_id': 'f'}),
                Entity('m', 'variable', 4, 5, metadata={'mention_id': 'm'})]
    context = [{'ref': '#/texts/4', 'quote': 'For constant mass, m is mass in kg.',
                'page': 2, 'source_kind': 'text'}]
    candidate = {'subject_id': 'f', 'object_id': 'm', 'predicate': 'uses_variable',
                 'evidence': text, 'evidence_occurrence': 0,
                 'qualifiers': {'polarity': 'positive', 'condition': 'constant mass', 'unit': 'kg'},
                 'supporting_refs': ['#/texts/4']}
    result = _parse_grounded_relation_result({'relations': [candidate]}, entities, text,
        'test', 'test', grounding_context=context)
    assert result[0].metadata['qualifiers']['condition'] == 'constant mass'
    assert result[0].metadata['supporting_refs'] == ['#/texts/4']
    candidate['supporting_refs'] = ['#/texts/99']
    with pytest.raises(ProcessingError, match='support'):
        _parse_grounded_relation_result({'relations': [candidate]}, entities, text,
            'test', 'test', grounding_context=context)


def test_uncited_context_cannot_authorize_a_qualifier():
    entities = [Entity('F', 'formula', 0, 1, metadata={'mention_id': 'f'}),
                Entity('m', 'variable', 4, 5, metadata={'mention_id': 'm'})]
    candidate = {'subject_id': 'f', 'object_id': 'm', 'predicate': 'uses_variable',
                 'evidence': 'F = ma', 'evidence_occurrence': 0,
                 'qualifiers': {'polarity': 'positive', 'unit': 'kg'}, 'supporting_refs': []}
    with pytest.raises(ProcessingError, match='exact evidence substring'):
        _parse_grounded_relation_result({'relations': [candidate]}, entities, 'F = ma',
            'test', 'test', grounding_context=[{'ref': '#/texts/4', 'quote': 'mass in kg'}])


def test_support_quotes_cannot_be_joined_to_invent_a_condition():
    entities = [Entity('F', 'formula', 0, 1, metadata={'mention_id': 'f'}),
                Entity('m', 'variable', 4, 5, metadata={'mention_id': 'm'})]
    candidate = {'subject_id': 'f', 'object_id': 'm', 'predicate': 'uses_variable',
                 'evidence': 'F = ma', 'evidence_occurrence': 0,
                 'qualifiers': {'polarity': 'positive', 'condition': 'constant mass'},
                 'supporting_refs': ['a', 'b']}
    with pytest.raises(ProcessingError, match='exact evidence substring'):
        _parse_grounded_relation_result({'relations': [candidate]}, entities, 'F = ma',
            'test', 'test', grounding_context=[{'ref': 'a', 'quote': 'constant'}, {'ref': 'b', 'quote': 'mass'}])


def test_document_context_reaches_both_native_prompts_without_leaking_provider_kwargs():
    from semantica.semantic_extract.grounded_window import extract_grounded_window
    from semantica.semantic_extract.schemas import GroundedEntitiesResponse, GroundedRelationsResponse

    class Provider:
        def __init__(self):
            self.prompts = []

        def is_available(self):
            return True

        def generate_typed(self, prompt, schema, **kwargs):
            assert 'grounding_context' not in kwargs
            self.prompts.append(prompt)
            if schema is GroundedEntitiesResponse:
                return schema.model_validate({'entities': [
                    {'text': 'F', 'label': 'formula', 'occurrence': 0},
                    {'text': 'm', 'label': 'variable', 'occurrence': 0}]})
            assert schema is GroundedRelationsResponse
            return schema.model_validate({'relations': [{
                'subject_id': 'mention:0', 'object_id': 'mention:1', 'predicate': 'uses_variable',
                'evidence': 'F = ma', 'evidence_occurrence': 0,
                'qualifiers': {'polarity': 'positive', 'unit': 'kg'}, 'supporting_refs': ['definition']}]})

    provider = Provider()
    _, relations, _ = extract_grounded_window('F = ma', model='test', provider_instance=provider,
        grounding_context=[{'ref': 'definition', 'quote': 'm is mass in kg.'}])
    assert len(provider.prompts) == 2
    assert all('m is mass in kg.' in prompt for prompt in provider.prompts)
    assert relations[0].metadata['qualifiers']['unit'] == 'kg'
