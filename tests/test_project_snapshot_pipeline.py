import io
import json
from zipfile import ZipFile
import os
import threading
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from semantica.project_snapshot_pipeline import _canonical_graph_projection
from semantica.project_snapshot_pipeline import build_project_snapshot
from semantica.project_snapshot_schema import ProjectSnapshotBuildRequest
from semantica.project_snapshot_schema import KnowledgeEntity, KnowledgeRelation, ModelReceipt, ProjectSnapshot, stable_digest
from semantica.project_snapshot_worker import serve

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64


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
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision="material-1", mimeType="text/plain", name="source.txt"), False)
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
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"assignments": assignments}, receipt))
    with pytest.raises(SnapshotBuildError):
        _classify_source(built, ClassificationProfile.model_validate(_classification_profile()), None)


def test_semantic_classification_preserves_source_offsets_and_unclassified_dimensions(tmp_path, monkeypatch):
    from semantica.project_snapshot_pipeline import _build_source, _source_passages, _classify_source
    from semantica.project_snapshot_schema import ClassificationProfile, SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision="material-1", mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    span = built["passages"][0]
    receipt = ModelReceipt(id="receipt:test", operation="source_classification", provider="test", model="test", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"assignments": [{"dimension_id": "purpose", "item_id": "history", "confidence": 0.9, "citations": [{"evidence_id": span.id, "quote": span.quote}]}]}, receipt))
    classification, _ = _classify_source(built, ClassificationProfile.model_validate(_classification_profile()), None)
    assert classification.assignments[0].evidence_ids == [span.id]
    assert classification.unclassified_dimension_ids == ["topic"]
    assert built["text"][span.locator.start_char:span.locator.end_char] == span.quote


@pytest.mark.parametrize("citation", [[], [{"evidence_id": "evidence:invented", "quote": "unknown"}]])
def test_explanation_rejects_missing_or_hallucinated_citations(tmp_path, monkeypatch, citation):
    from semantica.project_snapshot_pipeline import _build_source, _source_passages, _explanation_reports, SnapshotBuildError
    from semantica.project_snapshot_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    built = _build_source(SourceBuildInput(filePath=str(source), sourceId="source-1", materialRevision="material-1", mimeType="text/plain", name="source.txt"), False)
    built["passages"] = _source_passages(built)
    receipt = ModelReceipt(id="receipt:test", operation="knowledge_explanation", provider="test", model="test", input_digest=H1, output_digest=H2)
    monkeypatch.setattr("semantica.project_snapshot_pipeline._product_json", lambda *args: ({"sections": [{"title": "Explanation", "text": "Unsupported claim", "citations": citation}]}, receipt))
    with pytest.raises(SnapshotBuildError):
        _explanation_reports("project-1", [built], built["entities"], [], [], [], [], [*built["evidence"], *built["passages"]], None)


def _request(source: Path, output_dir: Path, *, recipe: str = "deterministic") -> dict:
    return {
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
            "sources": [{"filePath": str(source), "materialRevision": "material-1", "mimeType": "text/plain", "name": source.name, "sourceId": "source-1"}],
        },
    }


def test_worker_builds_complete_snapshot_from_real_text_file(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine. The Engine influenced Charles Babbage.", encoding="utf-8")
    stdin = io.StringIO(json.dumps(_request(source, tmp_path)) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
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
            evidence_ids=["evidence:source-1:0:42"],
        )
    ]

    graph_relationships, context_edges = _canonical_graph_projection(entities, relations)

    assert {item["id"] for item in graph_relationships} == {relations[0].id}
    assert {edge.edge_id for edge in context_edges} == {relations[0].id}
    assert {edge.source_id for edge in context_edges} == {entities[0].id}
    assert {edge.target_id for edge in context_edges} == {entities[1].id}


def test_worker_fails_closed_for_unsupported_source_format(tmp_path):
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"not-an-epub")
    request = _request(source, tmp_path)
    request["params"]["sources"][0]["mimeType"] = "application/msword"
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] == "SnapshotBuildError"
    assert "dedicated adapter" in response["error"]["message"] or "does not match" in response["error"]["message"]


