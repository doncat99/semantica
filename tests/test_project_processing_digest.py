"""Only actual semantic inputs determine paid result identities."""
import pytest


def extraction_request():
    from types import SimpleNamespace
    return SimpleNamespace(
        recipe=SimpleNamespace(extraction_spec=None, classification_profile='classification-a',
                               id='publication-a', version='1'),
        relays={'model': SimpleNamespace(binding_id='generation-binding', model_id='generation-model',
                context_window_tokens=32000, max_output_tokens=4000),
                'embedding': SimpleNamespace(binding_id='embedding-binding', model_id='embedding-model')})


def test_extraction_recipe_ignores_publication_and_other_model_owners(monkeypatch):
    from semantica import semantic_publication_builder as builder
    request = extraction_request()
    expected = builder._extraction_recipe(request)
    request.recipe.classification_profile = 'classification-b'
    request.recipe.id = 'publication-b'
    request.recipe.version = '2'
    request.relays['embedding'].model_id = 'different-embedding'
    monkeypatch.setattr(builder, 'PROJECT_PROCESSING_DIGEST', 'query-reader-receipt-change', raising=False)
    monkeypatch.setattr(builder, '_product_json', lambda *args: 'different-classification')
    monkeypatch.setattr(builder, '_request_embedding', lambda *args: 'different-embedding')
    from semantica.semantic_extract.cache import ExtractionCache
    monkeypatch.setattr(ExtractionCache, 'get_accepted', lambda *args, **kwargs: None)
    assert builder._extraction_recipe(request) == expected


@pytest.mark.parametrize('field,value', [('binding_id', 'other-binding'), ('model_id', 'other-model'),
    ('context_window_tokens', 64000), ('max_output_tokens', 8000)])
def test_extraction_recipe_binds_actual_generation_parameters(field, value):
    from semantica.semantic_publication_builder import _extraction_recipe
    request = extraction_request()
    expected = _extraction_recipe(request)
    setattr(request.relays['model'], field, value)
    assert _extraction_recipe(request) != expected


def test_extraction_recipe_binds_specification():
    from types import SimpleNamespace
    from semantica.semantic_publication_builder import _extraction_recipe
    request = extraction_request()
    expected = _extraction_recipe(request)
    from semantica.semantic_extract.schema import ExtractionSpecification
    request.recipe.extraction_spec = ExtractionSpecification(id='actual', version='1', entity_types=[{'name':'ORG', 'description':'Organization'}])
    assert _extraction_recipe(request) != expected


@pytest.mark.parametrize('owner,symbol', [('methods', 'extract_entities_llm'),
    ('methods', 'extract_relations_llm'),
    ('methods', '_exact_occurrence'), ('methods', '_grounded_qualifiers'),
    ('methods', '_parse_grounded_relation_result')])
def test_extraction_recipe_ignores_producer_implementation(monkeypatch, owner, symbol):
    from semantica.semantic_publication_builder import _extraction_recipe
    import importlib
    module = importlib.import_module(f'semantica.semantic_extract.{owner}')
    request = extraction_request()
    expected = _extraction_recipe(request)
    def changed_semantic_producer(*args, **kwargs):
        return 'changed semantic production'
    monkeypatch.setattr(module, symbol, changed_semantic_producer)
    assert _extraction_recipe(request) == expected


