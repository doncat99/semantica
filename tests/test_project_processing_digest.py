"""Processing identities follow native implementation bytes, never checkout paths."""
from pathlib import Path

import pytest

from semantica.semantic_publication_builder import _project_processing_digest


@pytest.mark.parametrize('owner', ['triplet_store', 'pipeline', 'conflicts', 'vector_store', 'explorer', 'utils'])
def test_native_processing_owner_change_invalidates_recipe(tmp_path, owner):
    module = tmp_path / owner / 'native_owner.py'
    module.parent.mkdir()
    module.write_text('CURRENT = 1\n')
    before = _project_processing_digest(tmp_path)
    module.write_text('CURRENT = 2\n')
    assert _project_processing_digest(tmp_path) != before


def test_processing_digest_is_relocation_invariant_and_ignores_nonruntime_files(tmp_path):
    roots = [tmp_path / 'one', tmp_path / 'other' / 'checkout']
    for root in roots:
        (root / 'triplet_store').mkdir(parents=True)
        (root / 'semantic_publication_builder.py').write_text('OWNER = True\n')
        (root / 'triplet_store' / 'publication_records.py').write_text('SCHEMA = 3\n')
    expected = _project_processing_digest(roots[0])
    assert _project_processing_digest(roots[1]) == expected
    for relative in ['tests/test_owner.py', 'docs/design.py', 'triplet_store/__pycache__/owner.pyc', 'triplet_store/notes.md']:
        file = roots[1] / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('irrelevant content')
    assert _project_processing_digest(roots[1]) == expected


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
    monkeypatch.setattr(builder, 'PROJECT_PROCESSING_DIGEST', 'query-reader-receipt-change')
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
    request.recipe.extraction_spec = SimpleNamespace(digest='actual-specification')
    assert _extraction_recipe(request) != expected


@pytest.mark.parametrize('owner,symbol', [('methods', 'extract_entities_llm'),
    ('methods', 'extract_relations_llm'), ('methods', '_prompt_grounding_context'),
    ('methods', '_exact_occurrence'), ('methods', '_grounded_qualifiers'),
    ('methods', '_parse_grounded_relation_result')])
def test_extraction_recipe_tracks_prompt_and_grounding_producers(monkeypatch, owner, symbol):
    from semantica.semantic_publication_builder import _extraction_recipe
    import importlib
    module = importlib.import_module(f'semantica.semantic_extract.{owner}')
    request = extraction_request()
    expected = _extraction_recipe(request)
    def changed_semantic_producer(*args, **kwargs):
        return 'changed semantic production'
    monkeypatch.setattr(module, symbol, changed_semantic_producer)
    assert _extraction_recipe(request) != expected


def test_extraction_recipe_tracks_wire_validation_and_generation_payload(monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_extract import schemas
    request = extraction_request()
    expected = builder._extraction_recipe(request)
    def changed_payload(*args, **kwargs):
        return {'temperature': 1}
    monkeypatch.setattr(builder, '_generation_payload', changed_payload)
    assert builder._extraction_recipe(request) != expected
    monkeypatch.undo()
    def changed_qualifier_validation(value):
        return value
    monkeypatch.setattr(schemas, 'validate_fact_qualifiers', changed_qualifier_validation)
    assert builder._extraction_recipe(request) != expected


def test_classification_recipe_ignores_publication_and_other_paid_producers(monkeypatch):
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_extract import methods
    relay = extraction_request().relays['model']
    expected = builder._classification_recipe(relay)
    monkeypatch.setattr(builder, 'PROJECT_PROCESSING_DIGEST', 'reader-query-publication-change')
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
    assert builder._classification_recipe(relay) != expected
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
def test_paid_recipe_tracks_admitted_response_content(monkeypatch, recipe):
    from semantica import semantic_publication_builder as builder
    request = extraction_request()
    current = (lambda: builder._extraction_recipe(request)) if recipe == 'extraction' else (
        lambda: builder._classification_recipe(request.relays['model']))
    expected = current()
    def changed_content(*args):
        return 'changed response acceptance'
    monkeypatch.setattr(builder, '_generation_content', changed_content)
    assert current() != expected
