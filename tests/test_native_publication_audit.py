"""Test-only native publication probe; not a product schema or runtime.

One Oxigraph owner holds mutable facts. SQLite files contain only disposable
derived features/references. Child processes prove durable failure states.
"""

import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyoxigraph") is None,
    reason="native Oxigraph extra missing",
)


PROBE = r'''
import hashlib
from pathlib import Path
import sqlite3
import sys
from pyoxigraph import Store

root, action = Path(sys.argv[1]), sys.argv[2]
store = Store(str(root / 'facts'))

class NotReady(Exception):
    pass

class Stale(Exception):
    pass

def row():
    rows = list(store.query("""
      SELECT ?state ?input ?index ?digest ?value WHERE {
        GRAPH <urn:project:p> {
          <urn:source:s> <urn:state> ?state; <urn:input> ?input .
          OPTIONAL { <urn:source:s> <urn:index> ?index; <urn:digest> ?digest }
          OPTIONAL { <urn:fact:f> <urn:value> ?value }
        }
      }
    """))
    assert len(rows) == 1
    return tuple(term.value if term is not None else None for term in rows[0])

def begin(input_id):
    # Atomic invalidation precedes fact mutation. Old files cannot serve pending.
    store.update("""
      DELETE { GRAPH <urn:project:p> { <urn:source:s> ?p ?o } }
      INSERT { GRAPH <urn:project:p> {
        <urn:source:s> <urn:state> "pending"; <urn:input> "%s" .
      } }
      WHERE { OPTIONAL { GRAPH <urn:project:p> { <urn:source:s> ?p ?o } } }
    """ % input_id)
    store.flush()

def write_fact(value):
    store.update("""
      DELETE { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> ?old } }
      INSERT { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> "%s" } }
      WHERE { OPTIONAL { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> ?old } } }
    """ % value)
    store.flush()

def install(input_id, term):
    path = root / (input_id + '.sqlite')
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE binding(input TEXT NOT NULL); '
                        'CREATE TABLE features(record_ref TEXT NOT NULL, term TEXT NOT NULL);')
        db.execute('INSERT INTO binding VALUES (?)', (input_id,))
        db.execute('INSERT INTO features VALUES (?,?)', ('urn:fact:f', term))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()

def activate(input_id, path, digest):
    # Installation-time validation only, not a full-index query-time digest.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT input FROM binding').fetchone() == (input_id,)
    assert row()[0:2] == ('pending', input_id)
    store.update("""
      DELETE { GRAPH <urn:project:p> { <urn:source:s> <urn:state> "pending" } }
      INSERT { GRAPH <urn:project:p> {
        <urn:source:s> <urn:state> "ready"; <urn:index> "%s"; <urn:digest> "%s" .
      } }
      WHERE { GRAPH <urn:project:p> {
        <urn:source:s> <urn:state> "pending"; <urn:input> "%s" .
      } }
    """ % (path.name, digest, input_id))
    store.flush()
    assert row()[0:4] == ('ready', input_id, path.name, digest)

def read(hook=None):
    captured = row()
    state, input_id, filename, digest, value = captured
    if state != 'ready':
        raise NotReady(state)
    with sqlite3.connect('file:' + str(root / filename) + '?mode=ro', uri=True) as db:
        if db.execute('SELECT input FROM binding').fetchone() != (input_id,):
            raise Stale('wrong index input')
        refs = db.execute('SELECT record_ref FROM features WHERE term=?', (value.lower(),)).fetchall()
    if hook:
        hook()
    if row() != captured:
        raise Stale('native publication changed')
    assert refs == [('urn:fact:f',)]
    return value

if action == 'seed':
    begin('a')
    write_fact('RED')
    path, digest = install('a', 'red')
    activate('a', path, digest)
    assert read() == 'RED'
elif action == 'begin':
    begin('b')
elif action == 'fact':
    write_fact('BLUE')
elif action == 'crash-after-fact':
    import os
    begin('b')
    write_fact('BLUE')
    os._exit(73)
elif action == 'install':
    install('b', 'blue')
elif action == 'assert-blocked':
    try:
        read()
    except NotReady:
        pass
    else:
        raise AssertionError('incomplete publication was readable')
elif action == 'bad-install':
    path, digest = install('b', 'blue')
    path.write_bytes(b'broken staged index')
    try:
        activate('b', path, digest)
    except AssertionError:
        pass
    else:
        raise AssertionError('corrupt installation activated')
    assert row()[0:2] == ('pending', 'b')
elif action == 'wrong-index':
    path = root / 'a.sqlite'
    try:
        activate('b', path, hashlib.sha256(path.read_bytes()).hexdigest())
    except AssertionError:
        pass
    else:
        raise AssertionError('old index activated for new input')
elif action == 'publish':
    path = root / 'b.sqlite'
    activate('b', path, hashlib.sha256(path.read_bytes()).hexdigest())
elif action == 'assert-blue':
    assert read() == 'BLUE'
    assert len(list(store.query('SELECT ?v WHERE { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> ?v } }'))) == 1
elif action == 'race-invalidation':
    try:
        read(lambda: begin('b'))
    except Stale:
        pass
    else:
        raise AssertionError('read crossed native invalidation')
elif action == 'race-full-publication':
    def replace():
        begin('b')
        write_fact('BLUE')
        path, digest = install('b', 'blue')
        activate('b', path, digest)
    try:
        read(replace)
    except Stale:
        pass
    else:
        raise AssertionError('read crossed replacement')
    assert read() == 'BLUE'
elif action == 'invalid-native-update':
    before = row()
    try:
        store.update('DELETE DATA { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> "RED" } }; INVALID')
    except SyntaxError:
        pass
    else:
        raise AssertionError('invalid update accepted')
    assert row() == before
    assert read() == 'RED'
else:
    raise AssertionError(action)
store.flush()
'''


