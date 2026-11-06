"""Conflict relation membership preserves qualified equality without unrelated scans."""
import pytest

from semantica.conflicts.conflict_detector import ConflictDetector
from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation


@pytest.mark.parametrize('group_count', [8, 16])
def test_conflict_relation_lookup_matches_full_reference_without_rescans(monkeypatch, group_count):
    assertions, relations = [], []
    for index in range(group_count):
        for polarity in ('positive', 'negative'):
            suffix = f'{index}:{polarity}'
            qualifiers = {'polarity': polarity, 'condition': 'at rest', 'time': '2025'}
            assertions.append(KnowledgeAssertion(
                id=f'assertion:{suffix}', subject_id=f'entity:{index}', predicate='owns',
                object='Asset', object_entity_id='entity:asset', qualifiers=qualifiers,
                evidence_ids=[f'evidence:{suffix}']))
            relations.append(KnowledgeRelation(
                id=f'relation:{suffix}', source_entity_id=f'entity:{index}', type='owns',
                target_entity_id='entity:asset',
                qualifiers=dict(reversed(list(qualifiers.items()))),
                evidence_ids=[f'evidence:{suffix}']))
        relations.append(KnowledgeRelation(
            id=f'relation:unrelated:{index}', source_entity_id=f'entity:other:{index}',
            type='owns', target_entity_id='entity:asset', qualifiers={'polarity': 'positive'},
            evidence_ids=[f'evidence:unrelated:{index}']))
    original_getattribute = KnowledgeRelation.__getattribute__
    source_reads = 0

    def read(instance, name):
        nonlocal source_reads
        if name == 'source_entity_id':
            source_reads += 1
        return original_getattribute(instance, name)

    monkeypatch.setattr(KnowledgeRelation, '__getattribute__', read)
    canonical_assertions, canonical_relations, conflicts = ConflictDetector.reconcile_qualified_facts(
        'project:one', assertions[::-1], relations[::-1])
    measured_reads = source_reads
    by_id = {item.id: item for item in canonical_assertions}
    assert len(conflicts) == group_count
    for conflict in conflicts:
        members = [by_id[identity] for identity in conflict.assertion_ids]
        expected = sorted(relation.id for relation in canonical_relations if any(
            relation.source_entity_id == assertion.subject_id
            and relation.target_entity_id == assertion.object_entity_id
            and relation.type == assertion.predicate
            and relation.qualifiers == assertion.qualifiers for assertion in members))
        assert conflict.relation_ids == expected
        assert len(expected) == 2
        assert all(item.status == 'contradicted' for item in members)
    assert measured_reads <= len(canonical_relations) * 3, (
        f'{measured_reads} endpoint reads for {len(canonical_relations)} relations; '
        'each conflict must retrieve its endpoint/predicate bucket'
    )
