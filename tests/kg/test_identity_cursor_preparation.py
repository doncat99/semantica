from copy import deepcopy
import weakref

import pytest

from semantica.kg.entity_resolver import EntityResolver
from tests.kg.test_contextual_identity import scoped


def test_context_preparation_uses_repeatable_hydrated_cursor_without_object_cache():
    rows = [
        scoped('a', 'Acme', 'Acme manufactures engines.'),
        scoped('b', 'Acme', 'Acme manufactures engines.'),
        scoped('c', 'Acme', 'Acme manufactures batteries.'),
    ]
    oracle = EntityResolver(strategy='contextual')
    oracle.duplicate_detector.disambiguator.prepare(rows)
    expected = oracle.duplicate_detector.disambiguator.compare(rows[0], rows[2])
    calls = []

    references = []

    class NativeRow(dict):
        pass

    def cursor():
        calls.append(1)
        for values in rows:
            row = NativeRow(deepcopy(values))
            references.append(weakref.ref(row))
            yield row

    resolver = EntityResolver(strategy='contextual')
    owner = resolver.duplicate_detector.disambiguator
    owner.prepare(cursor)
    assert len(calls) >= 6
    assert not hasattr(owner, '_supported_facts')
    assert all(reference() is None for reference in references)
    assert owner.compare(deepcopy(rows[0]), deepcopy(rows[2])) == expected


def test_prepared_components_keep_remote_definitions_and_native_resolution_semantics():
    rows = [
        scoped('a', 'Global Reporting Initiative',
               'Global Reporting Initiative (GRI) is an international reporting organization.', scope='source-a'),
        scoped('b', 'GRI', 'GRI is an international reporting organization.', scope='source-b'),
        scoped('c', 'Other Company', 'Other Company manufactures engines.', scope='source-c'),
    ]
    oracle = EntityResolver(strategy='contextual')
    expected = oracle.resolve_entities(deepcopy(rows))
    resolver = EntityResolver(strategy='contextual')
    resolver.duplicate_detector.disambiguator.prepare(lambda: iter(deepcopy(rows)))
    assert resolver.resolve_entities([], context_prepared=True) == []
    actual, selections = [], {}
    for component in (rows[:2], rows[2:]):
        actual.extend(resolver.resolve_entities(deepcopy(component), context_prepared=True))
        selections.update(deepcopy(resolver.resolution_selections))
    assert sorted(actual, key=lambda row: row['id']) == sorted(expected, key=lambda row: row['id'])
    assert selections == oracle.resolution_selections


def test_prepared_component_rejects_missing_project_context():
    resolver = EntityResolver(strategy='contextual')
    with pytest.raises(ValueError, match='completed contextual identity preparation'):
        resolver.resolve_entities([], context_prepared=True)
