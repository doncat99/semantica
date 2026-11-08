"""Exact component hydration supplies canonical DTOs without a project cache."""
import pytest

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import KnowledgeEntity
from semantica.triplet_store.identity_candidate_index import IdentityCandidateIndex
from tests.triplet_store.test_build_record_cursor import staged


@pytest.mark.parametrize('model_recipe',[False,True])
def test_native_canonical_entities_match_oracle_and_skip_unrelated_components(tmp_path,model_recipe,monkeypatch):
    store,generation,refs=staged(tmp_path,3,canonical_count=None)
    mentions=[KnowledgeEntity(id='urn:canonical:'+str(n),canonical_name=name,type='ORG',
        aliases=['Alias '+str(n)],description='Description '+str(n),context='Context '+str(n),
        evidence_ids=['e'+str(n)],attributes={'sector':'Energy'},
        metadata={'source_ids':['source-'+str(n)]})
        for n,name in enumerate(['Shared','Shared','Unrelated'])]
    def row(entity):
        return dict(id=entity.id,name=entity.canonical_name,type=entity.type,
            aliases=entity.aliases,properties=entity.attributes,description=entity.description,
            context=entity.context,evidence_ids=entity.evidence_ids,metadata=entity.metadata)
    resolver=builder.EntityResolver(strategy='contextual')
    index=IdentityCandidateIndex(store,'p',generation,resolver.duplicate_detector)
    try:
        index.build(lambda:iter(zip(refs,map(row,mentions))),resolve_candidates=model_recipe)
        if model_recipe:
            oracle,_,_=builder._resolve_native_entities(mentions,resolver=resolver,context_prepared=True)
            selections=resolver.resolution_selections
        else:
            oracle=mentions
            selections={entity.id:dict(representative=entity.id,members=[entity.id]) for entity in mentions}
        mapping=dict(zip((entity.id for entity in mentions),refs))
        for entity in oracle:
            selected=selections[entity.id]
            store.stage_publication_canonical('p',generation,[dict(id=entity.id,
                representative=mapping[selected['representative']],
                members=[mapping[member] for member in selected['members']],
                member_count=len(selected['members']),selectors=[dict(field=field,record=mapping[origin])
                    for field,origins in selected.get('field_sources',{}).items() for origin in origins],
                selector_count=sum(len(origins) for origins in selected.get('field_sources',{}).values()))])
        store.seal_publication_canonical_count('p',generation,len(oracle))
        def forbidden(*args,**kwargs):
            raise AssertionError('Reading completed canonical decisions must not run a resolver or restore a component')
        monkeypatch.setattr(builder,'_resolve_native_entities',forbidden)
        monkeypatch.setattr(index,'hydrate_component',forbidden)
        summaries=[]
        def summarize(ref):
            summaries.append(ref)
            entity=mentions[refs.index(ref)]
            return {key:value for key,value in entity.model_dump().items()
                if key in {'id','canonical_name','type','aliases','evidence_ids','metadata'}}
        hydrated=[]
        def hydrate(ref):
            hydrated.append(ref)
            return mentions[refs.index(ref)].model_copy(deep=True)
        def serialized(values):
            return sorted((value.model_dump(mode='json') for value in values),key=lambda value:value['id'])
        assert serialized(builder._native_canonical_entities(index,hydrate,summarize=summarize,
            model_recipe=model_recipe))==serialized(oracle)
        assert len(hydrated)<=len(refs)
        assert len(summaries)==len(refs)
        target=next(entity for entity in oracle if 'e0' in entity.evidence_ids)
        hydrated.clear()
        assert serialized(builder._native_canonical_entities(index,hydrate,summarize=summarize,
            model_recipe=model_recipe,ids=[target.id]))==serialized([target])
        assert refs[2] not in hydrated
        hydrated.clear()
        assert serialized(builder._native_canonical_entities(index,hydrate,summarize=summarize,
            model_recipe=model_recipe,evidence_ids=['e0']))==serialized([target])
        assert refs[2] not in hydrated
        assert list(builder._native_canonical_entities(index,hydrate,summarize=summarize,
            model_recipe=model_recipe,ids=[]))==[]
    finally:
        store.close()


