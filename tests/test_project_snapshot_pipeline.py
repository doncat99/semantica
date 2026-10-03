import io
import json
from zipfile import ZipFile
import os
import threading
import urllib.error
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from semantica.project_snapshot_pipeline import _canonical_graph_projection
from semantica.project_snapshot_pipeline import build_project_snapshot, parse_source_artifact
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest, ParseSourceRequest
from semantica.project_snapshot_schema import KnowledgeEntity, KnowledgeRelation, ModelReceipt, ProjectSnapshot, stable_digest
from semantica.project_snapshot_worker import serve
from semantica.project_source import source_content_revision

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


def _typed_prompt_context(payload):
    prompt = payload["messages"][0]["content"]
    marker = "Input JSON:\n"
    return json.JSONDecoder().raw_decode(prompt[prompt.index(marker) + len(marker):])[0]


def _worker_output(stdout):
    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return events, events[-1]


def test_unique_quote_ignores_model_position_but_duplicate_requires_occurrence():
    from semantica.project_snapshot_pipeline import _find_occurrence, SnapshotBuildError

    text = "Green Bonds and Private Equity. Green Bonds"
    assert _find_occurrence(text, "Private Equity", 590) == (16, 30)
    with pytest.raises(SnapshotBuildError, match="outside its source window"):
        _find_occurrence(text, "Green Bonds", 590)


def test_relay_http_failure_preserves_safe_structured_error(monkeypatch):
    from types import SimpleNamespace
    from semantica.project_snapshot_pipeline import _relay_json, SnapshotBuildError

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    def rejected(_request, timeout):
        raise urllib.error.HTTPError("http://127.0.0.1/", 500, "Internal Server Error", {}, io.BytesIO(
            b'{"error":{"code":"INTERNAL_ERROR","message":"provider failed for test-token","retryable":true,"status":500}}'))
    monkeypatch.setattr("urllib.request.urlopen", rejected)
    relay = SimpleNamespace(authorization_env="OPENAI_API_KEY", base_url="http://127.0.0.1/v1/chat/completions", model_id="model-1", binding_id="default")
    with pytest.raises(SnapshotBuildError, match="structured_extraction relay returned HTTP 500: INTERNAL_ERROR") as failure:
        _relay_json(relay, {"model": "model-1"}, "structured_extraction")
    assert failure.value.status == 500
    assert failure.value.code == "INTERNAL_ERROR"
    assert failure.value.retryable is True
    assert "test-token" not in str(failure.value)


def test_relay_waits_for_complete_gateway_response(monkeypatch):
    from types import SimpleNamespace
    from semantica.project_snapshot_pipeline import _relay_json

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"choices":[]}'

    def respond(_request, timeout):
        assert timeout > 15 * 60
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", respond)
    relay = SimpleNamespace(authorization_env="OPENAI_API_KEY", base_url="http://127.0.0.1/v1/chat/completions", model_id="model-1", binding_id="default")
    response, receipt = _relay_json(relay, {"model": "model-1"}, "structured_extraction")
    assert response == {"choices": []}
    assert receipt.operation == "structured_extraction"


