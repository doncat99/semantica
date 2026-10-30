from unittest.mock import patch

import pytest

from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.semantic_extract.methods import extract_entities_llm, extract_relations_llm
from semantica.semantic_extract.schemas import (
    EntitiesResponse,
    EntityOut,
    GroundedEntitiesResponse,
    GroundedRelationsResponse,
    RelationOut,
    RelationsResponse,
)
from semantica.semantic_extract.schema import ExtractionSpecification
from semantica.utils.exceptions import ProcessingError


class TypedProvider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []
        self.schemas = []
        self.kwargs = []

    def is_available(self):
        return True

    def generate_typed(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        self.schemas.append(schema)
        self.kwargs.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.parametrize('fact', [dict(owner='Acme'), dict(instance='2025'), {}])
def test_invalid_identity_fact_is_rejected_without_losing_grounded_mentions(fact):
    import json
    from semantica.semantic_extract.providers import BaseProvider

    text = 'Our ESG Committee reviews our ESG Report.'

    class Provider(BaseProvider):
        calls = 0

        def generate(self, prompt, **kwargs):
            self.calls += 1
            return json.dumps({'entities': [dict(text=name, label='ORG', occurrence=0,
                confidence=.9, attributes={}, identity_profile=dict(
                    evidence=text, evidence_occurrence=0, **fact))
                for name in ('ESG Committee', 'ESG Report')]})

    provider, receipts = Provider(), []
    entities = extract_entities_llm(text, provider='bifrost', provider_instance=provider,
        grounding='strict', rejection_receipts=receipts)
    assert [entity.text for entity in entities] == ['ESG Committee', 'ESG Report']
    assert all('identity_profile' not in entity.metadata for entity in entities)
    assert len(receipts) == 2
    assert all(receipt['kind'] == 'grounding' for receipt in receipts)
    assert provider.calls == 1


def test_grounded_description_has_separate_source_quote_and_no_extra_model_call():
    text = 'Acme manufactures medical instruments.'
    from semantica.semantic_extract.schemas import grounded_entities_wire
    schema = grounded_entities_wire()
    response = schema.model_validate({'entities': [{'text': 'Acme', 'label': 'ORG',
        'occurrence': 0, 'confidence': .9, 'attributes': {}, 'identity_profile': {
            'description': 'A medical instrument manufacturer', 'evidence': text,
            'evidence_occurrence': 0}}]})
    provider = TypedProvider(response)
    entity, = extract_entities_llm(text, provider='bifrost', provider_instance=provider, grounding='strict')
    assert entity.attributes == {}
    assert entity.metadata['identity_profile']['description'] == 'A medical instrument manufacturer'
    assert entity.metadata['identity_profile']['evidence_start'] == 0
    assert entity.metadata['identity_profile']['evidence_end'] == len(text)
    assert len(provider.prompts) == 1


@pytest.mark.parametrize('name,text,fact', [
    ('Audit Committee', 'Acme Audit Committee reviewed the report.',
     dict(owner='Acme', referent_kind='dependent_entity')),
    ('Annual Report', 'Acme Annual Report covers fiscal year 2024.',
     dict(instance='2024', referent_kind='report')),
    ('Sustainability Accounting Standards Board',
     'Sustainability Accounting Standards Board is a standard-setting institution.',
     dict(referent_kind='institution'))])
def test_independent_identity_fact_survives_native_extraction_without_description(name, text, fact):
    from semantica.semantic_extract.schemas import grounded_entities_wire
    schema = grounded_entities_wire()
    response = schema.model_validate({'entities': [dict(text=name, label='ORG',
        occurrence=0, confidence=.9, attributes={}, identity_profile=dict(
            description=None, evidence=text, evidence_occurrence=0, **fact))]})
    provider = TypedProvider(response)
    entity, = extract_entities_llm(text, provider='bifrost', provider_instance=provider, grounding='strict')
    profile = entity.metadata['identity_profile']
    assert profile['description'] is None
    assert all(profile[key] == value for key, value in fact.items())
    assert text[profile['evidence_start']:profile['evidence_end']] == text
    assert len(provider.prompts) == 1


@pytest.mark.parametrize('quote', ['Acme invented a warp drive.', 'Another manufactures medical instruments.',
                                  'Acme publishes newspapers.'])
def test_invalid_profile_keeps_the_located_mention_without_fabricated_support(quote):
    text = 'Acme reports. Another manufactures medical instruments. Acme publishes newspapers.'
    provider = TypedProvider(EntitiesResponse(entities=[EntityOut(text='Acme', label='ORG', occurrence=0,
        identity_profile={'description': 'A manufacturer', 'evidence': quote, 'evidence_occurrence': 0})]))
    receipts = []
    entity, = extract_entities_llm(text, provider='bifrost', provider_instance=provider,
        grounding='strict', rejection_receipts=receipts)
    assert 'identity_profile' not in entity.metadata
    assert receipts[0]['kind'] == 'grounding'
    assert len(provider.prompts) == 1


def test_native_grounded_extractors_apply_typed_spec_and_examples(monkeypatch):
    from semantica.semantic_extract import methods
    def forbidden_cache(*args, **kwargs):
        pytest.fail("provider-instance extraction must use its owner's checkpoint, not global cache")
    monkeypatch.setattr(methods._result_cache, "get", forbidden_cache)
    monkeypatch.setattr(methods._result_cache, "set", forbidden_cache)
    text = "Casting uses steel with density 7.85."
    specification = ExtractionSpecification.model_validate({
        "id": "manufacturing", "version": "1",
        "entity_types": [
            {"name": "Process", "description": "A manufacturing process"},
            {"name": "Material", "description": "A material", "attributes": {
                "density": {"type": "number", "description": "Density stated in source", "required": True},
            }},
        ],
        "relation_types": [{"name": "uses", "description": "Process uses material", "domain": ["Process"], "range": ["Material"]}],
        "examples": [{"text": "Forging uses iron.", "entities": [{"text": "Forging", "label": "Process"}, {"text": "iron", "label": "Material", "attributes": {"density": 7.87}}], "relations": [{"subject": "Forging", "predicate": "uses", "object": "iron"}]}],
    })
    provider = TypedProvider(
        EntitiesResponse(entities=[
            EntityOut(text="Casting", label="Process", occurrence=0),
            EntityOut(text="steel", label="Material", occurrence=0, attributes={"density": 7.85}),
        ]),
        RelationsResponse(relations=[RelationOut(subject="Casting", subject_id="mention:0", predicate="uses", object="steel", object_id="mention:1", evidence=text, evidence_occurrence=0, qualifiers={"polarity": "positive"})]),
    )

    entities = extract_entities_llm(text, provider="bifrost", provider_instance=provider, grounding="strict", extraction_spec=specification)
    relations = extract_relations_llm(text, entities, provider="bifrost", provider_instance=provider, grounding="strict", extraction_spec=specification)

    assert entities[1].attributes == {"density": 7.85}
    assert [relation.predicate for relation in relations] == ["uses"]
    assert "manufacturing process" in provider.prompts[0]
    assert "Forging uses iron" in provider.prompts[0]
    assert "Process uses material" in provider.prompts[1]


def test_native_grounded_extraction_rejects_invalid_attribute_candidate():
    text = "Blue whale is endangered."
    specification = ExtractionSpecification.model_validate({
        "id": "conservation", "version": "1",
        "entity_types": [{"name": "Species", "description": "A biological species", "attributes": {
            "endangered": {"type": "boolean", "description": "Whether source states endangered", "required": True},
        }}],
    })
    provider = TypedProvider(
        EntitiesResponse(entities=[EntityOut(text="Blue whale", label="Species", occurrence=0, attributes={"endangered": "yes"})]),
        EntitiesResponse(entities=[EntityOut(text="Blue whale", label="Species", occurrence=0, attributes={"endangered": True})]),
    )

    rejected = []
    entities = extract_entities_llm(text, provider="bifrost", provider_instance=provider, grounding="strict", grounding_retries=1, extraction_spec=specification, rejection_receipts=rejected)

    assert entities == []
    assert len(provider.prompts) == 1
    assert rejected[0]["kind"] == "schema"
    assert "invalid" in rejected[0]["reason"]


def test_grounded_native_extractors_preserve_mentions_evidence_and_qualifiers():
    text = "Reflective roofs do not directly shade pedestrians. Reflective roofs reduce heat."
    provider = TypedProvider(
        EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
            EntityOut(text="Reflective roofs", label="measure", occurrence=1),
        ]),
        RelationsResponse(relations=[RelationOut(
            subject="Reflective roofs",
            subject_id="mention:0",
            predicate="shades",
            object="pedestrians",
            object_id="mention:1",
            evidence="Reflective roofs do not directly shade pedestrians.",
            evidence_occurrence=0,
            qualifiers={"polarity": "negative", "condition": "directly"},
        )]),
    )

    with patch("semantica.semantic_extract.methods.create_provider") as create_provider:
        entities = extract_entities_llm(
            text, provider="bifrost", provider_instance=provider, grounding="strict"
        )
        relations = extract_relations_llm(
            text,
            entities,
            provider="bifrost",
            provider_instance=provider,
            grounding="strict",
        )

    create_provider.assert_not_called()
    assert [(item.start_char, item.end_char) for item in entities] == [(0, 16), (39, 50), (52, 68)]
    assert [item.metadata["mention_id"] for item in entities] == ["mention:0", "mention:1", "mention:2"]
    assert relations[0].subject is entities[0]
    assert relations[0].object is entities[1]
    assert relations[0].context == "Reflective roofs do not directly shade pedestrians."
    assert relations[0].metadata["qualifiers"] == {"polarity": "negative", "condition": "directly"}
    assert relations[0].metadata["evidence_start"] == 0
    assert "subject_id" in provider.prompts[1]
    assert "exact contiguous substring" in provider.prompts[1]
    assert "exact, case-sensitive" in provider.prompts[1]
    assert "entity-list" in provider.prompts[0]
    assert "table-of-contents" in provider.prompts[0]
    assert "navigation labels" in provider.prompts[0]
    assert provider.schemas[0].__name__ == "GroundedEntitiesWire"
    assert provider.schemas[1].__name__ == "GroundedRelationsWire"


