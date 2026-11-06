"""Preserve native conflict partition while removing duplicate sorted edge storage."""
import hashlib
from itertools import combinations, product
import json
import tracemalloc

from semantica.deduplication import duplicate_detector as owner


def test_partition_preserves_complete_small_graph_characterization(monkeypatch):
    detector = owner.DuplicateDetector(contextual_identity=True)
    rows = [dict(id=str(index), name='Example') for index in range(4)]
    pairs = list(combinations(range(4), 2))
    results = []
    for choices in product(('same', 'unknown', 'different'), repeat=len(pairs)):
        decisions = dict(zip(pairs, choices))
        calls = []

        def compare(left, right, score):
            pair = tuple(sorted((int(left['id']), int(right['id']))))
            calls.append(pair)
            return owner.DuplicateCandidate(left, right, score, 1.,
                metadata={'decision': decisions[pair]})

        monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
        group = owner.DuplicateGroup(entities=rows, similarity_scores={('0', '1'): .75})
        result = detector._partition_contextual_group(group)
        assert calls == pairs
        results.append([{'members': [row['id'] for row in item.entities],
                         'scores': sorted((list(pair), score) for pair, score in item.similarity_scores.items())}
                        for item in result])
    # Golden characterization of the original native partition over all 729
    # graphs, including unknown bridges, conflict isolation and score retention.
    digest = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
    assert digest == '3f2cd3b61af0b2d65ce0ddc9dc01aed2fddfdf9516e7773e0b9a488cdb289b44'


def test_dense_conflict_partition_sorts_only_one_neighbor_row_at_a_time(monkeypatch):
    detector = owner.DuplicateDetector(contextual_identity=True)
    mention_count = 256
    rows = [dict(id=f'{index:04}', name='Example') for index in range(mention_count)]
    comparisons = 0
    allocations = []

    def compare(left, right, score):
        nonlocal comparisons
        comparisons += 1
        decision = 'different' if {left['id'], right['id']} == {'0000', '0001'} else 'same'
        return owner.DuplicateCandidate(left, right, score, 1., metadata={'decision': decision})

    def measure_sorted(values, *args, **kwargs):
        tracemalloc.start()
        try:
            result = sorted(values, *args, **kwargs)
            _, peak = tracemalloc.get_traced_memory()
            allocations.append(peak)
            return result
        finally:
            tracemalloc.stop()

    monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
    monkeypatch.setattr(owner, 'sorted', measure_sorted, raising=False)
    # All intermediary mentions support both contradictory sides, so no group
    # may be emitted. Every pair is still examined by the native decision owner.
    assert detector._partition_contextual_group(owner.DuplicateGroup(entities=rows)) == []
    assert comparisons == mention_count * (mention_count - 1) // 2
    assert allocations and max(allocations) <= mention_count * 1024, (
        f'partition sort allocated {max(allocations)} bytes; '
        'sort existing neighbor rows without retaining a second complete edge list'
    )


def test_dense_conflict_partition_bounds_internal_pair_residency(monkeypatch):
    """A conflict that isolates every mention must not retain Python pair sets."""
    detector = owner.DuplicateDetector(contextual_identity=True)
    count = 256
    rows = [dict(id=f'{index:04}', name='Example') for index in range(count)]
    calls = 0

    def compare(left, right, score):
        nonlocal calls
        calls += 1
        decision = 'different' if {left['id'], right['id']} == {'0000', '0001'} else 'same'
        return owner.DuplicateCandidate(left, right, score, 1., metadata={'decision': decision})

    monkeypatch.setattr(detector, '_create_duplicate_candidate', compare)
    tracemalloc.start()
    try:
        result = detector._partition_contextual_group(owner.DuplicateGroup(entities=rows))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result == []
    assert calls == count * (count - 1) // 2
    assert peak <= count * 768, (
        f'{count} mentions allocated {peak} bytes for exact conflict partition; '
        'retain adjacency and blockers as compact bits, not Python pair objects'
    )


def test_group_confidence_does_not_copy_all_pair_scores():
    """Metrics consume the retained native pair map without another pair array."""
    detector = owner.DuplicateDetector(contextual_identity=True)
    count = 65536
    group = owner.DuplicateGroup(
        entities=[dict(id=str(index)) for index in range(5)],
        similarity_scores={(str(index), str(index + 1)): .75 for index in range(count)},
    )
    tracemalloc.start()
    try:
        confidence = detector._calculate_group_confidence(group)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert confidence == .75
    assert peak < 16384, f'confidence copied pair scores: {peak} bytes'


def test_review_summary_does_not_materialize_every_candidate_reason_pair():
    """Exact review counts need one active ID set, not all diagnostic tuples."""
    detector = owner.DuplicateDetector(contextual_identity=True)
    count = 8192
    detector._identity_review_ids = [f'mention:{index}' for index in range(count)]
    bits = (1 << count) - 1
    detector.identity_reviews = {0: {'reason-b': bits, 'reason-a': bits}}
    remap = {mention: f'entity:{index // 2:05}'
             for index, mention in enumerate(detector._identity_review_ids)}
    tracemalloc.start()
    try:
        summaries = list(detector.iter_identity_review_summaries(remap))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    canonical_count = count // 2 - 1
    assert summaries == [('mention:0', canonical_count * 2,
        [(f'entity:{index:05}', reason) for index in range(1, 5)
         for reason in ('reason-a', 'reason-b')])]
    assert peak < count * 64, (
        f'review summary allocated {peak} bytes; count every canonical candidate '
        'without retaining every candidate/reason tuple')