def test_product_output_repairs_citation_shape_through_native_typed_provider(monkeypatch):
    from types import SimpleNamespace
    from semantica import project_snapshot_pipeline as pipeline

    outputs = [
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [5]}]},
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}]},
    ]
    prompts = []

    def relay_response(relay, payload, operation):
        prompts.append(payload["messages"][0]["content"])
        result = {"model": relay.model_id, "choices": [{"message": {"content": json.dumps(outputs.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(prompts)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    result, receipts = pipeline._product_json(
        SimpleNamespace(model_id="model-1", binding_id="default"),
        "source_classification",
        "Classify the source.",
        {"evidence": [{"id": "evidence:source", "quote": "Source quote"}]},
        pipeline._ClassificationOutput,
    )

    assert result["assignments"][0]["citations"] == [{"evidence_id": "evidence:source", "quote": "Source quote"}]
    assert [receipt.id for receipt in receipts] == ["receipt:1", "receipt:2"]
    assert "Required JSON Schema" in prompts[1]
    assert "evidence_id" in prompts[1] and "quote" in prompts[1]


def test_product_output_repairs_semantic_citation_and_vocabulary(monkeypatch):
    from types import SimpleNamespace
    from semantica import project_snapshot_pipeline as pipeline

    valid = {"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
             "citations": [{"evidence_id": "evidence:source", "quote": "Source quote"}]}
    outputs = [
        {"assignments": [{**valid, "dimension_id": "invented", "citations": [
            {"evidence_id": "evidence:source", "quote": "Altered quote"}]}]},
        {"assignments": [valid]},
    ]
    prompts = []

    def relay_response(relay, payload, operation):
        prompts.append(payload["messages"][0]["content"])
        result = {"model": relay.model_id, "choices": [{"message": {"content": json.dumps(outputs.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(prompts)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    context = {
        "profile": _classification_profile(),
        "evidence": [{"id": "evidence:source", "quote": "Source quote"}],
    }
    result, receipts = pipeline._product_json(
        SimpleNamespace(model_id="model-1", binding_id="default"),
        "source_classification",
        "Classify the source.",
        context,
        pipeline._ClassificationOutput,
    )

    assert result == {"assignments": [valid]}
    assert [receipt.id for receipt in receipts] == ["receipt:1", "receipt:2"]
    assert "invented" in prompts[1]
    assert "Altered quote" in prompts[1]
    assert '"evidence_id":"evidence:source","quote":"Source quote"' in prompts[1]
    assert ']\nPrevious JSON response:' in prompts[1]


def test_product_output_repair_has_budget_for_schema_and_previous_json(monkeypatch):
    from types import SimpleNamespace
    from semantica import project_snapshot_pipeline as pipeline

    quote = "Grounded evidence. " * 2_400
    outputs = [
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [5], "invalid": "x" * 20_000}]},
        {"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9,
                          "citations": [{"evidence_id": "evidence:source", "quote": quote}]}]},
    ]

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self):
            return json.dumps({"model": "model-1", "choices": [{"message": {"content": json.dumps(outputs.pop(0))}}]}).encode()

    monkeypatch.setenv("OPENAI_API_KEY", "test-token")
    monkeypatch.setattr("urllib.request.urlopen", lambda _request, timeout: Response())
    result, receipts = pipeline._product_json(
        SimpleNamespace(model_id="model-1", binding_id="default", authorization_env="OPENAI_API_KEY",
                        base_url="http://127.0.0.1/v1/chat/completions"),
        "source_classification",
        "Classify the source.",
        {"evidence": [{"id": "evidence:source", "quote": quote}]},
        pipeline._ClassificationOutput,
    )

    assert result["assignments"][0]["citations"] == [{"evidence_id": "evidence:source", "quote": quote}]
    assert len(receipts) == 2


def test_identity_resolution_repairs_invalid_json_through_native_typed_provider(monkeypatch):
    from types import SimpleNamespace
    from semantica import project_snapshot_pipeline as pipeline

    candidates = [
        {"mention_id": "mention:1", "name": "Alpha", "type": "ORG", "source_id": "source:1",
         "previous_entity_id": None, "separate_from": [],
         "evidence": [{"id": "evidence:1", "quote": "Alpha one", "context": "Alpha one"}]},
        {"mention_id": "mention:2", "name": "Alpha", "type": "ORG", "source_id": "source:2",
         "previous_entity_id": None, "separate_from": [],
         "evidence": [{"id": "evidence:2", "quote": "Alpha two", "context": "Alpha two"}]},
    ]
    outputs = [[], {"merges": [{"mention_ids": ["mention:1", "mention:2"],
                                 "evidence_ids": ["evidence:1", "evidence:2"], "reason": "Same organization"}],
                    "splits": []}]
    prompts = []

    def relay_response(relay, payload, operation):
        prompts.append(payload["messages"][0]["content"])
        result = {"model": relay.model_id, "choices": [{"message": {"content": json.dumps(outputs.pop(0))}}]}
        return result, ModelReceipt(id=f"receipt:{len(prompts)}", operation=operation, provider="test",
                                    model=relay.model_id, input_digest=H1, output_digest=H2)

    monkeypatch.setattr(pipeline, "_relay_json", relay_response)
    judgments, receipts = pipeline._identity_batch(candidates, SimpleNamespace(model_id="model-1", binding_id="default"))

    assert judgments == [{"mention_ids": ["mention:1", "mention:2"],
                          "evidence_ids": ["evidence:1", "evidence:2"],
                          "reason": "Same organization", "decision_type": "merge"}]
    assert [receipt.id for receipt in receipts] == ["receipt:1", "receipt:2"]
    assert "Required JSON Schema" in prompts[1]


def test_relationship_discovery_omits_ungrounded_qualifier_without_losing_valid_relations(monkeypatch):
    from semantica.project_snapshot_pipeline import _discover_cross_source_relationships
    from semantica.project_snapshot_schema import DocumentLocator, EvidenceSpan

    entities = [KnowledgeEntity(id="entity:left", canonical_name="Left", type="concept"),
                KnowledgeEntity(id="entity:right", canonical_name="Right", type="concept")]
    evidence = [EvidenceSpan(id=f"evidence:{index}", representation_id=f"representation:{index}", quote=quote,
                             locator=DocumentLocator(representation_id=f"representation:{index}", origin="native",
                                                     quote=quote, start_char=0, end_char=len(quote), quality="precise"))
                for index, quote in [(1, "Left recorded 31."), (2, "Right observed 31.")]]
    candidate = {"candidate_id": "candidate:1", "source_entity": {"id": entities[0].id},
                 "target_entity": {"id": entities[1].id},
                 "evidence": [{"id": span.id, "quote": span.quote, "source_id": f"source:{index}",
                               "endpoint_ids": [entities[index - 1].id]} for index, span in enumerate(evidence, 1)]}
    citations = [{"evidence_id": span.id, "quote": span.quote} for span in evidence]
    valid = {"candidate_id": candidate["candidate_id"], "source_entity_id": entities[0].id,
             "target_entity_id": entities[1].id, "predicate": "associated with",
             "qualifiers": {"polarity": "positive"}, "citations": citations, "reason": "Both are observed."}
    receipt = ModelReceipt(id="receipt:relationship", operation="relationship_discovery", provider="test",
                           model="model-1", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._relationship_candidates", lambda *_: [candidate])
    monkeypatch.setattr("semantica.project_snapshot_pipeline._relationship_batch",
                        lambda *_: ([{**valid, "qualifiers": {"polarity": "positive", "unit": "percent"}}, valid], receipt))

    assertions, relations, receipts = _discover_cross_source_relationships(
        "project-1", [], entities, [], [], evidence, None)
    assert len(assertions) == len(relations) == 1
    assert relations[0].evidence_ids == [span.id for span in evidence]
    assert receipts == [receipt]


def _classification_profile():
    return {"id": "profile:test", "version": "1", "label": "Document purpose", "description": "Source purpose",
        "dimensions": [{"id": "purpose", "label": "Purpose", "cardinality": "single", "vocabulary": [{"id": "history", "label": "History"}, {"id": "manual", "label": "Manual"}]},
            {"id": "topic", "label": "Topic", "cardinality": "multi", "vocabulary": []}]}


@pytest.mark.parametrize("corruption", ["unknown-id", "altered-quote", "missing-citation", "unknown-category", "cardinality"])
def test_semantic_classification_rejects_invalid_model_evidence(tmp_path, monkeypatch, corruption):
    from semantica.project_snapshot_pipeline import _build_source, _source_passages, _classify_source, SnapshotBuildError
    from semantica.project_snapshot_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    citation = {"evidence_id": built["passages"][0].id, "quote": built["passages"][0].quote}
    assignment = {"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [citation]}
    if corruption == "unknown-id":
        citation["evidence_id"] = "evidence:invented"
    elif corruption == "altered-quote":
        citation["quote"] = "Ada invented a spaceship."
    elif corruption == "missing-citation":
        assignment["citations"] = []
    elif corruption == "unknown-category":
        assignment["item_id"] = "invented"
    assignments = [assignment]
    if corruption == "cardinality":
        assignments.append({**assignment, "item_id": "manual"})
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"assignments": assignments}, [receipt]))
    with pytest.raises(SnapshotBuildError):
        _classify_source(built, ClassificationProfile.model_validate(_classification_profile()), None)


def test_semantic_classification_preserves_source_offsets_and_unclassified_dimensions(tmp_path, monkeypatch):
    from semantica.project_snapshot_pipeline import _build_source, _source_passages, _classify_source
    from semantica.project_snapshot_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    span = built["passages"][0]
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [{"evidence_id": span.id, "quote": span.quote}]}]}, [receipt]))
    classification, _ = _classify_source(built, ClassificationProfile.model_validate(_classification_profile()), None)
    assert classification.assignments[0].evidence_ids == [span.id]
    assert classification.unclassified_dimension_ids == ["topic"]
    assert built["text"][span.locator.start_char:span.locator.end_char] == span.quote


