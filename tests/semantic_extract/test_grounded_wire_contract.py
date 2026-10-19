import pytest
from pydantic import ValidationError
from openai.lib._pydantic import to_strict_json_schema

from semantica.semantic_extract.schema import ExtractionSpecification
from semantica.semantic_extract.schemas import GroundedRelationsWire, grounded_entities_wire


def assert_closed(node):
    if isinstance(node, dict):
        if node.get('type') == 'object':
            assert node.get('additionalProperties') is False
            assert set(node.get('required', [])) == set(node.get('properties', {}))
        for value in node.values():
            assert_closed(value)
    elif isinstance(node, list):
        for value in node:
            assert_closed(value)


def test_grounded_wire_is_closed_and_uses_native_specification():
    specification = ExtractionSpecification.model_validate({'id': 'native', 'version': '1',
        'entity_types': [{'name': 'Person', 'description': 'Person', 'attributes': {
            'age': {'type': 'integer', 'description': 'Age'},
            'roles': {'type': 'string_list', 'description': 'Roles', 'required': True}}},
            {'name': 'Organization', 'description': 'Organization'}]})
    for schema in (grounded_entities_wire(), grounded_entities_wire(specification), GroundedRelationsWire):
        assert_closed(to_strict_json_schema(schema))
    schema = grounded_entities_wire(specification)
    entity = {'text': 'Ada', 'label': 'Person', 'occurrence': 0, 'confidence': 0.9,
              'attributes': {'age': None, 'roles': ['Researcher']}}
    assert schema.model_validate({'entities': [entity]}).entities[0].attributes.age is None
    for changed in ({**entity, 'invented': True}, {**entity, 'label': 'Unknown'},
                    {**entity, 'attributes': {}}, {**entity, 'occurrence': -1},
                    {**entity, 'attributes': {'roles': ['Researcher'], 'website': 'invented'}}):
        with pytest.raises(ValidationError):
            schema.model_validate({'entities': [changed]})
