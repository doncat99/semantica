"""Native RDF field capabilities, not a production schema or business engine.

Every phase runs in a separate process. Explicit RDF predicates/terms replace
opaque JSON; hand-authored mutations prove storage, not merge/classifier logic.
"""

import importlib.util
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyoxigraph") is None,
    reason="native Oxigraph extra missing",
)


COMMON = r'''
from pathlib import Path
import os
import sys
assert sys.dont_write_bytecode, "Native field audit subprocess must use -B"
if bundle_root := os.environ.get("ONTOSCIENCE_FROZEN_ORACLE_BUNDLE_ROOT"):
    import semantica
    assert Path(semantica.__file__).resolve().is_relative_to(Path(bundle_root).resolve()), "Field audit subprocess imported a foreign Semantica owner"
from pyoxigraph import Store, NamedNode, Literal, Quad
store = Store(str(Path(sys.argv[1]) / "native"))
N = lambda term: NamedNode("urn:" + term)
def add(subject, predicate, obj, graph="project:p"):
    store.add(Quad(N(subject), N(predicate), obj, N(graph)))
def values(subject, predicate, graph="project:p"):
    return {q.object for q in store.quads_for_pattern(N(subject), N(predicate), None, N(graph))}
def refs(subject, predicate, graph="project:p"):
    return {obj.value.removeprefix("urn:") for obj in values(subject, predicate, graph)}
'''


def phase(directory, code):
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", COMMON + "\n" + code + "\nstore.flush()\n", str(directory)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_mention_alias_merge_and_split_explicit_identity_edges(tmp_path):
    phase(tmp_path, '''
add("m1", "representation", N("rep1"))
add("m1", "item", N("item1"))
add("m1", "start", Literal(5))
add("m1", "end", Literal(9))
add("m1", "entity", N("e1"))
add("m2", "entity", N("e2"))
add("e1", "alias", Literal("Alpha"))
add("e2", "alias", Literal("ALPHA"))
add("e1", "name", Literal("Alpha Incorporated"))
add("e2", "name", Literal("Alpha Services"))
''')
    phase(tmp_path, '''
assert refs("m1", "entity") == {"e1"}
assert refs("m2", "entity") == {"e2"}
# A chosen identity operation, not an invented merge algorithm.
store.update("""
DELETE { GRAPH <urn:project:p> { <urn:m2> <urn:entity> <urn:e2> } }
INSERT { GRAPH <urn:project:p> {
 <urn:m2> <urn:entity> <urn:e1> .
 <urn:e1> <urn:alias> "ALPHA" .
 <urn:m2> <urn:merge-operation> <urn:op1> .
} }
WHERE { GRAPH <urn:project:p> { <urn:m2> <urn:entity> <urn:e2> } }
""")
''')
    phase(tmp_path, '''
assert refs("m1", "entity") == refs("m2", "entity") == {"e1"}
assert {x.value for x in values("e1", "alias")} == {"Alpha", "ALPHA"}
assert refs("m1", "representation") == {"rep1"}
assert values("m1", "start") == {Literal(5)}
assert values("m1", "end") == {Literal(9)}
# Explicit split withdraws only the merge-produced alias/contribution.
store.update("""
DELETE DATA { GRAPH <urn:project:p> {
 <urn:m2> <urn:entity> <urn:e1> .
 <urn:e1> <urn:alias> "ALPHA" .
 <urn:m2> <urn:merge-operation> <urn:op1> .
} };
INSERT DATA { GRAPH <urn:project:p> { <urn:m2> <urn:entity> <urn:e2> } }
""")
''')
    phase(tmp_path, '''
assert refs("m1", "entity") == {"e1"}
assert refs("m2", "entity") == {"e2"}
assert values("e1", "alias") == {Literal("Alpha")}
assert values("e2", "alias") == {Literal("ALPHA")}
assert refs("m2", "merge-operation") == set()
''')


