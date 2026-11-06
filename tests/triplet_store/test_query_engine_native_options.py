"""Public native query entry must not reuse query-only cache across options."""

import pytest

pytest.importorskip("pyoxigraph")
from pyoxigraph import NamedNode, Variable

from semantica.triplet_store.triplet_store import TripletStore
from semantica.utils.exceptions import ProcessingError, ValidationError


@pytest.fixture
def store(tmp_path):
    owner = TripletStore(backend="oxigraph", path=tmp_path / "rdf", enable_optimization=False)
    owner._store_backend.execute_update('''INSERT DATA {
      GRAPH <urn:project:p1> { <urn:subject> <urn:predicate> "one" }
      GRAPH <urn:project:p2> { <urn:subject> <urn:predicate> "two" }
    }''')
    return owner


def test_public_entry_same_query_keeps_native_project_bindings_isolated(store):
    query = "SELECT ?project ?value WHERE { GRAPH ?project { <urn:subject> <urn:predicate> ?value } }"
    # Populate the pre-existing query-only cache first, then require a scoped call.
    assert len(store.execute_query(query).bindings) == 2
    for project, expected in (("p1", "one"), ("p2", "two"), ("p1", "one")):
        result = store.execute_query(query,
            substitutions={Variable("project"): NamedNode("urn:project:" + project)},
            max_rows=1, max_bytes=2048)
        assert [row["value"]["value"] for row in result.bindings] == [expected]
        assert not result.metadata["cached"]


@pytest.mark.parametrize("budget", [{"max_rows": 1}, {"max_bytes": 1}])
def test_public_entry_stricter_budget_cannot_reuse_unbounded_cache(store, budget):
    query = "SELECT ?value WHERE { GRAPH ?project { <urn:subject> <urn:predicate> ?value } }"
    assert len(store.execute_query(query).bindings) == 2
    with pytest.raises(ProcessingError):
        store.execute_query(query, **budget)


def test_native_option_results_do_not_pollute_plain_query_cache(store):
    query = "SELECT ?project ?value WHERE { GRAPH ?project { <urn:subject> <urn:predicate> ?value } }"
    result = store.execute_query(query,
        substitutions={Variable("project"): NamedNode("urn:project:p1")})
    assert [row["value"]["value"] for row in result.bindings] == ["one"]
    assert store.query_engine.query_cache == {}
    assert len(store.execute_query(query).bindings) == 2


def test_plain_query_cache_does_not_hide_invalid_budget(store):
    query = "SELECT ?project ?value WHERE { GRAPH ?project { <urn:subject> <urn:predicate> ?value } }"
    store.execute_query(query)
    with pytest.raises(ValidationError, match="max_rows"):
        store.execute_query(query, max_rows=0)


@pytest.mark.parametrize("parameters", [{}, {"project": "urn:project:p1"}])
def test_public_entry_rejects_ignored_parameters_before_query_or_cache(store, parameters):
    query = "SELECT ?project ?value WHERE { GRAPH ?project { <urn:subject> <urn:predicate> ?value } }"
    store.execute_query(query)
    with pytest.raises(ValidationError, match="parameters.*substitutions"):
        store.execute_query(query, parameters=parameters)


def test_default_query_entry_does_not_silently_limit_native_results(tmp_path):
    owner = TripletStore(backend="oxigraph", path=tmp_path / "rdf", enable_caching=False)
    owner._store_backend.execute_update("INSERT DATA {" + " ".join(
        f'<urn:item:{i}> <urn:predicate> "value" .' for i in range(1001)
    ) + "}")
    result = owner.execute_query("SELECT ?s WHERE { ?s <urn:predicate> ?v }")
    assert len(result.bindings) == 1001


def test_default_query_entry_preserves_literal_whitespace_and_comments(tmp_path):
    owner = TripletStore(backend="oxigraph", path=tmp_path / "rdf", enable_caching=False)
    query = '''SELECT ?value WHERE {
      # The next line must not become part of this comment.
      BIND("a   b" AS ?value)
    }'''
    assert owner.execute_query(query).bindings == [
        {"value": {"value": "a   b", "type": "literal"}}
    ]


@pytest.mark.parametrize("config", [{}, {"enable_caching": True}])
def test_mutable_native_entry_always_reads_committed_state(tmp_path, config):
    owner = TripletStore(backend="oxigraph", path=tmp_path / "rdf", **config)
    query = "SELECT ?value WHERE { <urn:s> <urn:p> ?value }"
    assert owner.execute_query(query).bindings == []
    owner._store_backend.execute_update('INSERT DATA { <urn:s> <urn:p> "fresh" }')
    assert owner.execute_query(query).bindings == [
        {"value": {"type": "literal", "value": "fresh"}}
    ]
    owner._store_backend.execute_update('DELETE DATA { <urn:s> <urn:p> "fresh" }')
    assert owner.execute_query(query).bindings == []
    assert owner.query_engine.query_cache == {}
