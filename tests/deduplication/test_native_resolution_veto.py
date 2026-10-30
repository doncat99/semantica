"""Native positive decisions remain authoritative; conflicts only subtract."""
import pytest

from semantica.deduplication.similarity_calculator import SimilarityCalculator
from semantica.kg.entity_resolver import EntityResolver
from semantica.semantic_artifact_builder import _resolve_native_entities
from semantica.semantic_artifact_schema import KnowledgeEntity


SCHEMA = {"external_key": {"identity": True, "scope": ["registry"]}}


@pytest.mark.parametrize("names", [("Same organization", "Same organization"),
                                  ("Acme Holdings", "Acne Holding"),
                                  ("AAAAAAA", "ZZZZZZZ")])
@pytest.mark.parametrize("properties", [({}, {}),
    ({"external_key": "1"}, {"external_key": "2"}),
    ({"external_key": "1", "registry": "X"}, {}),
    ({"external_key": "1", "registry": "X"}, {"external_key": "2", "registry": "Y"}),
    ({"external_key": "1", "registry": "X"}, {"external_key": "1", "registry": "X"})])
def test_declared_fields_do_not_replace_native_positive_decision(names, properties):
    rows = [{"id": key, "name": name, "type": "ORG", "properties": props}
            for key, name, props in zip(("a", "b"), names, properties)]
    native = EntityResolver().resolve_entities(rows)
    constrained = EntityResolver(deduplication={"similarity": {"property_schema": SCHEMA}})
    assert constrained.resolve_entities(rows) == native
    assert (SimilarityCalculator(property_schema=SCHEMA).calculate_similarity(*rows).score
            == SimilarityCalculator().calculate_similarity(*rows).score)


def test_shared_identifier_cannot_promote_a_native_rejection():
    rows = [{"id": key, "name": name, "type": "ORG",
             "properties": {"external_key": "1", "registry": "X"}}
            for key, name in [("a", "AAAAAAA"), ("b", "ZZZZZZZ")]]
    plain = SimilarityCalculator().calculate_similarity(*rows)
    constrained = SimilarityCalculator(property_schema=SCHEMA).calculate_similarity(*rows)
    assert constrained.score == plain.score
    assert EntityResolver(deduplication={"similarity": {"property_schema": SCHEMA}}).resolve_entities(rows) == rows


def test_missing_properties_keep_native_score():
    assert SimilarityCalculator().calculate_property_similarity({}, {}) == 1.0


def test_artifact_name_resolution_is_native_not_identifier_gated():
    mentions = [KnowledgeEntity(id=f"mention:{key}", canonical_name="Same organization", type="ORG",
                               description="manufactures precision medical instruments",
                               context="Same organization manufactures precision medical instruments.",
                               metadata={"identity_scope": "representation:one"})
                for key in ("a", "b")]
    entities, remap, registry = _resolve_native_entities(mentions)
    assert len(entities) == 1
    assert remap["mention:a"] == remap["mention:b"]
    assert len(registry) == 2