def test_canonical_reads_apply_decisions_without_hydrating_unselected_members(tmp_path,monkeypatch):
    from semantica.triplet_store.extraction_records import F
    store,generation,refs=staged(tmp_path,3,canonical_count=None)
    resolver=builder.EntityResolver(strategy='contextual')
    index=IdentityCandidateIndex(store,'p',generation,resolver.duplicate_detector)
    mentions=[KnowledgeEntity(id='mention:'+str(n),canonical_name='Name '+str(n),type='ORG',
        context='Context '+str(n),description='Description '+str(n),evidence_ids=['ev:'+str(n)],
        attributes={'metric':n},metadata={'source_ids':['source:'+str(n)],
            'description_evidence_ids':['description:'+str(n)]}) for n in range(3)]
    def row(entity):
        return dict(id=entity.id,name=entity.canonical_name,type=entity.type,properties=entity.attributes,
            aliases=[],description=entity.description,context=entity.context,evidence_ids=entity.evidence_ids,
            metadata=entity.metadata)
    try:
        index.build(lambda:iter(zip(refs,map(row,mentions))),resolve_candidates=False)
        p=index.publication
        attr=refs[1].rsplit(':entity:',1)[0]+':selected-test-attribute'
        operation=refs[1].rsplit(':entity:',1)[0]
        store.store.update('INSERT DATA { GRAPH '+str(p.facts)+' { <'+operation+'> <'+F+'ownedRecord> <'+attr+'> . '
            '<'+refs[1]+'> <'+F+'attribute> <'+attr+'> . <'+attr+'> <'+F+'attributeName> "metric" ; <'+F+'attributeType> "integer" ; <'+F+'value> 37 . } }')
        selectors=[dict(field='name',record=refs[1]),dict(field='type',record=refs[0]),
            dict(field='description',record=refs[1]),dict(field='properties.metric',record=attr)]
        store.stage_publication_canonical('p',generation,[dict(id='canonical:test',representative=refs[0],
            members=refs,member_count=3,selectors=selectors,selector_count=len(selectors))])
        store.seal_publication_canonical_count('p',generation,1)
        def forbidden(*args,**kwargs): raise AssertionError('resolver forbidden on canonical read')
        monkeypatch.setattr(builder,'_resolve_native_entities',forbidden)
        monkeypatch.setattr(index,'hydrate_component',forbidden)
        hydrated=[]
        def hydrate(ref):
            hydrated.append(ref)
            return mentions[refs.index(ref)].model_copy(deep=True)
        def summarize(ref):
            entity=mentions[refs.index(ref)]
            return {key:value for key,value in entity.model_dump().items()
                if key in {'id','canonical_name','type','aliases','evidence_ids','metadata'}}
        entity,=builder._native_canonical_entities(index,hydrate,summarize=summarize,model_recipe=True)
        assert entity.id=='canonical:test'
        assert entity.canonical_name=='Name 1'
        assert entity.description=='Description 1'
        assert entity.context=='Context 1'
        assert entity.attributes=={'metric':37}
        assert entity.evidence_ids==['ev:0','ev:1','ev:2']
        assert entity.aliases==['Name 0','Name 2']
        assert entity.metadata['description_mention_id']=='mention:1'
        assert entity.metadata['mention_ids']==['mention:0','mention:1','mention:2']
        assert entity.metadata['source_ids']==['source:0','source:1','source:2']
        assert hydrated==refs[:2]
    finally:
        store.close()