def test_docling_evidence_preserves_reading_order_and_physical_locators(tmp_path):
    from semantica.project_snapshot_pipeline import _build_source, _docling_cell_evidence, _source_passages
    from semantica.project_snapshot_schema import SourceBuildInput

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"source")
    source = SourceBuildInput(filePath=str(source_path), sourceId="4830a9a9-25ed-45ac-87d0-afcc80587480",
                              materialRevision=source_content_revision(source_path),
                              mimeType="application/pdf", name="source.pdf")
    text = "Chapter\nRepeated\nRepeated\nx = y\nROE\n12%"
    def bbox(top):
        return {"l": 10, "t": top, "r": 100, "b": top + 10, "coord_origin": "TOPLEFT"}
    raw = {
        "texts": [
            {"self_ref": "#/texts/0", "label": "section_header", "level": 1, "text": "Chapter", "prov": [{"page_no": 1, "bbox": bbox(10)}]},
            {"self_ref": "#/texts/1", "label": "text", "text": "Repeated", "prov": [{"page_no": 1, "bbox": bbox(30)}]},
            {"self_ref": "#/texts/2", "label": "text", "text": "Repeated", "prov": [{"page_no": 2, "bbox": bbox(10)}]},
            {"self_ref": "#/texts/3", "label": "formula", "text": "x = y", "prov": [{"page_no": 2, "bbox": bbox(30)}]},
        ],
        "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 3, "bbox": bbox(10)}],
                    "data": {"table_cells": [
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 0, "row_span": 1, "col_span": 1, "text": "ROE", "bbox": bbox(20)},
                        {"start_row_offset_idx": 0, "start_col_offset_idx": 1, "row_span": 1, "col_span": 1, "text": "12%", "bbox": bbox(20)},
                    ]}}],
        "groups": [], "pictures": [], "key_value_items": [], "form_items": [],
        "body": {"children": [{"$ref": ref} for ref in
                              ("#/texts/0", "#/texts/1", "#/texts/2", "#/texts/3", "#/tables/0")]},
    }
    document = {"format": "docling", "document": raw, "text": text}
    model_result = {"entities": [{"id": "e1", "name": "Repeated", "type": "concept", "occurrence": 1}], "relations": []}
    built = _build_source(source, False, model_result=model_result,
                          parsed=(text, document, "native", source.material_revision, "docling", "2"))
    passages = _source_passages(built)
    assert all(len(span.id) <= 128 for span in passages)

    repeated = [span for span in passages if span.quote == "Repeated"]
    assert [span.locator.page for span in repeated] == [1, 2]
    assert repeated[1].locator.section_path == ["Chapter"]
    entity_span = next(span for span in built["evidence"] if span.quote == "Repeated")
    assert entity_span.locator.page == 2
    formula = next(span for span in passages if span.quote == "x = y")
    assert formula.metadata["source_kind"] == "formula"
    cell = next(span for span in _docling_cell_evidence(built) if span.quote == "12%")
    assert len(cell.id) <= 128
    assert cell.locator.table_id.startswith("table:")
    assert cell.metadata["source_ref"] == "#/tables/0"
    assert cell.locator.cell == "r0:c1"
    assert cell.locator.page == 3
    assert cell.locator.bbox == [10.0, 20.0, 100.0, 30.0]
    assert cell.locator.start_char is None and cell.locator.end_char is None


