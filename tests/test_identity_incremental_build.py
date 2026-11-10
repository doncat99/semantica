"""Source changes preserve unrelated native identity decisions in place."""
from copy import deepcopy
import pytest

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.source import source_content_revision
from semantica.triplet_store.identity_candidate_index import IdentityCandidateIndex
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.publication_records import PublicationRecords
from tests.test_semantic_artifact import _parsed_ref, _request


def test_unchanged_native_features_do_not_reopen_raw_rows(tmp_path):
    from tests.triplet_store.test_build_record_cursor import staged
    store, generation, refs = staged(tmp_path, 3, canonical_count=None)
    resolver = builder.EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    rows = [dict(id=str(n), name='Unique '+str(n), type='ORG',
        metadata={'identity_scope': 'source'+str(n)}) for n in range(3)]
    try:
        index.build(lambda: iter(zip(refs, rows)), policy_key='explicit-identity-policy')
        for n, ref in enumerate(refs):
            with index.resolution_scope(ref):
                canonical = 'urn:canonical:'+str(n)
                index.publication.stage_canonical(generation, [dict(id=canonical, representative=ref,
                    members=[ref], member_count=1,
                    selectors=[dict(field='name', record=ref)], selector_count=1)])
                index.seal_component(ref, [canonical])
        index.publication.seal_identity_stage(generation, 'input')

        def next_attempt():
            nonlocal generation, index
            p = index.publication
            source = p.values(p.publication_head, 'source', graph=p.publication_graph)[0]
            operations = [value.value for value in p.values(source, 'operation', graph=p.publication_graph)]
            generation = store.begin_publication('p', expected_generation=generation,
                source_count=1, canonical_count=None)['generation']
            store.stage_publication_sources('p', generation, [dict(source='s', material='m',
                representation='r', recipe='recipe', operation_count=len(operations), operations=operations)])
            index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)

        completed_graph = index.publication.graph
        completed_rows = set(store.store.quads_for_pattern(None, None, None, completed_graph))
        # Reuse occurs in a new attempt; completed stages remain immutable.
        next_attempt()

        def forbidden():
            raise AssertionError('immutable native features must not restore raw entities')

        retained = index.build(lambda: iter((ref, forbidden) for ref in refs),
            policy_key='explicit-identity-policy')
        assert retained['retained_components'] == 3
        assert retained['retained_canonical_count'] == 3
        assert set(store.store.quads_for_pattern(None, None, None, completed_graph)) == completed_rows
        assert index.publication.one(index.publication.head, 'identityDecisionPolicy') == 'explicit-identity-policy'
        index.publication.seal_identity_stage(generation, 'second-input')
        next_attempt()
        retained = index.build(lambda: iter((ref, forbidden) for ref in refs),
            policy_key='explicit-identity-policy')
        assert retained == dict(retained_components=3, retained_canonical_count=3)

        reads = []
        def changed(n):
            reads.append(n)
            return rows[n]
        retained = index.build(lambda: iter((ref, lambda n=n: changed(n)) for n, ref in enumerate(refs)),
            policy_key='changed-explicit-identity-policy')
        assert sorted(reads) == list(range(3))
        assert retained['retained_components'] == 0
    finally:
        store.close()


@pytest.mark.parametrize('grounded', [False, True])
def test_native_5000_equivalent_mentions_have_one_comparison(tmp_path, grounded):
    from semantica.semantic_artifact_schema import KnowledgeEntity
    from semantica.semantic_extract.types import Entity
    from semantica.triplet_store.extraction_records import ExtractionRecords
    store, sources, refs = OxigraphStore(tmp_path / 'facts'), [], []
    for source in range(50):
        text = 'N ' * 100
        binding = dict(project='p', source='s'+str(source), material='m', representation='r',
            recipe='recipe', model='model', specification='spec', parser='parser', grounding='grounding',
            window_start=0, window_end=len(text))
        entities = [Entity('N', 'ORG', 2*n, 2*n+1, .9,
            {'mention_id':str(source*100+n)}) for n in range(100)]
        receipt = store.adopt_extraction(binding, 'entities', entities, text=text,
            native_ranges=[dict(nativeRef='#/document/text', start=0, end=len(text),
                windowStart=0, windowEnd=len(text))], accepted_digest='accepted')
        records = ExtractionRecords(store, binding, 'entities')
        refs.extend(records.entity_node(entity).value for entity in entities)
        sources.append(dict(source=binding['source'], material='m', representation='r',
            recipe='recipe', operation_count=1, operations=[receipt['operation_id']]))
    generation = store.begin_publication('p', expected_generation=None,
        source_count=len(sources), canonical_count=None)['generation']
    store.stage_publication_sources('p', generation, sources)
    resolver = builder.EntityResolver(strategy='contextual')
    index = IdentityCandidateIndex(store, 'p', generation, resolver.duplicate_detector)
    def row(n):
        return dict(id='mention:'+str(n), name='Acme Holdings', type='ORG',
            context='Acme Holdings publishes its annual report.' if grounded else '',
            evidence_ids=['e'+str(n)], metadata={'identity_scope':'report'})
    try:
        index.build(lambda: iter((ref, row(n)) for n, ref in enumerate(refs)))
        features = {}
        def hydrate(ref):
            feature = index.read_identity_features(ref)
            features[feature['id']] = feature
            return KnowledgeEntity(id=feature['id'], canonical_name=feature['name'],
                type=feature['type'], evidence_ids=feature['evidence_ids'], metadata=feature['metadata'])
        _, mentions = index.hydrate_component(refs[0], hydrate)
        resolved, _, _ = builder._resolve_native_entities(list(mentions.values()), resolver=resolver,
            context_prepared=True, identity_features=features)
        assert len(resolved) == (1 if grounded else 5000)
        if grounded:
            assert len(resolver.resolution_selections[resolved[0].id]['members']) == 5000
        assert resolver.duplicate_detector.identity_comparison_stats == dict(
            mentions=5000, feature_groups=1, pair_comparisons=1)
    finally:
        store.close()


