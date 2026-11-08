"""Isolated storage/reducer scale; excludes extraction and model quality."""
from time import perf_counter

from semantica.semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation
from semantica.triplet_store.extraction_records import F
from semantica.triplet_store.publication_records import PublicationRecords, P
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations


def test_cold_fact_index_reduction_and_completion_at_esg_scale(tmp_path):
    store,generation,original,_=stage_duplicate_observations(tmp_path)
    p=PublicationRecords(store,'p')
    ox=store._oxigraph
    count,groups=56_700,21_620
    # Storage fixture only: construct native addresses and fields directly.
    template=list(store.store.quads_for_pattern(p.iri(original[0]),None,None,p.facts))
    operation=p.iri(original[0].rsplit(':relation:',1)[0])
    references=original+[operation.value+':relation:'+str(i) for i in range(1,count-1)]
    def quads():
        for number,reference in enumerate(references):
            node=p.iri(reference)
            if number>=2:
                yield ox.Quad(operation,ox.NamedNode(F+'ownedRecord'),node,p.facts)
                for quad in template:
                    yield ox.Quad(node,quad.predicate,quad.object,p.facts)
            yield ox.Quad(node,ox.NamedNode(F+'time'),ox.Literal(str(number%groups)),p.facts)
    store.store.extend(quads())
    store.flush()
    positions={reference:number for number,reference in enumerate(references)}
    def read(reference,kind,observation=None):
        number=positions[reference]
        shared=dict(qualifiers=dict(polarity='positive',time=str(number%groups)),evidence_ids=['e:'+str(number)])
        if kind=='assertion':
            return KnowledgeAssertion(id='a:'+str(number),subject_id='urn:canonical:0',
                predicate='owns',object='Engine',object_entity_id='urn:canonical:1',**shared).model_dump()
        return KnowledgeRelation(id='r:'+str(number),source_entity_id='urn:canonical:0',
            target_entity_id='urn:canonical:1',type='owns',**shared).model_dump()
    index=QualifiedFactIndex(store,'p',generation)
    p=index.publication
    timings={}
    try:
        with p.build_scope(generation),p.checkpointed(generation):
            started=perf_counter()
            index.build((reference,kind,read(reference,kind)) for reference in references for kind in ('assertion','relation'))
            timings['index']=perf_counter()-started
            print('scale index:',timings,flush=True)
            started=perf_counter()
            claims,links,selected,facts=[],[],{},[]
            members=0
            completed=0
            for assertions,relations,_,supports,selections in index.iter_reconciled(read):
                claims.extend(assertions)
                links.extend(relations)
                selected.update(selections)
                for relation in relations:
                    refs,representative=supports[relation.id]
                    facts.append(dict(id=relation.id,source=relation.source_entity_id,target=relation.target_entity_id,
                        representative=representative,members=refs,member_count=len(refs),status=relation.status))
                    members+=len(refs)
                if len(claims)+len(links)>=128:
                    index.stage_reconciled(claims,links,references=selected)
                    claims,links,selected=[],[],{}
                if members>=120:
                    p.stage_facts(generation,facts)
                    facts=[]
                    members=0
                completed+=1
            if claims or links:
                index.stage_reconciled(claims,links,references=selected)
            if facts:
                p.stage_facts(generation,facts)
            timings['reduce_and_stage']=perf_counter()-started
            assert completed==groups
            print('scale reduction:',timings,flush=True)
            started=perf_counter()
            p.seal_fact_stage(generation,'scale-input')
            timings['seal']=perf_counter()-started
            started=perf_counter()
            assert p.fact_stage_status(generation,'scale-input') is True
            timings['reuse']=perf_counter()-started
        print('56,700 native observations / 21,620 groups:',timings,flush=True)
        assert sum(timings.values())<180, timings
        assert timings['reuse']<0.1, timings
    finally:
        store.close()
