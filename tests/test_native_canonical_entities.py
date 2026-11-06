"""Exact component hydration supplies canonical DTOs without a project cache."""
import pytest

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import KnowledgeEntity
from semantica.triplet_store.identity_candidate_index import IdentityCandidateIndex
from tests.triplet_store.test_build_record_cursor import staged


@pytest.mark.parametrize('model_recipe',[False,True])
def test_native_canonical_entities_match_oracle_and_skip_unrelated_components(tmp_path,model_recipe):
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
                member_count=len(selected['members']),selectors=[],selector_count=0)])
        store.seal_publication_canonical_count('p',generation,len(oracle))
        hydrated=[]
        def hydrate(ref):
            hydrated.append(ref)
            return mentions[refs.index(ref)].model_copy(deep=True)
        def serialized(values):
            return sorted((value.model_dump(mode='json') for value in values),key=lambda value:value['id'])
        assert serialized(builder._native_canonical_entities(index,hydrate,resolver=resolver,
            model_recipe=model_recipe))==serialized(oracle)
        assert len(hydrated)==len(refs)
        target=next(entity for entity in oracle if 'e0' in entity.evidence_ids)
        hydrated.clear()
        assert serialized(builder._native_canonical_entities(index,hydrate,resolver=resolver,
            model_recipe=model_recipe,ids=[target.id]))==serialized([target])
        assert refs[2] not in hydrated
        hydrated.clear()
        assert serialized(builder._native_canonical_entities(index,hydrate,resolver=resolver,
            model_recipe=model_recipe,evidence_ids=['e0']))==serialized([target])
        assert refs[2] not in hydrated
        assert list(builder._native_canonical_entities(index,hydrate,resolver=resolver,
            model_recipe=model_recipe,ids=[]))==[]
    finally:
        store.close()
