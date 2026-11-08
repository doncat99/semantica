"""Repeated mentions share decisions only when every rule input is equivalent."""
from itertools import combinations, product
import pytest

from semantica.deduplication.duplicate_detector import DuplicateCandidate, DuplicateDetector
from semantica.kg.entity_resolver import EntityResolver


def mention(index, **metadata):
    return dict(id=f'm{index:05}', name='Acme Holdings', type='ORGANIZATION',
                context='Acme Holdings publishes its annual report.',
                evidence_ids=[f'e{index}'], metadata={'identity_scope': 'report', **metadata})


def members(groups):
    return sorted(sorted(row['id'] for row in group.entities) for group in groups)


def test_repeated_mentions_do_not_make_quadratic_identity_decisions(monkeypatch):
    detector = DuplicateDetector(contextual_identity=True)
    rows = [mention(index) for index in range(512)]
    original = detector._create_duplicate_candidate
    calls = 0

    def counted(*args):
        nonlocal calls
        calls += 1
        return original(*args)

    monkeypatch.setattr(detector, '_create_duplicate_candidate', counted)
    groups = detector.detect_duplicate_groups(rows)
    assert members(groups) == [[row['id'] for row in rows]]
    assert calls <= 2, f'{calls} comparisons for a single equivalent mention class'
    assert len(groups[0].similarity_scores) == len(rows) - 1


def test_pair_relations_prevent_unsafe_class_contraction():
    detector = DuplicateDetector(contextual_identity=True)
    rows = [mention(0, source_ids=['a']), mention(1, source_ids=['b']),
            mention(2, source_ids=['a'])]
    rows[0]['evidence_ids'] = ['shared']
    rows[2]['evidence_ids'] = ['shared']
    detector.disambiguator.prepare(rows)
    classes = detector._decision_equivalent_mentions(rows)
    assert sorted(sorted(row['id'] for row in group) for group in classes) == [
        ['m00000', 'm00002'], ['m00001']]


def test_resolver_materializes_adjudicated_group_without_comparing_again(monkeypatch):
    resolver = EntityResolver(strategy='contextual')
    rows = [mention(index) for index in range(512)]

    def reject_repeated_decision(*args):
        raise AssertionError('completed identity group must not be adjudicated again')

    monkeypatch.setattr(resolver.duplicate_detector, 'is_group_compatible', reject_repeated_decision)
    result = resolver.resolve_entities(rows)
    assert len(result) == 1
    assert resolver.duplicate_detector.identity_comparison_stats['pair_comparisons'] <= 2
    assert sorted(next(iter(resolver.resolution_selections.values()))['members']) == [row['id'] for row in rows]


def test_compact_selection_keeps_exact_description_grounding():
    rows = [mention(0), mention(1)]
    rows[1].update(description='publishes its annual report', properties={'sector':'Energy'})
    resolver = EntityResolver(strategy='contextual')
    original = resolver.resolve_entities(rows)
    original_sources = next(iter(resolver.resolution_selections.values()))['field_sources']
    disambiguator = resolver.duplicate_detector.disambiguator
    compact = []
    for row in rows:
        projected = disambiguator.identity_projection(row)
        compact.append({**row, 'context':'', '_identity_features':projected['_identity_features']})
    resolved = resolver.resolve_entities(compact, context_prepared=True)
    assert resolved[0]['description'] == original[0]['description']
    assert next(iter(resolver.resolution_selections.values()))['field_sources'] == original_sources
    assert resolved[0]['context'] == ''


def test_equivalent_contraction_preserves_all_conflict_graph_partitions(monkeypatch):
    detector = DuplicateDetector(contextual_identity=True)
    pairs = list(combinations(range(4), 2))
    rows = [dict(id=f'{index}{copy}', name='Example', kind=index)
            for index in range(4) for copy in range(2)]
    monkeypatch.setattr(detector.disambiguator, 'prepare', lambda rows: None)
    monkeypatch.setattr(detector.disambiguator, 'decision_signature', lambda row: (row['kind'],))
    monkeypatch.setattr(detector, 'candidate_keys', lambda row: {'example'})
    for choices in product(('same', 'unknown', 'different'), repeat=len(pairs)):
        decisions = dict(zip(pairs, choices))

        def compare(left, right, score):
            pair = tuple(sorted((left['kind'], right['kind'])))
            decision = 'same' if pair[0] == pair[1] else decisions[pair]
            return DuplicateCandidate(left, right, score, 1., metadata={
                'decision': decision, 'merge_allowed': decision == 'same', 'reason': decision})

        monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
        expected = detector._build_duplicate_groups(detector._contextual_candidates(rows, context_prepared=True))
        result = detector._contextual_groups(rows, context_prepared=True)
        assert members(result) == members(expected), decisions


@pytest.mark.parametrize('unknown_reason', ['unknown','context_requires_disambiguation'])
def test_unknown_twins_preserve_external_support_and_veto_semantics(monkeypatch,unknown_reason):
    detector = DuplicateDetector(contextual_identity=True)
    rows = [dict(id=f'{kind}{copy}', name='Example', kind=kind)
        for kind in range(3) for copy in range(2)]
    monkeypatch.setattr(detector.disambiguator, 'prepare', lambda rows: None)
    monkeypatch.setattr(detector.disambiguator, 'decision_signature', lambda row: (row['kind'],))
    monkeypatch.setattr(detector, 'candidate_keys', lambda row: {'example'})
    pairs = [(0,0),(1,1),(2,2),(0,1),(0,2),(1,2)]
    for choices in product(('same','unknown','different'), repeat=len(pairs)):
        decisions = dict(zip(pairs, choices))
        def compare(left, right, score):
            decision = decisions[tuple(sorted((left['kind'],right['kind'])))]
            return DuplicateCandidate(left,right,score,1.,metadata={
                'decision':decision,'merge_allowed':decision=='same',
                'reason':unknown_reason if decision=='unknown' else decision})
        monkeypatch.setattr(detector,'_create_duplicate_candidate',compare)
        expected = detector._build_duplicate_groups(detector._contextual_candidates(rows,context_prepared=True))
        result = detector._contextual_groups(rows,context_prepared=True)
        assert members(result) == members(expected), decisions


def test_unknown_equivalent_mentions_share_comparison_but_not_identity():
    resolver = EntityResolver(strategy='contextual')
    rows = [dict(id=f'm{index:05}',name='Acme Holdings',type='ORG',
        metadata={'identity_scope':'report'}) for index in range(5000)]
    resolved = resolver.resolve_entities(rows)
    assert len(resolved) == 5000
    assert resolver.duplicate_detector.identity_comparison_stats == dict(
        mentions=5000,feature_groups=1,pair_comparisons=1)
    # Each unresolved mention sees all other mentions, never itself.
    summaries = list(resolver.duplicate_detector.iter_identity_review_summaries(
        {row['id']:row['id'] for row in rows}))
    assert len(summaries) == 5000
    assert all(count == 4999 and len(sample) == 8 for _,count,sample in summaries)