@pytest.mark.parametrize("citation", [[], [{"evidence_id": "evidence:invented", "quote": "unknown"}]])
def test_explanation_rejects_missing_or_hallucinated_citations(tmp_path, monkeypatch, citation):
    from semantica.project_snapshot_pipeline import _build_source, _source_passages, _explanation_reports, SnapshotBuildError
    from semantica.project_snapshot_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision=source_content_revision(source), mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    receipt = ModelReceipt(id="receipt:test", operation="knowledge_explanation", provider="test", model="test", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"sections": [{"title": "Explanation", "text": "Unsupported claim", "citations": citation}]}, [receipt]))
    with pytest.raises(SnapshotBuildError):
        _explanation_reports("project-1", [built], built["entities"], [], [], [], [], [*built["evidence"], *built["passages"]], None)


def _parsed_ref(params, source):
    result = parse_source_artifact(ParseSourceRequest.model_validate({
        "source": source, "outputDir": str(Path(params["outputDir"]) / "parsed"),
        "forceOcr": source["sourceId"] in params["recipe"]["forceOcrSourceIds"],
        "documentProcessing": params.get("documentProcessing", {"mode": "local"}),
    }))
    return {key: result[key] for key in ("artifactPath", "artifactDigest", "sourceId")}


def _request(source: Path, output_dir: Path, *, recipe: str = "deterministic", prepare: bool = True) -> dict:
    request = {
        "protocol": "semantica.project-worker.v1",
        "id": "build-1",
        "method": "build_project_snapshot",
        "params": {
            "baseSnapshot": None,
            "inputRevision": H1,
            "outputDir": str(output_dir),
            "projectId": "project-1",
            "recipe": {"forceOcrSourceIds": [], "id": recipe, "version": "1"},
            "relays": {
                "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.snapshot.embed", "modelId": "embedding-1", "receipts": "required"},
                "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.snapshot.generate", "modelId": "model-1", "receipts": "required"},
            },
            "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json", "retrieval-index": "application/vnd.semantica.retrieval+json", "snapshot": "application/vnd.semantica.project-snapshot+json"}},
            "sources": [{"filePath": str(source), "materialRevision": source_content_revision(source), "mimeType": "application/epub+zip" if source.suffix == ".epub" else "text/plain", "name": source.name, "sourceId": "source-1"}],
        },
    }
    request["params"]["parsedSources"] = [_parsed_ref(request["params"], request["params"]["sources"][0])] if prepare else []
    return request


