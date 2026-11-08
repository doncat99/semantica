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
        # Current derived identity features retain names/identity observations,
        # not original source prose or a second full entity document.
        for identity in ids:
            feature = index.read_identity_features(identity)
            assert 'context' not in feature and 'description' not in feature
            assert '_identity_features' in feature
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
        merge = resolver.entity_merger._merge_adjudicated_group

        def invalidate_after_computation(*args, **kwargs):
            result = merge(*args, **kwargs)
            store.begin_publication('p', expected_generation=generation,
                                    source_count=0, canonical_count=0)
            return result

        monkeypatch.setattr(resolver.entity_merger, '_merge_adjudicated_group', invalidate_after_computation)
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

    def measured_prepare(entities, *, context, features_prepared=False):
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
            return prepare(entities, context=context, features_prepared=features_prepared)
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


def test_component_pages_and_hydration_do_not_rescan_members(tmp_path, monkeypatch):
    store, generation, ids = staged(tmp_path, 257)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Same', type='ORG') for n in range(len(ids))]
    try:
        index.build(lambda: iter(zip(ids, rows)))
        visited = []
        original = index.publication.values
        def counted(node, predicate):
            if predicate == 'identityNextMember':
                visited.append(node)
            return original(node, predicate)
        monkeypatch.setattr(index.publication, 'values', counted)
        cursor, actual = None, []
        while True:
            page = index.component(ids[0], after=cursor)
            actual.extend(page['records'])
            cursor = page['next_cursor']
            if cursor is None:
                break
        assert actual == ids
        assert len(visited) <= len(ids) + 3
        visited.clear()
        refs, _ = index.hydrate_component(ids[0], lambda ref: rows[ids.index(ref)])
        assert refs == ids
        assert len(visited) <= len(ids)
    finally:
        store.close()


def test_native_build_reads_raw_rows_once_and_never_bulk_relabels_members(tmp_path, monkeypatch):
    store, generation, ids = staged(tmp_path, 5)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name=name, type='ORG', aliases=aliases)
            for n, (name, aliases) in enumerate([
                ('First', []), ('Second', []), ('Third', []),
                ('Bridge', ['First', 'Second']), ('Last', ['Second', 'Third'])])]
    opens = []
    original = store._update_derived_graph
    def update(graph, **kwargs):
        assert kwargs.get('delete') not in ('?s ?predicate ?losing',)
        delete = kwargs.get('delete', '')
        assert not (delete.startswith('?s ?predicate <') and 'identityComponent' in kwargs.get('where', ''))
        return original(graph, **kwargs)
    def source():
        opens.append(1)
        yield from zip(ids, rows)
    monkeypatch.setattr(store, '_update_derived_graph', update)
    try:
        index.build(source)
        assert opens == [1]
        assert index.read_identity_features(ids[0])['name'] == 'First'
        with pytest.raises(ProcessingError, match='membership'):
            index.read_identity_features('urn:foreign')
        assert index.component(ids[0])['records'] == ids
        from semantica.triplet_store.publication_records import P
        for predicate in ('identityParent', 'identitySize', 'identityRepresentative', 'identityKeyParent'):
            assert not list(store.store.quads_for_pattern(None,
                index.publication.ox.NamedNode(P+predicate), None, index.publication.graph))
    finally:
        store.close()


