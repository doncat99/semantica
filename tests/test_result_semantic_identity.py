"""Implementation bytes never decide whether committed business results can be reused."""
from types import SimpleNamespace
from pathlib import Path


def relay(**changes):
    return SimpleNamespace(**(dict(binding_id='binding', model_id='model', context_window_tokens=12000, max_output_tokens=2000) | changes))


def test_paid_recipes_do_not_inspect_executable_source(monkeypatch):
    from semantica import semantic_extraction_recipe as extraction, semantic_embedding_recipe as embedding
    def forbidden(*_):
        raise AssertionError('Executable source used as a business input')
    for module in (extraction, embedding):
        monkeypatch.setattr(module, 'getsource', forbidden, raising=False)
    request = SimpleNamespace(relays={'model': relay()}, recipe=SimpleNamespace(extraction_spec=None))
    assert extraction.extraction_recipe(request)
    assert extraction.classification_recipe(relay())
    assert embedding.embedding_recipe(relay())


def test_parser_identity_does_not_read_implementation(monkeypatch):
    from semantica import source
    def forbidden(*_):
        raise AssertionError('Parser implementation used as a business input')
    monkeypatch.setattr(source, '_processing_implementation', forbidden, raising=False)
    args = dict(mime_type='text/plain', force_ocr=False, document_processing={'mode': 'local'})
    original = source.source_processing_revision(Path('input.txt'), **args)
    assert source.source_processing_revision(Path('renamed.txt'), **args) == original
    assert source.source_processing_revision(Path('input.txt'), **(args | {'force_ocr': True})) != original


def test_real_model_prompt_and_schema_changes_change_paid_identity(monkeypatch):
    from semantica import semantic_extraction_recipe as extraction, semantic_embedding_recipe as embedding
    from semantica import semantic_publication_builder as builder
    request = SimpleNamespace(relays={'model': relay()}, recipe=SimpleNamespace(extraction_spec=None))
    original = extraction.extraction_recipe(request)
    request.relays['model'] = relay(model_id='different-model')
    assert extraction.extraction_recipe(request) != original
    assert embedding.embedding_recipe(relay()) != embedding.embedding_recipe(relay(model_id='different-model'))
    original_classification = extraction.classification_recipe(relay())
    monkeypatch.setattr(builder, '_CLASSIFICATION_INSTRUCTION', builder._CLASSIFICATION_INSTRUCTION + '\nDifferent semantic instruction')
    assert extraction.classification_recipe(relay()) != original_classification
    original_schema = extraction.classification_recipe(relay())
    monkeypatch.setattr(builder._ClassificationOutput, 'model_json_schema', lambda: {'type': 'object', 'required': ['different']})
    assert extraction.classification_recipe(relay()) != original_schema
