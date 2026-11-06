"""Unrequested report subjects must not hydrate their membership collections."""
from types import SimpleNamespace

from semantica import semantic_publication_builder as builder
from tests.artifact_helpers import organization_report_owner


def test_explicit_overview_does_not_materialize_other_target_memberships(monkeypatch):
    class UnrequestedMembers:
        def __iter__(self):
            raise AssertionError('unrequested target membership was materialized')

    unrelated = SimpleNamespace(id='unrequested', title='Other subject', entity_ids=UnrequestedMembers())
    with organization_report_owner(monkeypatch):
        assert builder._explanation_reports('project', [], [], [], [], [unrelated], [unrelated], [],
            SimpleNamespace(model_id='offline'), target_ids=['project']) == ([], [])


def test_selected_target_memberships_are_released_between_reports(monkeypatch):
    events = []
    class Members:
        def __init__(self, label):
            self.label = label
        def __iter__(self):
            events.append(('members', self.label))
            return iter(())
    subjects = [SimpleNamespace(id=label, title=label, entity_ids=Members(label), relation_ids=[])
                for label in ('first', 'second')]
    def context(target, *args):
        events.append(('report', target['id']))
        return {}, {}
    monkeypatch.setattr(builder, '_reading_report_context', context)
    with organization_report_owner(monkeypatch):
        builder._explanation_reports('project', [], [], [], [], subjects, [], [],
            SimpleNamespace(model_id='offline'), target_ids=['first', 'second'])
    assert events == [('members', 'first'), ('report', 'first'),
                      ('members', 'second'), ('report', 'second')]


import gc
import weakref

import pytest


@pytest.mark.parametrize('mode', ['generate', 'restore', 'empty'])
def test_report_payload_is_released_before_next_context_is_hydrated(monkeypatch, mode):
    from semantica.semantic_artifact_schema import EvidenceSpan, KnowledgeEntity, ReportSection

    class Payload(dict):
        pass

    evidence = [EvidenceSpan(id=f'support:{name}', representation_id=name, quote=name,
        locator=dict(representation_id=name, origin='native', quote=name,
                     start_char=0, end_char=len(name), quality='precise')) for name in ('first', 'second')]
    entities = [KnowledgeEntity(id=span.representation_id, canonical_name=span.quote,
        type='CONCEPT', evidence_ids=[span.id]) for span in evidence]
    relay = SimpleNamespace(model_id='offline')
    context_owner = builder._reading_report_context
    references = []
    visits = []

    def context(*args):
        gc.collect()
        assert all(ref() is None for ref in references), 'previous report payload survives into next hydration'
        data, spans = context_owner(*args)
        data, spans = Payload(data), Payload(spans if mode != 'empty' else {})
        references.extend((weakref.ref(data), weakref.ref(spans)))
        visits.append(args[0]['id'])
        return data, spans

    def explain(data, _):
        return [ReportSection(title='Finding', text='Grounded',
            evidence_ids=[span['id'] for span in data['evidence']])], []

    monkeypatch.setattr(builder, '_grounded_explanation', explain)
    with organization_report_owner(monkeypatch), monkeypatch.context() as report_patch:
        saved_reports, _ = builder._explanation_reports('project', [], entities, [], [], [], [], evidence,
            relay, target_ids=['first', 'second'])
        if mode == 'restore':
            saved = dict(zip(('first', 'second'), saved_reports))
            report_patch.setattr(builder, '_organization_report_product',
                lambda action, identity, **kwargs: (saved[identity['targetId']], []))
            report_patch.setattr(builder, '_grounded_explanation',
                lambda *args: pytest.fail('adopted report must not call the model again'))
        report_patch.setattr(builder, '_reading_report_context', context)
        reports, receipts = builder._explanation_reports('project', [], entities, [], [], [], [], evidence,
            relay, target_ids=['first', 'second'])
    assert visits == ['first', 'second']
    assert all(ref() is None for ref in references)
    assert reports == ([] if mode == 'empty' else saved_reports)
    assert receipts == []