def test_extraction_recipe_tracks_wire_validation_and_generation_payload(monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_extract import schemas
    request = extraction_request()
    expected = builder._extraction_recipe(request)
    def changed_payload(*args, **kwargs):
        return {'temperature': 1}
    monkeypatch.setattr(builder, '_generation_payload', changed_payload)
    assert builder._extraction_recipe(request) == expected
    monkeypatch.undo()
    def changed_qualifier_validation(value):
        return value
    monkeypatch.setattr(schemas, 'validate_fact_qualifiers', changed_qualifier_validation)
    assert builder._extraction_recipe(request) == expected


def test_classification_recipe_ignores_publication_and_other_paid_producers(monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_extract import methods
    relay = extraction_request().relays['model']
    expected = builder._classification_recipe(relay)
    monkeypatch.setattr(builder, 'PROJECT_PROCESSING_DIGEST', 'reader-query-publication-change', raising=False)
    monkeypatch.setattr(builder, '_request_embedding', lambda *args: [])
    monkeypatch.setattr(methods, 'extract_entities_llm', lambda *args: [])
    assert builder._classification_recipe(relay) == expected


@pytest.mark.parametrize('field,value', [('binding_id', 'other-binding'), ('model_id', 'other-model'),
    ('context_window_tokens', 64000), ('max_output_tokens', 8000)])
def test_classification_recipe_binds_actual_model_parameters(field, value):
    from semantica.semantic_publication_builder import _classification_recipe
    relay = extraction_request().relays['model']
    expected = _classification_recipe(relay)
    setattr(relay, field, value)
    assert _classification_recipe(relay) != expected


def test_classification_recipe_tracks_prompt_generation_and_validator(monkeypatch):
    from semantica import semantic_publication_builder as builder
    relay = extraction_request().relays['model']
    expected = builder._classification_recipe(relay)
    monkeypatch.setattr(builder, '_CLASSIFICATION_INSTRUCTION', 'different semantic instruction')
    assert builder._classification_recipe(relay) != expected
    monkeypatch.undo()
    def changed_generation(*args, **kwargs):
        return 'changed semantic generation'
    monkeypatch.setattr(builder, '_product_json', changed_generation)
    assert builder._classification_recipe(relay) == expected
    monkeypatch.undo()
    monkeypatch.setattr(builder, '_ClassificationOutput', builder._ProductOutput)
    assert builder._classification_recipe(relay) != expected


@pytest.mark.parametrize('recipe', ['extraction', 'classification'])
def test_paid_recipe_ignores_transport_receipt_accounting(monkeypatch, recipe):
    from semantica import semantic_publication_builder as builder
    request = extraction_request()
    current = (lambda: builder._extraction_recipe(request)) if recipe == 'extraction' else (
        lambda: builder._classification_recipe(request.relays['model']))
    expected = current()
    monkeypatch.setattr(builder._ProjectModelProvider, 'generate', lambda *args, **kwargs: 'audit-only change')
    assert current() == expected


@pytest.mark.parametrize('recipe', ['extraction', 'classification'])
def test_paid_recipe_ignores_response_validator_implementation(monkeypatch, recipe):
    from semantica import semantic_publication_builder as builder
    request = extraction_request()
    current = (lambda: builder._extraction_recipe(request)) if recipe == 'extraction' else (
        lambda: builder._classification_recipe(request.relays['model']))
    expected = current()
    def changed_content(*args):
        return 'changed response acceptance'
    monkeypatch.setattr(builder, '_generation_content', changed_content)
    assert current() == expected


@pytest.mark.parametrize('recipe,symbol', [
    ('extraction', '_extraction_context_batches'),
    ('extraction', '_context_size'),
    ('extraction', '_request_size'),
    ('extraction', '_input_token_budget'),
    ('classification', '_context_batches'),
    ('classification', '_context_size'),
    ('classification', '_request_size'),
    ('classification', '_input_token_budget'),
])
def test_paid_recipe_ignores_batch_admission_implementation(monkeypatch, recipe, symbol):
    """Exact admitted window/context is already part of the operation binding."""
    from semantica import semantic_publication_builder as builder
    request = extraction_request()
    current = (lambda: builder._extraction_recipe(request)) if recipe == 'extraction' else (
        lambda: builder._classification_recipe(request.relays['model']))
    expected = current()
    def faster_admission(*args, **kwargs):
        raise AssertionError('Recipe hashing must not execute admission')
    monkeypatch.setattr(builder, symbol, faster_admission)
    assert current() == expected


def test_extraction_recipe_tracks_actual_prompt_and_output_contract(monkeypatch):
    from semantica.semantic_extraction_recipe import extraction_recipe
    from semantica.semantic_extract import methods
    request = extraction_request()
    before = extraction_recipe(request)
    prompt = methods.entity_extraction_prompt
    monkeypatch.setattr(methods, 'entity_extraction_prompt', lambda *a, **kw: prompt(*a, **kw) + '\nActual new instruction')
    assert extraction_recipe(request) != before
