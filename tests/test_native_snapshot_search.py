"""The wire query adapter delegates the complete search to the native owner."""
from unittest.mock import patch
from types import SimpleNamespace

from semantica.context.context_retriever import ContextRetriever, RetrievedContext
from tests.test_semantic_query_worker import _build, _request, _serve


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
    assert prepared[1] == {"rep": {"source_id": "source"}}
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
    prepared = (
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
