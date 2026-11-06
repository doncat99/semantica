import gc
import importlib
from unittest.mock import patch

import pytest

from semantica.semantic_extract.triplet_extractor import Triplet
from semantica.triplet_store import OxigraphStore, TripletStore
from semantica.utils.exceptions import ProcessingError, ValidationError

pytest.importorskip("pyoxigraph")


EX = "http://example.org/"


def _store(**config):
    return TripletStore(
        backend="oxigraph",
        enable_caching=False,
        enable_optimization=False,
        **config,
    )


def test_memory_store_crud_preserves_literal_metadata():
    store = _store()
    triplets = [
        Triplet(EX + "alice", EX + "knows", EX + "bob"),
        Triplet(
            EX + "alice",
            EX + "name",
            "Alice",
            metadata={"language": "en"},
        ),
        Triplet(
            EX + "alice",
            EX + "age",
            "42",
            metadata={"datatype": "xsd:integer"},
        ),
    ]

    result = store.add_triplets(triplets)

    assert result == {
        "success": True,
        "total": 3,
        "processed": 3,
        "failed": 0,
        "batches": 1,
    }
    saved = store.get_triplets(subject=EX + "alice")
    assert len(saved) == 3
    assert (
        next(t for t in saved if t.predicate == EX + "name").metadata["language"]
        == "en"
    )
    assert (
        next(t for t in saved if t.predicate == EX + "age").metadata["datatype"]
        == "http://www.w3.org/2001/XMLSchema#integer"
    )

    store.delete_triplet(triplets[0])

    assert store.get_triplets(predicate=EX + "knows") == []


def test_named_graphs_are_isolated_for_crud_and_queries():
    store = _store()
    default_triplet = Triplet(EX + "default", EX + "label", "default")
    named_triplet = Triplet(EX + "named", EX + "label", "named")
    graph = EX + "graphs/agents"

    store.add_triplet(default_triplet)
    store.add_triplet(named_triplet, graph=graph)

    assert [t.subject for t in store.get_triplets()] == [default_triplet.subject]
    assert [t.subject for t in store.get_triplets(graph=graph)] == [
        named_triplet.subject
    ]

    result = store.execute_query(
        "SELECT ?s WHERE { ?s <http://example.org/label> ?label }",
        graph=graph,
    )
    assert [row["s"]["value"] for row in result.bindings] == [named_triplet.subject]


@pytest.mark.parametrize("metadata", [{"datatype": "xsd:string"}, {"language": "en"}, {"literal_datatype": "xsd:anyURI"}])
def test_explicit_url_literal_survives_read_reinsert_and_delete(metadata):
    backend = OxigraphStore()
    triplet = Triplet(EX + "source", EX + "label", EX + "literal", metadata=metadata)
    backend.add_triplet(triplet)
    query = "SELECT ?value WHERE { <http://example.org/source> <http://example.org/label> ?value }"
    original = backend.execute_sparql(query)["bindings"]
    assert original[0]["value"]["type"] == "literal"
    saved = backend.get_triplets(subject=triplet.subject)[0]
    backend.delete_triplet(saved)
    assert backend.get_triplets(subject=triplet.subject) == []
    backend.add_triplet(saved)
    assert backend.execute_sparql(query)["bindings"] == original


