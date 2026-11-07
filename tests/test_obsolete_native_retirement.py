"""Offline retirement never deletes current owners or externally referenced facts."""
import importlib.util
import json
import runpy
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'.github/scripts/retire_obsolete_native_results.py'
spec = importlib.util.spec_from_file_location('retirement', SCRIPT)
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)


def test_operation_pages_group_sources_without_loss_or_repeated_native_sort(tmp_path):
    import pyoxigraph as ox
    from types import SimpleNamespace
    store = ox.Store()
    graph = ox.NamedNode('urn:project')
    field = 'urn:semantica:field:'
    expected = []
    for i in range(515):
        op = ox.NamedNode(f'urn:op:{i:04d}')
        source = f'source-{i % 3}'
        recipe = 'obsolete' if i % 5 else 'protected'
        store.add(ox.Quad(op, ox.NamedNode(field+'bindingRecipe'), ox.Literal(recipe), graph))
        store.add(ox.Quad(op, ox.NamedNode(field+'bindingSource'), ox.Literal(source), graph))
        if recipe == 'obsolete':
            expected.append((source, op.value, recipe))
    class IndexedOnly:
        def quads_for_pattern(self, *args):
            return store.quads_for_pattern(*args)
        def query(self, *args):
            pytest.fail('Maintenance must not repeatedly sort the full native operation set')
    owner = SimpleNamespace(_oxigraph=ox, store=IndexedOnly())
    pages = list(retirement.operation_pages(owner, graph, {'obsolete'}))
    assert len(pages) > 3 and all(0 < len(page) <= 128 for page in pages)
    actual = [(row['source'], row['op'].value, row['recipe'].value) for page in pages for row in page]
    assert actual == sorted(expected)
    assert len({row[1] for row in actual}) == len(expected)
    all_rows = [row for page in retirement.operation_pages(owner, graph) for row in page]
    assert len(all_rows) == 515
    reduction = ox.NamedNode('urn:classification-reduction')
    store.add(ox.Quad(reduction, ox.NamedNode(field+'bindingRecipe'), ox.Literal('obsolete'), graph))
    missing_source = [row for page in retirement.operation_pages(owner, graph, {'obsolete'}) for row in page]
    assert missing_source[0]['op'] == reduction and missing_source[0]['source'] == ''
    store.add(ox.Quad(ox.NamedNode('urn:op:0001'), ox.NamedNode(field+'bindingSource'), ox.Literal('conflicting'), graph))
    with pytest.raises(ValueError, match='source is duplicated'):
        list(retirement.operation_pages(owner, graph, {'obsolete'}))


@pytest.mark.parametrize('padding,expected_batches', [(0,3),(1000,5)])
def test_apply_groups_exact_subject_graph_pairs_into_bounded_atomic_updates(tmp_path,padding,expected_batches):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    cache_path = tmp_path/'accepted.sqlite'
    cache = sqlite3.connect(cache_path)
    cache.executescript('CREATE TABLE cache(namespace,key,value,accepted_digest); CREATE TABLE accepted_receipts(namespace,key,digest);')
    cache.close()
    keep_graph = ox.NamedNode('urn:keep')
    for i in range(259):
        node = ox.NamedNode('urn:node:'+str(i)+'x'*padding); graph = ox.NamedNode('urn:graph:'+str(i % 3))
        owner.store.add(ox.Quad(node, ox.NamedNode('urn:p'), ox.Literal('obsolete'), graph))
        owner.store.add(ox.Quad(node, ox.NamedNode('urn:p'), ox.Literal('protected'), keep_graph))
        plan.execute('INSERT INTO nodes VALUES(?,?)', (node.value,graph.value))
        digest,count = retirement.node_proof(owner,node.value,graph.value)
        plan.execute('INSERT INTO node_proofs VALUES(?,?,?,?)',(node.value,graph.value,digest,count))
    plan.commit()
    updates = []
    native = owner.store
    class CountingStore:
        def __getattr__(self, name):
            return getattr(native, name)
        def __iter__(self):
            return iter(native)
        def update(self, statement):
            updates.append(statement)
            native.update(statement)
    owner.store = CountingStore()
    retirement.apply_plan(owner,plan,cache_path)
    assert len(updates) == expected_batches
    assert all(statement.count('( <urn:node:') <= 128 and len(statement.encode()) <= 65536 for statement in updates)
    assert sum(1 for _ in owner.store.quads_for_pattern(None,None,None,keep_graph)) == 259
    assert sum(1 for _ in owner.store) == 259
    plan.close(); owner.close()