def test_worker_builds_complete_snapshot_from_real_text_file(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine. The Engine influenced Charles Babbage.", encoding="utf-8")
    stdin = io.StringIO(json.dumps(_request(source, tmp_path)) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    events, response = _worker_output(stdout)
    assert events[0]["type"] == "progress"
    assert events[0]["stage"] == "document_parsing"
    assert response["ok"] is True
    assert [item["kind"] for item in response["result"]["artifacts"]] == ["document-representation", "retrieval-index", "snapshot"]
    assert response["result"]["relayReceipts"] == {"embedding": [], "model": []}

    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert snapshot.id == response["result"]["snapshot"]["snapshotId"]
    assert snapshot.entities
    assert snapshot.relations == []
    assert snapshot.assertions == []
    assert snapshot.identity_decisions == []
    assert len(snapshot.communities) == len(snapshot.entities)
    assert len(snapshot.topics) == len(snapshot.communities)
    assert len(snapshot.reports) == len(snapshot.communities)
    assert snapshot.retrieval_manifests[0].community_ids
    assert snapshot.change_delta.added_ids
    assert snapshot.evidence_spans
    assert snapshot.model_receipts == []
    assert all(span.quote == span.locator.quote for span in snapshot.evidence_spans)
    assert all(span.locator.representation_id == span.representation_id for span in snapshot.evidence_spans)
    assert any(span.metadata.get("role") == "source-passage" for span in snapshot.evidence_spans)


def test_build_rejects_base_snapshot_from_another_project(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    initial_request = ProjectSnapshotBuildRequest.model_validate(_request(source, tmp_path / "initial")["params"])
    initial = build_project_snapshot(initial_request)
    request = _request(source, tmp_path / "next")["params"]
    request["projectId"] = "project-2"
    request["baseSnapshot"] = {
        "snapshotId": initial["snapshot"].id,
        "snapshotPath": str(initial["snapshot_path"]),
        "artifactDigest": initial["snapshot_digest"],
        "schemaDigest": H3,
    }
    with pytest.raises(Exception, match="project"):
        build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))


def test_canonical_graph_projection_preserves_snapshot_identity():
    entities = [
        KnowledgeEntity(id="entity:ada", canonical_name="Ada Lovelace", type="PERSON"),
        KnowledgeEntity(id="entity:engine", canonical_name="Analytical Engine", type="CONCEPT"),
    ]
    relations = [
        KnowledgeRelation(
            id="relation:source-1:0",
            source_entity_id="entity:ada",
            target_entity_id="entity:engine",
            type="designed",
            qualifiers={"polarity": "positive"},
            evidence_ids=["evidence:source-1:0:42"],
        )
    ]

    graph_relationships, context_edges = _canonical_graph_projection(entities, relations)

    assert {item["id"] for item in graph_relationships} == {relations[0].id}
    assert {edge.edge_id for edge in context_edges} == {relations[0].id}
    assert {edge.source_id for edge in context_edges} == {entities[0].id}
    assert {edge.target_id for edge in context_edges} == {entities[1].id}


def test_worker_fails_closed_for_unsupported_source_format(tmp_path):
    source = tmp_path / "source.unknown"
    source.write_bytes(b"not-an-epub")
    request = _request(source, tmp_path, prepare=False)
    request["params"]["sources"][0]["mimeType"] = "application/octet-stream"
    request["method"] = "parse_source"
    request["params"] = {"source": request["params"]["sources"][0], "outputDir": str(tmp_path), "forceOcr": False, "documentProcessing": {"mode": "local"}}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "unsupported" in response["error"]["message"].lower()


def test_cross_source_same_name_stays_unresolved(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    second.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    request = _request(first, tmp_path)
    request["params"]["sources"].append({
        "filePath": str(second),
        "materialRevision": source_content_revision(second),
        "mimeType": "text/plain",
        "name": second.name,
        "sourceId": "source-2",
    })
    request["params"]["parsedSources"].append(_parsed_ref(request["params"], request["params"]["sources"][-1]))
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is True
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    ada_candidates = [entity for entity in snapshot.entities if entity.canonical_name == "Ada Lovelace"]
    assert len(ada_candidates) == 2
    assert ada_candidates[0].id != ada_candidates[1].id
    assert snapshot.identity_decisions == []
    assert len(snapshot.conflicts) == 1
    assert snapshot.conflicts[0].conflict_type == "identity"
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["identity_decisions"] == []
    assert retrieval["conflicts"] == [snapshot.conflicts[0].model_dump(mode="json", by_alias=True)]


def test_epub_adapter_preserves_adapter_locator_origin(tmp_path):
    source = tmp_path / "book.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/chapter.xhtml",
            "<html><body><h1>Ada Lovelace</h1><p>Designed the Analytical Engine.</p></body></html>",
        )
    request = _request(source, tmp_path)
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    _, response = _worker_output(stdout)
    assert response["ok"] is True
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert snapshot.evidence_spans
    assert {item.locator.origin for item in snapshot.evidence_spans} == {"adapter"}
    representation_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "document-representation")
    persisted = json.loads(representation_path.read_text())
    assert "Ada Lovelace" in persisted["text"]
    assert all(persisted["text"][span.locator.start_char:span.locator.end_char] == span.quote for span in snapshot.evidence_spans)


