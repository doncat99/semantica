"""Identity semantics belong to native owners, never a company-specific matcher."""
from itertools import permutations

import pytest

from semantica.deduplication.duplicate_detector import DuplicateDetector
from semantica.deduplication.entity_merger import EntityMerger
from semantica.deduplication.similarity_calculator import SimilarityCalculator
from semantica.kg.entity_resolver import EntityResolver
from semantica.utils.exceptions import ValidationError


def entity(key, name="Acme Holdings", *, kind="ORGANIZATION", **properties):
    return {"id": key, "name": name, "type": kind, "properties": properties}


def detector_config(field="registry_number", *, scope=()):
    return {"similarity": {"property_schema": {
        field: {"identity": True, "scope": list(scope)}}}}


@pytest.mark.parametrize("strategy", ["fuzzy", "exact"])
@pytest.mark.parametrize("field", ["registry_number", "arbitrary_external_key"])
def test_declared_identifier_conflict_cannot_be_outweighed(strategy, field):
    rows = [entity("a", **{field: "0000000001"}), entity("b", **{field: "0000000002"})]
    resolver = EntityResolver(strategy=strategy, similarity_threshold=0,
        deduplication={**detector_config(field), "confidence_threshold": 0})
    assert len(resolver.resolve_entities(rows)) == 2
    assert resolver.duplicate_detector.incremental_detect(rows[:1], rows[1:], threshold=0) == []


