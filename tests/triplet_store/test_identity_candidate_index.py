"""Native candidate connectivity is complete across storage pages."""
import pytest

from semantica.kg.entity_resolver import EntityResolver
from semantica.triplet_store.identity_candidate_index import IdentityCandidateIndex
from semantica.utils.exceptions import ProcessingError
from tests.triplet_store.test_build_record_cursor import staged


def test_native_components_keep_alias_bridges_identifiers_and_input_order(tmp_path):
    store, generation, ids = staged(tmp_path, 5)
    rows = [dict(id=str(n), name=name, type='ORG', aliases=aliases, properties=properties)
            for n, (name, aliases, properties) in enumerate([
                ('First', ['Bridge'], {}), ('Bridge', ['Last'], {}),
                ('Last', [], {}), ('Unique', [], {'lei': 'same'}),
                ('Different', [], {'lei': 'same'})])]
    resolver = EntityResolver(strategy='contextual', deduplication={'similarity': {
        'property_schema': {'lei': {'identity': True}}}})
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter(zip(ids, rows)))
        roots = index.roots(limit=1)
        assert roots['records'] == [ids[0]]
        second = index.roots(after=roots['next_cursor'], limit=1)
        assert second['records'] == [ids[3]]
        assert second['next_cursor'] is None
        page = index.component(ids[0], limit=2)
        assert page['records'] == ids[:2]
        assert index.component(ids[0], after=page['next_cursor'])['records'] == ids[2:3]
        assert index.component(ids[3])['records'] == ids[3:]
        with pytest.raises(ProcessingError, match='cursor'):
            index.component(ids[3], after=page['next_cursor'])
        assert sorted(index.iter_components()) == sorted([ids[:3], ids[3:]])
        assert all('First' not in str(q) and 'Bridge' not in str(q)
                   for q in store.store.quads_for_pattern(None, None, None, index.publication.graph))
    finally:
        store.close()


def test_unsealed_incomplete_or_foreign_index_never_serves_partial_components(tmp_path):
    store, generation, ids = staged(tmp_path, 3)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Same', type='ORG') for n in range(3)]
    try:
        with pytest.raises(ProcessingError, match='not sealed'):
            index.roots()
        with pytest.raises(ProcessingError, match='incomplete'):
            index.build(lambda: iter(zip(ids[:2], rows[:2])))
        with pytest.raises(ProcessingError, match='not sealed'):
            index.roots()
        index.build(lambda: iter(zip(ids, rows)))
        with pytest.raises(ProcessingError, match='component budget'):
            list(index.iter_components(max_members=2))
        with pytest.raises(ProcessingError, match='membership'):
            index.component('urn:foreign')
        store.begin_publication('p', expected_generation=generation, source_count=0, canonical_count=0)
        with pytest.raises(ProcessingError, match='not pending'):
            index.roots()
    finally:
        store.close()


def test_native_component_crosses_physical_pages_and_survives_restart(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore

    store, generation, ids = staged(tmp_path, 131)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='N'+str(n), type='ORG', aliases=['N'+str(n+1)])
            for n in range(len(ids))]
    try:
        index.build(lambda: iter(zip(ids, rows)))
        store.close()
        store = OxigraphStore(tmp_path / 'facts')
        index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
        assert index.roots(limit=1)['records'] == ids[:1]
        first = index.component(ids[0])
        assert first['records'] == ids[:128]
        assert index.component(ids[0], after=first['next_cursor'])['records'] == ids[128:]
        assert list(index.iter_components(max_members=131)) == [ids]
        with pytest.raises(ProcessingError, match='component budget'):
            list(index.iter_components(max_members=130))
    finally:
        store.close()


def test_exact_mention_components_preserve_all_native_refs_without_name_merges(tmp_path):
    store, generation, ids = staged(tmp_path, 3)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=identity, name='Same', type='ORG') for identity in ('mention-a','mention-a','mention-b')]
    try:
        index.build(lambda: iter(zip(ids, rows)), resolve_candidates=False)
        assert list(index.iter_components()) == [ids[:2], ids[2:]]
    finally:
        store.close()


