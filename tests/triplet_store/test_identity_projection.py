"""Identity hydration stores addresses and reuses accepted native values."""
import pytest
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.semantic_extract.types import Entity
from semantica.utils.exceptions import ProcessingError


def fixture(tmp_path):
    text = 'Ada works at ACME.'
    binding = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=0, window_end=len(text))
    store = OxigraphStore(tmp_path / 'facts')
    records = ExtractionRecords(store, binding, 'entities')
    entity = Entity('Ada', 'Person', 0, 3, .9, {'mention_id':'native-mention'})
    records.adopt([entity], text=text, accepted_digest='accepted', native_ranges=[dict(
        nativeRef='#/document/text', start=0, end=len(text), windowStart=0, windowEnd=len(text))])
    return store, records, records.entity_node(entity).value, text


def test_native_projection_hydrates_identity_without_retaining_text(tmp_path):
    from semantica.semantic_publication_builder import _entity_id, _span_id
    store, records, ref, text = fixture(tmp_path)
    mention = _entity_id('s', 'representation:r', 'Person', 0, 3)
    evidence = [_span_id('representation:r', 0, 3), _span_id('representation:r', 0, len(text))]
    metadata = dict(identity_scope='representation:r', identity_context_evidence_id=evidence[1],
                    extraction_method='model', source_ids=['s'])
    try:
        before = records.receipt()
        reopened = ExtractionRecords.from_identity_reference(store,'p',ref)
        assert reopened.binding==records.binding
        with pytest.raises(ProcessingError,match='binding'):
            ExtractionRecords.from_identity_reference(store,'foreign',ref)
        records.write_identity_projection(ref, mention_id=mention, representation_id='representation:r',
            context_start=0, context_end=len(text), evidence_ids=evidence, metadata=metadata)
        calls = []
        def read(start, end):
            calls.append((start,end))
            return text[start:end]
        value = records.read_identity_projection(ref, read_text=read)
        assert value == dict(id=mention, canonical_name='Ada', type='Person', description='', context=text,
            aliases=[], attributes={}, evidence_ids=evidence, status='candidate', metadata=metadata)
        assert calls == [(0,len(text))]
        assert records.receipt() == before
        assert all(text not in str(q) for q in store.store.quads_for_pattern(
            None,None,None,records.identity_projection_graph))
        with pytest.raises(ProcessingError,match='byte budget'):
            records.read_identity_projection(ref, read_text=read, max_bytes=8)
        with pytest.raises(ProcessingError,match='differs'):
            records.write_identity_projection(ref, mention_id='changed', representation_id='representation:r',
                context_start=0, context_end=len(text), evidence_ids=evidence, metadata=metadata)
    finally:
        store.close()


def test_identity_projection_preserves_native_profile_after_restart(tmp_path):
    text = 'Ada works at ACME.'
    binding = dict(project='p', source='s', material='m', representation='r', recipe='recipe',
        model='model', specification='spec', parser='parser', grounding='grounding',
        window_start=50, window_end=50+len(text))
    store = OxigraphStore(tmp_path / 'facts')
    records = ExtractionRecords(store,binding,'entities')
    profile = dict(description='works at ACME',evidence_start=0,evidence_end=len(text),
                   evidence=text, owner='ACME',referent_kind='person')
    entity = Entity('Ada','Person',0,3,.9,dict(mention_id='m',identity_profile=profile))
    records.adopt([entity],text=text,accepted_digest='accepted',native_ranges=[dict(
        nativeRef='#/document/text',start=50,end=50+len(text),windowStart=0,windowEnd=len(text))])
    ref=records.entity_node(entity).value
    metadata=dict(identity_scope='representation:r',identity_context_evidence_id='context',
        extraction_method='model',source_ids=['s'],description_mention_id='mention',
        description_evidence_ids=['profile'],identity_profile=profile)
    records.write_identity_projection(ref,mention_id='mention',representation_id='representation:r',
        context_start=50,context_end=50+len(text),evidence_ids=['mention-ev','context','profile'],metadata=metadata)
    store.close()
    store=OxigraphStore(tmp_path / 'facts')
    records=ExtractionRecords(store,binding,'entities')
    try:
        summary=records.read_identity_summary(ref)
        assert summary['metadata']['description_evidence_ids']==['profile']
        assert 'identity_profile' not in summary['metadata']
        result=records.read_identity_projection(ref,read_text=lambda a,b:text[a-50:b-50])
        assert result['description']=='works at ACME'
        assert result['metadata']=={**metadata,'identity_profile':{**profile,
            'evidence_start':50,'evidence_end':50+len(text)}}
        assert result['evidence_ids']==['mention-ev','context','profile']
        selected=records.read_identity_selection(ref,description_grounded=True)
        assert selected=={**result,'context':'','metadata':{**result['metadata'],
            'identity_profile':{key:value for key,value in result['metadata']['identity_profile'].items()
                if key!='evidence'}}}
        assert selected['description']=='works at ACME'
        # Native profile descriptions were validated on acceptance; scalar field
        # selection does not need to ground the same quote a second time.
        assert records.read_identity_selection(ref,description_grounded=False)==selected
        with pytest.raises(ProcessingError,match='grounding observation'):
            records.read_identity_selection(ref,description_grounded=1)
        with pytest.raises(ProcessingError,match='source range'):
            records.read_identity_projection(ref,read_text=lambda a,b:'')
        graph=records.identity_projection_graph
        store.store.update('DELETE WHERE { GRAPH '+str(graph)+' { <'+ref+'> <'+F+'contextStart> ?v } }')
        with pytest.raises(ProcessingError,match='corrupt'):
            records.read_identity_projection(ref,read_text=lambda a,b:text[a-50:b-50])
    finally:
        store.close()