def run_probe(directory, action, expected_exit=0):
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(directory), action],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr


@pytest.mark.parametrize("interrupted_after", ["begin", "fact", "install"])
def test_pending_publication_survives_owner_restart_without_mixed_reads(tmp_path, interrupted_after):
    run_probe(tmp_path, "seed")
    for step in ["begin", "fact", "install"]:
        run_probe(tmp_path, step)
        run_probe(tmp_path, "assert-blocked")
        if step == interrupted_after:
            break


def test_validated_publication_replaces_one_fact_and_reopens(tmp_path):
    for action in ["seed", "begin", "fact", "wrong-index", "install", "publish", "assert-blue"]:
        run_probe(tmp_path, action)


def test_corrupt_index_cannot_publish_and_restart_stays_blocked(tmp_path):
    for action in ["seed", "begin", "fact", "bad-install", "assert-blocked"]:
        run_probe(tmp_path, action)


def test_abrupt_owner_exit_keeps_publication_unreadable_on_restart(tmp_path):
    run_probe(tmp_path, "seed")
    run_probe(tmp_path, "crash-after-fact", expected_exit=73)
    run_probe(tmp_path, "assert-blocked")


@pytest.mark.parametrize("action", ["race-invalidation", "race-full-publication", "invalid-native-update"])
def test_read_fence_or_native_atomicity_rejects_mixed_state(tmp_path, action):
    run_probe(tmp_path, "seed")
    run_probe(tmp_path, action)