def test_native_conflict_typed_reason_and_state_transitions(tmp_path):
    phase(tmp_path, '''
add("conflict:c", "kind", N("assertion-conflict"))
add("conflict:c", "state", N("open"))
add("conflict:c", "reason", Literal("Opposite polarity for the same period."))
add("conflict:c", "assertion", N("a1"))
add("conflict:c", "assertion", N("a2"))
add("conflict:c", "evidence", N("ev1"))
add("conflict:c", "evidence", N("ev2"))
''')
    for old, new in [("open", "resolved"), ("resolved", "ignored"), ("ignored", "open")]:
        phase(tmp_path, f'''
assert refs("conflict:c", "state") == {{"{old}"}}
store.update("""
DELETE DATA {{ GRAPH <urn:project:p> {{ <urn:conflict:c> <urn:state> <urn:{old}> }} }};
INSERT DATA {{ GRAPH <urn:project:p> {{ <urn:conflict:c> <urn:state> <urn:{new}> }} }}
""")
''')
    phase(tmp_path, '''
assert refs("conflict:c", "state") == {"open"}
assert values("conflict:c", "reason") == {Literal("Opposite polarity for the same period.")}
assert refs("conflict:c", "assertion") == {"a1", "a2"}
assert refs("conflict:c", "evidence") == {"ev1", "ev2"}
''')


def test_native_classification_hierarchy_preserves_cardinality_without_enforcing_it(tmp_path):
    phase(tmp_path, '''
add("dimension:sector", "cardinality", N("single"), "config:profile")
add("dimension:theme", "cardinality", N("multi"), "config:profile")
add("item:climate", "parent", N("item:environment"), "config:profile")
add("assignment:sector1", "source", N("source:s"))
add("assignment:sector1", "dimension", N("dimension:sector"))
add("assignment:sector1", "item", N("item:energy"))
add("assignment:theme1", "source", N("source:s"))
add("assignment:theme1", "dimension", N("dimension:theme"))
add("assignment:theme1", "item", N("item:climate"))
add("assignment:theme2", "source", N("source:s"))
add("assignment:theme2", "dimension", N("dimension:theme"))
add("assignment:theme2", "item", N("item:labour"))
add("assignment:theme1", "confidence", Literal("0.9100", datatype=NamedNode("http://www.w3.org/2001/XMLSchema#decimal")))
add("assignment:theme1", "evidence", N("ev1"))
add("source:s", "unclassified-dimension", N("dimension:region"))
''')
    phase(tmp_path, '''
assert refs("dimension:sector", "cardinality", "config:profile") == {"single"}
assert refs("dimension:theme", "cardinality", "config:profile") == {"multi"}
assert refs("item:climate", "parent", "config:profile") == {"item:environment"}
from decimal import Decimal
assert Decimal(next(iter(values("assignment:theme1", "confidence"))).value) == Decimal("0.9100")
assert refs("assignment:theme1", "evidence") == {"ev1"}
rows = list(store.query("""
 SELECT ?dim (COUNT(?a) AS ?count) WHERE { GRAPH <urn:project:p> {
 ?a <urn:source> <urn:source:s>; <urn:dimension> ?dim
 } } GROUP BY ?dim
"""))
assert {r["dim"].value: int(r["count"].value) for r in rows} == {
 "urn:dimension:sector": 1, "urn:dimension:theme": 2}
assert refs("source:s", "unclassified-dimension") == {"dimension:region"}
# Native RDF does NOT enforce application cardinality: this write is admitted.
add("assignment:sector2", "source", N("source:s"))
add("assignment:sector2", "dimension", N("dimension:sector"))
add("assignment:sector2", "item", N("item:finance"))
''')
    phase(tmp_path, '''
rows = list(store.query("""
 SELECT (COUNT(?a) AS ?count) WHERE { GRAPH <urn:project:p> {
 ?a <urn:source> <urn:source:s>; <urn:dimension> <urn:dimension:sector>
 } }
"""))
assert int(rows[0]["count"].value) == 2
# Limitation demonstrated; a production classifier must validate before publish.
''')


