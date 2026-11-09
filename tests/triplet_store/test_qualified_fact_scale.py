"""Persistent native projection -> semantic decisions -> precise sealing."""
from time import perf_counter
from itertools import islice, chain
import io
from semantica.triplet_store.extraction_records import F, _hash
from semantica.triplet_store.publication_records import PublicationRecords
from semantica.triplet_store.qualified_fact_index import QualifiedFactIndex
from tests.triplet_store.test_canonical_fact_publication import stage_duplicate_observations


def native_scale_fixture(tmp_path,count=56_700,groups=21_620):
    store,generation,original,_=stage_duplicate_observations(tmp_path)
    p=PublicationRecords(store,'p')
    ox=store._oxigraph
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
            # Construct the real immutable projection, including its integrity
            # digest. Timed code uses the production reader, never a DTO callback.
            graph=p.iri(reference.rsplit(':relation:',1)[0]+':fact-projection')
            fields=dict(buildAssertionId='a:'+str(number),buildRelationId='r:'+str(number),
                buildSourceId='urn:canonical:0',buildTargetId='urn:canonical:1',
                buildPredicate='owns')
            payload=[ox.Quad(node,ox.NamedNode(F+key),ox.Literal(value),graph) for key,value in fields.items()]
            child=p.iri(reference+':build-evidence:0')
            payload.extend([ox.Quad(node,ox.NamedNode(F+'buildEvidence'),child,graph),
                ox.Quad(child,ox.NamedNode(F+'position'),ox.Literal(0),graph),
                ox.Quad(child,ox.NamedNode(F+'referenceId'),ox.Literal('e:'+str(number)),graph)])
            yield from payload
            yield ox.Quad(node,ox.NamedNode(F+'factProjectionDigest'),ox.Literal(_hash(payload)),graph)
    from semantica.triplet_store.publication_records import _TripleStream
    def batches():
        batch=[]
        size=0
        for quad in quads():
            line=str(quad)+' .'
            amount=len(line.encode())+1
            if batch and size+amount>256*1024:
                yield batch
                batch=[]
                size=0
            batch.append(line)
            size+=amount
        if batch:
            yield batch
    iterator=iter(batches())
    while (first:=next(iterator,None)) is not None:
        with io.BufferedReader(_TripleStream(chain((first,),islice(iterator,127)))) as source:
            store.store.bulk_load(input=source,format=ox.RdfFormat.N_QUADS)
    store.flush()
    return store,generation,references


def test_cold_fact_index_reduction_and_completion_at_esg_scale(tmp_path):
    store,generation,references=native_scale_fixture(tmp_path)
    index=QualifiedFactIndex(store,'p',generation)
    p=index.publication
    timings={}
    original_input=index._physical_rows
    original_reduce=index._reduce_partition
    timings['native_read']=timings['semantic_reduce']=0
    def timed_input():
        iterator=iter(original_input())
        while True:
            started=perf_counter()
            item=next(iterator,None)
            timings['native_read']+=perf_counter()-started
            if item is None:
                return
            yield item
    def timed_reduce(*args):
        started=perf_counter()
        result=original_reduce(*args)
        timings['semantic_reduce']+=perf_counter()-started
        return result
    original_mutate=p.mutate
    original_flush=store.flush
    def timed_flush():
        started=perf_counter()
        result=original_flush()
        if 'completion_commit' in timings:
            timings['completion_commit']+=perf_counter()-started
        return result
    store.flush=timed_flush
    def timed_commit(*args,**kwargs):
        started=perf_counter()
        result=original_mutate(*args,**kwargs)
        timings['completion_commit']=perf_counter()-started
        return result
    p.mutate=timed_commit
    index._physical_rows=timed_input
    index._reduce_partition=timed_reduce
    try:
        with p.build_scope(generation),p.checkpointed(generation):
            started=perf_counter()
            index.reconcile_and_stage(input_key='scale-input')
            timings['read_sort_reduce_commit']=perf_counter()-started
            print('native decision build:',timings,flush=True)
            started=perf_counter()
            assert p.fact_stage_status(generation,'scale-input') is True
            timings['reuse']=perf_counter()-started
        print('56,700 physical observations / 21,620 groups:',timings,flush=True)
        assert timings['reuse']<0.1, timings
        assert timings['completion_commit']<5, timings
    finally:
        store.close()