def test_derived_reference_keyset_pages_before_native_point_reads(tmp_path):
    """Bounded candidate order is a search access path, never a fact mirror."""
    from pyoxigraph import Literal, NamedNode, Quad, Store, Variable

    store = Store(str(tmp_path / "native"))
    index = sqlite3.connect(tmp_path / "features.sqlite")
    index.execute(
        "CREATE TABLE features(project TEXT, source TEXT, term TEXT, record_ref TEXT, "
        "PRIMARY KEY(project, source, term, record_ref)) WITHOUT ROWID"
    )
    for project in ["p", "foreign"]:
        for number in range(23):
            record = f"urn:record:{number:03}"
            # The fact exists only in the native store. SQL has no body/value.
            store.add(Quad(NamedNode(record), NamedNode("urn:label"),
                           Literal(f"{project}-value-{number}"),
                           NamedNode(f"urn:project:{project}")))
            index.execute("INSERT INTO features VALUES (?,?,?,?)",
                          (project, "s", "esg", record))
    index.commit()
    query = (
        "SELECT record_ref FROM features WHERE project=? AND source=? AND term=? "
        "AND record_ref>? ORDER BY record_ref LIMIT ?"
    )
    plan = index.execute("EXPLAIN QUERY PLAN " + query,
                         ("p", "s", "esg", "urn:record:017", 6)).fetchall()
    assert any("SEARCH features USING PRIMARY KEY" in item[3] for item in plan)
    assert not any("TEMP B-TREE" in item[3] or "SCAN features" in item[3] for item in plan)

    cancel = Event()
    native_reads = []

    def page(cursor="", before_point_read=None):
        if cancel.is_set():
            raise InterruptedError("cancelled before indexed page")
        rows = index.execute(query, ("p", "s", "esg", cursor, 6)).fetchall()
        values = []
        for (record,) in rows:
            if before_point_read:
                before_point_read()
            if cancel.is_set():
                raise InterruptedError("cancelled before native point read")
            native_reads.append(record)
            result = list(store.query(
                "SELECT ?g ?id ?value WHERE { GRAPH ?g { ?id <urn:label> ?value } }",
                substitutions={Variable("g"): NamedNode("urn:project:p"),
                               Variable("id"): NamedNode(record)},
            ))
            assert len(result) == 1
            values.append(result[0]["value"].value)
        return rows, values

    cursor, all_values, sizes = "", [], []
    while True:
        rows, values = page(cursor)
        if not rows:
            break
        sizes.append(len(rows))
        all_values.extend(values)
        cursor = rows[-1][0]
    assert sizes == [6, 6, 6, 5]
    assert all_values == [f"p-value-{number}" for number in range(23)]
    assert len(native_reads) == 23
    # Deep direct seek fetches exactly its page, not the preceding records.
    native_reads.clear()
    rows, values = page("urn:record:017")
    assert len(native_reads) == 5
    assert values == [f"p-value-{number}" for number in range(18, 23)]
    assert index.execute("SELECT record_ref FROM features WHERE project=? AND source=?",
                         ("p", "other-source")).fetchall() == []
    cancel.set()
    native_reads.clear()
    with pytest.raises(InterruptedError, match="before indexed page"):
        page()
    assert native_reads == []
    cancel.clear()
    with pytest.raises(InterruptedError, match="before native point read"):
        page(before_point_read=cancel.set)
    assert native_reads == []
    index.close()