def test_completed_identity_survives_generation_without_copy_and_exact_dependencies(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords, P
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store, generation, ids = staged(tmp_path, 3, canonical_count=None)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Name '+str(n), type='ORG') for n in range(3)]
    try:
        index.build(lambda: iter(zip(ids, rows)), resolve_candidates=False)
        p = index.publication
        with pytest.raises(ProcessingError, match='coverage'):
            p.seal_identity_stage(generation, 'exact-input')
        for n, ref in enumerate(ids):
            p.stage_canonical(generation, [dict(id='urn:canonical:'+str(n),
                representative=ref, members=[ref], member_count=1,
                selectors=[dict(field='name', record=ref)], selector_count=1)])
        assert p.seal_identity_stage(generation, 'exact-input') == 3
        before = set(q for q in store.store.quads_for_pattern(None, None, None, p.graph)
            if q.predicate.value.startswith(P+'identity') or q.subject.value.startswith('urn:canonical:'))
        update = store._update_derived_graph
        def indexed_identity_retention(graph, **kwargs):
            # Each selector lookup must bind its canonical before checking membership.
            assert '?identityCanonical <'+P+'selector> ?s' in kwargs['where']
            assert 'FILTER EXISTS' in kwargs['where']
            return update(graph, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(store, '_update_derived_graph', indexed_identity_retention)
            next_generation = store.begin_publication('p', expected_generation=generation,
                source_count=1, canonical_count=None)['generation']
        assert p.identity_stage_status(next_generation, 'changed-input') is None
        assert p.identity_stage_status(next_generation, 'exact-input')['canonical_count'] == 3
        after = set(q for q in store.store.quads_for_pattern(None, None, None, p.graph)
            if q.predicate.value.startswith(P+'identity') or q.subject.value.startswith('urn:canonical:'))
        assert before == after
        assert len(p.values(p.head, 'canonical')) == 3
        assert not p.values(p.head, 'canonicalCount')
        with pytest.raises(ProcessingError, match='stale'):
            p.identity_stage_status(generation, 'exact-input')
        store.close()
        store = OxigraphStore(tmp_path / 'facts')
        p = PublicationRecords(store, 'p')
        assert p.identity_stage_status(next_generation, 'exact-input')['canonical_count'] == 3
        retry = store.begin_publication('p', expected_generation=next_generation,
            source_count=1, canonical_count=None)['generation']
        assert p.identity_stage_status(retry, 'exact-input')['canonical_count'] == 3
        p.reset_identity_stage(retry)
        assert p.identity_stage_status(retry, 'exact-input') is None
        assert not p.values(p.head, 'canonical')
    finally:
        store.close()


def test_unfinished_identity_never_survives_generation(tmp_path):
    store, generation, ids = staged(tmp_path, 2)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter(zip(ids, [dict(id=str(n), name='Same', type='ORG') for n in range(2)])),
                    resolve_candidates=False)
        generation = store.begin_publication('p', expected_generation=generation,
            source_count=1, canonical_count=None)['generation']
        assert not index.publication.values(index.publication.head, 'identityIndexSealed')
        assert store.identity_stage_status('p', generation, 'exact-input') is None
    finally:
        store.close()


def test_native_identity_features_exclude_unrelated_property_payloads(tmp_path):
    store, generation, ids = staged(tmp_path, 1)
    resolver = EntityResolver(strategy='contextual', deduplication={'similarity': {
        'property_schema': {'lei': {'identity': True, 'scope': ['jurisdiction']}}}})
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    row = dict(id='one', name='Acme', type='ORG', properties={
        'lei': '123', 'jurisdiction': 'HK', 'unrelated_body': 'x' * (2 * 1024 * 1024)})
    try:
        index.build(lambda: iter([(ids[0], row)]))
        feature = index.read_identity_features(ids[0])
        assert feature['properties'] == {'lei': '123', 'jurisdiction': 'HK'}
    finally:
        store.close()


def test_component_reuse_tracks_absent_context_and_preserves_untouched_selectors(tmp_path):
    store, generation, ids = staged(tmp_path, 3, canonical_count=None)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Unique '+str(n), type='ORG',
                 metadata={'identity_scope': 'scope'+str(n)}) for n in range(3)]
    try:
        assert index.build(lambda: iter(zip(ids, rows)), policy_key='identity-rules')['retained_components'] == 0
        p = index.publication
        for n, ref in enumerate(ids):
            with index.resolution_scope(ref):
                if n == 0:
                    assert index._context.mapping('project_definitions').get('xyz') is None
                p.stage_canonical(generation, [dict(id='urn:decision:'+str(n), representative=ref,
                    members=[ref], member_count=1, selectors=[dict(field='name', record=ref)], selector_count=1)])
                index.seal_component(ref, ['urn:decision:'+str(n)])
        p.seal_identity_stage(generation, 'first')
        untouched = p.ox.NamedNode('urn:decision:1')
        before = set(store.store.quads_for_pattern(untouched, None, None, p.graph))
        selector = p.values(untouched, 'selector')[0]
        before_selector = set(store.store.quads_for_pattern(selector, None, None, p.graph))
        # A newly available definition invalidates a prior ABSENT read even
        # though neither the mention nor its candidate membership changed.
        from semantica.semantic_extract.types import Entity
        from semantica.triplet_store.extraction_records import ExtractionRecords
        source_node = p.values(p.head, 'source')[0]
        old_operation = p.one(source_node, 'operation')
        binding = dict(project='p', source='new', material='new-material', representation='new-repr',
            recipe='recipe', model='model', specification='spec', parser='parser', grounding='grounding',
            window_start=0, window_end=3)
        entity = Entity('XYZ', 'ORG', 0, 3, .9, {'mention_id': 'new'})
        receipt = store.adopt_extraction(binding, 'entities', [entity], text='XYZ',
            native_ranges=[dict(nativeRef='#/document/text', start=0, end=3, windowStart=0, windowEnd=3)],
            accepted_digest='new-paid')
        new_ref = ExtractionRecords(store, binding, 'entities').entity_node(entity).value
        generation = store.begin_publication('p', expected_generation=generation,
            source_count=2, canonical_count=None)['generation']
        p.stage_sources(generation, [dict(source='s', material='m', representation='r',
            recipe='recipe', operation_count=1, operations=[old_operation]),
            dict(source='new', material='new-material', representation='new-repr',
                recipe='recipe', operation_count=1, operations=[receipt['operation_id']])])
        index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
        new_row = dict(id='new', name='A new definition', type='ORG',
            metadata={'identity_scope':'new-scope'})
        new_row = resolver.duplicate_detector.disambiguator.identity_projection(new_row)
        new_row['_identity_features']['grounded_definitions'] = [('xyz', 'x y z')]
        result = index.build(lambda: iter([*zip(ids, rows), (new_ref, new_row)]), policy_key='identity-rules')
        assert result == dict(retained_canonical_count=2, retained_components=2)
        assert index.roots(affected_only=True)['records'] == [ids[0], new_ref]
        assert set(p.values(p.head, 'canonical')) == {untouched, p.ox.NamedNode('urn:decision:2')}
        assert set(store.store.quads_for_pattern(untouched, None, None, p.graph)) == before
        assert set(store.store.quads_for_pattern(selector, None, None, p.graph)) == before_selector
        assert p.status()['state'] == 'pending'
    finally:
        store.close()