def test_canonical_reference_pages_point_and_evidence_filters_survive_restart(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store,generation,ids=staged(tmp_path,131,canonical_count=None)
    resolver=EntityResolver(strategy='contextual')
    rows=[dict(id=str(n),name='N'+str(n),type='ORG',evidence_ids=['e'+str(n%2)])
          for n in range(131)]
    index=IdentityCandidateIndex(store,'p',generation,resolver.duplicate_detector)
    try:
        index.build(lambda:iter(zip(ids,rows)),resolve_candidates=False)
        records=[dict(id='urn:canonical:'+str(n).zfill(3),representative=ref,
            members=[ref],member_count=1,selectors=[],selector_count=0)
            for n,ref in enumerate(ids)]
        for offset in range(0,len(records),128):
            store.stage_publication_canonical('p',generation,records[offset:offset+128])
        store.seal_publication_canonical_count('p',generation,131)
        first=index.canonical_references()
        assert len(first['records'])==128
        assert index.canonical_references(after=first['next_cursor'])['records']==[
            dict(id=record['id'],representative=record['representative']) for record in records[128:]]
        assert index.canonical_reference(records[130]['id'])==dict(
            id=records[130]['id'],representative=ids[130])
        selected=index.canonical_references(evidence_ids=['e1'],limit=2)
        assert [record['id'] for record in selected['records']]==[records[1]['id'],records[3]['id']]
        with pytest.raises(ProcessingError,match='cursor'):
            index.canonical_references(evidence_ids=['e0'],after=selected['next_cursor'])
        with pytest.raises(ProcessingError,match='byte budget'):
            index.canonical_references(max_bytes=10)
        with pytest.raises(ProcessingError,match='Unknown'):
            index.canonical_reference('urn:canonical:absent')
        assert index.canonical_references(evidence_ids=[])['records']==[]
        store.close()
        store=OxigraphStore(tmp_path/'facts')
        index=IdentityCandidateIndex(store,'p',generation,resolver.duplicate_detector)
        next_page=index.canonical_references(evidence_ids=['e1'],after=selected['next_cursor'],limit=2)
        assert [record['id'] for record in next_page['records']]==[records[5]['id'],records[7]['id']]
        store.begin_publication('p',expected_generation=generation,source_count=0,canonical_count=0)
        with pytest.raises(ProcessingError,match='not pending'):
            index.canonical_reference(records[0]['id'])
    finally:
        store.close()


def test_identity_hydration_complete_cross_page_oracle_and_exact_byte_boundary(tmp_path):
    import json
    store,generation,ids=staged(tmp_path,131)
    resolver=EntityResolver(strategy='contextual')
    index=IdentityCandidateIndex(store,'p',generation,resolver.duplicate_detector)
    rows=[dict(id=str(n),name='Same',type='ORG',aliases=['Alias '+str(n)]) for n in range(131)]
    try:
        index.build(lambda:iter(zip(ids,rows)))
        values=dict(zip(ids,rows))
        size=sum(len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()) for row in rows)
        refs,actual=index.hydrate_component(ids[0],values.__getitem__,max_bytes=size)
        assert refs==ids
        assert list(actual.values())==rows
        with pytest.raises(ProcessingError,match='byte budget exceeded'):
            index.hydrate_component(ids[0],values.__getitem__,max_bytes=size-1)
        calls=[]
        with pytest.raises(ProcessingError,match='record budget exceeded'):
            index.hydrate_component(ids[0],lambda ref:calls.append(ref),max_members=130)
        assert calls==[]
        # Default byte budget is exercised exactly; one additional byte rejects.
        default_bytes=16*1024*1024
        padded={ref:dict(value) for ref,value in values.items()}
        padded[ids[0]]['padding']=''
        empty_size=sum(len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()) for row in padded.values())
        # Keep each hydrated item under the native projection transport ceiling.
        remaining=default_bytes-empty_size
        for ref in ids:
            padded[ref].setdefault('padding','')
        empty_size=sum(len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()) for row in padded.values())
        remaining=default_bytes-empty_size
        for offset,ref in enumerate(ids):
            count=min(128000,remaining)
            padded[ref]['padding']='x'*count
            remaining-=count
        assert remaining==0
        assert len(index.hydrate_component(ids[0],padded.__getitem__)[0])==131
        padded[ids[-1]]['padding']+='x'
        with pytest.raises(ProcessingError,match='byte budget exceeded'):
            index.hydrate_component(ids[0],padded.__getitem__)
    finally:
        store.close()