def test_completed_identity_stage_reuses_native_decisions_after_restart(tmp_path, monkeypatch):
    """Release/vector changes cannot turn complete identity output into new work."""
    from copy import deepcopy
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.publication_records import PublicationRecords
    from tests.test_semantic_artifact import _request

    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine. Ada Lovelace worked in London.')
    params = _request(source, tmp_path / 'out')['params']

    def forbidden(*args, **kwargs):
        raise AssertionError('Completed identity decisions must not be rebuilt or re-resolved')

    # This complete deterministic build must stay entirely local.
    monkeypatch.setattr(builder, '_relay_json', forbidden)
    monkeypatch.setattr(builder, '_organization_report_product', forbidden)

    def build(parameters):
        events = []
        result = builder.build_semantic_artifacts(
            SemanticArtifactBuildRequest.model_validate(parameters), progress=events.append)
        completed = [event['metadata'] for event in events
            if event.get('stage') == 'entity_resolution'
            and event.get('metadata', {}).get('state') == 'completed']
        assert len(completed) == 1
        return result, completed[0]

    def decisions():
        # The builder closed its store: this read is across a real close/reopen.
        store = OxigraphStore(params['nativeStoreDir'])
        try:
            p = PublicationRecords(store, params['projectId'])
            rows = []
            for node in p.values(p.head, 'canonical'):
                members, selectors = p._canonical_references(node)
                rows.append((node.value, tuple(sorted(members)),
                    tuple(sorted((item['field'], item['record']) for item in selectors))))
            return p.one(p.head, 'identityStageInput'), tuple(sorted(rows))
        finally:
            store.close()

    _, cold = build(params)
    before = decisions()
    assert cold['canonicalEntities'] > 0
    assert not cold.get('reused', False)
    assert before[1]

    original_build = IdentityCandidateIndex.build
    with monkeypatch.context() as guarded:
        guarded.setattr(IdentityCandidateIndex, 'build', forbidden)
        guarded.setattr(IdentityCandidateIndex, 'hydrate_component', forbidden)
        guarded.setattr(builder, '_resolve_native_entities', forbidden)
        warm_params = deepcopy(params)
        warm_params['release']['artifactDigest'] = 'sha256:' + 'f' * 64
        warm_params['relays']['embedding']['modelId'] = 'other-vector-space'
        _, warm = build(warm_params)
    assert warm['reused'] is True
    assert warm['canonicalEntities'] == cold['canonicalEntities']
    assert decisions() == before

    # A real material change must invalidate this stage, even after warm reuse.
    source.write_text('Ada Lovelace designed the Analytical Engine. Charles Babbage worked in London.')
    changed = _request(source, tmp_path / 'changed-out')['params']
    calls = []
    def record_build(self, *args, **kwargs):
        calls.append(True)
        return original_build(self, *args, **kwargs)
    monkeypatch.setattr(IdentityCandidateIndex, 'build', record_build)
    _, recomputed = build(changed)
    assert calls == [True]
    assert not recomputed.get('reused', False)
    assert decisions()[0] != before[0]


def test_canonical_metadata_preserves_owner_only_identity_profile(tmp_path):
    """A profile carries identity evidence even when it selects no description."""
    store, generation, refs = staged(tmp_path, 2, canonical_count=None)
    profile = dict(owner='ACME', referent_kind='organization', evidence='ACME board',
        evidence_start=0, evidence_end=10)
    mentions = [KnowledgeEntity(id='member-'+str(n), canonical_name='Board', type='ORG',
        evidence_ids=['e'+str(n)], metadata={'source_ids':['s'+str(n)],
            **({'identity_profile':profile, 'description_evidence_ids':['profile-evidence']} if n else {})})
        for n in range(2)]
    index = IdentityCandidateIndex(store, 'p', generation,
        builder.EntityResolver(strategy='contextual').duplicate_detector)
    try:
        index.build(lambda: iter((ref, dict(id=entity.id, name=entity.canonical_name,
            type=entity.type, properties={}, metadata=entity.metadata))
            for ref,entity in zip(refs,mentions)), resolve_candidates=False)
        store.stage_publication_canonical('p',generation,[dict(id='urn:canonical:board',
            representative=refs[0],members=refs,member_count=2,
            selectors=[dict(field='name',record=refs[0]),dict(field='type',record=refs[0]),
                dict(field='identity_profile',record=refs[1])],selector_count=3)])
        store.seal_publication_canonical_count('p',generation,1)
        def summary(ref):
            item=mentions[refs.index(ref)].model_dump()
            item['metadata']={key:value for key,value in item['metadata'].items()
                if key != 'identity_profile'}
            return item
        hydrated=[]
        def selected(ref):
            hydrated.append(ref)
            return mentions[refs.index(ref)].model_copy(deep=True)
        result=list(builder._native_canonical_entities(index,selected,
            summarize=summary,model_recipe=True))
        assert result[0].metadata['identity_profile']==profile
        assert result[0].metadata['description_evidence_ids']==['profile-evidence']
        assert hydrated==refs
    finally:
        store.close()