def test_grounded_native_relation_extraction_rejects_ungrounded_qualifier():
    text = "Reflective roofs do not shade pedestrians."
    provider = TypedProvider(
        RelationsResponse(relations=[RelationOut(
            subject="Reflective roofs",
            subject_id="mention:0",
            predicate="shades",
            object="pedestrians",
            object_id="mention:1",
            evidence=text,
            evidence_occurrence=0,
            qualifiers={"polarity": "negative", "condition": "in summer"},
        )]),
    )
    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])),
        grounding="strict",
    )

    relations = extract_relations_llm(
        text,
        entities,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=0,
    )
    assert relations == []


def test_grounded_native_extractors_retry_invalid_grounding():
    text = "Exposure affects outcomes."
    entity_provider = TypedProvider(
        EntitiesResponse(entities=[EntityOut(text="exposure variables", label="concept", occurrence=0)]),
        EntitiesResponse(entities=[
            EntityOut(text="Exposure", label="concept", occurrence=0),
            EntityOut(text="outcomes", label="concept", occurrence=0),
        ]),
    )
    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=entity_provider,
        grounding="strict",
        grounding_retries=1,
    )
    assert [entity.text for entity in entities] == ["Exposure", "outcomes"]
    assert "outside source text" in entity_provider.prompts[1]

    relation_provider = TypedProvider(
        RelationsResponse(relations=[RelationOut(
            subject="Exposure", subject_id="invented", predicate="affects",
            object="outcomes", object_id="mention:1", evidence=text,
            evidence_occurrence=0, qualifiers={"polarity": "positive"},
        )]),
        RelationsResponse(relations=[RelationOut(
            subject="Exposure", subject_id="mention:0", predicate="affects",
            object="outcomes", object_id="mention:1", evidence=text,
            evidence_occurrence=0, qualifiers={"polarity": "positive"},
        )]),
    )
    relations = extract_relations_llm(
        text,
        entities,
        provider="bifrost",
        provider_instance=relation_provider,
        grounding="strict",
        grounding_retries=1,
    )
    assert [relation.predicate for relation in relations] == ["affects"]
    assert "does not reference an entity mention" in relation_provider.prompts[1]
    assert "candidate_index=0" in relation_provider.prompts[1]
    assert "Previous grounded JSON" not in relation_provider.prompts[1]
    assert relation_provider.prompts[0] in relation_provider.prompts[1]


