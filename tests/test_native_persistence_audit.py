"""G1 capability evidence, not a replacement knowledge schema or runtime owner.

Run with the existing native optional extras installed. Every persistence check
uses independent Python processes and temporary data; no models or network.
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_process(code, directory):
    result = subprocess.run(
        [sys.executable, "-c", code, str(directory)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.skipif(importlib.util.find_spec('pyoxigraph') is None, reason='native Oxigraph extra missing')
def test_native_large_scalar_and_fanout_caps_are_not_execution_caps(tmp_path):
    output = run_process('''
import json
import sys
import tracemalloc
from pathlib import Path
from threading import Event
from pyoxigraph import NamedNode, Literal, Quad
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.semantic_worker_context import query_cancellation
from semantica.utils.exceptions import ProcessingError
store = OxigraphStore(path=Path(sys.argv[1]) / 'limits-rdf')
graph, predicate = NamedNode('urn:project:p1'), NamedNode('urn:p')
store.store.extend(Quad(NamedNode('urn:s:' + str(i)), predicate, Literal(i), graph) for i in range(20000))
store.store.add(Quad(NamedNode('urn:large'), predicate, Literal('x' * (2 * 1024 * 1024)), graph))
store.flush()
try:
    store.execute_sparql('SELECT ?s WHERE { GRAPH <urn:project:p1> { ?s <urn:p> ?o } }', max_rows=2, max_bytes=2048)
except ProcessingError as error:
    assert 'row budget' in str(error)
else:
    raise AssertionError('fanout overflow silently accepted')
tracemalloc.start()
try:
    store.execute_sparql('SELECT ?o WHERE { GRAPH <urn:project:p1> { <urn:large> <urn:p> ?o } }', max_rows=1, max_bytes=1024)
except ProcessingError as error:
    assert 'byte budget' in str(error)
else:
    raise AssertionError('giant scalar silently accepted')
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
# Limitation probe: value conversion/JSON encoding precedes retained-byte rejection.
assert peak > 2 * 1024 * 1024
event = Event()
event.set()
token = query_cancellation.set(event)
try:
    # Limitation probe: existing worker Event does not interrupt the native owner.
    result = store.execute_sparql('ASK { GRAPH <urn:project:p1> { <urn:s:1> <urn:p> ?o } }')
    assert result['metadata']['boolean']
finally:
    query_cancellation.reset(token)
print(json.dumps({'large_scalar_python_peak_bytes': peak, 'fanout_records': 20000,
    'scalar_bytes': 2 * 1024 * 1024, 'configured_byte_cap': 1024,
    'preset_worker_cancel_observed_by_native': False}))
''', tmp_path)
    print("native-limit-measurements=" + output.strip())


@pytest.mark.skipif(importlib.util.find_spec('pyoxigraph') is None, reason='native Oxigraph extra missing')
def test_native_execution_process_can_be_terminated_and_store_reopened(tmp_path):
    """Existing worker-style process termination works; no query service added."""
    run_process('''
import sys
from pathlib import Path
from pyoxigraph import Store, NamedNode, Literal, Quad
store = Store(str(Path(sys.argv[1]) / 'deadline-rdf'))
store.extend(Quad(NamedNode('urn:s:' + str(i)), NamedNode('urn:p'), Literal(i), NamedNode('urn:project:p1')) for i in range(2000))
store.flush()
''', tmp_path)
    code = '''
import sys
from pathlib import Path
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=Path(sys.argv[1]) / 'deadline-rdf')
print('ready', flush=True)
store.execute_sparql('SELECT (COUNT(*) AS ?count) WHERE { GRAPH <urn:project:p1> { ?a <urn:p> ?x . ?b <urn:p> ?y . ?c <urn:p> ?z . FILTER(STRLEN(SHA256(CONCAT(STR(?x), STR(?y), STR(?z)))) > 0) } }', max_rows=1, max_bytes=1024)
'''
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(subprocess.TimeoutExpired):
            child.communicate(timeout=0.2)
        started = time.perf_counter()
        child.terminate()  # Existing host lifecycle sends SIGTERM, then SIGKILL.
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=5)
        stop_ms = (time.perf_counter() - started) * 1000
        assert child.returncode != 0
        print("native-process-stop-ms=" + str(round(stop_ms, 3)))
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
    run_process('''
import sys
from pathlib import Path
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=Path(sys.argv[1]) / 'deadline-rdf')
assert store.execute_sparql('ASK { GRAPH <urn:project:p1> { <urn:s:1999> <urn:p> ?o } }')['metadata']['boolean']
''', tmp_path)


@pytest.mark.skipif(importlib.util.find_spec('pyoxigraph') is None, reason='native Oxigraph extra missing')
def test_native_project_source_id_point_reads_scale_without_python_materialization(tmp_path):
    """Measured allocation probe, not a native physical-read or deadline proof."""
    measurements = []
    for count in (1000, 100000):
        directory = tmp_path / str(count)
        directory.mkdir()
        run_process('''
import sys
from pathlib import Path
from pyoxigraph import Store, NamedNode, Literal, Quad
store = Store(str(Path(sys.argv[1]) / 'scale-rdf'))
count = ''' + str(count) + '''
predicate = NamedNode('urn:predicate:value')
project = NamedNode('urn:project:p1')
def rows():
    for index in range(count):
        subject = NamedNode('urn:record:' + str(index))
        yield Quad(subject, predicate, Literal('x' * 256), project)
        yield Quad(subject, predicate, Literal('source' * 32), NamedNode('urn:source:p1:' + str(index % 100)))
    yield Quad(NamedNode('urn:record:0'), predicate, Literal('foreign'), NamedNode('urn:project:p2'))
store.extend(rows())
store.flush()
''', directory)
        output = run_process('''
import json
import resource
import sys
import time
import tracemalloc
from pathlib import Path
from pyoxigraph import NamedNode, Variable
from semantica.triplet_store.oxigraph_store import OxigraphStore
started = time.perf_counter()
store = OxigraphStore(path=Path(sys.argv[1]) / 'scale-rdf')
open_ms = (time.perf_counter() - started) * 1000
# The production wrapper must call native query, not enumerate graph records in Python.
native = store.store
class PointQueryOnly:
    def query(self, query, **kwargs):
        return native.query(query, **kwargs)
store.store = PointQueryOnly()
before = resource.getrusage(resource.RUSAGE_SELF)
tracemalloc.start()
started = time.perf_counter()
values = []
for graph in ('urn:project:p1', 'urn:source:p1:0', 'urn:source:p1:99'):
    result = store.execute_sparql(
        'SELECT ?graph ?subject ?value WHERE { GRAPH ?graph { ?subject <urn:predicate:value> ?value } }',
        substitutions={Variable('graph'): NamedNode(graph), Variable('subject'): NamedNode('urn:record:0')},
        max_rows=1, max_bytes=2048)['bindings']
    values.append([row['value']['value'] for row in result])
elapsed_ms = (time.perf_counter() - started) * 1000
_, peak = tracemalloc.get_traced_memory()
after = resource.getrusage(resource.RUSAGE_SELF)
assert values == [['x' * 256], ['source' * 32], []]
print(json.dumps({'open_ms': open_ms, 'query_ms': elapsed_ms, 'python_peak_bytes': peak,
    'maxrss_raw': after.ru_maxrss, 'rss_increase_raw': after.ru_maxrss - before.ru_maxrss,
    'input_blocks': after.ru_inblock - before.ru_inblock,
    'rss_unit': 'bytes' if sys.platform == 'darwin' else 'KiB'}))
''', directory)
        measurements.append({"records": count, **json.loads(output)})
    # 100x stored data must not become a Python list/JSON/string of all records.
    # This allocation budget says nothing about native RocksDB cache or scan I/O.
    assert all(row['python_peak_bytes'] < 1024 * 1024 for row in measurements)
    print("native-point-read-measurements=" + json.dumps(measurements, sort_keys=True))


@pytest.mark.skipif(importlib.util.find_spec('pyoxigraph') is None, reason='native Oxigraph extra missing')
def test_native_typed_qualified_facts_and_shared_support_withdrawal(tmp_path):
    """Capability proof: typed RDF terms, never a JSON snapshot in a triple."""
    imports = '''
import sys
from pathlib import Path
from pyoxigraph import NamedNode, Literal, Variable
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=Path(sys.argv[1]) / 'qualified-rdf')
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
XSD = 'http://www.w3.org/2001/XMLSchema#'
PROV = 'http://www.w3.org/ns/prov#'
SEM = 'urn:semantica:audit:'
project = NamedNode('urn:project:p1')
def iri(value):
    return str(NamedNode(value))
def lit(value, datatype=None):
    return str(Literal(value, datatype=NamedNode(datatype))) if datatype else str(Literal(value))
def triple(s, p, o):
    return f'{iri(s)} {iri(p)} {o} .'
def ask(pattern):
    return store.execute_sparql('ASK { ' + pattern + ' }', max_rows=1,
        max_bytes=8192)['metadata']['boolean']
'''
    run_process(imports + '''
facts = [
    ('integer', lit('42', XSD + 'integer')),
    ('decimal', lit('12.3400', XSD + 'decimal')),
    ('boolean', lit('false', XSD + 'boolean')),
    ('string', lit('00042')),
    ('entity', iri('urn:entity:target')),
]
rows = []
for key, value in facts:
    statement = 'urn:statement:' + key
    rows.extend([
        triple(statement, RDF + 'type', iri(RDF + 'Statement')),
        triple(statement, RDF + 'subject', iri('urn:entity:issuer')),
        triple(statement, RDF + 'predicate', iri('urn:predicate:' + key)),
        triple(statement, RDF + 'object', value),
    ])
rows.extend([
    triple('urn:statement:decimal', SEM + 'polarity', lit('negative')),
    triple('urn:statement:decimal', SEM + 'condition', lit('if acquisition closes')),
    triple('urn:statement:decimal', SEM + 'time', lit('FY2024')),
    triple('urn:statement:decimal', SEM + 'unit', lit('tCO2e')),
    # Existing qualifier value is a lexical string, distinct from typed object.
    triple('urn:statement:decimal', SEM + 'value', lit('approximately 12.3400')),
])
store.execute_update('INSERT DATA { GRAPH ' + str(project) + ' { ' + '\\n'.join(rows) + ' } }')
for source, confidence, start in [('one', '0.91', 3), ('two', '0.83', 51)]:
    graph = 'urn:source-revision:' + source
    evidence = 'urn:evidence:' + source
    rows = [
        triple(graph, SEM + 'project', str(project)),
        triple('urn:statement:decimal', PROV + 'wasDerivedFrom', iri(evidence)),
        triple(evidence, PROV + 'hadPrimarySource', iri('urn:representation:' + source)),
        triple(evidence, SEM + 'itemRef', lit('#/texts/7')),
        triple(evidence, SEM + 'startCodepoint', lit(str(start), XSD + 'integer')),
        triple(evidence, SEM + 'endCodepoint', lit(str(start + 8), XSD + 'integer')),
        triple(evidence, SEM + 'page', lit('2', XSD + 'integer')),
        triple(evidence, SEM + 'confidence', lit(confidence, XSD + 'decimal')),
    ]
    store.execute_update('INSERT DATA { GRAPH ' + iri(graph) + ' { ' + '\\n'.join(rows) + ' } }')
''', tmp_path)
    run_process(imports + '''
result = store.execute_sparql('SELECT ?project ?o WHERE { GRAPH ?project { <urn:statement:decimal> '
    + iri(RDF + 'object') + ' ?o } } LIMIT 1',
    substitutions={Variable('project'): project}, max_rows=1, max_bytes=8192)['bindings']
assert result[0]['o']['datatype'] == XSD + 'decimal'
# Numeric comparison preserves value; lexical decimal normalization is engine-owned.
assert ask('GRAPH ' + str(project) + ' { <urn:statement:decimal> ' + iri(RDF + 'object') + ' ?o FILTER(?o = 12.34) }')
for key, datatype in [('integer', 'integer'), ('boolean', 'boolean'), ('string', 'string')]:
    assert ask('GRAPH ' + str(project) + ' { <urn:statement:' + key + '> ' + iri(RDF + 'object')
        + ' ?o FILTER(DATATYPE(?o) = ' + iri(XSD + datatype) + ') }')
assert ask('GRAPH ' + str(project) + ' { <urn:statement:entity> ' + iri(RDF + 'object')
    + ' ?o FILTER(isIRI(?o)) }')
assert ask('GRAPH ' + str(project) + ' { <urn:statement:string> ' + iri(RDF + 'object') + ' "00042" }')
for field, value in [('polarity', 'negative'), ('condition', 'if acquisition closes'),
                     ('time', 'FY2024'), ('unit', 'tCO2e'), ('value', 'approximately 12.3400')]:
    assert ask('GRAPH ' + str(project) + ' { <urn:statement:decimal> ' + iri(SEM + field) + ' ' + lit(value) + ' }')
# Negative/conditional statement is never asserted as an unconditional positive edge.
assert not ask('GRAPH ' + str(project) + ' { <urn:entity:issuer> <urn:predicate:decimal> ?o }')
supports = store.execute_sparql('SELECT ?project ?e ?confidence ?ref ?start ?end ?page WHERE { '
    'GRAPH ?g { ?g ' + iri(SEM + 'project') + ' ?project . '
    '<urn:statement:decimal> ' + iri(PROV + 'wasDerivedFrom') + ' ?e . '
    '?e ' + iri(SEM + 'confidence') + ' ?confidence ; ' + iri(SEM + 'itemRef') + ' ?ref ; '
    + iri(SEM + 'startCodepoint') + ' ?start ; ' + iri(SEM + 'endCodepoint') + ' ?end ; '
    + iri(SEM + 'page') + ' ?page . } } ORDER BY ?e LIMIT 2',
    substitutions={Variable('project'): project}, max_rows=2, max_bytes=8192)['bindings']
assert [row['confidence']['value'] for row in supports] == ['0.91', '0.83']
assert [int(row['start']['value']) for row in supports] == [3, 51]
assert all(row['ref']['value'] == '#/texts/7' and row['page']['value'] == '2' for row in supports)
assert all(int(row['end']['value']) - int(row['start']['value']) == 8 for row in supports)
# Atomic source withdrawal and orphan removal, without touching shared facts.
def withdraw(source):
    store.execute_update('DROP GRAPH ' + iri('urn:source-revision:' + source) + '; '
        'DELETE { GRAPH ' + str(project) + ' { ?statement ?p ?o } } WHERE { '
        'GRAPH ' + str(project) + ' { ?statement ?p ?o . '
        '?statement ' + iri(RDF + 'type') + ' ' + iri(RDF + 'Statement') + ' } '
        'FILTER(?statement = <urn:statement:decimal>) '
        'FILTER NOT EXISTS { GRAPH ?g { ?g ' + iri(SEM + 'project') + ' ' + str(project) + ' . '
        '?statement ' + iri(PROV + 'wasDerivedFrom') + ' ?e } } }')
withdraw('one')
assert ask('GRAPH ' + str(project) + ' { <urn:statement:decimal> ' + iri(RDF + 'object') + ' ?o }')
assert not ask('GRAPH <urn:source-revision:one> { ?s ?p ?o }')
''', tmp_path)
    run_process(imports + '''
assert ask('GRAPH ' + str(project) + ' { <urn:statement:decimal> ' + iri(RDF + 'object') + ' ?o }')
assert ask('GRAPH <urn:source-revision:two> { <urn:statement:decimal> ' + iri(PROV + 'wasDerivedFrom') + ' <urn:evidence:two> }')
store.execute_update('DROP GRAPH <urn:source-revision:two>; DELETE { GRAPH ' + str(project)
    + ' { <urn:statement:decimal> ?p ?o } } WHERE { GRAPH ' + str(project)
    + ' { <urn:statement:decimal> ?p ?o } FILTER NOT EXISTS { GRAPH ?g { ?g '
    + iri(SEM + 'project') + ' ' + str(project) + ' . <urn:statement:decimal> '
    + iri(PROV + 'wasDerivedFrom') + ' ?e } } }')
assert not ask('GRAPH ' + str(project) + ' { <urn:statement:decimal> ?p ?o }')
assert ask('GRAPH ' + str(project) + ' { <urn:statement:integer> ' + iri(RDF + 'object') + ' ?o }')
''', tmp_path)


def test_native_extraction_cache_and_provenance_survive_restart(tmp_path):
    imports = """