def test_full_inventory_protects_current_and_blocks_unclassified_owners(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    fixture = runpy.run_path(str(Path(__file__).with_name('test_native_extraction_handoff.py')))
    child = fixture['run_child'](tmp_path, recipe='current')
    assert child.returncode == 0, child.stderr
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    accepted = sqlite3.connect((tmp_path/'accepted.sqlite').as_uri()+'?mode=ro', uri=True)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    def inventory(resume=False):
        retirement.inventory_all(owner, plan, accepted, tmp_path, 'project-1',
            {'current'}, {'obsolete'}, lambda binding: fixture['TEXT'], resume=resume)
    inventory()
    assert plan.execute("SELECT count(*) FROM inventory WHERE disposition='obsolete'").fetchone() == (0,)
    assert plan.execute("SELECT count(*) FROM inventory WHERE kind='operation' AND disposition='protected'").fetchone() == (2,)
    assert plan.execute('SELECT count(*) FROM cache_keys').fetchone() == (0,)
    assert plan.execute('SELECT count(*) FROM protected_receipts').fetchone()[0] > 0
    inventory(resume=True)
    graph = ox.NamedNode('urn:semantica:project:' + __import__('hashlib').sha256(b'project-1').hexdigest())
    unknown = ox.Quad(ox.NamedNode('urn:unknown-operation'),
        ox.NamedNode('urn:semantica:field:bindingRecipe'), ox.Literal('unreviewed'), graph)
    owner.store.add(unknown)
    with pytest.raises(ValueError, match='Unknown native recipe'):
        inventory(resume=True)
    owner.store.remove(unknown)
    orphan = ox.Quad(ox.NamedNode('urn:orphan-subject'),ox.NamedNode('urn:p'),ox.Literal('unclassified'),graph)
    owner.store.add(orphan)
    with pytest.raises(ValueError, match='Unclassified project fact subject'):
        inventory(resume=True)
    owner.store.remove(orphan)
    foreign = ox.Quad(ox.NamedNode('urn:foreign'), ox.NamedNode('urn:p'), ox.Literal('unclassified'), ox.NamedNode('urn:foreign-graph'))
    owner.store.add(foreign)
    with pytest.raises(ValueError, match='Unclassified native graph'):
        inventory(resume=True)
    owner.store.remove(foreign)
    owner.store.remove_graph(ox.NamedNode('urn:foreign-graph'))
    vector = tmp_path/'embedding-unreviewed.sqlite'
    conn = sqlite3.connect(vector)
    conn.execute('CREATE TABLE embedding_space(id,identity,dimension)')
    conn.execute('INSERT INTO embedding_space VALUES(1,?,2048)', (json.dumps(dict(recipe='unreviewed',binding='sha256:unreviewed',model='embedding')),))
    conn.commit(); conn.close()
    with pytest.raises(ValueError, match='Unknown native recipe'):
        inventory(resume=True)
    vector.unlink()
    operation = plan.execute("SELECT id FROM inventory WHERE kind='operation' LIMIT 1").fetchone()[0]
    mutation = ox.Quad(ox.NamedNode(operation),ox.NamedNode('urn:unexpected'),ox.Literal('changed'),graph)
    owner.store.add(mutation)
    from semantica.utils.exceptions import ProcessingError
    with pytest.raises((ValueError,ProcessingError), match='Inventory changed after certification|receipt missing or corrupt'):
        inventory(resume=True)
    owner.store.remove(mutation)
    accepted.close()
    cache = sqlite3.connect(tmp_path/'accepted.sqlite')
    cache.execute("INSERT INTO accepted_receipts VALUES('embedding','unknown-key','unknown-digest')")
    cache.commit(); cache.close()
    accepted = sqlite3.connect((tmp_path/'accepted.sqlite').as_uri()+'?mode=ro', uri=True)
    with pytest.raises(ValueError, match='Unclassified acceptance'):
        inventory(resume=True)
    assert next(owner.store.quads_for_pattern(None, None, None, graph), None) is not None
    plan.close(); accepted.close(); owner.close()


def test_exact_pending_publication_closure_rejects_ready_changed_and_protected(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.publication_records import PublicationRecords, P
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    records = PublicationRecords(owner,'project')
    status = records.begin(expected_generation=None,source_count=1,canonical_count=0)
    op = ox.NamedNode('urn:obsolete-operation')
    reference = ox.Quad(ox.NamedNode(records.graph.value+':source'),ox.NamedNode(P+'operation'),op,records.graph)
    owner.store.add(reference)
    with pytest.raises(ValueError,match='exact pending draft'):
        retirement.plan_pending_publication(owner,plan,'project','different-generation')
    with pytest.raises(ValueError,match='protected or unknown'):
        retirement.plan_pending_publication(owner,plan,'project',status['generation'])
    plan.execute('INSERT INTO operations VALUES(?,?,?,?,?)',(op.value,'obsolete','{}','{}','[]'))
    pending = ox.Quad(records.head,ox.NamedNode(P+'state'),ox.Literal('pending'),records.graph)
    ready = ox.Quad(records.head,ox.NamedNode(P+'state'),ox.Literal('withdrawn'),records.graph)
    owner.store.remove(pending); owner.store.add(ready)
    with pytest.raises(ValueError,match='exact pending draft'):
        retirement.plan_pending_publication(owner,plan,'project',status['generation'])
    owner.store.remove(ready); owner.store.add(pending)
    retirement.plan_pending_publication(owner,plan,'project',status['generation'])
    assert plan.execute('SELECT kind FROM graphs').fetchone() == ('pending-publication',)
    assert plan.execute('SELECT count(*) FROM nodes').fetchone() == plan.execute('SELECT count(*) FROM node_proofs').fetchone()
    retirement.assert_no_external_references(owner,plan)
    external = ox.Quad(ox.NamedNode('urn:current'),ox.NamedNode('urn:ref'),reference.subject,ox.NamedNode('urn:current-graph'))
    owner.store.add(external)
    with pytest.raises(ValueError,match='another owner references'):
        retirement.assert_no_external_references(owner,plan)
    owner.store.remove(external)
    plan.close(); owner.close()


def test_pending_publication_proof_streams_membership_beyond_window_byte_budget():
    import pyoxigraph as ox
    from types import SimpleNamespace
    graph = 'urn:semantica:publication:project'
    identity = graph+':head'
    def prove(reverse=False,changed=False):
        class StreamingStore:
            def quads_for_pattern(self,*_):
                for i in (reversed(range(400)) if reverse else range(400)):
                    yield ox.Quad(ox.NamedNode(identity),ox.NamedNode('urn:member'),
                        ox.Literal(str(i)+'x'*6000+('changed' if changed and i==399 else '')),ox.NamedNode(graph))
        return retirement.node_proof(SimpleNamespace(_oxigraph=ox,store=StreamingStore()),identity,graph)
    proof = prove()
    assert proof[1] == 400 and proof == prove(reverse=True)
    assert proof != prove(changed=True)


def test_full_inventory_obsolete_cleanup_resume_keeps_audit(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    fixture = runpy.run_path(str(Path(__file__).with_name('test_native_extraction_handoff.py')))
    child = fixture['run_child'](tmp_path, recipe='obsolete')
    assert child.returncode == 0, child.stderr
    owner = OxigraphStore(tmp_path/'facts')
    accepted_path = tmp_path/'accepted.sqlite'
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro',uri=True)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    ox = owner._oxigraph
    import hashlib
    facts = ox.NamedNode('urn:semantica:project:'+hashlib.sha256(b'project-1').hexdigest())
    operation = next(owner.store.quads_for_pattern(None,ox.NamedNode('urn:semantica:field:bindingRecipe'),None,facts)).subject
    projection = ox.NamedNode(operation.value+':identity-projection')
    quads = [ox.Quad(ox.NamedNode('urn:projection:'+str(i)),ox.NamedNode('urn:p'),ox.Literal('certified'),projection) for i in range(2)]
    for quad in quads:
        owner.store.add(quad)
    retirement.plan_facts(owner,plan,accepted,'project-1',{'obsolete'},lambda binding:fixture['TEXT'])
    retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},{'obsolete'},lambda binding:fixture['TEXT'])
    certificate = retirement.digest_rows(plan)
    accepted.close()
    # Crash after atomic operation-subject deletion, before its owned subjects
    # and acceptance keys: retained proofs must safely attribute that remainder.
    operation, = plan.execute('SELECT id FROM operations LIMIT 1').fetchone()
    graph, = plan.execute('SELECT graph FROM nodes WHERE id=?',(operation,)).fetchone()
    owner.store.update(f'DELETE WHERE {{ GRAPH {owner._oxigraph.NamedNode(graph)} {{ {owner._oxigraph.NamedNode(operation)} ?p ?o }} }}')
    owner.store.remove(quads[0])
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro',uri=True)
    mutation = ox.Quad(quads[1].subject,ox.NamedNode('urn:new-field'),ox.Literal('uncertified'),projection)
    owner.store.add(mutation)
    with pytest.raises(ValueError, match='Obsolete projection subject changed'):
        retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},{'obsolete'},lambda binding:fixture['TEXT'],resume=True)
    owner.store.remove(mutation)
    retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},{'obsolete'},lambda binding:fixture['TEXT'],resume=True)
    accepted.close()
    retirement.apply_plan(owner,plan,accepted_path,resume=True)
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro',uri=True)
    retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},{'obsolete'},lambda binding:fixture['TEXT'],resume=True)
    assert certificate==retirement.digest_rows(plan)
    assert plan.execute("SELECT count(*) FROM inventory WHERE kind='operation'").fetchone()==(2,)
    accepted.close();plan.close();owner.close()