def test_late_bridge_relabels_existing_native_components_and_rebuilds(tmp_path):
    store, generation, ids = staged(tmp_path, 5)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name=name, type='ORG', aliases=aliases)
            for n, (name, aliases) in enumerate([
                ('First', []), ('Second', []), ('Third', []),
                ('Bridge', ['First', 'Second']), ('Last', ['Second', 'Third'])])]
    try:
        index.build(lambda: iter(zip(ids, rows)))
        assert index.roots()['records'] == ids[:1]
        for seed in ids:
            assert index.component(seed)['records'] == ids
        index.build(lambda: iter(zip(ids, rows)), resolve_candidates=False)
        assert index.roots()['records'] == ids
        assert all(index.component(seed)['records'] == [seed] for seed in ids)
    finally:
        store.close()


def test_native_index_checkpoints_bounded_rows_and_reopens_complete(tmp_path, monkeypatch):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store, generation, ids = staged(tmp_path, 280)
    index = IdentityCandidateIndex(store, 'p', generation,
        EntityResolver(strategy='contextual').duplicate_detector)
    flushes = []
    native_flush = store.flush
    def observed_flush():
        flushes.append(True)
        return native_flush()
    monkeypatch.setattr(store, 'flush', observed_flush)
    def rows():
        return ((ref, dict(id=str(n), name='Same', type='ORG', evidence_ids=['e'+str(n)]))
                for n,ref in enumerate(ids))
    index.build(rows, resolve_candidates=False)
    assert len(flushes) < 20
    store.close()
    store = OxigraphStore(tmp_path/'facts')
    try:
        index = IdentityCandidateIndex(store, 'p', generation,
            EntityResolver(strategy='contextual').duplicate_detector)
        assert len(list(index.iter_components())) == len(ids)
    finally:
        store.close()


@pytest.mark.parametrize('resolve_candidates', [False, True])
def test_identity_checkpoint_cancel_stays_unsealed_after_restart_and_retry(tmp_path, resolve_candidates):
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store, generation, ids = staged(tmp_path, 140)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    event = Event()
    def rows():
        for n, ref in enumerate(ids):
            if n == 130:
                event.set()
            yield ref, dict(id=str(n), name='Same', type='ORG')
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            index.build(rows, resolve_candidates=resolve_candidates)
        assert store._build_plan_scope is None
    finally:
        query_cancellation.reset(token)
    store.close()
    store = OxigraphStore(tmp_path/'facts')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        with pytest.raises(ProcessingError, match='not sealed'):
            index.roots()
        index.build(lambda: ((ref, dict(id=str(n), name='Same', type='ORG'))
                    for n, ref in enumerate(ids)), resolve_candidates=False)
        assert len(list(index.iter_components())) == len(ids)
    finally:
        store.close()


@pytest.mark.parametrize('resolve_candidates', [False, True])
def test_identity_staging_cannot_cross_generation_change(tmp_path, resolve_candidates):
    store, generation, ids = staged(tmp_path, 2)
    index = IdentityCandidateIndex(store, 'p', generation,
        EntityResolver(strategy='contextual').duplicate_detector)
    changed = False
    def rows():
        nonlocal changed
        yield ids[0], dict(id='0', name='A', type='ORG')
        if not changed:
            changed = True
            store.begin_publication('p', expected_generation=generation,
                source_count=0, canonical_count=0)
        yield ids[1], dict(id='1', name='B', type='ORG')
    try:
        with pytest.raises(ProcessingError, match='not pending'):
            index.build(rows, resolve_candidates=resolve_candidates)
        assert store._build_plan_scope is None
    finally:
        store.close()


def test_component_reads_only_its_native_reverse_index(tmp_path):
    """Opening one singleton must not rejoin all project ordinals/members."""
    store, generation, ids = staged(tmp_path, 5)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Unique '+str(n), type='ORG') for n in range(5)]
    try:
        index.build(lambda: iter(zip(ids, rows)), resolve_candidates=False)
        native = store.store

        class PointReads:
            def __getattr__(self, name):
                return getattr(native, name)

            def query(self, query, *args, **kwargs):
                assert 'identityComponent' not in query, 'component reopened the project-wide SPARQL join'
                return native.query(query, *args, **kwargs)

        store.store = PointReads()
        assert index.component(ids[3])['records'] == [ids[3]]
        refs, values = index.hydrate_component(ids[3], dict(zip(ids, rows)).__getitem__)
        assert refs == [ids[3]] and list(values.values()) == [rows[3]]
    finally:
        store.store = native
        store.close()


