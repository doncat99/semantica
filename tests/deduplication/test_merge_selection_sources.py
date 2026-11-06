import pytest
from copy import deepcopy

from semantica.deduplication.merge_strategy import MergeStrategyManager
from semantica.deduplication.entity_merger import EntityMerger


def test_merge_metadata_and_provenance_leave_source_observations_unchanged():
    entities = [
        {"id": "a", "name": "Acme", "type": "ORG", "metadata": {
            "tags": ["first"], "labels": {"shared": "old"},
            "provenance": {"origin": "import"}}},
        {"id": "b", "name": "Acme", "type": "ORG", "metadata": {
            "tags": ["second", "first"], "labels": {"shared": "new"}}},
    ]
    original = deepcopy(entities)
    operation = EntityMerger().merge_entity_group(entities, strategy="keep_first")
    assert entities == original
    assert operation.merged_entity["metadata"] == {
        "tags": ["first", "second", "first"], "labels": {"shared": "new"},
        "provenance": {"origin": "import", "merge_count": 2, "merged_from": [
            {"id": "a", "name": "Acme", "source": None},
            {"id": "b", "name": "Acme", "source": None}]},
    }


def test_merge_metadata_copies_newly_adopted_containers_before_later_merge():
    entities = [{"id": "a"}, {"id": "b", "metadata": {"tags": [1], "labels": {"a": 1}}},
                {"id": "c", "metadata": {"tags": [2], "labels": {"b": 2}}}]
    original = deepcopy(entities)
    result = MergeStrategyManager(default_strategy="keep_first").merge_entities(entities)
    assert entities == original
    assert result.merged_entity["metadata"] == {"tags": [1, 2], "labels": {"a": 1, "b": 2}}


@pytest.mark.parametrize("strategy,expected", [("keep_first", ["a"]), ("keep_last", ["b"]), ("merge_all", ["a", "b"])])
def test_property_selection_records_decision_not_value_matching(strategy, expected):
    entities = [{"id": "a", "name": "X", "properties": {"value": [1]}},
                {"id": "b", "name": "X", "properties": {"value": 2}}]
    manager = MergeStrategyManager(default_strategy="keep_first")
    manager.add_property_rule("value", strategy)
    result = manager.merge_entities(entities)
    assert result.property_sources["value"] == expected
    assert entities[0]["properties"]["value"] == [1]


def test_custom_computed_property_is_not_misrepresented_as_source_selection():
    manager = MergeStrategyManager()
    manager.add_property_rule("value", "custom", conflict_resolution=lambda a, b: a + b)
    result = manager.merge_entities([
        {"id": "a", "properties": {"value": 1}},
        {"id": "b", "properties": {"value": 2}},
    ])
    assert result.property_sources["value"] is None
    assert result.merged_entity["properties"]["value"] == 3


def test_new_and_single_properties_keep_source_identity():
    manager = MergeStrategyManager()
    result = manager.merge_entities([{"id": "a", "properties": {"x": 1}}])
    assert result.property_sources == {"x": ["a"]}
    result = manager.merge_entities([
        {"id": "a", "properties": {"x": 1}},
        {"id": "b", "properties": {"y": 2}},
    ])
    assert result.property_sources == {"x": ["a"], "y": ["b"]}


def test_single_entity_missing_fields_have_no_source_selection():
    result = MergeStrategyManager().merge_entities([{"id": "a", "name": None}])
    assert result.field_sources == {"name": [], "type": []}


def test_top_level_rule_tracks_its_actual_source_even_with_equal_values():
    manager = MergeStrategyManager(default_strategy="keep_first")
    manager.add_property_rule("name", "keep_last")
    result = manager.merge_entities([
        {"id": "a", "name": "Old", "type": "ORG"},
        {"id": "b", "name": "New", "type": "ORG"},
        {"id": "c", "name": "New", "type": "ORG"},
    ])
    assert result.field_sources == {"name": ["b"], "type": ["a"]}
