"""Exercise installed model paths against a loopback-only deterministic relay."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from hashlib import file_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def invoke(module, request):
    process = subprocess.run([sys.executable, "-I", "-B", "-m", module],
        input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=180)
    assert process.returncode == 0, (process.returncode, process.stdout[-8000:], process.stderr[-8000:])
    response = json.loads(process.stdout.splitlines()[-1])
    assert response["ok"], response
    return response["result"]


class QuerySession:
    """One acquired native owner per fresh query worker process."""
    def __enter__(self):
        # Executor futures otherwise retain uncaught exceptions until the next input.
        bootstrap = """import faulthandler, traceback
from semantica import semantic_query_worker as worker
faulthandler.enable()
faulthandler.dump_traceback_later(60, repeat=True)
original = worker._serve_line
def diagnosed(*args):
    try:
        return original(*args)
    except BaseException:
        traceback.print_exc()
        raise
worker._serve_line = diagnosed
worker.main()
"""
        # A PIPE that is read only at exit can block the worker before stdout.
        self.diagnostics = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        try:
            self.process = subprocess.Popen([sys.executable, "-I", "-B", "-c", bootstrap],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.diagnostics,
                text=True, encoding="utf-8")
        except BaseException:
            self.diagnostics.close()
            raise
        return self

    def diagnostic_tail(self):
        self.diagnostics.flush()
        self.diagnostics.seek(0)
        return self.diagnostics.read()[-12000:]

    def call(self, method, params):
        context = {"method": method, "mode": params.get("mode"), "target": params.get("target")}
        print("Native query acceptance: " + json.dumps(context), file=sys.stderr, flush=True)
        self.process.stdin.write(json.dumps({"id": "acceptance-" + method,
            "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = threading.Timer(180, self.process.kill)
        deadline.start()
        try:
            line = self.process.stdout.readline()
            assert line, (f"native query worker exited or exceeded its 180-second deadline: "
                f"{json.dumps(context)}; returncode={self.process.poll()}; {self.diagnostic_tail()}")
            response = json.loads(line)
        finally:
            deadline.cancel()
        assert response["ok"], response
        return response["result"]

    def __exit__(self, exc_type, _exc, _traceback):
        try:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
            try:
                self.process.wait(timeout=30)
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(timeout=10)
            if exc_type is None:
                assert self.process.returncode == 0, self.diagnostic_tail()
        finally:
            self.process.stdout.close()
            self.diagnostics.close()


def reader_request(parsed, source):
    def reference(path, kind):
        with path.open("rb") as stream:
            digest = "sha256:" + file_digest(stream, "sha256").hexdigest()
        stat = path.stat()
        return {"path": str(path), "kind": kind, "digest": digest, "mediaType": "application/json",
            "installation": {"digest": digest, "identity": ":".join(map(str,
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)))}}
    path = Path(parsed["artifactPath"])
    return {"id": "acceptance-reader", "sourceId": source["sourceId"],
        "materialRevision": source["materialRevision"], "representationRevision": parsed["representationRevision"],
        "artifact": reference(path, "document-representation"),
        "readerIndex": reference(path.with_suffix(".reader.sqlite"), "document-reader-index"),
        "selection": {"field": "chunks", "limit": 128, "maxBytes": 262144}}


def verify_model_paths(root, destination):
    from semantica.semantic_artifact_schema import stable_digest
    from semantica.source import source_content_revision

    manifest = json.loads((root / "manifest.json").read_text())
    calls = []
    products = {}

    class Relay(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.headers.get("Authorization") == "Bearer native-acceptance-only"
            payload = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if self.path.startswith("/v1/products/semantic-organization/"):
                operation = stable_digest([payload[key] for key in
                    ("projectId", "inputRevision", "recipeDigest", "modelId", "targetId", "inputDigest")])
                if self.path.endswith("/adopt"):
                    products[operation] = {"report": payload["report"], "receipts": payload["receipts"],
                        "operationId": operation, "digest": stable_digest(payload)}
                else:
                    assert self.path.endswith("/read"), self.path
                response = products.get(operation, {"report": None})
            elif self.path == "/v1/embeddings":
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
            second_source = scratch / "second.txt"
            second_source.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            second_ref = {**source_ref, "sourceId": "native-second", "filePath": str(second_source), "name": second_source.name}
            second_parsed = invoke("semantica.semantic_worker", {"id": "model-second-parse", "method": "parse_source",
                "params": {"source": second_ref, "outputDir": str(scratch / "parsed"),
                    "forceOcr": False, "documentProcessing": {"mode": "local"}}})
            relays = {key: {"authorizationEnv": token_name,
                "baseUrl": f"http://127.0.0.1:{server.server_port}/v1/{endpoint}",
                "modelId": model, "bindingId": "native-acceptance", "capability": capability, "receipts": "required",
                **({"contextWindowTokens": 500000, "maxOutputTokens": 393216} if key == "model" else {})}
                for key, endpoint, model, capability in [
                    ("model", "chat/completions", "model-1", "knowledge.publication.generate"),
                    ("embedding", "embeddings", "embedding-1", "knowledge.publication.embed")]}
            built = invoke("semantica.semantic_worker", {"protocol": "semantica.semantic-worker.v1",
                "id": "model-build", "method": "build_semantic_artifacts", "params": {
                "projectId": "native", "inputRevision": "sha256:" + "1" * 64,
                "nativeCacheDir": str(scratch / "native-cache"), "nativeStoreDir": str(scratch / "native-store"),
                "organizationReports": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1/products/semantic-organization",
                    "authorizationEnv": token_name, "recipeDigest": "sha256:" + "1" * 64},
                "outputDir": str(scratch / "output"), "parallelism": 1,
                "recipe": {"id": "model", "version": "1", "forceOcrSourceIds": [], "classificationProfile": {
                    "id": "profile:acceptance", "version": "1", "label": "Purpose", "description": "Source purpose",
                    "dimensions": [{"id": "purpose", "label": "Purpose", "cardinality": "single",
                                    "vocabulary": [{"id": "history", "label": "History"}]}]}},
                "sources": [source_ref, second_ref], "parsedSources": [{key: item[key] for key in
                    ("sourceId", "artifactPath", "artifactDigest", "representationRevision", "readerIndexPath", "readerIndexDigest")} for item in (parsed, second_parsed)],
                "documentProcessing": {"mode": "local"}, "relays": relays,
                "release": {key: manifest[key] for key in ("artifactDigest", "schemaDigest", "mediaTypes")}}})
            assert built["publication"]["state"] == "ready", built
            assert built["semanticStore"]["project"] == "native"
            assert built["semanticStore"]["generation"] == built["publication"]["generation"]
            assert "artifacts" not in built and "semanticGraph" not in built
            assert not (scratch / "output/semantic-graph.json").exists()
            assert not (scratch / "output/snapshot.json").exists()
            reader = reader_request(parsed, source_ref)
            readers = {"native-source": reader, "native-second": reader_request(second_parsed, second_ref)}
            base = {"projectId": "native", "semanticStore": built["semanticStore"],
                "generation": built["publication"]["generation"], "nativeIndexes": built["nativeIndexes"],
                "sourceIds": ["native-source"]}
            descriptor = built["nativeIndexes"]["semantic"]["space"]
            embedding = {"bindingId": descriptor["bindingId"], "modelId": descriptor["modelId"],
                "vector": [0.25, 0.5, 0.75]}
            with QuerySession() as session:
                session.call("acquire_store", {"semanticStore": built["semanticStore"]})
                scene_params = {"projectId": "native", "semanticStore": built["semanticStore"]}
                themes = session.call("scene", {**scene_params,
                    "selection": {"kind": "topics", "limit": 128, "maxBytes": 262144}})
                assert themes["generation"] == built["publication"]["generation"]
                assert themes["nodes"] and themes["next_cursor"] is None, themes
                theme = themes["nodes"][0]
                assert theme["organization"]["basis"] == "grounded-overview-section"
                assert theme["evidenceCount"] > 0 and theme["memberCount"] > 0, theme
                members = session.call("scene", {**scene_params, "selection": {
                    "kind": "nodes", "topicId": theme["id"], "limit": 128, "maxBytes": 262144}})
                assert members["nodes"] and members["next_cursor"] is None, members
                assert len(members["nodes"]) == theme["memberCount"]
                header = session.call("classification", {"projectId": "native",
                    "semanticStore": built["semanticStore"], "selection": {"sourceId": "native-source"}})
                assert header["dimensionIds"] == ["purpose"], header
                classification = session.call("classification", {"projectId": "native",
                    "semanticStore": built["semanticStore"],
                    "selection": {"sourceId": "native-source", "dimensionId": "purpose", "limit": 128}})
                assert "history" in json.dumps(classification), classification
                evidence_ids = []
                for mode in ("keyword", "semantic"):
                    params = {**base, "query": "Ada", "mode": mode, "target": "knowledge", "limit": 5,
                        "sourceArtifacts": {"native-source": reader},
                        **({"embedding": embedding} if mode == "semantic" else {})}
                    queried = session.call("query", params)
                    assert queried["contexts"] and all(hit["evidenceIds"] for hit in queried["contexts"])
                    evidence_ids = sorted({identity for hit in queried["contexts"] for identity in hit["evidenceIds"]})
                assert evidence_ids
                # Exact IDs and explicit source grants go through the canonical record owner.
                identity = queried["contexts"][0]["id"]
                canonical = session.call("records", {"projectId": "native", "semanticStore": built["semanticStore"],
                    "selection": {"ids": [identity], "sourceIds": ["native-source"]}})
                assert canonical["generation"] == built["publication"]["generation"]
                assert [row["id"] for row in canonical["records"]] == [identity]
                for mode in ("keyword", "semantic"):
                    params = {**base, "query": "Ada", "mode": mode, "target": "documents", "limit": 1,
                        **({"embedding": embedding} if mode == "semantic" else {})}
                    if mode == "keyword":
                        params.pop("sourceIds")
                    visited = []
                    for _ in range(2 if mode == "keyword" else 1):
                        selected = session.call("query", params)
                        assert selected["contexts"] == [] and len(selected["requiredSourceIds"]) == 1
                        refs = {key: readers[key] for key in selected["requiredSourceIds"]}
                        document_page = session.call("query", {**params, "sourceArtifacts": refs})
                        assert len(document_page["contexts"]) == 1
                        hit = document_page["contexts"][0]
                        assert hit["kind"] == "source_text" and len(hit["sourceIds"]) == 1
                        assert hit["locator"]["quote"] == hit["text"]
                        assert hit["text"] == ("Ada" if mode == "keyword" else source.read_text(encoding="utf-8"))
                        assert not hit["evidenceIds"]
                        visited.extend(hit["sourceIds"])
                        if document_page.get("nextPosition") is not None:
                            params.update(position=document_page["nextPosition"], offset=document_page["nextOffset"])
                    assert document_page.get("nextPosition") is None
                    if mode == "keyword":
                        assert set(visited) == set(readers) and document_page["total"] == 2
                session.call("release_store", {"semanticStore": {key: built["semanticStore"][key]
                    for key in ("path", "project")}})
            # A second fresh process must acquire the same ready publication explicitly.
            with QuerySession() as reopened:
                reopened.call("acquire_store", {"semanticStore": built["semanticStore"]})
                reopened_themes = reopened.call("scene", {**scene_params,
                    "selection": {"kind": "topics", "limit": 128, "maxBytes": 262144}})
                assert reopened_themes == themes
                reopened.call("records", {"projectId": "native", "semanticStore": built["semanticStore"],
                    "selection": {"ids": [identity], "sourceIds": ["native-source"]}})
                reopened.call("release_store", {"semanticStore": {key: built["semanticStore"][key]
                    for key in ("path", "project")}})
            explanation_source = {key: value for key, value in reader.items() if key not in ("id", "selection")}
            explained = invoke("semantica.semantic_worker", {"id": "model-explanation", "method": "explain_evidence",
                "params": {"projectId": "native", "semanticStore": built["semanticStore"],
                    "target": {"id": "native-source", "type": "source-scope", "title": "Historical role"},
                    "sources": [explanation_source], "evidenceIds": evidence_ids[:32],
                    "outputDir": str(scratch), "relay": relays["model"]}})
            explanation = json.loads(Path(explained["path"]).read_text())
            assert explained["sectionCount"] > 0 and explained["receiptCount"] > 0
            assert explanation["evidenceIds"] and set(explanation["evidenceIds"]) <= set(evidence_ids)
            assert set(calls) == {"entities", "relations", "embedding", "classification", "explanation"}, calls
            assert built["relayReceiptManifest"] and built["relayReceipts"]["embedding"] and built["relayReceipts"]["model"]
            result = {"loopbackOnly": True, "freshBuildWorker": True, "freshQueryWorker": True,
                "operations": calls, "queryModes": ["keyword", "semantic"], "semanticOriginalRanges": True,
                "nativeAcquisitionReopen": True, "boundedCanonicalRecords": True,
                "nativeGroundedTopics": True, "nativeTopicMembers": True,
                "modelReceipts": len(built["relayReceiptManifest"]), "explanationReceipts": explained["receiptCount"]}
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