def test_model_recipe_uses_bifrost_chat_and_embedding_and_records_receipts(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")

    class RelayHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers["content-length"])
            payload = json.loads(self.rfile.read(length))
            if self.path == "/v1/chat/completions":
                prompt = payload["messages"][0]["content"]
                explanation = "Explain the supplied knowledge" in prompt
                context = _typed_prompt_context(payload) if explanation else None
                if explanation:
                    content = {"sections": [{"title": "Historical role", "text": "Ada Lovelace is connected to the Analytical Engine through the documented design work.", "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]}
                else:
                    content = ({
                        "relations": [{
                            "subject": "Ada Lovelace", "subject_id": "mention:0",
                            "predicate": "designed", "object": "Analytical Engine",
                            "object_id": "mention:1",
                            "evidence": "Ada Lovelace designed the Analytical Engine.",
                            "evidence_occurrence": 0,
                            "qualifiers": {"polarity": "positive"},
                        }],
                    } if "Extract source-grounded relations" in prompt else {
                        "entities": [
                            {"text": "Ada Lovelace", "label": "PERSON", "occurrence": 0},
                            {"text": "Analytical Engine", "label": "CONCEPT", "occurrence": 0},
                        ],
                    })
                response = {
                    "choices": [{"message": {"content": json.dumps(content), "role": "assistant"}}],
                    "model": payload["model"],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8},
                }
                if "Classify this source" in payload["messages"][0]["content"]:
                    context = _typed_prompt_context(payload)
                    response["choices"][0]["message"]["content"] = json.dumps({"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.95, "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]})
            elif self.path == "/v1/embeddings":
                assert payload["model"] == "embedding-1"
                response = {"data": [{"embedding": [0.25, 0.5, 0.75], "index": 0}], "model": "embedding-1", "usage": {"prompt_tokens": 4, "total_tokens": 4}}
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    previous_token = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "relay-test-token"
    try:
        request = _request(source, tmp_path, recipe="model")
        request["params"]["recipe"]["classificationProfile"] = _classification_profile()
        request["params"]["relays"]["model"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        request["params"]["relays"]["embedding"]["baseUrl"] = f"http://127.0.0.1:{server.server_port}/v1/embeddings"
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        _, response = _worker_output(stdout)
    finally:
        if previous_token is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_token
        server.shutdown()
        server.server_close()

    assert response["ok"] is True
    assert len(response["result"]["relayReceipts"]["model"]) == 8
    assert len(response["result"]["relayReceipts"]["embedding"]) == 1
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert len(snapshot.model_receipts) == 9
    extraction_receipts = [receipt for receipt in snapshot.model_receipts if receipt.operation == "structured_extraction"]
    assert {receipt.metadata["extraction_stage"] for receipt in extraction_receipts} == {"entities", "relations"}
    assert snapshot.source_classifications[0].assignments[0].item_id == "history"
    assert snapshot.classification_profile.id == "profile:test"
    assert "classification:source-1" in snapshot.change_delta.added_ids
    assert {report.report_type for report in snapshot.reports} == {"overview", "concept", "topic", "community"}
    assert all(report.sections and report.evidence_ids and len(report.model_receipt_ids) == 1 for report in snapshot.reports)
    assert all(receipt.input_digest.startswith("sha256:") and receipt.output_digest.startswith("sha256:") for receipt in snapshot.model_receipts)
    assert snapshot.relations[0].status == "candidate"
    assert snapshot.relations[0].evidence_ids
    assert snapshot.retrieval_manifests[0].model_receipt_ids == [receipt.id for receipt in snapshot.model_receipts]
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["embeddings"] == [{"source_id": "source-1", "start_char": 0, "end_char": len(source.read_text()), "vector": [0.25, 0.5, 0.75]}]
    assert retrieval["provenance"]["evidence"]
    evidence_lineage = next(iter(retrieval["provenance"]["evidence"].values()))
    assert evidence_lineage["source_documents"] == ["source-1"]
    assert evidence_lineage["metadata"]["origin"] == "native"
    assert evidence_lineage["lineage_chain"][0]["source_quote"] == "Ada Lovelace"
    assert evidence_lineage["lineage_chain"][0]["source_location"] == "char:0-12"
    relation_id = snapshot.relations[0].id
    assert retrieval["provenance"]["relations"][relation_id]["source_documents"] == ["source-1"]


def test_model_recipe_fails_closed_without_relay_token(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    previous_token = os.environ.pop("OPENAI_API_KEY", None)
    try:
        stdin = io.StringIO(json.dumps(_request(source, tmp_path, recipe="model")) + "\n")
        stdout = io.StringIO()
        assert serve(stdin, stdout) == 0
        _, response = _worker_output(stdout)
    finally:
        if previous_token is not None:
            os.environ["OPENAI_API_KEY"] = previous_token
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "authorization" in response["error"]["message"]


def test_incremental_delta_ignores_audit_time_and_tracks_only_dependent_reports(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    second.write_text("Charles Babbage designed machines.", encoding="utf-8")
    request = _request(first, tmp_path / "first-build")["params"]
    request["sources"].append({"filePath": str(second), "materialRevision": source_content_revision(second), "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    request["parsedSources"].append(_parsed_ref(request, request["sources"][-1]))
    initial = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))
    assert all(report.metadata.get("source_ids") for report in initial["snapshot"].reports)
    assert any(report.metadata["source_ids"] == ["source-1"] for report in initial["snapshot"].reports)
    request["baseSnapshot"] = {"snapshotId": initial["snapshot"].id, "snapshotPath": str(initial["snapshot_path"]), "artifactDigest": initial["snapshot_digest"], "schemaDigest": H3}
    request["inputRevision"] = H2
    request["outputDir"] = str(tmp_path / "identical-build")
    identical = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))["snapshot"]
    assert identical.change_delta.updated_ids == []
    assert identical.change_delta.affected_report_ids == []
    assert all(report.evidence_ids for report in identical.reports)

    first.write_text("Grace Hopper studied mathematics.", encoding="utf-8")
    request["sources"][0]["materialRevision"] = source_content_revision(first)
    request["outputDir"] = str(tmp_path / "changed-build")
    request["parsedSources"][0] = _parsed_ref(request, request["sources"][0])
    updated = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))["snapshot"]
    unchanged_reports = {report.id for report in initial["snapshot"].reports if "Charles Babbage" in report.title}
    assert unchanged_reports
    changed_representations = {item.id for snapshot in [initial["snapshot"], updated] for item in snapshot.document_representations if item.source_id == "source-1"}
    assert set(updated.change_delta.changed_representation_ids) == changed_representations
    assert len(changed_representations) == 2
    assert not unchanged_reports.intersection(updated.change_delta.affected_report_ids)
    removed_reports = {report.id for report in initial["snapshot"].reports if "Ada Lovelace" in report.title}
    assert removed_reports.issubset(set(updated.change_delta.affected_report_ids))


