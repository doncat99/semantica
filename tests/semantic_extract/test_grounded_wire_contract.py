import pytest
from pydantic import ValidationError
from openai.lib._pydantic import to_strict_json_schema

from semantica.semantic_extract.schema import ExtractionSpecification
from semantica.semantic_extract.schemas import GroundedRelationsWire, grounded_entities_wire


def test_description_support_is_not_an_ontology_attribute():
    schema = grounded_entities_wire()
    profile = {'description': 'A medical instrument manufacturer',
               'evidence': 'Acme manufactures medical instruments.', 'evidence_occurrence': 0}
    entity = schema.model_validate({'entities': [{'text': 'Acme', 'label': 'ORG',
        'occurrence': 0, 'confidence': .9, 'attributes': {}, 'identity_profile': profile}]}).entities[0]
    assert entity.identity_profile.description == profile['description']
    assert entity.attributes.model_dump() == {}


def test_identity_profile_owner_must_be_source_grounded():
    from semantica.semantic_extract.schemas import IdentityProfileOut
    profile = {'description': 'Acme audit body', 'evidence': 'Acme Audit Committee meets.',
               'evidence_occurrence': 0, 'referent_kind': 'dependent_entity', 'owner': 'Acme'}
    assert IdentityProfileOut.model_validate(profile).owner == 'Acme'
    for changed in ({**profile, 'owner': 'Invented'}, {**profile, 'referent_kind': 'invented'}):
        with pytest.raises(ValidationError):
            IdentityProfileOut.model_validate(changed)


@pytest.mark.parametrize('facts', [dict(owner='Acme'), dict(referent_kind='report'),
                                  dict(instance='fiscal year 2023')])
def test_identifying_facts_do_not_require_invented_description(facts):
    from semantica.semantic_extract.schemas import IdentityProfileOut
    profile = dict(evidence='Acme Annual Report covers fiscal year 2023.', evidence_occurrence=0, **facts)
    assert IdentityProfileOut.model_validate(profile).description is None


@pytest.mark.parametrize('facts', [{}, dict(instance='2024'), dict(owner='Invented')])
def test_empty_or_unsupported_profile_is_rejected(facts):
    from semantica.semantic_extract.schemas import IdentityProfileOut
    with pytest.raises(ValidationError):
        IdentityProfileOut.model_validate(dict(evidence='Acme report for 2023.', evidence_occurrence=0, **facts))


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