def test_native_organization_membership_withdrawal_preserves_other_source(tmp_path):
    phase(tmp_path, '''
for source in ["s1", "s2"]:
 graph = "source:" + source
 add("community:c", "member", N("entity:shared"), graph)
 add("topic:t", "member", N("entity:shared"), graph)
 add("topic:t", "community", N("community:c"), graph)
 add("entity:shared", "support", N("evidence:" + source), graph)
add("community:child", "parent", N("community:c"), "source:s1")
add("topic:t", "member", N("entity:only-s1"), "source:s1")
add("topic:t", "title", Literal("Climate commitments"), "product:organization")
''')
    phase(tmp_path, '''
store.update("CLEAR GRAPH <urn:source:s1>")
''')
    phase(tmp_path, '''
assert refs("community:c", "member", "source:s1") == set()
assert refs("topic:t", "member", "source:s2") == {"entity:shared"}
assert refs("entity:shared", "support", "source:s2") == {"evidence:s2"}
assert refs("community:child", "parent", "source:s1") == set()
rows = list(store.query("""
 SELECT ?g WHERE { GRAPH ?g { <urn:topic:t> <urn:member> <urn:entity:only-s1> } }
"""))
assert rows == []
assert values("topic:t", "title", "product:organization") == {Literal("Climate commitments")}
store.update("CLEAR GRAPH <urn:source:s2>")
''')
    phase(tmp_path, '''
assert list(store.query("SELECT ?g WHERE { GRAPH ?g { <urn:topic:t> <urn:member> ?member } }")) == []
# Text retention is storage capability only; validity after last support is a
# product publication rule, NOT something RDF automatically enforces.
assert values("topic:t", "title", "product:organization") == {Literal("Climate commitments")}
''')


def test_native_qualifier_absence_types_precision_and_nonfinite_limit(tmp_path):
    phase(tmp_path, '''
X = lambda name: NamedNode("http://www.w3.org/2001/XMLSchema#" + name)
add("a:absent", "polarity", N("positive"))
add("a:present", "polarity", N("positive"))
add("a:present", "condition", Literal("only if verified"))
add("a:present", "time", Literal("FY2024"))
add("a:present", "unit", Literal("tCO2e"))
add("a:present", "qualifier-value", Literal("00042"))
add("a:negative", "polarity", N("negative"))
add("scalar:int", "value", Literal("9007199254740993", datatype=X("integer")))
add("scalar:decimal", "value", Literal("12345678901234567890.12345678901234567890", datatype=X("decimal")))
add("scalar:bool", "value", Literal(False))
add("scalar:string", "value", Literal("false"))
add("scalar:url", "value", Literal("https://example.test/reference"))
add("scalar:entity", "value", NamedNode("https://example.test/reference"))
# Native XSD double permits these; producer finiteness is a separate gate.
add("scalar:infinity", "value", Literal("INF", datatype=X("double")))
add("scalar:nan", "value", Literal("NaN", datatype=X("double")))
''')
    phase(tmp_path, '''
from decimal import Decimal
X = lambda name: NamedNode("http://www.w3.org/2001/XMLSchema#" + name)
assert refs("a:absent", "polarity") == refs("a:present", "polarity") == {"positive"}
assert values("a:absent", "condition") == set()
assert values("a:present", "condition") == {Literal("only if verified")}
assert values("a:present", "time") == {Literal("FY2024")}
assert values("a:present", "unit") == {Literal("tCO2e")}
assert values("a:present", "qualifier-value") == {Literal("00042")}
assert refs("a:negative", "polarity") == {"negative"}
integer = next(iter(values("scalar:int", "value")))
decimal = next(iter(values("scalar:decimal", "value")))
assert integer.datatype == X("integer")
assert int(integer.value) == 9007199254740993
assert decimal.datatype == X("decimal")
assert Decimal(decimal.value) == Decimal("12345678901234567890.12345678901234567890")
assert values("scalar:bool", "value") != values("scalar:string", "value")
assert values("scalar:url", "value") == {Literal("https://example.test/reference")}
assert values("scalar:entity", "value") == {NamedNode("https://example.test/reference")}
assert next(iter(values("scalar:infinity", "value"))).value in {"INF", "+INF"}
assert next(iter(values("scalar:nan", "value"))).value == "NaN"
''')
