"""Adopted embedding bodies must not survive into global publication stages."""
from types import SimpleNamespace
import weakref

import pytest

from semantica.semantic_publication_builder import _assemble_source_results, SemanticArtifactError


class Vector(list):
    pass


def test_assembled_source_retains_native_addresses_without_vector_bodies():
    vector = Vector([1.] * 8192)
    ref = weakref.ref(vector)
    binding = {'space': 'space', 'model': 'model', 'recipe': 'recipe'}
    ranges = [{'nativeRef': '#/document/text', 'start': 0, 'end': 3}]
    receipt = SimpleNamespace(_native_vector_ids=['vector:one'], _native_vector_path='/native/vector.sqlite',
                              _native_vector_binding=binding, _native_vector_ranges=ranges)
    result, embeddings, receipts = _assemble_source_results(
        [(0, 3, 'Ada')], [({'entities': [], 'relations': []}, [], False)], [([vector], receipt)])
    assert ref() is not None
    del vector
    del result
    assert ref() is None, 'global source result must release the adopted float body'
    assert embeddings == [{'start_char': 0, 'end_char': 3, 'vector_id': 'vector:one',
                           'vector_store_path': '/native/vector.sqlite',
                           'native_binding': binding, 'native_ranges': ranges}]
    assert receipts == [receipt]


def test_dimension_validation_survives_releasing_vector_bodies():
    with pytest.raises(SemanticArtifactError, match='inconsistent dimensions'):
        _assemble_source_results([(0, 1, 'a'), (1, 2, 'b')],
            [({'entities': [], 'relations': []}, [], False)] * 2,
            [([[1.]], SimpleNamespace()), ([[1., 2.]], SimpleNamespace())])
