import pytest
from pydantic import ValidationError

from semantica.semantic_extract.schemas import TripletOut, TripletsResponse


def test_triplet_generation_has_no_unbounded_model_provenance():
    to_strict_json_schema = pytest.importorskip('openai.lib._pydantic').to_strict_json_schema
    wire = to_strict_json_schema(TripletsResponse)
    item = wire['$defs']['TripletOut']
    assert 'metadata' not in item['properties']
    assert set(item['required']) == {'subject', 'predicate', 'object', 'confidence'}
    assert item['additionalProperties'] is False
    assert TripletOut(subject='a', predicate='b', object='c', confidence=.9).metadata == {}


@pytest.mark.parametrize('confidence', ['high', '0.9', -1, 2, None, True])
def test_triplet_confidence_is_not_repaired(confidence):
    with pytest.raises(ValidationError):
        TripletOut.model_validate(dict(subject='a', predicate='b', object='c', confidence=confidence), strict=True)