def test_unique_grounded_quote_uses_its_deterministic_occurrence():
    text = "Alpha references Beta."
    provider = TypedProvider(EntitiesResponse(entities=[
        EntityOut(text="Beta", label="concept", occurrence=7),
    ]))

    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=0,
    )

    assert entities[0].start_char == text.index("Beta")
    assert entities[0].metadata["span_occurrence"] == 0


def test_grounded_quote_accepts_source_line_breaks_between_words():
    text = "Policy tools include Emission Trading\nSystems."
    provider = TypedProvider(EntitiesResponse(entities=[
        EntityOut(text="Emission Trading Systems", label="concept", occurrence=0),
    ]))

    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=0,
    )

    assert text[entities[0].start_char:entities[0].end_char] == "Emission Trading\nSystems"


def test_grounded_relation_validates_qualifiers_against_canonical_source_slice():
    text = "Policy applies where outcomes are financially  material."
    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Policy", label="concept", occurrence=0),
            EntityOut(text="outcomes", label="concept", occurrence=0),
        ])),
        grounding="strict",
    )
    provider = TypedProvider(RelationsResponse(relations=[RelationOut(
        subject="Policy",
        subject_id="mention:0",
        predicate="applies_to",
        object="outcomes",
        object_id="mention:1",
        evidence="Policy applies where outcomes are financially material.",
        evidence_occurrence=0,
        qualifiers={"polarity": "positive", "condition": "financially material"},
    )]))

    relations = extract_relations_llm(
        text,
        entities,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=0,
    )

    assert len(relations) == 1
    assert relations[0].context == text
    assert relations[0].metadata["qualifiers"]["condition"] == "financially  material"