def test_identity_projection_rejects_unowned_context_and_unbounded_addresses(tmp_path):
    store,records,ref,text=fixture(tmp_path)
    metadata=dict(identity_scope='r',identity_context_evidence_id='context',extraction_method='model',source_ids=['s'])
    arguments=dict(mention_id='mention',representation_id='r',context_start=0,
        context_end=len(text),evidence_ids=['evidence'],metadata=metadata)
    try:
        with pytest.raises(ProcessingError,match='membership'):
            records.write_identity_projection('urn:foreign',**arguments)
        with pytest.raises(ProcessingError,match='contain'):
            records.write_identity_projection(ref,**{**arguments,'context_start':4})
        with pytest.raises(ProcessingError,match='address budget'):
            records.write_identity_projection(ref,**{**arguments,'evidence_ids':['x']*129})
        with pytest.raises(ProcessingError,match='address budget'):
            records.write_identity_projection(ref,**{**arguments,'evidence_ids':[{}]})
        with pytest.raises(ProcessingError,match='metadata'):
            records.write_identity_projection(ref,**{**arguments,'metadata':{**metadata,'body':text}})
    finally:
        store.close()


def test_native_identity_projection_matches_build_source_oracle(tmp_path, monkeypatch):
    """Compare hydrated native identities with the actual source builder output."""
    from semantica import semantic_publication_builder as builder
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    from semantica.triplet_store.extraction_records import BINDING
    from tests.test_semantic_artifact import _request
    source=tmp_path/'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine. Ada Lovelace worked in London.')
    original=builder._build_source
    checked=[]
    def inspect(*args,**kwargs):
        built=original(*args,**kwargs)
        _,store,_=builder._native_build.get()
        evidence={span.id:span for span in built['evidence']}
        for entity in built['entities']:
            context=evidence[entity.metadata['identity_context_evidence_id']].locator
            for ref in built['native_entity_refs'][entity.id]:
                operation=store._oxigraph.NamedNode(ref.rsplit(':entity:',1)[0])
                binding={}
                for key in BINDING:
                    rows=list(store.store.quads_for_pattern(operation,
                        store._oxigraph.NamedNode(F+'binding'+key[0].upper()+key[1:]),None,None))
                    assert len(rows)==1
                    value=rows[0].object.value
                    binding[key]=int(value) if key in {'window_start','window_end'} else value
                records=ExtractionRecords(store,binding,'entities')
                records.write_identity_projection(ref,mention_id=entity.id,
                    representation_id=built['representation'].id,context_start=context.start_char,
                    context_end=context.end_char,evidence_ids=entity.evidence_ids,metadata=entity.metadata)
                actual=records.read_identity_projection(ref,read_text=lambda a,b:built['text'][a:b])
                assert actual['id'] == entity.id
                assert actual['evidence_ids'] == entity.evidence_ids
                assert actual['metadata'] == entity.metadata
                assert actual['canonical_name'] in {'Ada Lovelace', 'Analytical Engine'}
                checked.append(ref)
        return built
    monkeypatch.setattr(builder,'_build_source',inspect)
    builder.build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(
        _request(source,tmp_path/'out')['params']))
    assert checked


def test_withdrawal_fences_projection_consumers_without_destroying_accepted_work(tmp_path):
    store, records, ref, text = fixture(tmp_path)
    metadata = dict(identity_scope='r', identity_context_evidence_id='context',
        extraction_method='model', source_ids=['s'])
    records.write_identity_projection(ref, mention_id='mention', representation_id='r',
        context_start=0, context_end=len(text), evidence_ids=['evidence'], metadata=metadata)
    receipt = records.receipt()
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=1)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r', recipe='recipe',
        operation_count=1, operations=[receipt['operation_id']])])
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:ada', representative=ref, members=[ref], selectors=[], member_count=len([ref]), selector_count=len([]))])
    indexes = dict(keyword=dict(kind='native-keyword', store_id='kw', recipe_digest='recipe'),
        semantic=dict(kind='native-vector', store_id='vectors', recipe_digest='recipe', space_id='space'))
    store.activate_publication('p', generation, indexes=indexes)
    store.withdraw_publication('p', expected_generation=generation)
    with pytest.raises(ProcessingError, match='not ready'):
        store.read_native_records('p', generation, [ref])
    binding = records.binding
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    try:
        records = ExtractionRecords(store, binding, 'entities')
        assert records.receipt() == receipt
        assert records.read_identity_projection(ref, read_text=lambda a,b:text[a:b])['canonical_name'] == 'Ada'
        with pytest.raises(ProcessingError, match='not ready'):
            store.read_native_records('p', generation, [ref])
    finally:
        store.close()


