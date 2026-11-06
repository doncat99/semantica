"""Identity pair coverage must not require retaining every candidate object."""
import gc
from itertools import combinations, product
import tracemalloc
import weakref

import pytest

from semantica.kg import EntityResolver
from semantica.deduplication.duplicate_detector import DuplicateCandidate, DuplicateDetector


@pytest.mark.parametrize('mention_count', [16, 32, 64])
def test_same_name_candidates_stream_with_linear_object_residency(monkeypatch, mention_count):
    resolver = EntityResolver(strategy='contextual')
    detector = resolver.duplicate_detector
    rows = [dict(id=f'm{index}', name='Acme Holdings', type='ORGANIZATION',
                 context='Acme Holdings publishes its annual report.',
                 evidence_ids=[f'e{index}'], metadata={'identity_scope': f'r{index}'})
            for index in range(mention_count)]
    create_candidate = detector._create_duplicate_candidate
    residency = {'live': 0, 'peak': 0}

    def released():
        residency['live'] -= 1

    def create(*args, **kwargs):
        candidate = create_candidate(*args, **kwargs)
        residency['live'] += 1
        residency['peak'] = max(residency['peak'], residency['live'])
        weakref.finalize(candidate, released)
        return candidate

    monkeypatch.setattr(detector, '_create_duplicate_candidate', create)
    observed = set()
    # Keep only IDs in the oracle; the consumer never retains candidate objects.
    for candidate in detector._contextual_candidates(rows):
        assert candidate.metadata['decision'] == 'same'
        assert candidate.metadata['merge_allowed'] is True
        pair = tuple(sorted((candidate.entity1['id'], candidate.entity2['id'])))
        assert pair not in observed, 'identity candidate pair was emitted twice'
        observed.add(pair)
    del candidate
    gc.collect()
    expected = {tuple(sorted(pair)) for pair in combinations((row['id'] for row in rows), 2)}
    assert observed == expected, 'streaming must preserve every admitted identity comparison'
    assert residency['live'] == 0, 'consumer finished but candidate objects remain retained'
    # This is a complexity requirement, not a limit on admitted project size.
    assert residency['peak'] <= mention_count, (
        f'{mention_count} mentions retained {residency["peak"]} simultaneous candidate objects; '
        f'all {len(expected)} pairs were covered, but pair objects must stream with linear residency'
    )


def test_group_compatibility_matches_complete_small_graph_oracle(monkeypatch):
    detector = DuplicateDetector(contextual_identity=True)
    rows = [dict(id=str(index)) for index in range(4)]
    pairs = list(combinations(range(4), 2))
    for choices in product(('same', 'unknown', 'different'), repeat=len(pairs)):
        decisions = dict(zip(pairs, choices))
        observed = []

        def compare(left, right, score):
            pair = (int(left['id']), int(right['id']))
            observed.append(pair)
            return DuplicateCandidate(left, right, score, 1.,
                                      metadata={'decision': decisions[pair]})

        monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
        reached = {0}
        while True:
            expanded = reached | {index for pair, decision in decisions.items()
                                  if decision == 'same' and reached.intersection(pair)
                                  for index in pair}
            if expanded == reached:
                break
            reached = expanded
        expected = 'different' not in choices and len(reached) == len(rows)
        assert detector.is_group_compatible(rows) is expected
        first_block = next((i for i, choice in enumerate(choices) if choice == 'different'), None)
        expected_pairs = pairs[:first_block + 1] if first_block is not None else pairs
        assert observed == expected_pairs


@pytest.mark.parametrize('reason', ['context_requires_disambiguation', 'descriptions_require_disambiguation'])
def test_group_compatibility_preserves_unknown_blockers_and_trivial_groups(monkeypatch, reason):
    detector = DuplicateDetector(contextual_identity=True)
    rows = [dict(id=str(index)) for index in range(2)]
    monkeypatch.setattr(detector, '_create_duplicate_candidate', lambda left, right, score:
        DuplicateCandidate(left, right, score, 1., metadata={'decision': 'unknown', 'reason': reason}))
    assert detector.is_group_compatible([])
    assert detector.is_group_compatible(rows[:1])
    assert not detector.is_group_compatible(rows)


def test_group_compatibility_does_not_retain_dense_pair_adjacency(monkeypatch):
    detector = DuplicateDetector(contextual_identity=True)
    mention_count = 256
    rows = [dict(id=str(index)) for index in range(mention_count)]
    comparisons = 0

    def compare(left, right, score):
        nonlocal comparisons
        comparisons += 1
        return DuplicateCandidate(left, right, score, 1., metadata={'decision': 'same'})

    monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
    tracemalloc.start()
    try:
        assert detector.is_group_compatible(rows)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert comparisons == mention_count * (mention_count - 1) // 2
    # Allocation budget concerns connectivity bookkeeping, never input admission.
    assert peak <= mention_count * 1024