def test_grounded_relation_records_rejected_candidate_without_losing_valid_fact():
    text = "Reflective roofs do not shade pedestrians."
    entities = extract_entities_llm(
        text, provider="bifrost", provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])), grounding="strict",
    )
    rejected = []
    provider = TypedProvider(RelationsResponse(relations=[
        RelationOut(subject="Reflective roofs", subject_id="mention:0", predicate="shades",
                    object="pedestrians", object_id="mention:1", evidence=text, evidence_occurrence=0,
                    qualifiers={"polarity": "negative", "condition": "in summer"}),
        RelationOut(subject="Reflective roofs", subject_id="mention:0", predicate="shades",
                    object="pedestrians", object_id="mention:1", evidence=text, evidence_occurrence=0,
                    qualifiers={"polarity": "negative"}),
    ]))
    relations = extract_relations_llm(text, entities, provider="bifrost", provider_instance=provider,
                                      grounding="strict", grounding_retries=0, rejection_receipts=rejected)

    assert len(relations) == 1
    assert rejected == [{"candidate_index": 0, "reason": "grounded relation qualifier condition is not an exact evidence substring"}]


def test_grounded_relation_isolates_candidate_missing_required_field_after_typed_validation():
    item_schema = GroundedRelationsResponse.model_json_schema()["properties"]["relations"]["items"]
    relation_schema = GroundedRelationsResponse.model_json_schema()["$defs"]["GroundedRelationOut"]
    required = relation_schema["required"]
    assert "qualifiers" in required
    assert "subject_id" in required and "object_id" in required
    assert "subject" not in required and "object" not in required
    assert "subject" not in relation_schema["properties"]
    assert "object" not in relation_schema["properties"]
    text = "Reflective roofs do not shade pedestrians."
    entities = extract_entities_llm(
        text, provider="bifrost", provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])), grounding="strict",
    )

    class ValidatingProvider(TypedProvider):
        def generate_typed(self, prompt, schema, **kwargs):
            # Decoder regression for retained responses; wire protocol validation is tested separately.
            return GroundedRelationsResponse.model_validate(self.responses.pop(0))

    candidate = {"subject": "Reflective roofs", "subject_id": "mention:0", "predicate": "shades",
                 "object": "pedestrians", "object_id": "mention:1", "evidence": text,
                 "evidence_occurrence": 0, "confidence": 0.9, "qualifiers": {"polarity": "negative"}}
    provider = ValidatingProvider({"relations": [{key: value for key, value in candidate.items() if key != "qualifiers"}, candidate]})
    rejected = []

    relations = extract_relations_llm(text, entities, provider="bifrost", provider_instance=provider,
                                      grounding="strict", grounding_retries=0, rejection_receipts=rejected)

    assert len(relations) == 1
    assert rejected[0]["candidate_index"] == 0
    assert "qualifiers" in rejected[0]["reason"]