def test_exact_operation_closure_references_and_physical_retirement(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    fixture = runpy.run_path(str(Path(__file__).with_name('test_native_extraction_handoff.py')))
    child = fixture['run_child'](tmp_path, recipe='obsolete')
    assert child.returncode == 0, child.stderr
    owner = OxigraphStore(tmp_path/'facts')
    accepted_path = tmp_path/'accepted.sqlite'
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro', uri=True)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_facts(owner, plan, accepted, 'project-1', {'obsolete'}, lambda binding: fixture['TEXT'])
    assert plan.execute('SELECT count(*) FROM operations').fetchone()[0] == 2
    assert plan.execute('SELECT count(*) FROM cache_keys').fetchone()[0] == 2
    identity = plan.execute('SELECT id FROM nodes LIMIT 1').fetchone()[0]
    ox = owner._oxigraph
    ref = ox.Quad(ox.NamedNode('urn:current'), ox.NamedNode('urn:reference'), ox.NamedNode(identity), ox.NamedNode('urn:publication'))
    owner.store.add(ref)
    with pytest.raises(ValueError, match='another owner references'):
        retirement.assert_no_external_references(owner, plan)
    owner.store.remove(ref)
    encoded = ox.Quad(ox.NamedNode('urn:current'), ox.NamedNode('urn:reference'), ox.Literal('{"reference":"' + identity.replace(':', '%3A') + '"}'), ox.NamedNode('urn:publication'))
    owner.store.add(encoded)
    with pytest.raises(ValueError, match='Encoded external reference'):
        retirement.assert_no_external_references(owner, plan)
    owner.store.remove(encoded)
    keep = ox.Quad(ox.NamedNode('urn:keep'), ox.NamedNode('urn:predicate'), ox.Literal('current'), ox.NamedNode('urn:current-graph'))
    owner.store.add(keep)
    certificate = retirement.digest_rows(plan)
    assert certificate == retirement.digest_rows(plan)
    accepted.close()
    retirement.apply_plan(owner, plan, accepted_path)
    assert keep in owner.store
    assert plan.execute('SELECT count(*) FROM operations').fetchone()[0] == 2
    cache = sqlite3.connect(accepted_path)
    assert cache.execute('SELECT count(*) FROM accepted_receipts').fetchone()[0] == 0
    cache.close()
    # A restart after any deletion phase can replay the retained certificate.
    retirement.apply_plan(owner, plan, accepted_path, resume=True)
    plan.close(); owner.close()
    reopened = OxigraphStore(tmp_path/'facts')
    assert keep in reopened.store
    assert len(reopened.store) == 1
    reopened.close()


def test_rebound_operation_retirement_removes_only_its_logical_index(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.extraction_records import ExtractionRecords
    fixture = runpy.run_path(str(Path(__file__).with_name('test_native_extraction_handoff.py')))
    child = fixture['run_child'](tmp_path, recipe='old-paid')
    assert child.returncode == 0, child.stderr
    child = fixture['run_child'](tmp_path, recipe='current', source='protected-source')
    assert child.returncode == 0, child.stderr
    owner = OxigraphStore(tmp_path/'facts')
    old = dict(project='project-1', source='source-1', material='material-1',
        representation='representation-1', recipe='old-paid', model='model-1',
        specification='specification-1', parser='parser-1', grounding='grounding-1',
        window_start=0, window_end=len(fixture['TEXT']))
    rebound = dict(old, recipe='obsolete-current-identity')
    for stage in ('entities', 'relations'):
        owner.rebind_extraction(old, rebound, stage)
    index = ExtractionRecords(owner, rebound, 'entities').index_graph
    assert len(list(owner.store.quads_for_pattern(None,None,None,index))) == 4
    accepted_path = tmp_path/'accepted.sqlite'
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro', uri=True)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_facts(owner,plan,accepted,'project-1',{'obsolete-current-identity'},lambda _:fixture['TEXT'])
    retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},
        {'obsolete-current-identity'},lambda _:fixture['TEXT'])
    assert plan.execute('SELECT count(*) FROM nodes WHERE graph=?',(index.value,)).fetchone() == (2,)
    protected_link = next(q for q in owner.store.quads_for_pattern(None,None,None,index)
        if not plan.execute('SELECT 1 FROM nodes WHERE id=? AND graph=?',(q.subject.value,index.value)).fetchone())
    owner.store.remove(protected_link)
    with pytest.raises(ValueError, match='Native operation identity or receipt differs'):
        retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},
            {'obsolete-current-identity'},lambda _:fixture['TEXT'],resume=True)
    owner.store.add(protected_link)
    accepted.close()
    retirement.apply_plan(owner,plan,accepted_path)
    assert len(list(owner.store.quads_for_pattern(None,None,None,index))) == 2
    assert owner.extraction_receipt(rebound, 'entities') is None
    accepted = sqlite3.connect(accepted_path.as_uri()+'?mode=ro', uri=True)
    retirement.inventory_all(owner,plan,accepted,tmp_path,'project-1',{'current'},
        {'obsolete-current-identity'},lambda _:fixture['TEXT'],resume=True)
    accepted.close(); plan.close(); owner.close()


