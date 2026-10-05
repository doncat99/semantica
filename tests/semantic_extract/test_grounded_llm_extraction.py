from unittest.mock import patch

import pytest

from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.semantic_extract.methods import extract_entities_llm, extract_relations_llm
from semantica.semantic_extract.schemas import (
    EntitiesResponse,
    EntityOut,
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

    def is_available(self):
        return True

    def generate_typed(self, prompt, schema, **_kwargs):
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return self.responses.pop(0)


def test_native_grounded_extractors_apply_typed_spec_and_examples():
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


def test_native_grounded_extraction_retries_schema_violations():
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

    entities = extract_entities_llm(text, provider="bifrost", provider_instance=provider, grounding="strict", grounding_retries=1, extraction_spec=specification)

    assert entities[0].attributes == {"endangered": True}
    assert "invalid type" in provider.prompts[1]


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
    assert "table-of-contents" in provider.prompts[0]
    assert "navigation labels" in provider.prompts[0]
    assert provider.schemas[0].__name__ == "GroundedEntitiesResponse"
    assert provider.schemas[1].__name__ == "GroundedRelationsResponse"


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
    assert "qualifiers" in GroundedRelationsResponse.model_json_schema()["properties"]["relations"]["items"]["required"]
    text = "Reflective roofs do not shade pedestrians."
    entities = extract_entities_llm(
        text, provider="bifrost", provider_instance=TypedProvider(EntitiesResponse(entities=[
            EntityOut(text="Reflective roofs", label="measure", occurrence=0),
            EntityOut(text="pedestrians", label="population", occurrence=0),
        ])), grounding="strict",
    )

    class ValidatingProvider(TypedProvider):
        def generate_typed(self, prompt, schema, **kwargs):
            return schema.model_validate(self.responses.pop(0))

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


def test_repeated_grounded_quote_retry_includes_range_and_previous_json():
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
    assert '"occurrence": 7' in provider.prompts[1]


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
