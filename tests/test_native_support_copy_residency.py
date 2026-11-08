"""Canonical decisions retain references, never copies of support bodies."""
from copy import deepcopy

import pytest

from semantica.deduplication.entity_merger import EntityMerger


@pytest.mark.parametrize('statuses,expected_status,evidence', [
    (['accepted', 'retracted'], 'accepted', ['e:0']),
    (['candidate', 'contradicted'], 'contradicted', ['e:0', 'e:1']),
    (['retracted', 'retracted'], 'retracted', ['e:0', 'e:1']),
    (['rejected', 'accepted'], 'candidate', ['e:0', 'e:1']),
    (['rejected', 'rejected'], 'rejected', ['e:0', 'e:1']),
])
def test_support_references_preserve_status_and_evidence_without_copying_bodies(statuses, expected_status, evidence):
    copies=[]
    class Body(dict):
        def __deepcopy__(self,memo):
            copies.append(self['id'])
            return dict(self)
    source=[dict(id=f'input:{index}',status=status,evidence_ids=[f'e:{index}'],
        metadata={'audit':Body(id=str(index),text='original')}) for index,status in enumerate(statuses)]
    original=deepcopy(source)
    copies.clear()
    result=EntityMerger.merge_qualified_fact_group('canonical',source)
    assert result['status']==expected_status
    assert result['evidence_ids']==result['support_ids']==evidence
    assert result['metadata']['support_observation_ids']==['input:0','input:1']
    assert 'support_observations' not in result['metadata']
    assert len(copies)<=2, 'only selected representative metadata may be copied'
    assert source==original
    result['metadata']['audit']['text']='edited'
    assert all(item['metadata']['audit']['text']=='original' for item in source)


def test_reference_reduction_is_order_independent_and_idempotent():
    source=[dict(id=f'input:{index}',status='accepted',evidence_ids=[str(index)],metadata={}) for index in range(20)]
    result=EntityMerger.merge_qualified_fact_group('canonical',source)
    assert result==EntityMerger.merge_qualified_fact_group('canonical',reversed(source))
    assert result==EntityMerger.merge_qualified_fact_group('canonical',[result])
