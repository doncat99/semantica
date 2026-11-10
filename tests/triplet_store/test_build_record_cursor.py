"""Pending-build reads use native membership, never a project DTO mirror."""
import pytest

from semantica.semantic_extract.types import Entity
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError


def staged(tmp_path, count=137, *, source_count=1, operation_count=1, canonical_count=0):
    store = OxigraphStore(tmp_path / 'facts')
    names = ['N'+str(n) for n in range(count)]
    text = ' '.join(names)
    entities, start = [], 0
    binding = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    for n, name in enumerate(names):
        entities.append(Entity(name, 'ORG', start, start+len(name), .9, {'mention_id':str(n)}))
        start += len(name)+1
    receipt = store.adopt_extraction(binding, 'entities', entities, text=text,
        native_ranges=[dict(nativeRef='#/document/text', start=0, end=len(text), windowStart=0,
            windowEnd=len(text))], accepted_digest='accepted')
    generation = store.begin_publication('p', expected_generation=None,
        source_count=source_count, canonical_count=canonical_count)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m',
        representation='r', recipe='recipe', operation_count=operation_count,
        operations=[receipt['operation_id']])])
    ids = sorted(ExtractionRecords(store, binding, 'entities').entity_node(e).value for e in entities)
    return store, generation, ids


def test_build_cursor_projects_fields_and_pages_without_loss_after_restart(tmp_path):
    store, generation, expected = staged(tmp_path)
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    fields, after, found = [F+'name'], None, []
    try:
        while True:
            page = store.read_build_records('p', generation, kind='Entity', source='s',
                fields=fields, after=after, limit=17)
            for record in page['records']:
                assert set(record['fields']) == set(fields)
                found.append(record['id'])
            after = page['next_cursor']
            if after is None:
                break
        assert found == expected
        assert store.read_build_records('p', generation, kind='Relation')['records'] == []
        assert store.read_build_records('p', generation, kind='Entity', source='foreign')['records'] == []
        point = store.read_build_nodes('p', generation, expected[:2], fields=fields)
        assert [item['id'] for item in point] == expected[:2]
        with pytest.raises(ProcessingError, match='not ready'):
            store.read_native_records('p', generation, expected[:1])
    finally:
        store.close()


