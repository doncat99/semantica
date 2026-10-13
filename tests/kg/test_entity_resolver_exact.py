from semantica.kg.entity_resolver import EntityResolver


def test_exact_resolution_does_not_merge_similar_names():
    entities = [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Alicia"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert {entity["id"] for entity in resolved} == {"1", "2"}


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


def test_exact_resolution_can_scope_names_without_fuzzy_redetection():
    entities = [{'id': '1', 'name': ' Fund ', 'type': 'ORG', 'scope': 'a'},
                {'id': '2', 'name': 'fund', 'type': 'ORG', 'scope': 'a'},
                {'id': '3', 'name': 'fund', 'type': 'ORG', 'scope': 'b'}]
    resolved = EntityResolver(strategy='exact', exact_key=lambda item: (
        item['name'].strip().casefold(), item['type'], item['scope'])).resolve_entities(entities)
    assert len(resolved) == 2
    assert set(next(item['merged_from'] for item in resolved if 'merged_from' in item)) == {'1', '2'}


def test_admitted_pairs_use_native_transitive_grouping_without_detection(monkeypatch):
    from semantica.deduplication.duplicate_detector import DuplicateCandidate, DuplicateDetector
    detector = DuplicateDetector()
    entities = [{'id': str(i), 'name': str(i)} for i in range(4)]
    def unexpected(*args, **kwargs):
        raise AssertionError('admitted pairs must not run similarity detection again')
    monkeypatch.setattr(detector, 'detect_duplicates', unexpected)
    pairs = [DuplicateCandidate(entities[0], entities[1], 1, 1),
             DuplicateCandidate(entities[1], entities[2], 1, 1)]
    groups = detector.detect_duplicate_groups(entities, candidates=pairs)
    assert [{item['id'] for item in group.entities} for group in groups] == [{'0', '1', '2'}]
    assert detector.detect_duplicate_groups(entities, candidates=[]) == []