def test_cross_source_same_name_stays_unresolved(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
    second.write_text("Ada Lovelace studied mathematics.", encoding="utf-8")
    request = _request(first, tmp_path)
    request["params"]["sources"].append({
        "filePath": str(second),
        "materialRevision": "material-2",
        "mimeType": "text/plain",
        "name": second.name,
        "sourceId": "source-2",
    })
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    ada_candidates = [entity for entity in snapshot.entities if entity.canonical_name == "Ada Lovelace"]
    assert len(ada_candidates) == 2
    assert ada_candidates[0].id != ada_candidates[1].id
    assert snapshot.identity_decisions == []
    assert len(snapshot.conflicts) == 1
    assert snapshot.conflicts[0].conflict_type == "identity"


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
    request["params"]["sources"][0]["mimeType"] = "application/epub+zip"
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
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
                explanation = "Explain the supplied knowledge" in payload["messages"][0]["content"]
                context = json.loads(payload["messages"][1]["content"]) if explanation else None
                response = {
                    "choices": [{"message": {"content": json.dumps({"sections": [{"title": "Historical role", "text": "Ada Lovelace is connected to the Analytical Engine through the documented design work.", "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]} if explanation else {
                        "entities": [
                            {"name": "Ada Lovelace", "type": "PERSON"},
                            {"name": "Analytical Engine", "type": "CONCEPT"},
                        ],
                        "relations": [{"subject": "Ada Lovelace", "predicate": "designed", "object": "Analytical Engine", "evidence": "Ada Lovelace designed the Analytical Engine."}],
                    }), "role": "assistant"}}],
                    "model": payload["model"],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8},
                }
                if "Classify this source" in payload["messages"][0]["content"]:
                    context = json.loads(payload["messages"][1]["content"])
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
        response = json.loads(stdout.getvalue())
    finally:
        if previous_token is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_token
        server.shutdown()
        server.server_close()

    assert response["ok"] is True
    assert len(response["result"]["relayReceipts"]["model"]) == 7
    assert len(response["result"]["relayReceipts"]["embedding"]) == 1
    snapshot_path = next(Path(item["path"]) for item in response["result"]["artifacts"] if item["kind"] == "snapshot")
    snapshot = ProjectSnapshot.model_validate_json(snapshot_path.read_bytes())
    assert len(snapshot.model_receipts) == 8
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
        response = json.loads(stdout.getvalue())
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
    request["sources"].append({"filePath": str(second), "materialRevision": "material-2", "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    initial = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))
    request["baseSnapshot"] = {"snapshotId": initial["snapshot"].id, "snapshotPath": str(initial["snapshot_path"]), "artifactDigest": initial["snapshot_digest"], "schemaDigest": H3}
    request["inputRevision"] = H2
    request["outputDir"] = str(tmp_path / "identical-build")
    identical = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))["snapshot"]
    assert identical.change_delta.updated_ids == []
    assert identical.change_delta.affected_report_ids == []
    assert all(report.evidence_ids for report in identical.reports)

    first.write_text("Grace Hopper studied mathematics.", encoding="utf-8")
    request["outputDir"] = str(tmp_path / "changed-build")
    updated = build_project_snapshot(ProjectSnapshotBuildRequest.model_validate(request))["snapshot"]
    unchanged_reports = {report.id for report in initial["snapshot"].reports if "Charles Babbage" in report.title}
    assert unchanged_reports
    assert updated.change_delta.changed_representation_ids == ["representation:source-1"]
    assert not unchanged_reports.intersection(updated.change_delta.affected_report_ids)
    removed_reports = {report.id for report in initial["snapshot"].reports if "Ada Lovelace" in report.title}
    assert removed_reports.issubset(set(updated.change_delta.affected_report_ids))


def test_model_identity_remaps_graph_and_keeps_all_source_provenance(tmp_path, monkeypatch):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    text = "Ada Lovelace designed the Analytical Engine."
    first.write_text(text, encoding="utf-8")
    second.write_text(text + " Ada Lovelace was a mathematician.", encoding="utf-8")
    operations = []

    def relay_response(relay, payload, operation):
        operations.append(operation)
        if operation == "embedding":
            result = {"data": [{"embedding": [0.25, 0.5, 0.75]}], "model": relay.model_id}
        else:
            if operation == "identity_resolution":
                candidates = json.loads(payload["messages"][1]["content"])
                groups = [[item for item in candidates if item["name"] == name] for name in {item["name"] for item in candidates}]
                content = {"merges": [{"mention_ids": [item["mention_id"] for item in group],
                    "evidence_ids": [span["id"] for item in group for span in item["evidence"]],
                    "reason": "The same named mathematician and designed machine are corroborated by both source contexts."} for group in groups]}
            elif operation == "knowledge_explanation":
                context = json.loads(payload["messages"][1]["content"])
                content = {"sections": [{"title": "Design", "text": "Ada Lovelace designed the Analytical Engine.", "citations": [{"evidence_id": context["evidence"][0]["id"], "quote": context["evidence"][0]["quote"]}]}]}
            else:
                content = {"entities": [{"name": "Ada Lovelace", "type": "PERSON"}, {"name": "Analytical Engine", "type": "CONCEPT"}],
                    "relations": [{"subject": "Ada Lovelace", "predicate": "designed", "object": "Analytical Engine", "evidence": text}]}
            result = {"choices": [{"message": {"content": json.dumps(content)}}], "model": relay.model_id}
        receipt = ModelReceipt(id="receipt:" + stable_digest([operation, payload]).split(":")[1], operation=operation,
            provider="fixture", model=relay.model_id, input_digest=stable_digest(payload), output_digest=stable_digest(result))
        return result, receipt

    monkeypatch.setattr("semantica.project_snapshot_pipeline._relay_json", relay_response)
    request = _request(first, tmp_path / "build", recipe="model")
    request["params"]["sources"].append({"filePath": str(second), "materialRevision": "material-2", "mimeType": "text/plain", "name": second.name, "sourceId": "source-2"})
    stdout = io.StringIO()
    assert serve(io.StringIO(json.dumps(request) + "\n"), stdout) == 0
    response = json.loads(stdout.getvalue())
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
    for entity in snapshot.entities:
        assert set(retrieval["provenance"]["entities"][entity.id]["source_documents"]) == {"source-1", "source-2"}