def test_select_ask_and_construct_result_shapes():
    backend = OxigraphStore()
    backend.add_triplet(
        Triplet(
            EX + "alice",
            EX + "name",
            "Alice",
            metadata={"language": "en"},
        )
    )

    selected = backend.execute_sparql(
        "SELECT ?name WHERE { <http://example.org/alice> "
        "<http://example.org/name> ?name }"
    )
    assert selected["variables"] == ["name"]
    assert selected["bindings"] == [
        {"name": {"type": "literal", "value": "Alice", "xml:lang": "en"}}
    ]

    asked = backend.execute_sparql("ASK { ?s ?p ?o }")
    assert asked["metadata"]["boolean"] is True

    constructed = backend.execute_sparql("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    assert constructed["variables"] == []
    assert constructed["triples"] == [
        (EX + "alice", EX + "name", "Alice", {"language": "en"})
    ]


def test_on_disk_store_survives_reopen(tmp_path):
    path = tmp_path / "oxigraph"
    first = OxigraphStore(path=path)
    first.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    first.flush()
    del first
    gc.collect()

    reopened = OxigraphStore(path=path)

    assert len(reopened.get_triplets()) == 1
    assert reopened.get_triplets()[0].object == EX + "bob"


def test_invalid_result_format_is_rejected():
    backend = OxigraphStore()

    with pytest.raises(ValidationError, match="Invalid result_format"):
        backend.execute_sparql("SELECT * WHERE { ?s ?p ?o }", result_format="csv")


def test_query_substitutions_preserve_literal_and_graph_scope():
    from pyoxigraph import Literal, NamedNode, Variable

    backend = OxigraphStore()
    text = 'quoted " value 😀 } UNION { ?s ?p ?o } #'
    backend.add_triplets([Triplet(EX + "one", EX + "label", text)], graph=EX + "p1")
    backend.add_triplets([Triplet(EX + "two", EX + "label", text)], graph=EX + "p2")
    result = backend.execute_sparql(
        "SELECT ?s ?graph ?value WHERE { GRAPH ?graph { ?s <http://example.org/label> ?value } } LIMIT 2",
        substitutions={Variable("graph"): NamedNode(EX + "p1"), Variable("value"): Literal(text)},
        max_rows=2, max_bytes=4096,
    )
    assert [row["s"]["value"] for row in result["bindings"]] == [EX + "one"]


@pytest.mark.parametrize("query", [
    "SELECT ?s ?p ?o WHERE { ?s ?p ?o }",
    "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
])
def test_query_budget_rejects_overflow_instead_of_truncating(query):
    backend = OxigraphStore()
    backend.add_triplets([Triplet(EX + str(i), EX + "label", "body" * 100) for i in range(3)])
    with pytest.raises(ProcessingError, match="row budget"):
        backend.execute_sparql(query, max_rows=2, max_bytes=8192)
    with pytest.raises(ProcessingError, match="byte budget"):
        backend.execute_sparql(query, max_rows=3, max_bytes=1024)


@pytest.mark.parametrize("option,value", [("max_rows", 0), ("max_rows", True),
                                         ("max_bytes", -1), ("max_bytes", 1.5)])
def test_query_budget_options_are_validated(option, value):
    with pytest.raises(ValidationError, match=option):
        OxigraphStore().execute_sparql("ASK {}", **{option: value})


def test_native_update_is_atomic_and_durable(tmp_path):
    backend = OxigraphStore(path=tmp_path / "atomic")
    update = 'INSERT DATA { <http://example.org/one> <http://example.org/label> "one" }'
    backend.execute_update(update)
    with pytest.raises(ProcessingError, match="update failed"):
        backend.execute_update(update.replace("/one>", "/bad>") + "; INVALID")
    assert backend.get_triplets(subject=EX + "bad") == []
    del backend
    gc.collect()
    assert OxigraphStore(path=tmp_path / "atomic").get_triplets(subject=EX + "one")[0].object == "one"


def test_update_native_literal_serialization_prevents_syntax_injection():
    from pyoxigraph import Literal

    backend = OxigraphStore()
    text = '" } }; DROP ALL; INSERT DATA { <urn:bad> <urn:p> "😀'
    backend.execute_update(
        'INSERT DATA { <http://example.org/one> <http://example.org/label> '
        + str(Literal(text)) + ' }'
    )
    assert backend.get_triplets(subject=EX + "one")[0].object == text
    assert len(backend.get_triplets()) == 1


def test_update_flush_failure_reports_already_committed_state(tmp_path):
    backend = OxigraphStore(path=tmp_path / "flush-failure")
    with patch.object(backend, "flush", side_effect=OSError("disk unavailable")):
        with pytest.raises(ProcessingError, match="committed but durability flush failed"):
            backend.execute_update(
                'INSERT DATA { <http://example.org/one> <http://example.org/label> "one" }'
            )
    assert backend.get_triplets(subject=EX + "one")[0].object == "one"


def test_invalid_rdf_term_is_reported_as_processing_error():
    backend = OxigraphStore()

    with pytest.raises(ProcessingError, match="Oxigraph load failed"):
        backend.add_triplet(Triplet("not an iri", EX + "predicate", "value"))


def test_missing_optional_dependency_has_install_hint():
    real_import_module = importlib.import_module

    def import_without_oxigraph(name, package=None):
        if name == "pyoxigraph":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    with patch(
        "semantica.triplet_store.oxigraph_store.importlib.import_module",
        side_effect=import_without_oxigraph,
    ):
        with pytest.raises(ImportError, match="tripletstore-oxigraph"):
            _store()


def test_on_disk_add_triplets_calls_flush(tmp_path):
    """add_triplets on a disk-backed store must flush once after the batch.

    The pyoxigraph background-thread flush "might lag a little bit"; an
    explicit flush after the batch closes that race without fsyncing on
    every individual write.  This test verifies the contract directly
    without relying on CPython destructor timing.
    """
    store = OxigraphStore(path=tmp_path / "oxigraph")
    with patch.object(store, "flush") as mock_flush:
        store.add_triplets([
            Triplet(EX + "alice", EX + "knows", EX + "bob"),
            Triplet(EX + "bob", EX + "knows", EX + "carol"),
        ])
    mock_flush.assert_called_once()


def test_on_disk_add_triplet_does_not_flush(tmp_path):
    """add_triplet (single write) must NOT flush on every call.

    Individual writes are committed to the store in memory; the caller is
    responsible for calling flush() when a hard durability boundary is
    needed.  Flushing on every add_triplet() call would fsync on every
    write, causing a severe throughput regression for workloads that write
    triplets one at a time.
    """
    store = OxigraphStore(path=tmp_path / "oxigraph")
    with patch.object(store, "flush") as mock_flush:
        store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    mock_flush.assert_not_called()


def test_in_memory_add_triplets_does_not_flush(tmp_path):
    """In-memory stores must not call flush() — there is nothing to flush."""
    store = OxigraphStore()  # no path → in-memory
    with patch.object(store, "flush") as mock_flush:
        store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
        store.add_triplets([Triplet(EX + "bob", EX + "knows", EX + "carol")])
    mock_flush.assert_not_called()


def test_on_disk_add_triplets_is_durable_on_reopen(tmp_path):
    """End-to-end durability: a batch written via add_triplets and closed
    cleanly survives a reopen.

    This is an integration test for the full add_triplets → flush → close →
    reopen lifecycle.  The durability contract here is provided by the
    explicit ``store.flush()`` call before deletion; the internal flush
    inside add_triplets reduces (but does not eliminate) the crash-window
    race.  The authoritative unit test for the internal flush behaviour is
    ``test_on_disk_add_triplets_calls_flush``.
    """
    path = tmp_path / "oxigraph"
    store = OxigraphStore(path=path)
    store.add_triplets([
        Triplet(EX + "alice", EX + "knows", EX + "bob"),
        Triplet(EX + "bob", EX + "knows", EX + "carol"),
    ])
    store.flush()   # belt-and-suspenders: ensures close is clean
    del store
    gc.collect()

    reopened = OxigraphStore(path=path)
    assert len(reopened.get_triplets()) == 2


def test_storage_path_is_accepted_as_alias_for_path(tmp_path):
    """Regression: ``storage_path=...`` used to be silently swallowed by
    ``**config`` (the __init__ parameter is named ``path``), so the store
    silently degraded to in-memory with no warning. It must now be accepted
    as an alias consistent with other Semantica stores (e.g. ProvenanceManager)."""
    storage_path = tmp_path / "oxigraph"

    store = OxigraphStore(storage_path=str(storage_path))

    assert store.path == str(storage_path)
    # and it must actually persist (proves the alias wired through to the
    # on-disk path, not just set the attribute)
    store.add_triplet(Triplet(EX + "alice", EX + "knows", EX + "bob"))
    del store
    gc.collect()

    reopened = OxigraphStore(storage_path=str(storage_path))
    assert len(reopened.get_triplets()) == 1
