"""Complete candidate resolution must stop cooperatively without partial success."""
from threading import Event

import pytest

from semantica.kg.entity_resolver import EntityResolver
from semantica.semantic_worker_context import query_cancellation
from semantica.utils.exceptions import ProcessingError


def rows():
    return [dict(id=str(i), name='Acme Holdings', type='ORGANIZATION',
                 context='Acme Holdings publishes its annual report.',
                 evidence_ids=[str(i)], metadata={'identity_scope': str(i)})
            for i in range(16)]


@pytest.mark.parametrize('strategy', ['contextual', 'exact'])
def test_preset_cancellation_never_resolves_component(strategy):
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            EntityResolver(strategy=strategy).resolve_entities(rows())
    finally:
        query_cancellation.reset(token)


def test_inflight_pair_cancellation_stops_before_next_comparison(monkeypatch):
    event = Event()
    resolver = EntityResolver(strategy='contextual')
    detector = resolver.duplicate_detector
    native = detector._create_duplicate_candidate
    calls = []

    def compare(*args, **kwargs):
        calls.append(1)
        if len(calls) == 4:
            event.set()
        return native(*args, **kwargs)

    monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            resolver.resolve_entities(rows())
    finally:
        query_cancellation.reset(token)
    assert len(calls) == 4


def test_resolution_features_do_not_leak_between_mutated_inputs():
    resolver = EntityResolver(strategy='contextual')
    inputs = rows()
    assert len(resolver.resolve_entities(inputs)) == 1
    assert resolver.duplicate_detector.disambiguator._resolution_features is None
    for index, entity in enumerate(inputs):
        entity['name'] = f'Unique Company {index}'
        entity['context'] = entity['name'] + ' publishes a report.'
    assert len(resolver.resolve_entities(inputs)) == 16
    assert resolver.duplicate_detector.disambiguator._resolution_features is None


def test_complete_pair_decisions_are_reused_only_within_one_resolution(monkeypatch):
    resolver = EntityResolver(strategy='contextual')
    disambiguator = resolver.duplicate_detector.disambiguator
    compare = disambiguator.compare
    calls = []

    def observe(left, right, **kwargs):
        calls.append((left['id'], right['id']))
        return compare(left, right, **kwargs)

    monkeypatch.setattr(disambiguator, 'compare', observe)
    inputs = rows()
    for entity in inputs:
        entity['id'] = entity['id'].zfill(2)
    merged = resolver.resolve_entities(inputs)
    expected = 16 * 15 // 2
    assert len(calls) == expected
    assert len(set(calls)) == expected
    assert len(merged) == 1
    assert set(merged[0]['merged_from']) == {entity['id'] for entity in inputs}
    assert set(resolver.resolution_selections[merged[0]['id']]['members']) == {entity['id'] for entity in inputs}
    assert {evidence for entity in inputs if entity['id'] in merged[0]['merged_from'] for evidence in entity['evidence_ids']} == {str(i) for i in range(16)}
    assert resolver.duplicate_detector._resolution_pair_cache is None
    resolver.resolve_entities(inputs)
    assert len(calls) == 2 * expected


def test_pair_decision_memo_preserves_ordered_semantics(monkeypatch):
    resolver = EntityResolver(strategy='contextual')
    detector = resolver.duplicate_detector
    inputs = rows()[:2]
    calls = []

    def directed(left, right, **kwargs):
        calls.append((left['id'], right['id']))
        return {'decision': 'same', 'confidence': .9, 'reason': left['id']}

    monkeypatch.setattr(detector.disambiguator, 'compare', directed)
    with detector.decision_scope(inputs):
        for left, right in (inputs, inputs, inputs[::-1], inputs[::-1]):
            result = detector._create_duplicate_candidate(left, right, 1.)
            assert result.metadata['reason'] == left['id']
    assert calls == [('0', '1'), ('1', '0')]