def test_repeated_grounded_quote_retry_includes_range_without_echoing_output():
    text = "Alpha references Alpha."
    provider = TypedProvider(
        EntitiesResponse(entities=[EntityOut(text="Alpha", label="concept", occurrence=7)]),
        EntitiesResponse(entities=[EntityOut(text="Alpha", label="concept", occurrence=1)]),
    )

    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=1,
    )

    assert entities[0].start_char == text.rindex("Alpha")
    assert "found 2 exact occurrence(s)" in provider.prompts[1]
    assert "Previous grounded JSON" not in provider.prompts[1]
    assert provider.prompts[0] in provider.prompts[1]


def test_grounding_retry_does_not_grow_with_rejected_output():
    text = "Alpha references Beta." + " " * 60_000
    provider = TypedProvider(
        EntitiesResponse(entities=[
            EntityOut(text="missing", label="concept", occurrence=0,
                      attributes={"untrusted": "x" * 40_000}),
        ]),
        EntitiesResponse(entities=[EntityOut(text="Alpha", label="concept", occurrence=0)]),
    )
    entities = extract_entities_llm(text, provider="bifrost", provider_instance=provider,
                                    grounding="strict", grounding_retries=1, max_text_length=100_000)
    assert entities[0].text == "Alpha"
    assert provider.prompts[0] in provider.prompts[1]
    assert len(provider.prompts[1].encode()) - len(provider.prompts[0].encode()) < 4096


def test_strict_grounding_delegates_schema_repair_to_native_provider():
    text = "A affects B."
    entity_provider = TypedProvider(EntitiesResponse(entities=[
        EntityOut(text="A", label="concept", occurrence=0),
        EntityOut(text="B", label="concept", occurrence=0),
    ]))
    entities = extract_entities_llm(text, provider="bifrost", provider_instance=entity_provider, grounding="strict")
    assert entity_provider.kwargs[0]["max_retries"] == 2

    relation_provider = TypedProvider(RelationsResponse(relations=[RelationOut(
        subject="A", subject_id="mention:0", predicate="affects", object="B", object_id="mention:1",
        evidence=text, evidence_occurrence=0, qualifiers={"polarity": "positive"},
    )]))
    extract_relations_llm(text, entities, provider="bifrost", provider_instance=relation_provider, grounding="strict")
    assert relation_provider.kwargs[0]["max_retries"] == 2


def test_grounded_relation_keeps_valid_facts_when_peer_is_invalid():
    text = "Reflective roofs do not shade pedestrians."
    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])),
        grounding="strict",
    )
    provider = TypedProvider(RelationsResponse(relations=[
        RelationOut(
            subject="Reflective roofs", subject_id="invented", predicate="listed_on",
            object="pedestrians", object_id="mention:1", evidence=text,
            evidence_occurrence=0, qualifiers={"polarity": "positive"},
        ),
        RelationOut(
            subject="Reflective roofs", subject_id="mention:0", predicate="shades",
            object="pedestrians", object_id="mention:1", evidence=text,
            evidence_occurrence=0, qualifiers={"polarity": "negative"},
        ),
    ]))
    relations = extract_relations_llm(
        text,
        entities,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=0,
    )
    assert [relation.predicate for relation in relations] == ["shades"]


@pytest.mark.parametrize("qualifiers", [{"polarity": "positive"}, [{"polarity": "positive"}]])
def test_grounded_relation_normalizes_singleton_qualifiers_without_model_retry(qualifiers):
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    from semantica.semantic_extract.types import Entity

    text = "A uses B."
    entities = [Entity("A", "CONCEPT", 0, 1, 0.9, {"mention_id": "mention:0"}),
                Entity("B", "CONCEPT", 7, 8, 0.9, {"mention_id": "mention:1"})]
    candidate = {"subject_id": "mention:0", "object_id": "mention:1", "predicate": "uses",
                 "evidence": text, "evidence_occurrence": 0, "qualifiers": qualifiers}
    relations = _parse_grounded_relation_result({"relations": [candidate]}, entities, text, "bifrost", "test")
    assert relations[0].metadata["qualifiers"] == {"polarity": "positive"}
    assert candidate["qualifiers"] == qualifiers


@pytest.mark.parametrize("qualifiers", [[], [{"polarity": "positive"}, {"polarity": "negative"}], ["positive"],
                                       [{"polarity": "invalid"}], [{"polarity": "positive", "condition": "absent"}]])
