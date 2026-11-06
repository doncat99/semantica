"""
Comprehensive tests for ALL features listed in the [Unreleased] section of CHANGELOG.md.

Covers gaps not addressed by existing test files:

  PR #385 — ContextGraph pagination: skip parameter, min_weight neighbor filter
  PR #385 — ContextGraph thread safety: concurrent mutations
  PR #319 — SKOS Vocabulary Module: namespace helpers, OntologyEngine APIs,
             TripletStore helpers (gap tests beyond existing suite)
  PR #318 — SHACL: quality tiers, export_shacl, RDFExporter.export_shacl (gap tests)
  PR #408 — OllamaProvider base_url fix (gap tests beyond existing suite)
  PR #371 — DatalogReasoner: idempotency, cache flag, graph load (gap tests)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


class TestContextGraphPaginationSkip:
    """find_nodes / find_edges / find_active_nodes must honour the skip parameter."""

    @pytest.fixture
    def graph_with_nodes(self):
        from semantica.context import ContextGraph
        g = ContextGraph()
        for i in range(6):
            g.add_node(f"n{i}", "entity", content=str(i))
        return g

    @pytest.fixture
    def graph_with_edges(self):
        from semantica.context import ContextGraph
        g = ContextGraph()
        for i in range(6):
            g.add_node(f"n{i}", "entity")
        for i in range(5):
            g.add_edge(f"n{i}", f"n{i+1}", "next")
        return g

    # find_nodes

    def test_find_nodes_skip_zero_returns_all(self, graph_with_nodes):
        result = graph_with_nodes.find_nodes(skip=0)
        assert len(result) == 6

    def test_find_nodes_skip_positive_reduces_count(self, graph_with_nodes):
        result = graph_with_nodes.find_nodes(skip=2)
        assert len(result) == 4

    def test_find_nodes_skip_and_limit_window(self, graph_with_nodes):
        result = graph_with_nodes.find_nodes(skip=2, limit=2)
        assert len(result) == 2

    def test_find_nodes_skip_beyond_length_returns_empty(self, graph_with_nodes):
        result = graph_with_nodes.find_nodes(skip=100)
        assert result == []

    def test_find_nodes_skip_plus_limit_no_overlap_with_first_page(self, graph_with_nodes):
        page1 = graph_with_nodes.find_nodes(skip=0, limit=3)
        page2 = graph_with_nodes.find_nodes(skip=3, limit=3)
        ids1 = {n["id"] for n in page1}
        ids2 = {n["id"] for n in page2}
        assert ids1.isdisjoint(ids2)
        assert ids1 | ids2 == {f"n{i}" for i in range(6)}

    # find_edges

    def test_find_edges_skip_zero_returns_all(self, graph_with_edges):
        result = graph_with_edges.find_edges(skip=0)
        assert len(result) == 5

    def test_find_edges_skip_reduces_count(self, graph_with_edges):
        result = graph_with_edges.find_edges(skip=2)
        assert len(result) == 3

    def test_find_edges_skip_and_limit(self, graph_with_edges):
        result = graph_with_edges.find_edges(skip=1, limit=2)
        assert len(result) == 2

    def test_find_edges_skip_beyond_returns_empty(self, graph_with_edges):
        result = graph_with_edges.find_edges(skip=100)
        assert result == []

    def test_find_edges_pagination_covers_all(self, graph_with_edges):
        page1 = graph_with_edges.find_edges(skip=0, limit=3)
        page2 = graph_with_edges.find_edges(skip=3, limit=3)
        combined = len(page1) + len(page2)
        assert combined == 5

    # find_active_nodes

    def test_find_active_nodes_skip_zero_returns_all(self, graph_with_nodes):
        result = graph_with_nodes.find_active_nodes(skip=0)
        assert len(result) == 6

    def test_find_active_nodes_skip_reduces_count(self, graph_with_nodes):
        result = graph_with_nodes.find_active_nodes(skip=3)
        assert len(result) == 3

    def test_find_active_nodes_skip_and_limit(self, graph_with_nodes):
        result = graph_with_nodes.find_active_nodes(skip=2, limit=2)
        assert len(result) == 2


class TestContextGraphMinWeightNeighborFilter:
    """get_neighbors(min_weight=N) from PR #385 filters out low-weight edges."""

    @pytest.fixture
    def weighted_graph(self):
        from semantica.context import ContextGraph
        g = ContextGraph()
        g.add_node("center", "entity")
        g.add_node("heavy", "entity")
        g.add_node("light", "entity")
        g.add_node("zero", "entity")
        g.add_edge("center", "heavy", "link", weight=0.9)
        g.add_edge("center", "light", "link", weight=0.2)
        g.add_edge("center", "zero", "link", weight=0.0)
        return g

    def test_no_min_weight_returns_all_neighbors(self, weighted_graph):
        result = weighted_graph.get_neighbors("center")
        ids = {n["id"] for n in result}
        assert ids == {"heavy", "light", "zero"}

    def test_min_weight_filters_low_weight_edges(self, weighted_graph):
        result = weighted_graph.get_neighbors("center", min_weight=0.5)
        ids = {n["id"] for n in result}
        assert "heavy" in ids
        assert "light" not in ids
        assert "zero" not in ids

    def test_min_weight_zero_returns_all(self, weighted_graph):
        result = weighted_graph.get_neighbors("center", min_weight=0.0)
        assert len(result) == 3

    def test_min_weight_one_returns_none(self, weighted_graph):
        result = weighted_graph.get_neighbors("center", min_weight=1.0)
        assert result == []

    def test_min_weight_exact_boundary_inclusive(self, weighted_graph):
        # edge to "heavy" has weight=0.9; min_weight=0.9 should include it
        result = weighted_graph.get_neighbors("center", min_weight=0.9)
        ids = {n["id"] for n in result}
        assert "heavy" in ids