JOINT_PROBE = r'''
import hashlib, sqlite3, sys
from pathlib import Path
from pyoxigraph import Store, NamedNode, Literal, Quad
from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
root, action = Path(sys.argv[1]), sys.argv[2]
store = Store(str(root/'facts'))
G = NamedNode('urn:project:p')
S = NamedNode('urn:source:s')
N = lambda name: NamedNode('urn:publication:'+name)
FIELDS = ('project', 'source', 'material', 'representation', 'recipe', 'schema',
          'facts_epoch', 'embedding_model', 'embedding_revision', 'dimension',
          'metric', 'keyword_recipe', 'vector_recipe')
def dependency(epoch):
    return ('p','s','material:'+epoch,'representation:'+epoch,'extract:r1','rdf:r1',
            epoch,'embed:m1','embed:revision1','2','cosine','kw:r1','vec:r1')
def value(predicate):
    rows = list(store.quads_for_pattern(S,N(predicate),None,G))
    assert len(rows) == 1
    return rows[0].object.value
def captured():
    state = value('state')
    if state != 'ready':
        return (state,)
    return (state, *(value(f) for f in FIELDS),
            *(value(f) for f in ('keyword','keyword_digest','vector','vector_digest')))
def set_state(state, epoch=None):
    triples = f'<urn:source:s> <urn:publication:state> "{state}" .'
    if epoch:
        triples += ''.join(f'<urn:source:s> <urn:publication:{f}> "{v}" .'
                           for f,v in zip(FIELDS,dependency(epoch)))
    store.update('DELETE { GRAPH <urn:project:p> { <urn:source:s> ?p ?o } } '
        'INSERT { GRAPH <urn:project:p> { '+triples+' } } '
        'WHERE { OPTIONAL { GRAPH <urn:project:p> { <urn:source:s> ?p ?o } } }')
    store.flush()
def fact(epoch):
    store.update('DELETE { GRAPH <urn:project:p> { <urn:fact:f> ?p ?o } } '
      'INSERT { GRAPH <urn:project:p> { <urn:fact:f> <urn:value> "'+epoch+'" } } '
      'WHERE { OPTIONAL { GRAPH <urn:project:p> { <urn:fact:f> ?p ?o } } }')
    store.flush()
def binding(db, epoch):
    db.execute('CREATE TABLE binding('+','.join(f+' TEXT NOT NULL' for f in FIELDS)+')')
    db.execute('INSERT INTO binding VALUES ('+','.join('?' for _ in FIELDS)+')',dependency(epoch))
def stage(epoch):
    keyword = root/(epoch+'-keyword.sqlite')
    with sqlite3.connect(keyword) as db:
        binding(db,epoch)
        db.execute('CREATE TABLE terms(term TEXT, record_ref TEXT, PRIMARY KEY(term,record_ref)) WITHOUT ROWID')
        db.execute('INSERT INTO terms VALUES (?,?)',('esg','urn:fact:f'))
    vector = root/(epoch+'-vector.sqlite')
    vectors = SQLiteVecStore(str(vector),'vectors',2,'cosine')
    vectors.add([[1.,0.]],ids=['urn:fact:f'])
    vectors.close()
    with sqlite3.connect(vector) as db:
        binding(db,epoch)
    return keyword, vector
def admit(epoch, files):
    for path in files:
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT * FROM binding').fetchall() == [dependency(epoch)]
    assert value('state') == 'pending' and value('facts_epoch') == epoch
    # One native activation point includes BOTH installed identities/digests.
    additions = ''.join(f'<urn:source:s> <urn:publication:{kind}> "{path.name}"; '
        f'<urn:publication:{kind}_digest> "{hashlib.sha256(path.read_bytes()).hexdigest()}" .'
        for kind,path in zip(('keyword','vector'),files))
    store.update('DELETE { GRAPH <urn:project:p> { <urn:source:s> <urn:publication:state> "pending" } } '
        'INSERT { GRAPH <urn:project:p> { <urn:source:s> <urn:publication:state> "ready" . '+additions+' } } '
        'WHERE { GRAPH <urn:project:p> { <urn:source:s> <urn:publication:state> "pending"; '
        '<urn:publication:facts_epoch> "'+epoch+'" } }')
    store.flush()
def read(expected_epoch):
    before = captured()
    if before[0] != 'ready':
        return before[0]
    identity = before[1:1+len(FIELDS)]
    if identity != dependency(expected_epoch):
        return 'stale_reference'
    paths = (root/before[-4], root/before[-2])
    for path in paths:
        if not path.exists():
            return 'missing_index'
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            if db.execute('SELECT * FROM binding').fetchall() != [identity]:
                return 'dependency_mismatch'
    with sqlite3.connect('file:'+str(paths[0])+'?mode=ro',uri=True) as db:
        keyword_refs = db.execute('SELECT record_ref FROM terms WHERE term=? LIMIT 2',('esg',)).fetchall()
    vectors = SQLiteVecStore(str(paths[1]),'vectors',2,'cosine',read_only=True)
    vector_refs = [hit['id'] for hit in vectors.search([1.,0.],top_k=1)]
    vectors.close()
    assert keyword_refs == [('urn:fact:f',)] and vector_refs == ['urn:fact:f']
    rows = list(store.quads_for_pattern(NamedNode('urn:fact:f'),NamedNode('urn:value'),None,G))
    assert len(rows) == 1 and rows[0].object.value == expected_epoch
    return 'ready' if captured() == before else 'changed_during_read'
if action == 'seed':
    set_state('pending','a'); fact('a'); admit('a',stage('a')); assert read('a') == 'ready'
elif action == 'stage-failure-before-mutation':
    files = stage('b')
    # Mismatched vector space is rejected before invalidating the valid owner.
    with sqlite3.connect(files[1]) as db:
        db.execute("UPDATE binding SET embedding_revision='wrong'")
    try:
        admit('b',files)
    except AssertionError:
        store.add(Quad(N('attempt:b'),N('state'),Literal('failed_before_mutation'),G))
        store.flush()
    else:
        raise AssertionError('mismatched joint index admitted')
    assert read('a') == 'ready'
elif action == 'begin-b':
    set_state('pending','b'); fact('b')
    assert read('a') == read('b') == 'pending'
elif action == 'failed-after-mutation':
    set_state('failed','b')
    assert read('a') == read('b') == 'failed'
elif action == 'assert-failed':
    assert read('a') == read('b') == 'failed'
elif action == 'publish-b':
    set_state('pending','b'); fact('b')
    files=(root/'b-keyword.sqlite',root/'b-vector.sqlite')
    with sqlite3.connect(files[1]) as db:
        db.execute("UPDATE binding SET embedding_revision='embed:revision1'")
    admit('b',files)
    assert read('a') == 'stale_reference' and read('b') == 'ready'
elif action == 'assert-b':
    assert read('a') == 'stale_reference' and read('b') == 'ready'
elif action == 'withdraw':
    set_state('withdrawn','b')
    store.update('DELETE WHERE { GRAPH <urn:project:p> { <urn:fact:f> ?p ?o } }')
    store.flush()
    assert read('a') == read('b') == 'withdrawn'
elif action == 'assert-withdrawn':
    assert read('a') == read('b') == 'withdrawn'
    assert list(store.quads_for_pattern(NamedNode('urn:fact:f'),None,None,G)) == []
elif action == 'missing-vector':
    (root/'a-vector.sqlite').unlink()
    assert read('a') == 'missing_index'
elif action == 'each-binding-field':
    for field, original in zip(FIELDS, dependency('a')):
        with sqlite3.connect(root/'a-vector.sqlite') as db:
            db.execute('UPDATE binding SET '+field+'=?', ('wrong',))
        assert read('a') == 'dependency_mismatch', field
        with sqlite3.connect(root/'a-vector.sqlite') as db:
            db.execute('UPDATE binding SET '+field+'=?', (original,))
    assert read('a') == 'ready'
else:
    raise AssertionError(action)
store.flush()
'''


def joint_phase(directory, action):
    result = subprocess.run([sys.executable, "-c", JOINT_PROBE, str(directory), action],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(importlib.util.find_spec("sqlite_vec") is None, reason="native vector extra missing")
def test_joint_native_facts_keyword_vector_failure_recovery_and_withdrawal(tmp_path):
    for action in ("seed", "stage-failure-before-mutation", "begin-b", "failed-after-mutation",
                   "assert-failed", "publish-b", "assert-b", "withdraw", "assert-withdrawn"):
        joint_phase(tmp_path, action)


@pytest.mark.skipif(importlib.util.find_spec("sqlite_vec") is None, reason="native vector extra missing")
def test_joint_publication_missing_required_vector_is_explicit_not_keyword_success(tmp_path):
    joint_phase(tmp_path, "seed")
    joint_phase(tmp_path, "each-binding-field")
    joint_phase(tmp_path, "missing-vector")