def test_completion_reads_stay_bounded_across_native_mutation(tmp_path, monkeypatch):
    """Completion reads never enumerate payloads; explicit audits detect unread damage."""
    store, records, ref, text = fixture(tmp_path)
    records.write_identity_projection(ref, mention_id='mention', representation_id='r',
        context_start=0, context_end=len(text), evidence_ids=['evidence'], metadata={'source_ids':['s'], 'identity_scope':'r', 'identity_context_evidence_id':'evidence', 'extraction_method':'model'})
    records.receipt()
    scans = []
    native_read = store.store.quads_for_pattern
    def observed(subject, predicate, value, graph):
        if graph == records.graph and predicate is None:
            scans.append(subject)
        return native_read(subject, predicate, value, graph)
    native = store.store
    monkeypatch.setattr(native, 'quads_for_pattern', observed)
    try:
        reopened = ExtractionRecords.from_identity_reference(store, 'p', ref)
        reopened.read_identity_projection(ref, read_text=lambda a,b:text[a:b])
        assert scans == []
        generation = store.begin_publication('p', expected_generation=None, source_count=0, canonical_count=0)['generation']
        reopened.read_identity_projection(ref, read_text=lambda a,b:text[a:b])
        assert scans == []
        # A derived writer cannot target the accepted fact graph.
        with pytest.raises(ProcessingError, match='cannot target'):
            store._update_derived_graph(records.graph, insert='')
        # Completion remains a header lookup; explicit audit detects fact loss.
        quad = next(native_read(records.ox.NamedNode(ref), records.ox.NamedNode(F+'name'), None, records.graph))
        store.store.remove(quad)
        assert records.receipt() is not None
        with pytest.raises(ProcessingError, match='corrupt'):
            records.audit()
    finally:
        store.close()


def test_identity_summary_reads_no_original_text_attributes_or_model_receipts(tmp_path,monkeypatch):
    store,records,ref,text=fixture(tmp_path)
    metadata=dict(identity_scope='r',identity_context_evidence_id='context',
        extraction_method='model',source_ids=['s'])
    try:
        records.write_identity_projection(ref,mention_id='mention',representation_id='r',
            context_start=0,context_end=len(text),evidence_ids=['evidence'],metadata=metadata)
        def forbidden(*args,**kwargs):
            raise AssertionError('A member summary must not hydrate entity fields or text')
        monkeypatch.setattr(records,'read_identity_projection',forbidden)
        original_values=records.values
        def values(node,key):
            if key in ('attribute','modelReceipt','receipt'): forbidden()
            return original_values(node,key)
        monkeypatch.setattr(records,'values',values)
        assert records.read_identity_summary(ref)==dict(id='mention',canonical_name='Ada',type='Person',
            aliases=[],evidence_ids=['evidence'],metadata=metadata)
        with pytest.raises(ProcessingError,match='byte budget'):
            records.read_identity_summary(ref,max_bytes=1)
    finally:
        store.close()


def test_identity_selection_uses_grounding_observation_without_reading_prose(tmp_path):
    from semantica.semantic_extract.schema import ExtractionSpecification
    text='Ada works at ACME.'
    binding=dict(project='p',source='s',material='m',representation='r',recipe='recipe',
        model='model',specification='spec',parser='parser',grounding='grounding',
        window_start=0,window_end=len(text))
    store=OxigraphStore(tmp_path/'facts')
    records=ExtractionRecords(store,binding,'entities')
    entity=Entity('Ada','Person',0,3,.9,{'mention_id':'m'},attributes={'description':'works at ACME'})
    specification=ExtractionSpecification.model_validate(dict(id='spec',version='1',entity_types=[dict(
        name='Person',description='person',attributes={'description':dict(type='string',description='description')})]))
    try:
        records.adopt([entity],text=text,accepted_digest='accepted',extraction_spec=specification,
            native_ranges=[dict(nativeRef='#/document/text',start=0,end=len(text),windowStart=0,windowEnd=len(text))])
        ref=records.entity_node(entity).value
        records.write_identity_projection(ref,mention_id='m',representation_id='r',
            context_start=0,context_end=len(text),evidence_ids=['mention'],metadata=dict(
                source_ids=['s'],identity_scope='r',identity_context_evidence_id='mention',extraction_method='model'))
        result=records.read_identity_selection(ref,description_grounded=True)
        assert result['description']=='works at ACME'
        assert result['context']==''
        assert result['attributes']==entity.attributes
        assert records.read_identity_selection(ref,description_grounded=False)['description']==''
        with pytest.raises(ProcessingError,match='byte budget'):
            records.read_identity_selection(ref,description_grounded=True,max_bytes=8)
    finally:
        store.close()
