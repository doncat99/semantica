from semantica.kg.entity_resolver import EntityResolver


def test_resolution_exposes_native_property_selections_without_copying_values():
    resolver = EntityResolver(strategy="exact")
    rows = [{"id": "a", "name": "X", "properties": {"x": 1}},
            {"id": "b", "name": "X", "properties": {"y": 2}}]
    resolved = resolver.resolve_entities(rows)
    selection = resolver.resolution_selections[resolved[0]["id"]]
    assert selection == {"representative": resolved[0]["id"], "members": ["a", "b"],
                         "property_sources": {"x": ["a"], "y": ["b"]},
                         "field_sources": {"name": [resolved[0]["id"]], "type": []}}
    resolver.resolve_entities([])
    assert resolver.resolution_selections == {}


def test_exact_resolution_does_not_merge_similar_names():
    entities = [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Alicia"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert {entity["id"] for entity in resolved} == {"1", "2"}


def test_resolution_selection_does_not_invent_missing_fields():
    resolver = EntityResolver(strategy="exact")
    resolver.resolve_entities([{"id": "a", "name": "X", "type": None}])
    assert resolver.resolution_selections["a"]["field_sources"] == {"name": ["a"], "type": []}


def test_unhashable_entity_id_remains_usable_without_durable_selection():
    resolver = EntityResolver(strategy="exact")
    entity = {"id": ["a"], "name": "X"}
    assert resolver.resolve_entities([entity]) == [entity]
    assert resolver.resolution_selections == {}


def test_exact_resolution_merges_case_and_whitespace_variants():
    entities = [
        {"id": "1", "name": " Alice "},
        {"id": "2", "name": "alice"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert len(resolved) == 1


def test_resolution_preserves_non_duplicate_entities_without_ids():
    entities = [
        {"name": "Alice"},
        {"name": "Bob"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert resolved == entities


def test_exact_resolution_does_not_merge_whitespace_only_names():
    entities = [
        {"id": "1", "name": "   "},
        {"id": "2", "name": "\t"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert {entity["id"] for entity in resolved} == {"1", "2"}


def test_exact_resolution_falls_back_to_text_when_name_is_blank():
    entities = [
        {"id": "1", "name": " ", "text": "Alice"},
        {"id": "2", "name": "Alice"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert len(resolved) == 1