import sys
from pathlib import Path
from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
from semantica.provenance.storage import SQLiteStorage
from semantica.provenance.schemas import ProvenanceEntry
directory = Path(sys.argv[1])
cache = ExtractionCache(backend=SqliteCacheBackend(str(directory / 'cache.db')))
provenance = SQLiteStorage(str(directory / 'provenance.db'))
"""
    run_process(imports + """
cache.set('relations', 'same source', [{'predicate': 'reports'}], model='m1', recipe='r1')
provenance.store(ProvenanceEntry(entity_id='e1', entity_type='relationship',
    activity_id='extract', source_document='source:1', start_index=3,
    end_index=9, metadata={'revision': 'rev:1'}))
""", tmp_path)
    run_process(imports + """
assert cache.get('relations', 'same source', model='m1', recipe='r1') == [{'predicate': 'reports'}]
assert cache.get('relations', 'same source', model='m2', recipe='r1') is None
assert cache.get('relations', 'same source', model='m1', recipe='r2') is None
entry = provenance.retrieve('e1')
assert (entry.source_document, entry.start_index, entry.end_index) == ('source:1', 3, 9)
assert entry.metadata['revision'] == 'rev:1'
""", tmp_path)


@pytest.mark.skipif(importlib.util.find_spec('sqlite_vec') is None, reason='native sqlite-vec extra missing')
def test_native_vector_restart_and_existing_filter_limitation(tmp_path):
    imports = """
