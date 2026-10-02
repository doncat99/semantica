from unittest.mock import patch

import pytest

from semantica.semantic_extract import NERExtractor, RelationExtractor
from semantica.semantic_extract.methods import extract_entities_llm, extract_relations_llm
from semantica.semantic_extract.schemas import (
    EntitiesResponse,
    EntityOut,
    RelationOut,
    RelationsResponse,
)
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


def test_canonical_strict_extractors_do_not_fallback():
    text = "Exposure affects outcomes."
    provider = TypedProvider(
        EntitiesResponse(entities=[EntityOut(text="invented", label="concept", occurrence=0)]),
        EntitiesResponse(entities=[EntityOut(text="still invented", label="concept", occurrence=0)]),
    )
    with pytest.raises(ProcessingError, match="outside source text"):
        NERExtractor(
            method="llm",
            provider="bifrost",
            provider_instance=provider,
            grounding="strict",
            grounding_retries=1,
        ).extract(text)