def test_grounded_relation_singleton_normalization_preserves_validation(qualifiers):
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    from semantica.semantic_extract.types import Entity

    entities = [Entity("A", "CONCEPT", 0, 1, 0.9, {"mention_id": "mention:0"}),
                Entity("B", "CONCEPT", 7, 8, 0.9, {"mention_id": "mention:1"})]
    candidate = {"subject_id": "mention:0", "object_id": "mention:1", "predicate": "uses",
                 "evidence": "A uses B.", "evidence_occurrence": 0, "qualifiers": qualifiers}
    with pytest.raises(ProcessingError):
        _parse_grounded_relation_result({"relations": [candidate]}, entities, "A uses B.", "bifrost", "test")


def test_malformed_relation_sibling_is_rejected_without_semantic_repair():
    text = "Reflective roofs shade pedestrians."
    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])),
        grounding="strict",
    )
    valid = {
        "subject_id": "mention:0", "object_id": "mention:1", "predicate": "shades",
        "evidence": text, "evidence_occurrence": 0, "confidence": 0.9,
        "qualifiers": {"polarity": "positive"},
    }
    provider = TypedProvider({"relations": [{"subject_id": "mention:0"}, valid]})
    rejected = []

    relations = extract_relations_llm(
        text, entities, provider="bifrost", provider_instance=provider,
        grounding="strict", grounding_retries=1, rejection_receipts=rejected,
    )

    assert [relation.predicate for relation in relations] == ["shades"]
    assert len(provider.prompts) == 1
    assert rejected[0]["candidate_index"] == 0
    assert rejected[0]["kind"] == "schema"


def test_malformed_entity_sibling_is_rejected_without_semantic_repair():
    text = "CFA Institute publishes standards."
    provider = TypedProvider(GroundedEntitiesResponse.model_validate({"entities": [
        {"text": "CFA Institute", "occurrence": 0},
        {"text": "standards", "label": "concept", "occurrence": 0},
    ]}))
    rejected = []

    entities = extract_entities_llm(
        text, provider="bifrost", provider_instance=provider,
        grounding="strict", grounding_retries=1, rejection_receipts=rejected,
    )

    assert [entity.text for entity in entities] == ["standards"]
    assert entities[0].metadata["mention_id"] == "mention:0"
    assert len(provider.prompts) == 1
    assert rejected[0]["candidate_index"] == 0
    assert rejected[0]["kind"] == "schema"


def test_strict_entity_rejects_normalized_text_instead_of_mutating_provenance():
    text = "CFA Institute publishes standards."
    provider = TypedProvider(GroundedEntitiesResponse.model_validate({"entities": [
        {"text": " CFA Institute ", "label": "organization", "occurrence": 0},
    ]}))
    rejected = []

    entities = extract_entities_llm(
        text, provider="bifrost", provider_instance=provider,
        grounding="strict", grounding_retries=0, rejection_receipts=rejected,
    )

    assert entities == []
    assert rejected[0]["kind"] == "schema"


def test_grounded_entity_keeps_valid_mentions_when_repair_stays_invalid():
    text = "Margaret Franklin leads CFA Institute."
    invalid = EntitiesResponse(entities=[
        EntityOut(text="Marg Franklin", label="person", occurrence=0),
        EntityOut(text="CFA Institute", label="organization", occurrence=0),
    ])
    provider = TypedProvider(invalid, invalid)

    entities = extract_entities_llm(
        text,
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=1,
    )

    assert [entity.text for entity in entities] == ["CFA Institute"]
    assert len(provider.prompts) == 2


def test_canonical_strict_extractors_do_not_fallback():
    text = "Exposure affects outcomes."
    provider = TypedProvider(
        EntitiesResponse(entities=[EntityOut(text="invented", label="concept", occurrence=0)]),
        EntitiesResponse(entities=[EntityOut(text="still invented", label="concept", occurrence=0)]),
    )
    entities = NERExtractor(
        method="llm",
        provider="bifrost",
        provider_instance=provider,
        grounding="strict",
        grounding_retries=1,
    ).extract(text)

    assert entities == []
    assert len(provider.prompts) == 2


