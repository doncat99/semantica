"""Exercise installed model paths against a loopback-only deterministic relay."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def invoke(module, request):
    process = subprocess.run([sys.executable, "-I", "-B", "-m", module],
        input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=180, check=True)
    response = json.loads(process.stdout.splitlines()[-1])
    assert response["ok"], response
    return response["result"]


def verify_model_paths(root, destination):
    from semantica.semantic_artifact_builder import explain_evidence
    from semantica.semantic_artifact_schema import SemanticArtifact, RelayRef
    from semantica.source import source_content_revision

    manifest = json.loads((root / "manifest.json").read_text())
    calls = []

    class Relay(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.headers.get("Authorization") == "Bearer native-acceptance-only"
            payload = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if self.path == "/v1/embeddings":
                calls.append("embedding")
                response = {"model": payload["model"], "data": [
                    {"embedding": [0.25, 0.5, 0.75], "index": index}
                    for index, _ in enumerate(payload["input"])], "usage": {"total_tokens": 4}}
            elif self.path == "/v1/chat/completions":
                assert payload["response_format"] == {"type": "json_object"}
                prompt = payload["messages"][0]["content"]
                schema = json.loads(prompt.split("\nReturn one JSON object matching this JSON Schema:\n", 1)[1])
                assert schema["type"] == "object" and schema["properties"]
                if "Explain the supplied knowledge" in prompt:
                    calls.append("explanation")
                    refs = re.findall(r"^(?:- )?\[([^\]\n]+)\]: ", prompt, re.MULTILINE)
                    assert refs
                    content = {"title": "Historical role", "summary": "Supported explanation", "findings": [
                        {"summary": "Historical role", "explanation": "Ada designed the Analytical Engine.",
                         "citations": [{"evidence_id": refs[0]}]}]}
                elif "Classify this source" in prompt:
                    calls.append("classification")
                    context = json.JSONDecoder().raw_decode(prompt.split("Input JSON:\n", 1)[1])[0]
                    content = {"assignments": [{"dimension_id": "purpose", "item_id": "history",
                        "confidence": 0.95, "citations": [{"evidence_id": context["evidence"][0]["id"],
                        "quote": context["evidence"][0]["quote"]}]}]}
                elif "Extract source-grounded relations" in prompt:
                    calls.append("relations")
                    content = {"relations": [{"subject_id": "mention:0", "predicate": "designed",
                        "object_id": "mention:1", "confidence": 0.9,
                        "evidence": "Ada Lovelace designed the Analytical Engine.", "evidence_occurrence": 0,
                        "qualifiers": {"polarity": "positive"}, "supporting_refs": []}]}
                else:
                    calls.append("entities")
                    content = {"entities": [
                        {"text": "Ada Lovelace", "label": "PERSON", "occurrence": 0, "attributes": {}, "confidence": 0.9},
                        {"text": "Analytical Engine", "label": "CONCEPT", "occurrence": 0, "attributes": {}, "confidence": 0.9}]}
                response = {"model": payload["model"], "choices": [{"finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(content)}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8}}
            else:
                raise AssertionError(self.path)
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    token_name = "SEMANTICA_NATIVE_ACCEPTANCE_TOKEN"
    previous = os.environ.get(token_name)
    os.environ[token_name] = "native-acceptance-only"
    try:
        with tempfile.TemporaryDirectory(prefix="semantica-model-acceptance-") as directory:
            scratch = Path(directory)
            source = scratch / "source.txt"
            source.write_text("Ada Lovelace designed the Analytical Engine.", encoding="utf-8")
            source_ref = {"sourceId": "native-source", "filePath": str(source), "name": source.name,
                "mimeType": "text/plain", "materialRevision": source_content_revision(source)}
            parsed = invoke("semantica.semantic_worker", {"protocol": "semantica.semantic-worker.v1",
                "id": "model-parse", "method": "parse_source", "params": {"source": source_ref,
                "outputDir": str(scratch / "parsed"), "forceOcr": False, "documentProcessing": {"mode": "local"}}})
            relays = {key: {"authorizationEnv": token_name,
                "baseUrl": f"http://127.0.0.1:{server.server_port}/v1/{endpoint}",
                "modelId": model, "bindingId": "native-acceptance", "capability": capability, "receipts": "required",
                **({"contextWindowTokens": 500000, "maxOutputTokens": 393216} if key == "model" else {})}
                for key, endpoint, model, capability in [
                    ("model", "chat/completions", "model-1", "knowledge.snapshot.generate"),
                    ("embedding", "embeddings", "embedding-1", "knowledge.snapshot.embed")]}
            built = invoke("semantica.semantic_worker", {"protocol": "semantica.semantic-worker.v1",
                "id": "model-build", "method": "build_semantic_artifacts", "params": {
                "projectId": "native", "baseSnapshot": None, "inputRevision": "sha256:" + "1" * 64,
                "outputDir": str(scratch / "output"), "parallelism": 1,
                "recipe": {"id": "model", "version": "1", "forceOcrSourceIds": [], "classificationProfile": {
                    "id": "profile:acceptance", "version": "1", "label": "Purpose", "description": "Source purpose",
                    "dimensions": [{"id": "purpose", "label": "Purpose", "cardinality": "single",
                                    "vocabulary": [{"id": "history", "label": "History"}]}]}},
                "sources": [source_ref], "parsedSources": [{key: parsed[key] for key in ("sourceId", "artifactPath", "artifactDigest")}],
                "documentProcessing": {"mode": "local"}, "relays": relays,
                "release": {key: manifest[key] for key in ("artifactDigest", "schemaDigest", "mediaTypes")}}})
            artifacts = {item["kind"]: {key: item[key] for key in ("path", "digest", "kind", "mediaType")}
                         for item in built["artifacts"]}
            graph = json.loads(Path(artifacts["semantic-graph"]["path"]).read_text())
            admitted = SemanticArtifact.model_validate(graph)
            assert admitted.project_id == "native"
            assert admitted.id == built["semanticGraph"]["artifactRevision"]
            assert len(admitted.entities) == 2 and len(admitted.relations) == 1
            assert admitted.source_classifications[0].assignments[0].item_id == "history"
            sections, receipts = explain_evidence(admitted,
                {"id": "native-source", "type": "source-scope", "title": "Historical role"},
                [span.id for span in admitted.evidence_spans], RelayRef.model_validate(relays["model"]))
            assert sections and all(section.evidence_ids for section in sections) and receipts
            snapshot_ref = artifacts["semantic-graph"]
            for mode in ("keyword", "semantic"):
                queried = invoke("semantica.semantic_query_worker", {"protocol": "semantica.semantic-query.v1",
                    "id": "model-query", "method": "query", "params": {"projectId": "native",
                    "snapshotId": admitted.id, "snapshot": snapshot_ref,
                    "retrieval": artifacts["retrieval-index"], "query": "Ada", "mode": mode, "limit": 5,
                    **({"embedding": {"bindingId": "native-acceptance", "modelId": "embedding-1",
                         "vector": [0.25, 0.5, 0.75]}} if mode == "semantic" else {})}})
                assert queried["contexts"] and all(context["evidenceIds"] for context in queried["contexts"])
            assert set(calls) == {"entities", "relations", "embedding", "classification", "explanation"}, calls
            result = {"loopbackOnly": True, "freshBuildWorker": True, "freshQueryWorker": True,
                "operations": calls, "queryModes": ["keyword", "semantic"],
                "modelReceipts": len(admitted.model_receipts), "explanationReceipts": len(receipts)}
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return result
    finally:
        if previous is None:
            os.environ.pop(token_name, None)
        else:
            os.environ[token_name] = previous
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    verify_model_paths(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