def test_community_and_topic_deltas_affect_only_their_reports(tmp_path):
    from semantica.project_snapshot_pipeline import _change_delta

    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    base = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(_request(source, tmp_path / "build")["params"]))["snapshot"]
    revised = base.model_copy(deep=True)
    revised.communities[0].title += " revised"
    revised.topics[0].title += " revised"
    delta = _change_delta(base, "next-snapshot", revised.document_representations, revised.entities,
        revised.assertions, revised.relations, revised.communities, revised.topics, revised.reports,
        [item.id for item in revised.retrieval_manifests], revised.evidence_spans, revised.source_classifications)
    assert {revised.communities[0].id, revised.topics[0].id}.issubset(delta.updated_ids)
    affected = {report.id for report in revised.reports if report.community_id == revised.communities[0].id
        or report.topic_id == revised.topics[0].id
        or set(report.metadata.get("depends_on", [])).intersection([revised.communities[0].id, revised.topics[0].id])}
    assert affected
    assert set(delta.affected_report_ids) == affected


def test_model_identity_remaps_graph_and_keeps_all_source_provenance(tmp_path, monkeypatch):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    text = "Ada Lovelace designed the Analytical Engine."
    first.write_text(text, encoding="utf-8")
    second.write_text(text + " Ada Lovelace was a mathematician.", encoding="utf-8")
    operations = []

    def relay_response(relay, payload, operation):
        operations.append(operation)
        if operation == "embedding":
            result = {"data": [
                {"index": index, "embedding": [0.25, 0.5, 0.75]}
                for index, _ in enumerate(payload["input"])
            ], "model": relay.model_id}
        else:
            if operation == "structured_extraction":
                prompt = payload["messages"][0]["content"]
                content = ({"relations": [{
                    "subject": "Ada Lovelace", "subject_id": "mention:0",
                    "predicate": "designed", "object": "Analytical Engine",
                    "object_id": "mention:1", "evidence": text,
                    "evidence_occurrence": 0,
                    "qualifiers": {"polarity": "positive"},
                }]} if "Extract source-grounded relations" in prompt else {
                    "entities": [
                        {"text": "Ada Lovelace", "label": "PERSON", "occurrence": 0},
                        {"text": "Analytical Engine", "label": "CONCEPT", "occurrence": 0},
                    ],
                })
            elif operation == "identity_resolution":
                candidates = _typed_prompt_context(payload)["candidates"]
                groups = [[item for item in candidates if item["name"] == name] for name in {item["name"] for item in candidates}]
                content = {"splits": [], "merges": [{"mention_ids": [item["mention_id"] for item in group],
                    "evidence_ids": [span["id"] for item in group for span in item["evidence"]],
                    "reason": "The same named mathematician and designed machine are corroborated by both source contexts."} for group in groups]}
            elif operation == "relationship_discovery":
                content = {"relations": []}
            elif operation == "knowledge_explanation":
                context = _typed_prompt_context(payload)
                content = {"sections": [{"title": "Design", "text": "Ada Lovelace designed the Analytical Engine.", "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]}
            else:
                content = {}
            result = {"choices": [{"message": {"content": json.dumps(content)}}], "model": relay.model_id}
        receipt = ModelReceipt(id="receipt:" + stable_digest([operation, payload]).split(":")[1], operation=operation,
            provider="fixture", model=relay.model_id, input_digest=stable_digest(payload), output_digest=stable_digest(result))
        return result, receipt

    monkeypatch.setattr("semantica.project_snapshot_pipeline._relay_json", relay_response)
    request = _request(first, tmp_path / "build", recipe="model")
    request["params"]["sources"].append({"filePath": str(second), "materialRevision": source_content_revision(second), "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    request["params"]["parsedSources"].append(_parsed_ref(request["params"], request["params"]["sources"][-1]))
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    events, response = _worker_output(stdout)
    embedding_progress = [event for event in events if event.get("stage") == "embedding"]
    assert embedding_progress[-1]["metadata"] == {
        "completedChunks": 2,
        "restoredChunks": 0,
        "totalChunks": 2,
    }
    assert response["ok"] is True, response
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert len(snapshot.entity_mentions) == 4
    assert len(snapshot.entities) == 2
    assert snapshot.conflicts == []
    assert len(snapshot.identity_decisions) == 2
    identity_receipt = next(receipt for receipt in snapshot.model_receipts if receipt.operation == "identity_resolution")
    assert identity_receipt.id in response["result"]["relayReceipts"]["model"]
    assert all(decision.metadata["model_receipt_id"] == identity_receipt.id for decision in snapshot.identity_decisions)
    initial_explanations = operations.count("knowledge_explanation")
    request["params"]["baseSnapshot"] = {"snapshotId": snapshot.id, "snapshotPath": str(snapshot_path), "artifactDigest": next(item["digest"] for item in response["result"]["artifacts"] if item["kind"] == "snapshot"), "schemaDigest": H3}
    request["params"]["outputDir"] = str(tmp_path / "repeat")
    repeated = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request["params"]))["snapshot"]
    assert operations.count("knowledge_explanation") == initial_explanations
    assert repeated.change_delta.affected_report_ids == []
    assert [report.model_dump() for report in repeated.reports] == [report.model_dump() for report in snapshot.reports]
    canonical_ids = {entity.id for entity in snapshot.entities}
    assert {relation.source_entity_id for relation in snapshot.relations}.issubset(canonical_ids)
    assert {relation.target_entity_id for relation in snapshot.relations}.issubset(canonical_ids)
    assert {assertion.subject_id for assertion in snapshot.assertions}.issubset(canonical_ids)
    retrieval_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "retrieval-index")
    retrieval = json.loads(retrieval_path.read_text())
    assert retrieval["identity_decisions"] == [
        decision.model_dump(mode="json", by_alias=True) for decision in snapshot.identity_decisions
    ]
    assert retrieval["conflicts"] == []
    for entity in snapshot.entities:
        assert set(retrieval["provenance"]["entities"][entity.id]["source_documents"]) == {"source-1", "source-2"}
