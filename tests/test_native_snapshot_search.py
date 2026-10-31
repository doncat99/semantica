"""The wire query adapter delegates the complete search to the native owner."""
from unittest.mock import patch
from types import SimpleNamespace
import pytest

from semantica.context.context_retriever import ContextRetriever, RetrievedContext
from tests.test_semantic_query_worker import _build, _request, _serve


def test_keyword_worker_does_not_import_vector_or_graph_analytics():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c", '''
import sys
from importlib.abc import MetaPathFinder
class RejectUnrelatedImports(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("semantica.vector_store", "semantica.kg", "numpy", "scipy")):
            raise AssertionError("keyword imported unrelated capability: " + fullname)
sys.meta_path.insert(0, RejectUnrelatedImports())
import semantica.semantic_query_worker
from semantica.context import ContextRetriever
from semantica.context.context_retriever import ContextRetriever as Owner
assert ContextRetriever is Owner
assert Owner().search_snapshot(Owner.prepare_snapshot_search(type("Empty", (), {
    field: [] for field in ("entities", "assertions", "relations", "conflicts", "topics", "evidence_spans", "document_representations")
})()), query="ESG", mode="keyword", retrieval=None) == []
'''], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("query", ["Ada", "a", "Lovelace Engine", "環境", "é", "scope-1", "missing"])
@pytest.mark.parametrize("sources", [None, ["source-1"], ["source-2"], []])
def test_persisted_keyword_preserves_full_native_selection_scores_order(tmp_path, query, sources):
    from tests.test_semantic_query_worker import _rewrite_artifacts
    from semantica.semantic_artifact_schema import SemanticArtifact
    from semantica.explorer.search_index import ReferenceGraphSearchIndex
    built = _build(tmp_path, second_source=True)
    def enrich(payload):
        original = payload["entities"][0]
        payload["entities"].extend({**original, "id": f"entity:unicode:{i}", "canonical_name": text}
            for i, text in enumerate(["環境永續 Ada", "énergie", "scope-1", "xAdax"]))
    _rewrite_artifacts(built, snapshot_change=enrich)
    artifact = SemanticArtifact.model_validate_json(built["graph_path"].read_bytes())
    retriever = ContextRetriever()
    expected = retriever.search_snapshot(retriever.prepare_snapshot_search(artifact), query=query,
        mode="keyword", retrieval=None, source_ids=sources, max_results=1000)
    with patch("semantica.explorer.search_index.GraphSearchIndex.rebuild", side_effect=AssertionError("full rebuild")):
        reader = ReferenceGraphSearchIndex(built["keyword_path"], built["keyword_digest"],
            built["graph_path"], built["graph_digest"], artifact.project_id, artifact.id)
        try:
            sparse, matched = reader.prepare_matches(query.lower().split())
            actual = retriever.search_snapshot(sparse, query=query, mode="keyword", retrieval=None,
                source_ids=sources, max_results=1000, matched_ids=matched)
        finally:
            reader.close()
    assert actual == expected


def test_offline_native_index_does_not_rewrite_graph_or_store_content(tmp_path):
    import sqlite3
    from semantica.explorer.search_index import GraphSearchIndex
    built = _build(tmp_path)
    before = built["graph_path"].read_bytes()
    identity = built["graph_path"].stat()
    path = tmp_path / "offline.sqlite"
    graph_digest, index_digest = GraphSearchIndex.index_artifact(built["graph_path"], path)
    assert graph_digest == built["graph_digest"]
    assert before == built["graph_path"].read_bytes()
    assert identity == built["graph_path"].stat()
    with sqlite3.connect(path) as db:
        assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"metadata", "records", "terms", "postings"}
        assert [row[1] for row in db.execute("PRAGMA table_info(records)")] == ["n", "field", "id", "ordinal", "offset", "length", "digest"]
    request = _request(built)
    request["params"]["keywordIndex"].update(path=str(path), digest=index_digest)
    assert _serve(request)["result"] == _serve(_request(built))["result"]
    with pytest.raises(ValueError, match="already exists"):
        GraphSearchIndex.index_artifact(built["graph_path"], path)


@pytest.mark.parametrize("mutation", ["missing", "project", "revision", "graph", "offset", "record-digest", "index-digest",
                                      "evidence-digest", "missing-catalog", "canonical-header"])
def test_persisted_keyword_rejects_invalid_identity_and_references(tmp_path, mutation):
    import sqlite3
    from tests.test_semantic_query_worker import _digest
    built = _build(tmp_path)
    request = _request(built)
    if mutation == "missing":
        request["params"].pop("keywordIndex")
    elif mutation == "index-digest":
        request["params"]["keywordIndex"]["digest"] = "sha256:" + "0" * 64
    else:
        with sqlite3.connect(built["keyword_path"]) as db:
            if mutation in {"project", "revision", "graph"}:
                key = {"project": "project_id", "revision": "snapshot_id", "graph": "graph_digest"}[mutation]
                db.execute("UPDATE metadata SET value='different' WHERE key=?", (key,))
            elif mutation == "offset":
                db.execute("UPDATE records SET offset=-1 WHERE field='entities'")
            elif mutation == "evidence-digest":
                db.execute("UPDATE records SET digest=? WHERE field='evidence_spans'", ("0" * 64,))
            elif mutation == "missing-catalog":
                db.execute("DELETE FROM records WHERE field='document_representations'")
            elif mutation == "canonical-header":
                db.execute("""UPDATE records SET (offset,length,digest) =
                    (SELECT offset,length,digest FROM records WHERE field='snapshot_id') WHERE field='project_id'""")
            else:
                db.execute("UPDATE records SET digest=? WHERE field='entities'", ("0" * 64,))
        request["params"]["keywordIndex"]["digest"] = _digest(built["keyword_path"])
    assert _serve(request)["ok"] is False


@pytest.mark.parametrize("mutation", ["changed", "removed", "added", "duplicate", "foreign-scope"])
def test_native_query_owns_current_source_version_admission(tmp_path, mutation):
    built = _build(tmp_path)
    request = _request(built)
    sources = request["params"]["sources"]
    if mutation == "changed":
        sources[0]["contentHash"] = "b3-" + "f" * 64
    elif mutation == "removed":
        sources.clear()
    elif mutation == "added":
        sources.append({"sourceId": "new-source", "contentHash": "b3-" + "e" * 64})
    elif mutation == "duplicate":
        sources.append(sources[0].copy())
    else:
        request["params"]["sourceIds"] = ["foreign-source"]
    response = _serve(request)
    assert response["ok"] is False
    assert "result" not in response


def test_artifact_admission_checks_mention_owners_in_one_pass(tmp_path):
    from semantica.semantic_artifact_schema import KnowledgeEntity, IdentityRegistryEntry

    artifact = _build(tmp_path)["snapshot"]
    reads = []
    class CountedMetadata(dict):
        def get(self, key, default=None):
            if key == "mention_ids":
                reads.append(key)
            return super().get(key, default)
    entities, mentions, registry = [], [], []
    for i in range(40):
        mention_id, entity_id = f"mention:{i}", f"entity:{i}"
        entity = KnowledgeEntity(id=entity_id, canonical_name="ESG", type="Topic")
        entity.metadata = CountedMetadata(mention_ids=[mention_id])
        entities.append(entity)
        mentions.append(KnowledgeEntity(id=mention_id, canonical_name="ESG", type="Topic"))
        registry.append(IdentityRegistryEntry(mention_id=mention_id, entity_id=entity_id,
                                              canonical_name="ESG", type="Topic"))
    artifact = artifact.model_copy(update={"entities": entities, "entity_mentions": mentions,
        "identity_registry": registry, "assertions": [], "relations": [], "communities": [],
        "topics": [], "conflicts": [], "retrieval_manifests": []})
    artifact.validate_references()
    assert len(reads) <= len(entities), "admission rescanned all entities for every mention"
    registry[-1].entity_id = entities[0].id
    with pytest.raises(ValueError, match="identity registry disagrees"):
        artifact.validate_references()
    entities[-1].metadata["mention_ids"] = []
    registry[-1].entity_id = entities[-1].id
    with pytest.raises(ValueError, match="identity registry disagrees"):
        artifact.validate_references()
    entities[-1].metadata["mention_ids"] = "mention:39"
    with pytest.raises(ValueError, match="mention_ids must be a list"):
        artifact.validate_references()


@pytest.mark.parametrize("query", ["ESG", "es", "g", "ESG governance", "環境", "é", "scope-1", "missing"])
def test_indexed_keyword_equals_exhaustive_native_results_and_reuses_index(query):
    from semantica.context.snapshot_search import PreparedSnapshotSearch
    texts = ["ESG", "xESGx", "governance ESG", "環境永續 ESG", "énergie", "scope-1"]
    candidates = [(f"record:{i}", "entity", text, ["ev"], "accepted", None, ["source"])
                  for i, text in enumerate(texts + ["unrelated"] * 100)]
    prepared = PreparedSnapshotSearch({}, {}, candidates)
    retriever = ContextRetriever()
    expected = retriever._keyword_match_entities(
        [{"id": item[0], "name": item[2]} for item in candidates], query, len(candidates))
    with patch.object(retriever, "_keyword_match_entities", wraps=retriever._keyword_match_entities) as score:
        first = retriever.search_snapshot(prepared, query=query, mode="keyword", retrieval=None, max_results=1000)
        assert [(hit.source, hit.score) for hit in first] == [(item["id"], value) for item, value in expected]
        assert len(score.call_args.args[0]) < len(candidates)
    with patch.object(prepared.keyword_index, "rebuild", side_effect=AssertionError("rebuilt warm index")):
        second = retriever.search_snapshot(prepared, query=query, mode="keyword", retrieval=None, max_results=1000)
    assert second == first


def test_native_index_has_complete_unicode_substring_candidates_and_tracks_mutations():
    from semantica.explorer.search_index import GraphSearchIndex

    index = GraphSearchIndex(secondary_scan_limit=1)
    index.rebuild([{"id": "exact", "content": "ESG"},
                   {"id": "inside", "content": "xESGx 環境永續"},
                   {"id": "secondary", "properties": {"description": "ESG"}},
                   {"id": "other", "content": "governance"}])
    assert index.substring_candidates("esg".split()) == {"exact", "inside", "secondary"}
    assert index.substring_candidates(["環境", "governance"]) == {"inside", "other"}
    assert index.substring_candidates(["e"]) == {"exact", "inside", "secondary", "other"}
    index.upsert({"id": "inside", "content": "replaced"})
    index.remove("exact")
    assert index.substring_candidates(["esg"]) == {"secondary"}
    index.rebuild([])
    assert not index.substring_candidates(["esg"])


def test_substring_search_does_not_prepare_unused_ranked_indexes():
    from semantica.explorer.search_index import GraphSearchIndex

    index = GraphSearchIndex()
    with patch("semantica.explorer.search_index._tokenize", side_effect=AssertionError("keyword prepared ranked tokens")):
        index.rebuild([{"id": "a", "content": "ESG"}, {"id": "b", "content": "governance"}])
        assert index.substring_candidates(["esg"]) == {"a"}
        index.upsert({"id": "a", "content": "report"})
        index.remove("b")
        assert index.substring_candidates(["report"]) == {"a"}
    assert index.search("report")[0][0][0] == "a"
    index.upsert({"id": "a", "content": "climate"})
    assert not index.search("report")[0]
    assert index.search("climate")[0][0][0] == "a"
    index.remove("a")
    assert not index.search("climate")[0]


def test_keyword_never_reads_vectors_or_calls_vector_retrieval(tmp_path, monkeypatch):
    from pathlib import Path
    from semantica.vector_store.vector_store import VectorRetriever

    built = _build(tmp_path)
    request = _request(built)
    request["params"].pop("retrieval")
    read_bytes = Path.read_bytes
    def read(path):
        assert path != built["retrieval_path"], "keyword read vectors"
        return read_bytes(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(VectorRetriever, "search_similar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("keyword used vectors")))
    result = _serve(request)
    assert result["ok"], result
    assert result["result"]["contexts"]


def test_search_projection_ignores_unconsumed_document_and_entity_payloads():
    from semantica.semantic_artifact_schema import KnowledgeEntity, EvidenceSpan, DocumentLocator, DocumentRepresentation

    evidence = EvidenceSpan(id="ev", representation_id="rep", quote="ESG reporting",
        locator=DocumentLocator(representation_id="rep", origin="native", quote="ESG reporting",
                                start_char=0, end_char=13, quality="precise"),
        metadata={"unused": object()})
    entity = KnowledgeEntity(id="entity", canonical_name="ESG", type="Topic", evidence_ids=["ev"],
                             metadata={"unused": object()})
    representation = DocumentRepresentation.model_construct(id="rep", source_id="source",
                                                            metadata={"document": object()})
    artifact = SimpleNamespace(evidence_spans=[evidence], entities=[entity],
        document_representations=[representation], assertions=[], relations=[], conflicts=[], topics=[])
    prepared = ContextRetriever.prepare_snapshot_search(artifact)
    assert prepared.representations == {"rep": {"source_id": "source"}}
    hits = ContextRetriever().search_snapshot(prepared, query="ESG", mode="keyword", retrieval={}, max_results=1000)
    assert {hit.source for hit in hits} == {"entity", "ev"}
    assert all(hit.metadata["evidence_ids"] == ["ev"] for hit in hits)


def test_wire_query_delegates_selection_and_score_to_native_search(tmp_path):
    built = _build(tmp_path)
    assert callable(getattr(ContextRetriever, "search_snapshot", None))
    with patch.object(ContextRetriever, "search_snapshot", return_value=[
        RetrievedContext(content="native selection", score=0.375, source="native",
            metadata={"id": "native", "kind": "entity", "evidence_ids": ["ev"],
                      "source_ids": ["source-1"], "status": "accepted", "polarity": None})
    ]) as search:
        result = _serve(_request(built))
    assert result["ok"] is True, result
    assert result["result"]["contexts"][0]["id"] == "native"
    assert result["result"]["contexts"][0]["score"] == 0.375
    assert search.call_count == 1


def test_native_search_keeps_full_provenance_scope_and_unmodified_vector_order():
    from semantica.context.snapshot_search import PreparedSnapshotSearch
    prepared = PreparedSnapshotSearch(
        {"ev-a": {"representation_id": "rep-a", "locator": {"start_char": 0, "end_char": 10}},
         "ev-b": {"representation_id": "rep-b", "locator": {"start_char": 0, "end_char": 10}}},
        {"rep-a": {"source_id": "a"}, "rep-b": {"source_id": "b"}},
        [("cross", "entity", "ESG", ["ev-a", "ev-b"], "accepted", None, ["a", "b"]),
         ("a", "entity", "ESG", ["ev-a"], "accepted", None, ["a"]),
         ("b", "evidence", "ESG", ["ev-b"], "native", None, ["b"])])
    retrieval = {"embedding_space": {"model_id": "m", "binding_id": "binding", "dimensions": 2},
                 "embeddings": [
                     {"source_id": "a", "start_char": 0, "end_char": 10, "vector": [0.0, 1.0]},
                     {"source_id": "b", "start_char": 0, "end_char": 10, "vector": [1.0, 0.0]}]}
    retriever = ContextRetriever()
    with patch.object(retriever, "retrieve", side_effect=AssertionError("hybrid/model path forbidden")):
        for mode in ("keyword", "semantic"):
            hits = retriever.search_snapshot(prepared, query="ESG", mode=mode, retrieval=retrieval,
                embedding=SimpleNamespace(model_id="m", binding_id="binding", vector=[1.0, 0.0]),
                source_ids=["a"], max_results=1)
            assert [hit.source for hit in hits] == ["a"]
            assert hits[0].score == (2.0 if mode == "keyword" else 0.0)
        hits = retriever.search_snapshot(prepared, query="no lexical overlap", mode="semantic",
            retrieval=retrieval, embedding=SimpleNamespace(model_id="m", binding_id="binding", vector=[1.0, 0.0]),
            max_results=10)
        assert [hit.source for hit in hits] == ["cross", "b", "a"]
        assert [hit.score for hit in hits] == [1.0, 1.0, 0.0]