import sys
from pathlib import Path
from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
store = SQLiteVecStore(str(Path(sys.argv[1]) / 'vectors.db'), 'vectors', 2)
"""
    run_process(imports + """
store.add([[1., 0.], [0., 1.]], ids=['v1', 'v2'], metadata=[{'project': 'p1'}, {'project': 'p2'}])
store.close()
""", tmp_path)
    run_process(imports + """
assert store.get(['v1'])[0]['id'] == 'v1'
assert store.search([1., 0.], top_k=1)[0]['id'] == 'v1'
# Capability audit: the generic API applies auxiliary metadata after global KNN.
# This is a documented defect, not the desired project-filter contract.
assert store.search([1., 0.], top_k=1, filter={'project': 'p2'}) == []
store.close()
""", tmp_path)


@pytest.mark.skipif(importlib.util.find_spec('pyoxigraph') is None, reason='native Oxigraph extra missing')
def test_native_oxigraph_named_graph_restart_ranges_and_metadata_gap(tmp_path):
    imports = """
import sys
from pathlib import Path
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.semantic_extract.types import Triplet
store = OxigraphStore(path=Path(sys.argv[1]) / 'rdf')
"""
    run_process(imports + """
store.add_triplets([
    Triplet('urn:entity:1', 'urn:predicate', 'one', confidence=.7,
            metadata={'evidence': 'urn:evidence:1', 'qualifiers': {'year': 2024}}),
    Triplet('urn:entity:2', 'urn:predicate', 'two'),
], graph='urn:project:p1')
store.add_triplets([Triplet('urn:entity:0', 'urn:predicate', 'other')], graph='urn:project:p2')
# Test standard RDF reification capability only; no new product schema.
store.store.update('''INSERT DATA { GRAPH <urn:project:p1> {
  <urn:statement:1> a <http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement> ;
    <http://www.w3.org/1999/02/22-rdf-syntax-ns#subject> <urn:entity:1> ;
    <http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate> <urn:predicate> ;
    <http://www.w3.org/1999/02/22-rdf-syntax-ns#object> "one" ;
    <http://www.w3.org/ns/prov#generatedAtTime> "2024-01-01T00:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> ;
    <http://www.w3.org/ns/prov#wasDerivedFrom> <urn:evidence:1> .
} }''')
store.flush()
""", tmp_path)
    run_process(imports + """