def test_current_space_excluded_and_published_obsolete_space_blocks(tmp_path):
    cache = sqlite3.connect(':memory:')
    cache.execute('CREATE TABLE accepted_receipts(namespace,key,digest)')
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    path = tmp_path/'embedding-obsolete.sqlite'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE embedding_space(id,identity,dimension)')
    conn.execute('INSERT INTO embedding_space VALUES(1,?,2048)', (json.dumps({'binding':'sha256:obsolete','recipe':'old','model':'embedding'}),))
    conn.execute('CREATE TABLE embeddings_native_publications(project)')
    conn.execute("INSERT INTO embeddings_native_publications VALUES('project')")
    conn.commit();conn.close()
    with pytest.raises(ValueError, match='publication receipts'):
        retirement.plan_spaces(tmp_path, plan, cache, {'old'}, 'current')
    plan.close();cache.close()


def test_changed_subject_after_dryrun_blocks_before_any_deletion(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    graph = 'urn:graph'; identity = 'urn:old'
    quad = ox.Quad(ox.NamedNode(identity), ox.NamedNode('urn:predicate'), ox.Literal('before'), ox.NamedNode(graph))
    owner.store.add(quad)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    plan.execute('INSERT INTO nodes VALUES(?,?)', (identity, graph))
    proof = retirement.node_proof(owner, identity, graph)
    plan.execute('INSERT INTO node_proofs VALUES(?,?,?,?)', (identity, graph, *proof)); plan.commit()
    owner.store.add(ox.Quad(ox.NamedNode(identity), ox.NamedNode('urn:another'), ox.Literal('changed'), ox.NamedNode(graph)))
    with pytest.raises(ValueError, match='subject changed'):
        retirement.apply_plan(owner, plan, tmp_path/'unused.sqlite')
    assert quad in owner.store
    assert not (tmp_path/'unused.sqlite').exists()
    plan.close(); owner.close()


def test_vector_retirement_keeps_current_space_and_model_audit(tmp_path):
    import hashlib
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.semantic_extract.cache import ExtractionCache
    accepted_path = tmp_path/'accepted.sqlite'
    cache = sqlite3.connect(accepted_path)
    cache.executescript('CREATE TABLE accepted_receipts(namespace,key,digest); CREATE TABLE cache(namespace,key);')
    receipt = json.dumps({'model': 'same-embedding-model', 'request_id': 'original-model-receipt'})
    key = ExtractionCache()._generate_key('urn:obsolete-operation')
    cache.execute('INSERT INTO accepted_receipts VALUES(?,?,?)', ('embedding', key, 'accepted-digest'))
    cache.execute('INSERT INTO cache VALUES(?,?)', ('embedding', key))
    cache.execute("INSERT INTO accepted_receipts VALUES('embedding','keep','current-digest')")
    cache.commit()
    obsolete = tmp_path/'embedding-obsolete.sqlite'
    conn = sqlite3.connect(obsolete)
    conn.executescript('''CREATE TABLE embedding_space(id,identity,dimension);
      CREATE TABLE embeddings_embedding_operations(id,count,digest,receipt,receipt_digest,accepted_digest);
      CREATE TABLE embeddings_rowids(id);''')
    conn.execute('INSERT INTO embedding_space VALUES(1,?,2048)', (json.dumps({'binding':'sha256:obsolete','recipe':'old'}),))
    conn.execute('INSERT INTO embeddings_embedding_operations VALUES(?,1,?,?,?,?)', ('urn:obsolete-operation','vector-digest',receipt,hashlib.sha256(receipt.encode()).hexdigest(),'accepted-digest'))
    conn.execute('INSERT INTO embeddings_rowids VALUES(1)'); conn.commit();conn.close()
    current = tmp_path/'embedding-current.sqlite'
    conn = sqlite3.connect(current)
    conn.execute('CREATE TABLE embedding_space(id,identity,dimension)')
    conn.execute('INSERT INTO embedding_space VALUES(1,?,2048)', (json.dumps({'binding':'sha256:current','recipe':'current'}),))
    conn.commit();conn.close()
    current_bytes = current.read_bytes()
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_spaces(tmp_path, plan, cache, {'old'}, 'current')
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    quad = ox.Quad(ox.NamedNode('urn:old'), ox.NamedNode('urn:p'), ox.Literal('obsolete'), ox.NamedNode('urn:g'))
    owner.store.add(quad)
    plan.execute("INSERT INTO nodes VALUES('urn:old','urn:g')")
    plan.execute('INSERT INTO node_proofs VALUES(?,?,?,?)', ('urn:old','urn:g',*retirement.node_proof(owner,'urn:old','urn:g'))); plan.commit()
    cache.execute("UPDATE accepted_receipts SET digest='changed' WHERE key=?", (key,));cache.commit()
    with pytest.raises(ValueError, match='Acceptance changed'):
        retirement.apply_plan(owner, plan, accepted_path)
    assert quad in owner.store and obsolete.exists()
    cache.execute("UPDATE accepted_receipts SET digest='accepted-digest' WHERE key=?", (key,));cache.commit();cache.close()
    retirement.apply_plan(owner, plan, accepted_path)
    retirement.apply_plan(owner, plan, accepted_path, resume=True)
    assert not obsolete.exists() and current.read_bytes() == current_bytes
    assert plan.execute('SELECT receipt FROM vector_audit').fetchone() == (receipt,)
    cache = sqlite3.connect(accepted_path)
    assert cache.execute('SELECT * FROM accepted_receipts').fetchall() == [('embedding','keep','current-digest')]
    assert quad not in owner.store
    cache.close();plan.close();owner.close()


def test_classification_reduction_retires_with_batches_without_fabricated_cache_key(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.semantic_extract.cache import ExtractionCache
    fixture = runpy.run_path(str(Path(__file__).parent/'triplet_store/test_classification_records.py'))
    profile, binding, receipt, value = fixture['inputs']()
    owner = OxigraphStore(tmp_path/'facts')
    batch = ClassificationRecords(owner, binding)
    batch.adopt(value, profile=profile, allowed_evidence_ids=['evidence-1'], accepted_digest='paid', receipts=[receipt])
    reduction = ClassificationRecords(owner, dict(binding, context_digest='reduced'))
    reduction.adopt_reduction([batch.operation.value], profile=profile)
    cache_path = tmp_path/'accepted.sqlite'; cache = sqlite3.connect(cache_path)
    cache.executescript('CREATE TABLE accepted_receipts(namespace,key,digest); CREATE TABLE cache(namespace,key);')
    cache.execute('INSERT INTO accepted_receipts VALUES(?,?,?)', ('classification',ExtractionCache()._generate_key(binding['context_digest'], native_operation=batch.operation.value),'paid'));cache.commit()
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_facts(owner, plan, cache, 'project', {'recipe'}, lambda _: pytest.fail('Classification must not load document text'))
    assert plan.execute('SELECT count(*) FROM operations').fetchone()[0] == 2
    assert plan.execute('SELECT count(*) FROM cache_keys').fetchone()[0] == 1
    cache.close()
    retirement.apply_plan(owner, plan, cache_path)
    assert len(owner.store) == 0
    assert json.loads(plan.execute('SELECT model_receipts FROM operations WHERE id=?', (batch.operation.value,)).fetchone()[0]) == [receipt]
    plan.close();owner.close()


def pending_fixture(tmp_path):
    import hashlib
    cache_path = tmp_path/'accepted.sqlite'
    cache = sqlite3.connect(cache_path)
    cache.executescript('CREATE TABLE accepted_receipts(namespace,key,digest); CREATE TABLE cache(namespace,key,value,accepted_digest);')
    for namespace, key, value in [('embedding','old-embed',{'vectors':[[1,2]],'receipt':{'request':'original-embedding'}}),
                                  ('entities','old-failed',{'values':[],'receipts':[{'request':'original-generation'}]}),
                                  ('embedding','current',{'vectors':[[3,4]],'receipt':{'request':'current'}})]:
        blob = json.dumps(value).encode(); digest = hashlib.sha256(blob).hexdigest()
        cache.execute('INSERT INTO cache VALUES(?,?,?,?)',(namespace,key,blob,digest))
        cache.execute('INSERT INTO accepted_receipts VALUES(?,?,?)',(namespace,key,digest))
    cache.commit()
    scopes = [dict(namespace='embedding',source='source',recipe='old',count=1),dict(namespace='entities',source='source',recipe='old',count=1)]
    def candidates(scope):
        yield ('old-embed' if scope['namespace']=='embedding' else 'old-failed'), dict(source='source',recipe='old'), 'input-digest'
    return cache_path,cache,scopes,candidates


def test_pending_exact_keys_delete_failed_body_without_adopting_it_and_keep_model_audit(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    path,cache,scopes,candidates = pending_fixture(tmp_path)
    current = cache.execute("SELECT * FROM cache WHERE key='current'").fetchone()
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_pending(plan,cache,scopes,{'old'},'current',candidates)
    assert plan.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
    assert plan.execute('SELECT count(*) FROM pending_audit').fetchone()[0] == 2
    assert 'original-generation' in plan.execute("SELECT model_receipts FROM pending_audit WHERE namespace='entities'").fetchone()[0]
    cache.close()
    owner = OxigraphStore(tmp_path/'facts')
    retirement.apply_plan(owner,plan,path)
    retirement.apply_plan(owner,plan,path,resume=True)
    cache = sqlite3.connect(path)
    assert cache.execute('SELECT * FROM cache').fetchall() == [current]
    assert cache.execute('SELECT key FROM accepted_receipts').fetchall() == [('current',)]
    cache.close();plan.close();owner.close()


def test_pending_attribution_current_count_duplicate_and_corruption_fail_closed(tmp_path):
    path,cache,scopes,candidates = pending_fixture(tmp_path)
    for index, (change, message) in enumerate([
        (dict(recipe='current'), 'Pending scope'), (dict(count=2),'exact count')]):
        plan = retirement.create_plan(tmp_path/f'bad-{index}.sqlite')
        with pytest.raises(ValueError,match=message):
            retirement.plan_pending(plan,cache,[dict(scopes[0],**change)],{'old'},'current',candidates)
        plan.close()
    plan = retirement.create_plan(tmp_path/'duplicate.sqlite')
    with pytest.raises(ValueError,match='duplicates'):
        retirement.plan_pending(plan,cache,[scopes[0],scopes[0]],{'old'},'current',candidates)
    plan.close()
    cache.execute("UPDATE cache SET value=x'7b7d' WHERE key='old-embed'");cache.commit()
    plan = retirement.create_plan(tmp_path/'corrupt.sqlite')
    with pytest.raises(ValueError,match='body digest'):
        retirement.plan_pending(plan,cache,[scopes[0]],{'old'},'current',candidates)
    plan.close();cache.close()


def test_pending_changed_body_blocks_before_any_rdf_deletion(tmp_path):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    path,cache,scopes,candidates = pending_fixture(tmp_path)
    plan = retirement.create_plan(tmp_path/'plan.sqlite')
    retirement.plan_pending(plan,cache,scopes,{'old'},'current',candidates)
    owner = OxigraphStore(tmp_path/'facts'); ox = owner._oxigraph
    quad = ox.Quad(ox.NamedNode('urn:old'),ox.NamedNode('urn:p'),ox.Literal('keep'),ox.NamedNode('urn:g'))
    owner.store.add(quad)
    plan.execute("INSERT INTO nodes VALUES('urn:old','urn:g')")
    plan.execute('INSERT INTO node_proofs VALUES(?,?,?,?)',('urn:old','urn:g',*retirement.node_proof(owner,'urn:old','urn:g')));plan.commit()
    cache.execute("UPDATE cache SET value=x'7b7d' WHERE key='old-failed'");cache.commit();cache.close()
    with pytest.raises(ValueError,match='Pending body changed'):
        retirement.apply_plan(owner,plan,path)
    assert quad in owner.store
    plan.close();owner.close()