def test_point_membership_uses_reverse_native_indexes_and_preserves_source_scope(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords
    store, _, ids = staged(tmp_path, 3)
    native = store.store

    class IndexedOnly:
        def __getattr__(self, key):
            return getattr(native, key)

        def query(self, *args, **kwargs):
            raise AssertionError('Point membership must use keyed native indexes')

    monkeypatch.setattr(store, 'store', IndexedOnly())
    publication = PublicationRecords(store, 'p')
    try:
        publication.member(publication.iri(ids[0]))
        publication.member(publication.iri(ids[0]), ['s'])
        with pytest.raises(ProcessingError, match='outside current publication'):
            publication.member(publication.iri(ids[0]), ['foreign'])
        with pytest.raises(ProcessingError, match='batch'):
            publication.member(publication.iri(ids[0]), [])
        with pytest.raises(ProcessingError, match='outside current publication'):
            PublicationRecords(store, 'foreign').member(publication.iri(ids[0]))
        with pytest.raises(ProcessingError, match='Duplicate'):
            publication.member(publication.iri(ids[0]), ['s', 's'])
    finally:
        store.close()


def test_build_pages_sort_only_operation_scoped_records(tmp_path, monkeypatch):
    store, generation, expected = staged(tmp_path, 137)
    native = store.store

    class OperationPagesOnly:
        def __getattr__(self, key):
            return getattr(native, key)

        def query(self, query, *args, **kwargs):
            if '?operation <'+F+'ownedRecord> ?record' in query:
                assert 'VALUES ?operation {' in query, 'Record joins must have a bounded operation window'
                assert query.count('urn:semantica:extraction:') <= 128
            return native.query(query, *args, **kwargs)

    monkeypatch.setattr(store, 'store', OperationPagesOnly())
    try:
        found, cursor = [], None
        while True:
            page = store.read_build_records('p', generation, kind='Entity', fields=[F+'name'],
                after=cursor, limit=17)
            found.extend(row['id'] for row in page['records'])
            cursor = page['next_cursor']
            if cursor is None:
                break
        assert found == expected
    finally:
        store.close()


def test_scoped_build_traversal_does_not_resort_operations_per_page(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords
    store, generation, expected = staged(tmp_path, 137)
    native, queries = store.store, []

    class Measured:
        def __getattr__(self, key):
            return getattr(native, key)

        def query(self, query, **options):
            queries.append(query)
            return native.query(query, **options)

    monkeypatch.setattr(store, 'store', Measured())
    try:
        found, cursor = [], None
        with PublicationRecords(store, 'p').build_scope(generation):
            while True:
                page = store.read_build_records('p', generation, kind='Entity',
                    fields=[F+'name'], after=cursor, limit=7)
                found.extend(row['id'] for row in page['records'])
                cursor = page['next_cursor']
                if cursor is None:
                    break
        assert found == expected
        assert sum('SELECT DISTINCT ?operation' in query for query in queries) == 1
        assert not any('SELECT DISTINCT ?record' in query for query in queries)
    finally:
        store.close()


@pytest.mark.parametrize('restart', [False, True])
def test_build_cursor_crosses_operation_pages_without_loss_or_source_leak(tmp_path, monkeypatch, restart):
    from contextlib import nullcontext
    from semantica.triplet_store.publication_records import PublicationRecords
    store = OxigraphStore(tmp_path / 'facts')
    sources, expected = [], []
    for index in range(130):
        source = 's'+str(index)
        binding = dict(project='p', source=source, material='m', representation='r',
            recipe='recipe', model='model', specification='spec', parser='parser',
            grounding='grounding', window_start=0, window_end=1)
        entity = Entity('N', 'ORG', 0, 1, .9, {'mention_id':source})
        receipt = store.adopt_extraction(binding, 'entities', [entity], text='N',
            native_ranges=[dict(nativeRef='#/document/text', start=0, end=1,
                windowStart=0, windowEnd=1)], accepted_digest='accepted')
        expected.append(ExtractionRecords(store, binding, 'entities').entity_node(entity).value)
        sources.append(dict(source=source, material='m', representation='r', recipe='recipe',
            operation_count=1, operations=[receipt['operation_id']]))
    generation = store.begin_publication('p', expected_generation=None,
        source_count=len(sources), canonical_count=0)['generation']
    for offset in range(0, len(sources), 128):
        store.stage_publication_sources('p', generation, sources[offset:offset+128])
    found, cursor = [], None
    queries = []
    native = store.store
    class Measured:
        def __getattr__(self, key):
            return getattr(native, key)
        def query(self, query, **options):
            queries.append(query)
            return native.query(query, **options)
    if not restart:
        monkeypatch.setattr(store, 'store', Measured())
    else:
        native = None
    try:
        with nullcontext() if restart else PublicationRecords(store, 'p').build_scope(generation):
            while True:
                page = store.read_build_records('p', generation, kind='Entity',
                    fields=[F+'name'], after=cursor, limit=17)
                found.extend(row['id'] for row in page['records'])
                cursor = page['next_cursor']
                if cursor is None:
                    break
                if restart:
                    store.close()
                    store = OxigraphStore(tmp_path / 'facts')
        assert found == sorted(expected)
        if not restart:
            assert sum('SELECT DISTINCT ?operation' in query for query in queries) == 1
        assert store.read_build_records('p', generation, kind='Entity', source='s3')['records'][0]['id'] == expected[3]
        assert store.read_build_records('p', generation, kind='Relation')['records'] == []
    finally:
        store.close()


@pytest.mark.parametrize('source_count,operation_count', [(2, 1), (1, 2)])
def test_incomplete_source_or_operation_plan_cannot_be_computed(tmp_path, source_count, operation_count):
    store, generation, _ = staged(tmp_path, 1, source_count=source_count, operation_count=operation_count)
    try:
        with pytest.raises(ProcessingError, match='incomplete'):
            store.read_build_records('p', generation, kind='Entity')
    finally:
        store.close()


def test_build_cursor_rejects_scope_changes_unowned_records_and_byte_overflow(tmp_path):
    store, generation, ids = staged(tmp_path, 3)
    try:
        page = store.read_build_records('p', generation, kind='Entity', fields=[F+'name'], limit=1)
        for changed in [dict(kind='Relation', fields=[F+'name']),
                        dict(kind='Entity', fields=[F+'entityType']),
                        dict(kind='Entity', fields=[F+'name'], source='s')]:
            with pytest.raises(ProcessingError, match='cursor'):
                store.read_build_records('p', generation, after=page['next_cursor'], **changed)
        with pytest.raises(ProcessingError, match='byte budget'):
            store.read_build_records('p', generation, kind='Entity', max_bytes=8)
        with pytest.raises(ProcessingError, match='current publication'):
            store.read_build_nodes('p', generation, ['urn:foreign'])
        with pytest.raises(ProcessingError, match='not pending'):
            store.read_build_records('p', 'other', kind='Entity')
        with pytest.raises(ProcessingError, match='projection'):
            store.read_build_records('p', generation, kind='Entity', fields=['invalid'])
        with pytest.raises(ProcessingError, match='kind'):
            store.read_build_records('p', generation, kind='unknown')
    finally:
        store.close()


def test_streamed_canonical_count_must_be_sealed_before_activation(tmp_path):
    from tests.triplet_store.test_publication_records import indexes
    store = OxigraphStore(tmp_path / 'facts')
    try:
        generation = store.begin_publication('p', expected_generation=None,
            source_count=0, canonical_count=None)['generation']
        assert store.publication_status('p')['canonical_count'] is None
        with pytest.raises(ProcessingError, match='not sealed'):
            store.activate_publication('p', generation, indexes=indexes())
        with pytest.raises(ProcessingError, match='does not match'):
            store.seal_publication_canonical_count('p', generation, 1)
        with pytest.raises(ProcessingError, match='Invalid'):
            store.seal_publication_canonical_count('p', generation, True)
        store.seal_publication_canonical_count('p', generation, 0)
        with pytest.raises(ProcessingError, match='already sealed'):
            store.seal_publication_canonical_count('p', generation, 0)
        store.activate_publication('p', generation, indexes=indexes())
        assert store.publication_status('p')['state'] == 'ready'
    finally:
        store.close()


def test_build_scope_reuses_plan_validation_but_never_stale_generation(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords

    store, generation, ids = staged(tmp_path, 3)
    p = PublicationRecords(store, 'p')
    native, plans = store.store, []

    class CountPlans:
        def __getattr__(self, key):
            return getattr(native, key)

        def query(self, query, *args, **kwargs):
            if 'operationCount' in query and 'HAVING' in query:
                plans.append(1)
            return native.query(query, *args, **kwargs)

    monkeypatch.setattr(store, 'store', CountPlans())
    try:
        with p.build_scope(generation):
            for _ in range(20):
                store.read_build_nodes('p', generation, ids[:1], fields=[F+'name'])
        assert len(plans) == 2
        with pytest.raises(ProcessingError, match='not pending'):
            with p.build_scope(generation):
                store.begin_publication('p', expected_generation=generation,
                    source_count=0, canonical_count=0)
                store.read_build_nodes('p', generation, ids[:1])
        assert store._build_plan_scope is None
    finally:
        store.close()


def test_reference_only_build_page_does_not_restore_fields(tmp_path, monkeypatch):
    from semantica.triplet_store.publication_records import PublicationRecords
    store, generation, expected = staged(tmp_path, 3)
    def forbidden(*args, **kwargs):
        pytest.fail('Reference traversal must not restore native fields')
    monkeypatch.setattr(PublicationRecords, '_read', forbidden)
    try:
        page = store.read_build_records('p', generation, kind='Entity', fields=[])
        assert page['records'] == [dict(id=ref, fields={}) for ref in expected]
        with pytest.raises(ProcessingError, match='byte budget'):
            store.read_build_records('p', generation, kind='Entity', fields=[], max_bytes=8)
    finally:
        store.close()
