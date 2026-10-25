"""Cold-process checks: a warmed pytest interpreter cannot prove import isolation."""
import subprocess
import sys
import textwrap
from pathlib import Path


def test_lightweight_worker_operations_do_not_import_build_pipeline():
    code = textwrap.dedent('''
        import io, json, sys, tempfile
        from hashlib import sha256
        from pathlib import Path
        from semantica.semantic_worker import handle_request, serve
        from semantica.source import source_content_revision

        def request(method, params=None):
            return handle_request({"id": method, "method": method, "params": params or {}})

        assert request("schema")["ok"]
        assert request("validate_extraction_spec", {"id": "general", "version": "1",
            "entity_types": [{"name": "Concept", "description": "A grounded concept"}]})["ok"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.txt"
            path.write_text("Ada builds Engine. " * 50)
            source = {"sourceId": "one", "filePath": str(path), "name": "source.txt",
                      "mimeType": "text/plain", "materialRevision": source_content_revision(path)}
            params = {"source": source, "outputDir": str(root / "parsed"),
                      "documentProcessing": {"mode": "local"}, "forceOcr": False}
            parsed = request("parse_source", params)["result"]
            old = root / "historical.json"
            payload = json.loads(Path(parsed["artifactPath"]).read_bytes())
            payload["protocol"] = "semantica.parsed-source.v1"
            payload.pop("processingRevision")
            old.write_text(json.dumps(payload))
            upgraded = request("upgrade_parsed_source", {"artifactPath": str(old),
                "artifactDigest": "sha256:" + sha256(old.read_bytes()).hexdigest(),
                "representationRevision": parsed["representationRevision"],
                "representationId": parsed["representationId"], "outputDir": str(root / "upgraded")})["result"]
            assert "processingRevision" not in upgraded
            bound = request("bind_parsed_source", {**params,
                "source": {**source, "sourceId": "two", "name": "other.txt"},
                "parsedArtifactPath": upgraded["artifactPath"],
                "parsedArtifactDigest": upgraded["artifactDigest"]})["result"]
            assert bound["sourceId"] == "two"
            assert "processingRevision" not in bound
            path.write_text("changed")
            output = io.StringIO()
            messages = [{"id": "bad", "method": "parse_source", "params": params},
                        {"id": "next", "method": "schema"}]
            assert serve(io.StringIO("".join(json.dumps(x) + "\\n" for x in messages)), output) == 0
            replies = [json.loads(x) for x in output.getvalue().splitlines()]
            assert not replies[0]["ok"] and replies[0]["error"]["type"] == "SemanticArtifactError"
            assert replies[1]["ok"]
        forbidden = [name for name in sys.modules if name == "semantica.semantic_artifact_builder"
                     or name.startswith(("semantica.kg.", "semantica.pipeline.", "torch", "spacy", "docling."))]
        assert not forbidden, forbidden
    ''')
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
