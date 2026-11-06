"""Paid window results leave the scheduler as references, not semantic copies."""
import gc
import weakref
from types import SimpleNamespace

from semantica import semantic_publication_builder as builder
from tests.artifact_helpers import native_extraction_owner, stub_native_provider


def test_scheduler_keeps_only_native_window_references_after_completion(tmp_path, monkeypatch):
    from tests.test_semantic_artifact_scheduling import scheduling_request

    receipts = []
    class Receipt:
        metadata = {}
    def extract(*args):
        receipt = Receipt()
        receipts.append(weakref.ref(receipt))
        return builder._AcceptedExtractionWindow((), None), [receipt], False
    def inspect(windows, extracted, embedded):
        gc.collect()
        assert len(extracted) == len(windows) == 12
        assert all(isinstance(item[0], builder._AcceptedExtractionWindow) and item[1] == [] for item in extracted)
        assert all(ref() is None for ref in receipts), 'completed scheduler entries retain receipt payloads'
        return 'reference-only'
    monkeypatch.setattr(builder, '_extract_window', extract)
    monkeypatch.setattr(builder, '_embed_texts', lambda texts, relay: ([[1.] for _ in texts], SimpleNamespace()))
    monkeypatch.setattr(builder, '_assemble_source_results', inspect)
    sources, request = scheduling_request(tmp_path, [('source-a', 'abcdefghijkl')], 3)
    assert builder._extract_project_sources(sources, request, None) == ['reference-only']


def test_split_window_releases_entities_then_restores_all_semantics_without_generation(tmp_path, monkeypatch):
    text = 'Acme owns Engine in 2026.'
    contexts = [[dict(ref=f'#/texts/{index}', quote=text, start=0, end=len(text), page=1)] for index in range(2)]
    monkeypatch.setattr(builder, '_extraction_context_batches', lambda *_: contexts)
    calls, objects = [], []
    def respond(stage, prompt):
        calls.append(stage)
        if stage == 'entities':
            return dict(entities=[dict(text=name, label='ORG', occurrence=0, confidence=.9, attributes={}) for name in ('Acme', 'Engine')])
        return dict(relations=[dict(predicate='owns', subject_id='mention:0', object_id='mention:1',
            evidence=text, evidence_occurrence=0, confidence=.8,
            qualifiers=dict(polarity='positive', time='2026'), supporting_refs=[])])
    stub_native_provider(monkeypatch, respond)
    grounded = builder.extract_grounded_window
    def tracked(*args, **kwargs):
        entities, relations, provider = grounded(*args, **kwargs)
        objects.extend(weakref.ref(item) for item in [*entities, *relations])
        return entities, relations, provider
    monkeypatch.setattr(builder, 'extract_grounded_window', tracked)
    args = (text, SimpleNamespace(model_id='test', context_window_tokens=8192, max_output_tokens=100), None, SimpleNamespace(context=lambda *_: []), (0, len(text), text))
    with native_extraction_owner(tmp_path / 'native', text=text) as store:
        handoff, receipts, reused = builder._extract_window(*args)
        gc.collect()
        assert not isinstance(handoff, dict), 'completed window retains materialized entity/relation dictionaries'
        assert objects and all(ref() is None for ref in objects), 'completed window retains native semantic payloads'
        assert not reused and calls == ['entities', 'relations', 'entities', 'relations']
        # Restoration must work after closing/reopening the native process owner.
        store.close()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('restoration called the model')
    monkeypatch.setattr(builder, '_project_model_provider', forbidden)
    with native_extraction_owner(tmp_path / 'native', text=text) as store:
        result, restored_receipts = builder._assemble_grounded_windows([(0, len(text), text)], [(handoff, [], reused)])
        assert [item['id'] for item in result['entities']] == ['0:batch0:mention:0', '0:batch0:mention:1', '0:batch1:mention:0', '0:batch1:mention:1']
        assert [item['subject'] for item in result['relations']] == ['0:batch0:mention:0', '0:batch1:mention:0']
        assert [item['object'] for item in result['relations']] == ['0:batch0:mention:1', '0:batch1:mention:1']
        assert all(item['evidence'] == text and item['qualifiers'] == dict(polarity='positive', time='2026') for item in result['relations'])
        assert all(item['native_ref'] for item in result['entities'])
        relation_refs = [ref for item in result['relations'] for ref in item['native_refs']]
        assert len(relation_refs) == len(set(relation_refs)) == 2
        from semantica.triplet_store.extraction_records import F, RDF_TYPE
        assert all(next(store.store.quads_for_pattern(store._oxigraph.NamedNode(ref),
            store._oxigraph.NamedNode(RDF_TYPE), store._oxigraph.NamedNode(F+'Relation'), None), None)
            for ref in relation_refs)
        assert len(result['native_operations']) == 4
        assert [r.model_dump() for r in restored_receipts] == [r.model_dump() for r in receipts]
        store.close()