def test_source_add_change_withdraw_only_resolves_affected_components(tmp_path, monkeypatch):
    first = tmp_path / 'first.txt'
    first.write_text('Ada Lovelace designed the Analytical Engine.')
    extra = tmp_path / 'extra.txt'
    extra.write_text('Grace Hopper developed the Compiler.')

    def forbidden(*args, **kwargs):
        raise AssertionError('Deterministic incremental identity specs must not call paid services')

    monkeypatch.setattr(builder, '_relay_json', forbidden)
    monkeypatch.setattr(builder, '_organization_report_product', forbidden)
    staged = []
    original_stage = PublicationRecords.stage_canonical

    def stage(self, generation, records):
        staged.extend(record['id'] for record in records if record['members'])
        return original_stage(self, generation, records)

    monkeypatch.setattr(PublicationRecords, 'stage_canonical', stage)

    def parameters(include_extra=False):
        params = _request(first, tmp_path / 'output')['params']
        if include_extra:
            source = dict(filePath=str(extra), materialRevision=source_content_revision(extra),
                mimeType='text/plain', name=extra.name, sourceId='source-2')
            params['sources'].append(source)
            params['parsedSources'].append(_parsed_ref(params, source))
        return params

    def build(params):
        staged.clear()
        events = []
        builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(params),
            progress=events.append)
        completed = [event['metadata'] for event in events
            if event.get('stage') == 'entity_resolution'
            and event.get('metadata', {}).get('state') == 'completed']
        assert len(completed) == 1
        return completed[0], set(staged)

    def decisions(params):
        store = OxigraphStore(params['nativeStoreDir'])
        try:
            p = PublicationRecords(store, params['projectId'])
            result = {}
            for node in p.values(p.head, 'canonical'):
                members, selectors = p._canonical_references(node)
                result[node.value] = (node.value, tuple(sorted(members)),
                    tuple(sorted((value['field'], value['record']) for value in selectors)))
            return result
        finally:
            store.close()

    initial = parameters()
    cold, initial_written = build(initial)
    before = decisions(initial)
    assert initial_written == set(before)
    assert cold['canonicalEntities'] == len(before) > 0

    added = parameters(True)
    addition, added_written = build(added)
    after_addition = decisions(added)
    assert addition['retainedComponents'] > 0
    assert addition['completedComponents'] > 0
    assert added_written and added_written.isdisjoint(before)
    assert all(after_addition[key] == value for key, value in before.items())
    assert len(after_addition) == addition['canonicalEntities']

    # No-input-change reuse must finish before reopening any native entity input.
    with monkeypatch.context() as guard:
        guard.setattr(IdentityCandidateIndex, 'build', forbidden)
        guard.setattr(IdentityCandidateIndex, 'hydrate_component', forbidden)
        warm, warm_written = build(deepcopy(added))
    assert warm['reused'] is True
    assert not warm_written
    assert decisions(added) == after_addition

    extra.write_text('Katherine Johnson calculated the Orbital Trajectory.')
    changed = parameters(True)
    change, changed_written = build(changed)
    after_change = decisions(changed)
    assert change['retainedComponents'] > 0
    assert changed_written and changed_written.isdisjoint(before)
    assert all(after_change[key] == value for key, value in before.items())
    assert set(after_addition).difference(before).isdisjoint(after_change)

    withdrawn = parameters()
    # Returning to a completed input references its entire stage, without indexing.
    with monkeypatch.context() as guard:
        guard.setattr(IdentityCandidateIndex, 'build', forbidden)
        guard.setattr(IdentityCandidateIndex, 'hydrate_component', forbidden)
        withdrawal, withdrawal_written = build(withdrawn)
    assert withdrawal['completedComponents'] == 0
    assert withdrawal['reused'] is True
    assert not withdrawal_written
    assert decisions(withdrawn) == before