result = store.execute_sparql('''SELECT ?s ?o WHERE {
  GRAPH <urn:project:p1> { ?s <urn:predicate> ?o }
} ORDER BY ?s LIMIT 1''')['bindings']
assert len(result) == 1 and result[0]['s']['value'] == 'urn:entity:1'
page = store.execute_sparql('''SELECT ?s WHERE {
  GRAPH <urn:project:p1> { ?s <urn:predicate> ?o FILTER(STR(?s) > "urn:entity:1") }
} ORDER BY ?s LIMIT 1''')['bindings']
assert page[0]['s']['value'] == 'urn:entity:2'
assert store.execute_sparql('''ASK { GRAPH <urn:project:p1> {
  <urn:statement:1> <http://www.w3.org/ns/prov#wasDerivedFrom> <urn:evidence:1>
} }''')['metadata']['boolean']
qualified = store.execute_sparql('''SELECT ?evidence WHERE {
  GRAPH <urn:project:p1> {
    <urn:statement:1> <http://www.w3.org/ns/prov#generatedAtTime> ?time ;
      <http://www.w3.org/ns/prov#wasDerivedFrom> ?evidence .
    FILTER(YEAR(?time) = 2024)
  }
} LIMIT 1''')['bindings']
assert qualified[0]['evidence']['value'] == 'urn:evidence:1'
record = store.get_triplets(subject='urn:entity:1', graph='urn:project:p1')[0]
assert record.confidence == 1.0 and 'qualifiers' not in record.metadata
# Native atomic SPARQL update: withdraw then replace within one request.
store.store.update('''DELETE { GRAPH <urn:project:p1> { <urn:entity:1> <urn:predicate> ?o } }
INSERT { GRAPH <urn:project:p1> { <urn:entity:1> <urn:predicate> "updated" } }
WHERE { GRAPH <urn:project:p1> { <urn:entity:1> <urn:predicate> ?o } }''')
try:
    store.store.update('''INSERT DATA { GRAPH <urn:project:p1> {
      <urn:entity:bad> <urn:predicate> "bad" } }; INVALID''')
except Exception:
    pass
else:
    raise AssertionError('invalid transaction accepted')
assert store.get_triplets(subject='urn:entity:bad', graph='urn:project:p1') == []
store.flush()
""", tmp_path)
    run_process(imports + """
assert store.get_triplets(subject='urn:entity:1', graph='urn:project:p1')[0].object == 'updated'
store.delete_triplet(Triplet('urn:entity:1', 'urn:predicate', 'updated'), graph='urn:project:p1')
store.flush()
assert store.get_triplets(subject='urn:entity:1', graph='urn:project:p1') == []
assert len(store.get_triplets(graph='urn:project:p2')) == 1
""", tmp_path)