def test_declared_alias_recalls_unrelated_names_without_model_or_network(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        pytest.fail("native identity must not call network or model")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("semantica.semantic_artifact_builder._relay_json", forbidden)
    monkeypatch.setattr("semantica.semantic_artifact_builder._product_json", forbidden)
    rows = [entity("a", "International Business Machines", registry_number="123"),
            entity("b", "IBM", registry_number="123")]
    rows[0]["aliases"] = ["IBM"]
    resolver = EntityResolver(deduplication=detector_config())
    assert len(resolver.resolve_entities(rows)) == 1
    assert len(resolver.duplicate_detector.incremental_detect(rows[:1], rows[1:])) == 1


@pytest.mark.parametrize("alias", ["IBM", "ibm", " IBM "])
def test_exact_declared_alias_recall(alias):
    rows = [entity("a", "International Business Machines"), entity("b", "IBM")]
    rows[0]["aliases"] = [alias]
    assert len(EntityResolver().resolve_entities(rows)) == 1
    assert len(EntityResolver(deduplication=detector_config()).resolve_entities(rows)) == 1


def test_exact_alias_cannot_override_identity_conflict():
    rows = [entity("a", "International Business Machines", registry_number="1"),
            entity("b", "IBM", registry_number="2")]
    rows[0]["aliases"] = ["IBM"]
    assert EntityResolver(deduplication=detector_config()).resolve_entities(rows) == rows


def test_fuzzy_aliases_do_not_promote_unrelated_canonical_names():
    rows = [entity("a", "AAAAAAA"), entity("b", "AZZZZZZ")]
    native_score = SimilarityCalculator().calculate_similarity(*rows).score
    rows[0]["aliases"] = ["Global Holdings"]
    rows[1]["aliases"] = ["Global Holding"]
    assert SimilarityCalculator().calculate_similarity(*rows).score == native_score
    assert EntityResolver().resolve_entities(rows) == rows


def test_aliases_do_not_multiply_fuzzy_comparisons(monkeypatch):
    calculator = SimilarityCalculator()
    calls = []
    original = calculator.calculate_string_similarity

    def counted(left, right, **kwargs):
        calls.append((left, right))
        return original(left, right, **kwargs)

    monkeypatch.setattr(calculator, "calculate_string_similarity", counted)
    rows = [entity("a", "AAAAAAA"), entity("b", "AZZZZZZ")]
    rows[0]["aliases"] = ["Global Holdings", "Research Group"]
    rows[1]["aliases"] = ["Global Holding", "Research Groups"]
    calculator.calculate_similarity(*rows)
    assert len(calls) == 1


def test_conflict_declarations_do_not_expand_native_candidate_recall():
    rows = [entity("a", "Acme Holdings", registry_number="1"),
            entity("b", "Bcme Holdings", registry_number="1")]
    assert SimilarityCalculator().batch_calculate_similarity(rows) == []
    constrained = SimilarityCalculator(**detector_config()["similarity"])
    assert constrained.batch_calculate_similarity(rows) == []
    assert EntityResolver(deduplication=detector_config()).resolve_entities(rows) == rows


@pytest.mark.parametrize("strategy", ["fuzzy", "exact"])
def test_missing_identity_does_not_override_native_resolution(strategy):
    rows = [entity("a"), entity("b")]
    assert len(EntityResolver(strategy=strategy).resolve_entities(rows)) == 1
    assert len(EntityResolver(strategy=strategy,
        deduplication=detector_config()).resolve_entities(rows)) == 1


@pytest.mark.parametrize("constraint", ["type", "identifier"])
def test_conflicting_component_abstains_independent_of_input_order(constraint):
    rows = ([entity("a"), entity("b", kind=""), entity("c", kind="PERSON")]
            if constraint == "type" else
            [entity("a", registry_number="1"), entity("b"), entity("c", registry_number="2")])
    for ordered in permutations(rows):
        result = EntityResolver(deduplication=detector_config()).resolve_entities(list(ordered))
        assert len(result) == 3


def test_explicit_merge_cannot_bypass_identity_conflict():
    merger = EntityMerger(detector=detector_config())
    with pytest.raises(ValidationError):
        merger.merge_entity_group([entity("a", registry_number="1"), entity("b", registry_number="2")])


def test_only_comparable_scoped_conflicts_veto_native_resolution():
    resolver = EntityResolver(deduplication=detector_config(scope=("jurisdiction",)))
    assert len(resolver.resolve_entities([
        entity("a", registry_number="1", jurisdiction="X"),
        entity("b", registry_number="1", jurisdiction="Y")])) == 1
    assert len(resolver.resolve_entities([
        entity("a", registry_number="1", jurisdiction="X"),
        entity("b", registry_number="1")])) == 1
    assert len(resolver.resolve_entities([
        entity("a", registry_number="1", jurisdiction="X"),
        entity("b", registry_number="1", jurisdiction="X")])) == 1
    assert len(resolver.resolve_entities([
        entity("a", registry_number="1", jurisdiction="X"),
        entity("b", registry_number="2", jurisdiction="X")])) == 2


def test_identity_conflict_uses_exact_typed_values_without_replacing_native_scores():
    calc = SimilarityCalculator(**detector_config()["similarity"])
    assert calc.calculate_similarity(entity("a", registry_number="00001"),
                                     entity("b", registry_number="00002")).score == 0
    assert calc.calculate_property_similarity(entity("a"), entity("b")) == 1.0
    rows = [entity("a", registry_number=1), entity("b", registry_number=True)]
    assert len(EntityResolver(deduplication=detector_config()).resolve_entities(rows)) == 2


def test_resolver_does_not_redetect_at_a_different_threshold():
    rows = [entity("a", "Acme Holdings"), entity("b", "Acne Holding")]
    resolver = EntityResolver(similarity_threshold=0.99)
    assert resolver.entity_merger.duplicate_detector is resolver.duplicate_detector
    assert resolver.resolve_entities(rows) == rows


@pytest.mark.parametrize("config", [
    {"property_schema": []}, {"property_schema": {"key": {"identity": "yes"}}},
    {"property_schema": {"key": {"identity": True, "scope": "country"}}},
    {"require_identity": "true"},
])
def test_invalid_identity_configuration_fails_explicitly(config):
    with pytest.raises(ValueError):
        SimilarityCalculator(**config)


def test_aliases_survive_materialization_and_repeated_native_resolution():
    rows = [entity("a", "International Business Machines"), entity("b", "IBM")]
    rows[0]["aliases"] = ["IBM", "ibm"]
    resolved = EntityResolver().resolve_entities(rows)
    assert len(resolved) == 1
    assert {"IBM", "ibm", "International Business Machines"} <= {
        resolved[0]["name"], *resolved[0]["aliases"]}
    assert len(EntityResolver().resolve_entities([*resolved, entity("c", "IBM")])) == 1
    assert SimilarityCalculator().batch_calculate_similarity(rows[:1]) == []


def test_one_matching_identifier_does_not_override_another_conflicting_identifier():
    config = {"similarity": {"property_schema": {
        name: {"identity": True} for name in ("key_a", "key_b")}}}
    rows = [entity("a", key_a="1", key_b="2"), entity("b", key_a="1", key_b="3")]
    assert len(EntityResolver(deduplication=config).resolve_entities(rows)) == 2


def test_resolver_preserves_merger_only_policy_and_rejects_competing_config():
    config = detector_config()
    assert len(EntityResolver(merger={"detector": config}).resolve_entities(
        [entity("a", registry_number="1"), entity("b", registry_number="2")])) == 2
    with pytest.raises(ValueError, match="Conflicting"):
        EntityResolver(merger={"detector": config}, deduplication=detector_config("other_key"))


def test_identity_policy_cannot_be_silently_overridden_per_call():
    calculator = SimilarityCalculator(**detector_config()["similarity"])
    with pytest.raises(ValueError, match="constructor"):
        calculator.calculate_similarity(entity("a"), entity("b"), require_identity=False)
    with pytest.raises(ValueError, match="constructor"):
        calculator.batch_calculate_similarity([entity("a"), entity("b")], require_identity=False)


def test_incremental_merge_cannot_choose_a_side_of_an_ambiguous_component():
    rows = [entity("a", registry_number="1"), entity("b"), entity("c", registry_number="2")]
    for known in (rows[::2], list(reversed(rows[::2]))):
        merger = EntityMerger(detector=detector_config())
        assert merger.incremental_merge([rows[1]], known) == []


def test_detector_preserves_native_object_input_with_declared_identity():
    from types import SimpleNamespace
    detector = DuplicateDetector(**detector_config())
    rows = [SimpleNamespace(id=key, text='Same name', type='ORGANIZATION',
                metadata={'properties': {'registry_number': value}})
            for key, value in [('a', '1'), ('b', '2')]]
    assert not detector._create_duplicate_candidate(*rows, 1.0).metadata['merge_allowed']


@pytest.mark.parametrize("limits", [{"max_results": 1}, {"top_k_per_entity": 1}])
def test_result_limits_cannot_hide_an_ambiguous_component(limits):
    rows = [entity("a", registry_number="1"), entity("b"), entity("c", registry_number="2")]
    detector = DuplicateDetector(**detector_config(), **limits)
    assert detector.detect_duplicates(rows) == []
    assert detector.incremental_detect([rows[1]], rows[::2]) == []


def test_object_batch_uses_existing_metadata_properties_for_identity():
    from types import SimpleNamespace
    rows = [SimpleNamespace(id=key, text=name, type="ORGANIZATION",
                metadata={"properties": {"registry_number": "1"}})
            for key, name in [("a", "Same name"), ("b", "Same name")]]
    detector = DuplicateDetector(**detector_config())
    assert len(detector.detect_duplicates(rows)) == 1


def test_single_remaining_candidate_is_not_confirmation():
    resolver = EntityResolver(deduplication=detector_config())
    target = entity("target", registry_number="1")
    rows = [entity("wrong", registry_number="2"), entity("unknown", "ZZZZZZZ")]
    assert resolver.duplicate_detector.incremental_detect(rows, [target]) == []
    assert resolver.resolve_entities([target, *rows]) == [target, *rows]