def test_grounded_relations_reject_duplicate_mentions_at_same_source_span():
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    from semantica.semantic_extract.types import Entity
    text = "The committee supervises reporting."
    entities = [Entity("committee", "organization", 4, 13, 0.9, {"mention_id": f"mention:{i}"}) for i in range(2)]
    result = {"relations": [{"subject": "committee", "subject_id": "mention:0", "predicate": "related_to",
        "object": "committee", "object_id": "mention:1", "evidence": text,
        "evidence_occurrence": 0, "confidence": 0.9, "qualifiers": {"polarity": "positive"}}]}
    with pytest.raises(ProcessingError, match="itself"):
        _parse_grounded_relation_result(result, entities, text, "bifrost", "test")
    rejected = []
    assert _parse_grounded_relation_result(result, entities, text, "bifrost", "test", reject_invalid=True, rejections=rejected) == []
    assert len(rejected) == 1
    assert "itself" in rejected[0]["reason"]


def test_grounded_relation_uses_id_endpoints_without_redundant_model_text():
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    from semantica.semantic_extract.types import Entity

    text = "Exposure affects outcomes."
    entities = [
        Entity("Exposure", "concept", 0, 8, 0.9, {"mention_id": "mention:0"}),
        Entity("outcomes", "concept", 17, 25, 0.9, {"mention_id": "mention:1"}),
    ]
    result = {"relations": [{
        "subject_id": "mention:0",
        "object_id": "mention:1",
        "predicate": "affects",
        "evidence": text,
        "evidence_occurrence": 0,
        "confidence": 0.9,
        "qualifiers": {"polarity": "positive"},
    }]}

    relations = _parse_grounded_relation_result(result, entities, text, "bifrost", "test")

    assert relations[0].subject is entities[0]
    assert relations[0].object is entities[1]


def test_grounded_relation_ignores_noncanonical_endpoint_text_but_keeps_id_validation():
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    from semantica.semantic_extract.types import Entity

    text = "Exposure affects outcomes."
    entities = [
        Entity("Exposure", "concept", 0, 8, 0.9, {"mention_id": "mention:0"}),
        Entity("outcomes", "concept", 17, 25, 0.9, {"mention_id": "mention:1"}),
    ]
    result = {"relations": [{
        "subject": "wrong endpoint",
        "object": "also wrong",
        "subject_id": "mention:0",
        "object_id": "mention:1",
        "predicate": "affects",
        "evidence": text,
        "evidence_occurrence": 0,
        "confidence": 0.9,
        "qualifiers": {"polarity": "positive"},
    }]}

    relations = _parse_grounded_relation_result(result, entities, text, "bifrost", "test")

    assert relations[0].subject.text == "Exposure"
    assert relations[0].object.text == "outcomes"

@pytest.mark.parametrize('first', [{'predicate': 'uses'}, {'relations': 'invalid'}, {'relations': [{}, 'qualifiers']}])
def test_strict_relation_repairs_invalid_envelope_without_echoing_previous_json(first):
    import json
    from semantica.semantic_extract.providers import BaseProvider
    from semantica.semantic_extract.types import Entity
    class JsonProvider(BaseProvider):
        def __init__(self):
            super().__init__(model='test')
            self.prompts = []
            self.responses = [first, {'relations': []}]
        def is_available(self): return True
        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return json.dumps(self.responses.pop(0))
    provider = JsonProvider()
    entities = [Entity('A', 'thing', 0, 1, .9, {'mention_id': 'mention:0'})]
    result = extract_relations_llm('A', entities, provider='bifrost',
        provider_instance=provider, grounding='strict', grounding_retries=1)
    assert result == []
    assert len(provider.prompts) == 2
    assert "Previous grounded JSON" not in provider.prompts[1]
    assert provider.prompts[0] in provider.prompts[1]


def test_strict_relation_keeps_valid_sibling_beside_scalar():
    from semantica.semantic_extract.types import Entity
    entities = [Entity('A', 'thing', 0, 1, .9, {'mention_id': 'mention:0'}),
                Entity('B', 'thing', 7, 8, .9, {'mention_id': 'mention:1'})]
    response = GroundedRelationsResponse.model_validate({'relations': [
        {'subject_id': 'mention:0', 'object_id': 'mention:1', 'predicate': 'uses',
         'evidence': 'A uses B', 'evidence_occurrence': 0, 'qualifiers': {'polarity': 'positive'}}, 'qualifiers']})
    rejected = []
    provider = TypedProvider(response)
    result = extract_relations_llm('A uses B', entities, provider='bifrost', provider_instance=provider,
        grounding='strict', grounding_retries=1, rejection_receipts=rejected)
    assert len(result) == 1
    assert len(provider.prompts) == 1
    assert rejected == [{'candidate_index': 1, 'reason': 'grounded relation must be an object', 'kind': 'schema'}]