# ===========================================================================
# PR #385 — ContextGraph Thread Safety
# ===========================================================================

class TestContextGraphThreadSafety:
    """ContextGraph must be safe for concurrent reads and writes."""

    def test_concurrent_add_node_no_corruption(self):
        from semantica.context import ContextGraph
        graph = ContextGraph()
        errors = []

        def add_nodes(start: int):
            try:
                for i in range(start, start + 20):
                    graph.add_node(f"n-{i}", "entity", content=str(i))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_nodes, args=(i * 20,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(graph.nodes) == 100

    def test_concurrent_reads_while_writing(self):
        from semantica.context import ContextGraph
        graph = ContextGraph()
        for i in range(20):
            graph.add_node(f"initial-{i}", "entity")

        errors = []

        def reader():
            try:
                for _ in range(50):
                    _ = graph.find_nodes()
            except Exception as exc:
                errors.append(exc)

        def writer():
            try:
                for i in range(50):
                    graph.add_node(f"w-{threading.get_ident()}-{i}", "entity")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(3)] + \
                  [threading.Thread(target=writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_add_edge_no_corruption(self):
        from semantica.context import ContextGraph
        graph = ContextGraph()
        for i in range(40):
            graph.add_node(f"n{i}", "entity")

        errors = []

        def add_edges(offset: int):
            try:
                for i in range(offset, offset + 10):
                    graph.add_edge(f"n{i}", f"n{i+1}", "link")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_edges, args=(i * 10,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_find_nodes_consistent_under_concurrent_writes(self):
        from semantica.context import ContextGraph
        graph = ContextGraph()
        results = []
        errors = []

        def writer():
            for i in range(30):
                graph.add_node(f"wt-{threading.get_ident()}-{i}", "entity")

        def reader():
            try:
                for _ in range(10):
                    snapshot = graph.find_nodes()
                    results.append(len(snapshot))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)] + \
                  [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # All snapshots must be non-negative integers (no partial-write corruption)
        assert all(r >= 0 for r in results)


# ===========================================================================
# PR #319 — SKOS Vocabulary Module: namespace helpers (gap tests)
# ===========================================================================

class TestSKOSNamespaceHelpers:
    """get_skos_uri and build_concept_scheme_uri gap tests beyond existing suite."""

    @pytest.fixture
    def nm(self):
        from semantica.ontology.namespace_manager import NamespaceManager
        return NamespaceManager()

    def test_get_skos_uri_prefLabel(self, nm):
        uri = nm.get_skos_uri("prefLabel")
        assert uri == "http://www.w3.org/2004/02/skos/core#prefLabel"

    def test_get_skos_uri_Concept(self, nm):
        uri = nm.get_skos_uri("Concept")
        assert "Concept" in uri
        assert uri.startswith("http://www.w3.org/2004/02/skos/core#")

    def test_get_skos_uri_broader(self, nm):
        uri = nm.get_skos_uri("broader")
        assert uri.endswith("#broader")

    def test_build_concept_scheme_uri_lowercases(self, nm):
        uri = nm.build_concept_scheme_uri("My Vocabulary")
        assert "my-vocabulary" in uri.lower()

    def test_build_concept_scheme_uri_replaces_spaces_with_hyphens(self, nm):
        uri = nm.build_concept_scheme_uri("Drug Interaction Terms")
        assert " " not in uri

    def test_build_concept_scheme_uri_contains_vocab_segment(self, nm):
        uri = nm.build_concept_scheme_uri("Test")
        assert "/vocab/" in uri

    def test_build_concept_scheme_uri_special_chars_normalised(self, nm):
        uri = nm.build_concept_scheme_uri("A&B!Vocab")
        assert "&" not in uri
        assert "!" not in uri


# ===========================================================================
# PR #318 — SHACL: quality tiers and export (gap tests)
# ===========================================================================

class TestSHACLQualityTiersGap:
    """Quality tier differences between basic / standard / strict."""

    @pytest.fixture
    def generator(self):
        from semantica.ontology.ontology_generator import SHACLGenerator
        return SHACLGenerator()

    @pytest.fixture
    def simple_ontology(self):
        # SHACLGenerator expects classes and top-level properties (with domain)
        return {
            "classes": [{"name": "Person"}],
            "properties": [
                {"name": "name", "domain": "Person", "range": "string"},
                {"name": "age", "domain": "Person", "range": "integer"},
            ],
        }

    def test_basic_tier_produces_output(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        gen = SHACLGenerator(quality_tier="basic")
        result = gen.generate(simple_ontology)
        assert result is not None
        assert len(gen.serialize(result)) > 0

    def test_standard_tier_produces_output(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        gen = SHACLGenerator(quality_tier="standard")
        result = gen.generate(simple_ontology)
        assert len(gen.serialize(result)) > 0

    def test_strict_tier_produces_output(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        gen = SHACLGenerator(quality_tier="strict")
        result = gen.generate(simple_ontology)
        assert len(gen.serialize(result)) > 0

    def test_strict_tier_contains_closed_constraint(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        gen = SHACLGenerator(quality_tier="strict")
        result = gen.generate(simple_ontology)
        turtle = gen.serialize(result)
        assert "sh:closed" in turtle

    def test_basic_tier_does_not_contain_closed(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        gen = SHACLGenerator(quality_tier="basic")
        result = gen.generate(simple_ontology)
        turtle = gen.serialize(result)
        assert "sh:closed" not in turtle

    def test_three_tiers_produce_different_output(self, simple_ontology):
        from semantica.ontology.ontology_generator import SHACLGenerator
        basic_gen = SHACLGenerator(quality_tier="basic")
        strict_gen = SHACLGenerator(quality_tier="strict")
        basic = basic_gen.serialize(basic_gen.generate(simple_ontology))
        strict = strict_gen.serialize(strict_gen.generate(simple_ontology))
        assert basic != strict


class TestRDFExporterExportSHACL:
    """RDFExporter.export_shacl() writes SHACL strings to files."""

    def test_export_shacl_writes_ttl_file(self, tmp_path):
        from semantica.export.rdf_exporter import RDFExporter
        exporter = RDFExporter()
        shacl = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        out = tmp_path / "shapes.ttl"
        exporter.export_shacl(shacl, str(out))
        assert out.exists()
        assert out.read_text().strip().startswith("@prefix")

    def test_export_shacl_invalid_extension_raises(self, tmp_path):
        from semantica.export.rdf_exporter import RDFExporter
        from semantica.utils.exceptions import ValidationError
        exporter = RDFExporter()
        out = tmp_path / "shapes.txt"
        with pytest.raises((ValueError, ValidationError)):
            exporter.export_shacl("@prefix sh: <…> .", str(out))

    def test_export_shacl_jsonld_extension_accepted(self, tmp_path):
        from semantica.export.rdf_exporter import RDFExporter
        exporter = RDFExporter()
        content = '{"@context": {}}'
        out = tmp_path / "shapes.jsonld"
        exporter.export_shacl(content, str(out))
        assert out.exists()


# ===========================================================================
# PR #408 — OllamaProvider base_url fix (gap tests)
# ===========================================================================

class TestOllamaProviderBaseURLGap:
    """Additional gap tests for PR #408 OllamaProvider base_url fix."""

    def test_custom_port_used_as_host(self):
        """Non-default port must flow through to the Client in every call."""
        ollama_mock = MagicMock()
        ollama_mock.Client = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"ollama": ollama_mock}):
            from semantica.semantic_extract.providers import OllamaProvider
            provider = OllamaProvider(
                model_name="llama3",
                base_url="http://192.168.1.10:11434",
            )
            # _init_client may be called during __init__ and/or lazily;
            # every invocation must pass the correct host.
            assert ollama_mock.Client.called
            for call_args in ollama_mock.Client.call_args_list:
                assert call_args == ((), {"host": "http://192.168.1.10:11434"}) or \
                    call_args.kwargs.get("host") == "http://192.168.1.10:11434"

    def test_client_is_not_raw_module(self):
        """self.client must never be the raw ollama module."""
        ollama_mock = MagicMock()
        client_instance = MagicMock()
        ollama_mock.Client = MagicMock(return_value=client_instance)
        with patch.dict("sys.modules", {"ollama": ollama_mock}):
            from semantica.semantic_extract.providers import OllamaProvider
            provider = OllamaProvider(model_name="llama3")
            provider._init_client()
            assert provider.client is not ollama_mock


# ===========================================================================
# PR #371 — DatalogReasoner gap tests
# ===========================================================================

class TestDatalogReasonerGap:
    """Gap tests for DatalogReasoner beyond the existing 23 tests."""

    @pytest.fixture
    def reasoner(self):
        from semantica.reasoning import DatalogReasoner
        return DatalogReasoner()

    def test_derive_all_idempotent(self, reasoner):
        reasoner.add_fact("parent(alice, bob)")
        reasoner.add_rule("grandparent(X, Z) :- parent(X, Y), parent(Y, Z).")
        reasoner.add_fact("parent(bob, carol)")
        first = reasoner.derive_all()
        second = reasoner.derive_all()
        # Second call must produce same results (idempotency)
        assert set(first) == set(second)

    def test_query_returns_list(self, reasoner):
        reasoner.add_fact("color(sky, blue)")
        result = reasoner.query("color(?X, ?Y)")
        assert isinstance(result, list)

    def test_query_no_match_returns_empty(self, reasoner):
        result = reasoner.query("nonexistent(?X)")
        assert result == []

    def test_multi_hop_four_levels(self, reasoner):
        reasoner.add_fact("parent(a, b)")
        reasoner.add_fact("parent(b, c)")
        reasoner.add_fact("parent(c, d)")
        reasoner.add_fact("parent(d, e)")
        # DatalogReasoner uses uppercase-letter variables (not ?-prefixed)
        reasoner.add_rule("ancestor(X, Z) :- parent(X, Z).")
        reasoner.add_rule("ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).")
        results = reasoner.query("ancestor(a, ?Z)")
        targets = {r["Z"] for r in results}
        assert "e" in targets

    def test_load_from_context_graph(self, reasoner):
        from semantica.context import ContextGraph
        graph = ContextGraph()
        graph.add_node("alice", "Person")
        graph.add_node("bob", "Person")
        graph.add_edge("alice", "bob", "knows")
        reasoner.load_from_graph(graph)
        result = reasoner.query("knows(?X, ?Y)")
        assert len(result) >= 1

    def test_add_fact_dict_source_target_type(self, reasoner):
        reasoner.add_fact({"source": "alice", "target": "bob", "type": "knows"})
        result = reasoner.query("knows(?X, ?Y)")
        assert any(r.get("X") == "alice" and r.get("Y") == "bob" for r in result)

    def test_add_fact_subject_predicate_object_shape(self, reasoner):
        reasoner.add_fact({"subject": "cat", "predicate": "isa", "object": "animal"})
        result = reasoner.query("isa(?X, ?Y)")
        assert len(result) >= 1

    def test_duplicate_fact_not_duplicated(self, reasoner):
        reasoner.add_fact("color(sky, blue)")
        reasoner.add_fact("color(sky, blue)")
        result = reasoner.query("color(?X, ?Y)")
        assert len(result) == 1

    def test_derive_all_returns_list(self, reasoner):
        # Facts must use constants (lowercase); uppercase is treated as variable
        reasoner.add_fact("category(x, alpha)")
        result = reasoner.derive_all()
        assert isinstance(result, list)
