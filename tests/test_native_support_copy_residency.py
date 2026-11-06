"""Canonical support audit payloads must be cloned only when retained."""
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
def test_qualified_support_clones_only_unique_retained_audit_payloads(statuses, expected_status, evidence):
    copies = {}

    class AuditPayload(dict):
        def __deepcopy__(self, memo):
            label = self['label']
            copies[label] = copies.get(label, 0) + 1
            result = AuditPayload()
            memo[id(self)] = result
            result.update((deepcopy(key, memo), deepcopy(value, memo)) for key, value in self.items())
            return result

    observations = [dict(id=f'input:{index}', status=status,
                         evidence_ids=[f'e:{index}'], support_ids=[],
                         metadata={'audit': AuditPayload(label=f'obs:{index}', values=['original'])})
                    for index, status in enumerate(statuses)]
    fact = dict(id='original', subject_id='entity:one', predicate='owns', object='Asset',
                qualifiers={'polarity': 'positive'}, status='contradicted', evidence_ids=['stale'],
                metadata={'audit': AuditPayload(label='representative', values=['original']),
                          'support_observations': observations + observations[::-1]})
    output = list(EntityMerger.merge_qualified_facts([fact], identity=lambda _: 'canonical'))
    target = output[0]
    assert target['id'] == 'canonical'
    assert target['status'] == expected_status
    assert target['evidence_ids'] == target['support_ids'] == evidence
    retained = target['metadata']['support_observations']
    assert {row['id'] for row in retained} == {'input:0', 'input:1'}
    assert {row['id']: row['status'] for row in retained} == {
        f'input:{index}': status for index, status in enumerate(statuses)}
    assert all(row == observations[int(row['id'].split(':')[1])] for row in retained)
    assert copies == {'representative': 1, 'obs:0': 1, 'obs:1': 1}
    # Outputs retain full independent audit bodies, including withdrawn supports.
    target['metadata']['audit']['values'].append('edited')
    retained[0]['metadata']['audit']['values'].append('edited')
    assert fact['metadata']['audit']['values'] == ['original']
    assert all(row['metadata']['audit']['values'] == ['original'] for row in observations)
    assert len(fact['metadata']['support_observations']) == 4


def test_qualified_fact_groups_release_dumped_inputs_as_outputs_are_consumed():
    import weakref

    dumped = []
    copies = []

    class DumpedFact(dict):
        def __deepcopy__(self, memo):
            copies.append(self['id'])
            return deepcopy(dict(self), memo)

    def facts():
        for index in range(8):
            item = DumpedFact(id=f'fact:{index}', qualifiers={'time': '2025'},
                              metadata={'audit': {'text': str(index) * 1000}},
                              evidence_ids=[f'e:{index}'], status='accepted')
            dumped.append(weakref.ref(item))
            yield item

    merged = EntityMerger.merge_qualified_facts(facts(), identity=lambda item: item['id'])
    assert not copies, 'canonical output must be consumed one group at a time'
    first = next(merged)
    assert first['id'] == 'fact:0'
    assert copies == ['fact:0']
    second = next(merged)
    assert second['id'] == 'fact:1'
    assert dumped[0]() is None, 'the consumed raw group must not overlap later outputs'
    remaining = list(merged)
    assert [item['id'] for item in remaining] == [f'fact:{index}' for index in range(2, 8)]
    assert all(reference() is None for reference in dumped)
    assert first['metadata']['support_observations'][0]['metadata']['audit']['text'] == '0' * 1000


def test_qualified_support_releases_full_json_keys_before_yield(monkeypatch):
    import json
    import weakref

    encoded_refs = []
    dumps = json.dumps

    class EncodedFact(str):
        pass

    def tracked_dumps(*args, **kwargs):
        value = EncodedFact(dumps(*args, **kwargs))
        encoded_refs.append(weakref.ref(value))
        return value

    observations = [dict(id=f'input:{index}', status='accepted', evidence_ids=[f'e:{index}'],
                         metadata={'audit': {'rows': ['retained support'] * 128}})
                    for index in range(32)]
    fact = dict(id='original', qualifiers={'polarity': 'positive'}, status='accepted',
                metadata={'support_observations': observations}, evidence_ids=[])
    monkeypatch.setattr(json, 'dumps', tracked_dumps)
    output = EntityMerger.merge_qualified_facts([fact], identity=lambda _: 'canonical')
    target = next(output)
    assert len(target['metadata']['support_observations']) == len(observations)
    assert encoded_refs and not any(reference() is not None for reference in encoded_refs), (
        'the suspended merger retains full JSON keys beside already-cloned support observations')
    assert list(output) == []


def test_qualified_fact_group_consumes_native_cursor_without_retaining_members():
    import weakref

    observed = []

    class NativeFact(dict):
        pass

    def cursor():
        for index in range(64):
            if index > 1:
                assert observed[index - 2]() is None, 'native cursor inputs accumulated during group reduction'
            fact = NativeFact(id=f'input:{index:03}', subject_id='entity:one', predicate='owns',
                              object='asset', qualifiers={'polarity': 'positive'}, status='accepted',
                              evidence_ids=[f'e:{index}'], metadata={'audit': {'index': index}})
            observed.append(weakref.ref(fact))
            yield fact

    target = EntityMerger.merge_qualified_fact_group('canonical', cursor())
    assert target['id'] == 'canonical'
    assert len(target['metadata']['support_observations']) == 64
    assert target['evidence_ids'] == sorted(f'e:{index}' for index in range(64))
    assert all(reference() is None for reference in observed)
