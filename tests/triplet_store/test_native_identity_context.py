"""Persist semantic indexing without retaining project-sized Python dictionaries."""
from semantica.normalize.entity_normalizer import EntityDisambiguator
from tests.triplet_store.test_build_record_cursor import staged


def test_native_semantic_context_matches_memory_oracle_and_reopens(tmp_path):
    from semantica.triplet_store.identity_context import NativeIdentityContext
    store, generation, _ = staged(tmp_path, 1)
    rows = [dict(id=str(n), name=name, type='ORG', context=context,
                 metadata={'identity_scope': scope, 'source_ids': [scope]})
            for n, (name, context, scope) in enumerate([
                ('Green Energy Alliance', 'Green Energy Alliance (GEA) is an energy organization.', 'a'),
                ('GEA', 'Green Energy Alliance (GEA) is an energy organization.', 'a'),
                ('GEA', 'GEA is an energy organization.', 'a'),
                ('GEA', 'Global Education Association (GEA) is a school organization.', 'b'),
                ('Global Education Association', 'Global Education Association (GEA) is a school organization.', 'b'),
            ])]
    oracle, actual = EntityDisambiguator(), EntityDisambiguator()
    try:
        oracle.prepare(rows)
        actual.prepare(lambda: iter(rows), context=NativeIdentityContext(store, 'p', generation))
        assert not isinstance(actual._project_definitions, dict)
        assert [actual.candidate_keys(row) for row in rows] == [oracle.candidate_keys(row) for row in rows]
        for left in rows:
            for right in rows:
                assert actual.compare(left, right) == oracle.compare(left, right)
        rebound = EntityDisambiguator()
        NativeIdentityContext(store, 'p', generation).bind(rebound)
        for row in rows:
            assert rebound.candidate_keys(row) == oracle.candidate_keys(row)
    finally:
        store.close()


def test_native_context_grows_on_disk_without_project_dicts(tmp_path):
    from semantica.triplet_store.identity_context import NativeIdentityContext
    store, generation, _ = staged(tmp_path, 1)
    actual = EntityDisambiguator()
    def rows():
        for n in range(180):
            yield dict(name=f'Alliance Organization Number {n}', type='ORG',
                context=f'Alliance Organization Number {n} (AON{n}) is an organization.',
                metadata={'identity_scope': str(n), 'source_ids': [str(n)]})
    try:
        actual.prepare(rows, context=NativeIdentityContext(store, 'p', generation))
        assert len(actual._defined_referents) == 180
        assert all(not isinstance(getattr(actual, '_'+field), dict)
                   for field in NativeIdentityContext.maps)
        assert actual._project_definitions.get('aon179') == {'alliance organization number 179'}
    finally:
        store.close()


def test_native_context_fences_stale_generation_and_oversized_semantic_group(tmp_path):
    import pytest
    from semantica.triplet_store.identity_context import NativeIdentityContext
    from semantica.utils.exceptions import ProcessingError
    store, generation, _ = staged(tmp_path, 1)
    context = NativeIdentityContext(store, 'p', generation)
    try:
        index = context.mapping('project_definitions')
        for n in range(128):
            index.setdefault('ambiguous', set()).add(str(n))
        index.setdefault('ambiguous', set()).add('128')
        with pytest.raises(ProcessingError, match='resource budget'):
            context.seal()
        store.begin_publication('p', expected_generation=generation, source_count=0, canonical_count=0)
        with pytest.raises(ProcessingError, match='not pending'):
            index.get('ambiguous')
    finally:
        store.close()
