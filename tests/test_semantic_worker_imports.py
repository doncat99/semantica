"""Cold-process checks: a warmed pytest interpreter cannot prove import isolation."""
import subprocess
import sys
import textwrap
from pathlib import Path


def test_docling_initializes_mime_types_without_host_files():
    code = textwrap.dedent('''
        import builtins, importlib.util, mimetypes, os.path
        blocked = "/semantica-denied-system-mime.types"
        mimetypes.knownfiles[:] = [blocked]
        original_open, original_isfile = builtins.open, os.path.isfile
        def denied_open(file, *args, **kwargs):
            if str(file) == blocked:
                raise PermissionError(1, "Operation not permitted", blocked)
            return original_open(file, *args, **kwargs)
        builtins.open = denied_open
        os.path.isfile = lambda path: str(path) == blocked or original_isfile(path)

        from semantica.parse import docling_parser
        # Exercise the same eager MIME initialization used by openpyxl,
        # plus later explicit reinitialization by ingestion.
        assert mimetypes.MimeTypes().guess_type("report.pdf")[0] == "application/pdf"
        mimetypes.init()
        assert mimetypes.guess_type("report.doc")[0] == "application/msword"
        assert mimetypes.guess_type("figure.png")[0] == "image/png"
        mimetypes.add_type("application/x-ndjson", ".ndjson")
        mimetypes.init(files=[])
        assert mimetypes.guess_type("records.ndjson")[0] == "application/x-ndjson"
        if importlib.util.find_spec("docling") is not None:
            assert docling_parser.DOCLING_AVAILABLE, docling_parser.DOCLING_IMPORT_ERROR
    ''')
    result = subprocess.run([sys.executable, "-B", "-c", code],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


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
            bound = request("bind_parsed_source", {**params,
                "source": {**source, "sourceId": "two", "name": "other.txt"},
                "parsedArtifactPath": parsed["artifactPath"],
                "parsedArtifactDigest": parsed["artifactDigest"],
                "parsedReaderIndexPath": parsed["readerIndexPath"],
                "parsedReaderIndexDigest": parsed["readerIndexDigest"]})["result"]
            assert bound["sourceId"] == "two"
            assert bound["processingRevision"].startswith("sha256:")
            assert bound["artifactPath"] == parsed["artifactPath"]
            assert bound["sourceHeader"]["parser"] == parsed["sourceHeader"]["parser"]
            path.write_text("changed")
            output = io.StringIO()
            messages = [{"id": "bad", "method": "parse_source", "params": params},
                        {"id": "next", "method": "schema"}]
            assert serve(io.StringIO("".join(json.dumps(x) + "\\n" for x in messages)), output) == 0
            replies = [json.loads(x) for x in output.getvalue().splitlines()]
            assert not replies[0]["ok"] and replies[0]["error"]["type"] == "SemanticArtifactError"
            assert replies[1]["ok"]
        forbidden = [name for name in sys.modules if name == "semantica.semantic_publication_builder"
                     or name.startswith(("semantica.kg.", "semantica.pipeline.", "torch", "spacy", "docling."))]
        assert not forbidden, forbidden
    ''')
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_publication_builder_is_the_only_current_builder_module():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'semantica' / 'semantic_publication_builder.py').is_file()
    assert not (root / 'semantica' / ('semantic_' + 'artifact_builder.py')).exists()
    worker = (root / 'semantica' / 'semantic_worker.py').read_text()
    assert 'from .semantic_publication_builder import build_semantic_artifacts' in worker