def test_native_resolution_revalidates_generation_before_result_handoff(tmp_path, monkeypatch):
    store, generation, ids = staged(tmp_path, 16)
    rows = [dict(id=str(n), name='Acme Holdings', type='ORGANIZATION',
                 context='Acme Holdings publishes its annual report.',
                 evidence_ids=[str(n)], metadata={'identity_scope': str(n)})
            for n in range(16)]
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter(zip(ids, rows)))
        merge = resolver.entity_merger.merge_entity_group

        def invalidate_after_computation(*args, **kwargs):
            result = merge(*args, **kwargs)
            store.begin_publication('p', expected_generation=generation,
                                    source_count=0, canonical_count=0)
            return result

        monkeypatch.setattr(resolver.entity_merger, 'merge_entity_group', invalidate_after_computation)
        with pytest.raises(ProcessingError, match='stale|not pending'):
            resolver.resolve_entities(rows, context_prepared=True)
        assert resolver.duplicate_detector.disambiguator._resolution_features is None
    finally:
        store.close()


def test_native_component_resolution_validates_whole_plan_only_at_handoffs(tmp_path, monkeypatch):
    store, generation, ids = staged(tmp_path, 16)
    rows = [dict(id=str(n), name='Acme Holdings', type='ORGANIZATION',
                 context='Acme Holdings publishes its annual report.',
                 evidence_ids=[str(n)], metadata={'identity_scope': str(n)})
            for n in range(16)]
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter(zip(ids, rows)))
        context = resolver.duplicate_detector.disambiguator._native_context
        native = context.publication._build_fence
        calls = []

        def complete_plan(*args, **kwargs):
            calls.append(1)
            return native(*args, **kwargs)

        monkeypatch.setattr(context.publication, '_build_fence', complete_plan)
        merged = resolver.resolve_entities(rows, context_prepared=True)
        assert len(merged) == 1
        assert len(calls) == 2, 'whole plan validation must not run per identity lookup'
        assert context._lookup_cache is None
        assert context._lookup_bytes == 0
    finally:
        store.close()


def test_native_preparation_checks_plan_at_handoffs_and_batches_durable_writes(tmp_path, monkeypatch):
    from semantica.triplet_store.identity_context import NativeIdentityContext

    store, generation, ids = staged(tmp_path, 200)
    rows = [dict(id=str(n), name='Company '+str(n), type='ORG',
                 context='Company '+str(n)+' operates services.',
                 metadata={'identity_scope': 'source'}) for n in range(len(ids))]
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    prepare = resolver.duplicate_detector.disambiguator.prepare
    context_counts = {}

    def measured_prepare(entities, *, context):
        complete, flush = context.publication._build_fence, store.flush
        calls, flushes = [], []

        def complete_plan(*args, **kwargs):
            calls.append(1)
            return complete(*args, **kwargs)

        def durable_flush():
            flushes.append(1)
            return flush()

        monkeypatch.setattr(context.publication, '_build_fence', complete_plan)
        monkeypatch.setattr(store, 'flush', durable_flush)
        try:
            return prepare(entities, context=context)
        finally:
            context_counts.update(plans=len(calls), flushes=len(flushes))
            monkeypatch.setattr(store, 'flush', flush)

    monkeypatch.setattr(resolver.duplicate_detector.disambiguator, 'prepare', measured_prepare)
    try:
        index.build(lambda: iter(zip(ids, rows)))
        assert context_counts['plans'] == 0, 'outer preparation scope must own complete-plan checks'
        assert context_counts['flushes'] <= 4, 'semantic observations must use bounded durable batches'
        context = resolver.duplicate_detector.disambiguator._native_context
        assert isinstance(context, NativeIdentityContext)
        assert context._resolution_depth == 0
        assert context._lookup_cache is None
        assert sum(len(group) for group in index.iter_components()) == len(ids)
    finally:
        store.close()
