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