def test_rebuild_invalidates_old_completion_before_resealing_index(tmp_path, monkeypatch):
    store, generation, ids = staged(tmp_path, 2)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    publication = index.publication
    rows = [dict(id=str(n), name='Same', type='ORG') for n in range(2)]
    try:
        index.build(lambda: iter(zip(ids, rows)), policy_key='identity-rules')
        publication.mutate(generation, [
            publication.triple(publication.head, 'identityStageInput', publication.scalar('old-input')),
            publication.triple(publication.head, 'identityStageCount', publication.ox.Literal(0))])

        def interrupt(_):
            assert publication.values(publication.head, 'identityIndexSealed')
            raise ProcessingError('canceled before decision reconciliation')

        monkeypatch.setattr(index, '_reconcile_decisions', interrupt)
        with pytest.raises(ProcessingError, match='canceled'):
            index.build(lambda: iter(zip(ids, rows)), policy_key='identity-rules')
        assert publication.identity_stage_status(generation, 'old-input') is None
        assert not publication.values(publication.head, 'identityStageCount')
    finally:
        store.close()


def test_component_dependencies_stream_beyond_single_write_budget(tmp_path):
    import json
    from semantica.triplet_store.publication_records import P, MAX_BYTES
    store, generation, ids = staged(tmp_path, 1, canonical_count=None)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter([(ids[0], dict(id='one', name='Unique', type='ORG'))]), policy_key='rules')
        p = index.publication
        with index.resolution_scope(ids[0]):
            for n in range(700):
                key = str(n) + 'x' * 2048
                index._context.mapping('project_definitions').get(key)
            # Enumeration must be captured too, including an empty map.
            assert list(index._context.mapping('project_definitions').items()) == []
            p.stage_canonical(generation, [dict(id='urn:decision:large', representative=ids[0],
                members=ids, member_count=1, selectors=[dict(field='name', record=ids[0])], selector_count=1)])
            index.seal_component(ids[0], ['urn:decision:large'])
        group = p.values(p.head, 'identityDecisionGroup')[0]
        dependencies = [q.object.value for q in store.store.quads_for_pattern(group,
            p.ox.NamedNode(P+'identityDecisionDependencies'), None, p.graph)]
        assert len(dependencies) == 701
        assert sum(len(value.encode()) for value in dependencies) > MAX_BYTES
        assert all(len(value.encode()) < MAX_BYTES for value in dependencies)
        assert all(index._context.dependency_digest(field, key) == digest
            for field, key, digest in map(json.loads, dependencies))
        assert index._reconcile_decisions(True)['retained_components'] == 1
        index._context.mapping('project_definitions').add('new-definition', 'value')
        assert index._reconcile_decisions(True)['retained_components'] == 0
    finally:
        store.close()


def test_identity_seal_checks_coverage_with_member_point_reads(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import P
    store, generation, ids = staged(tmp_path, 3, canonical_count=None)
    resolver = EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    try:
        index.build(lambda: iter(zip(ids, [dict(id=str(n), name='Name '+str(n), type='ORG')
            for n in range(3)])), resolve_candidates=False)
        p, native = index.publication, store.store
        ox = store._oxigraph
        for n, ref in enumerate(ids):
            p.stage_canonical(generation, [dict(id='urn:canonical:'+str(n),
                representative=ref, members=[ref], member_count=1,
                selectors=[], selector_count=0)])
        member = ox.NamedNode(P+'member')
        canonical = ox.NamedNode(P+'canonical')
        reads = []
        class IndexedCoverage:
            def __getattr__(self, key):
                return getattr(native, key)
            def query(self, query):
                assert 'FILTER NOT EXISTS' not in query, 'coverage must not join every canonical per mention'
                return native.query(query)
            def quads_for_pattern(self, s, pred, o, graph):
                if pred == member:
                    assert s is None and o is not None
                    reads.append(o)
                yield from native.quads_for_pattern(s, pred, o, graph)
        monkeypatch.setattr(store, 'store', IndexedCoverage())
        # A reference from an unregistered canonical must not satisfy coverage.
        target = ox.NamedNode('urn:canonical:2')
        quad = ox.Quad(p.head, canonical, target, p.graph)
        native.remove(quad)
        with pytest.raises(ProcessingError, match='coverage'):
            p.seal_identity_stage(generation, 'input')
        assert not p.values(p.head, 'identityStageInput')
        native.add(quad)
        reads.clear()
        assert p.seal_identity_stage(generation, 'input') == 3
        assert len(reads) == 3
    finally:
        store.close()
