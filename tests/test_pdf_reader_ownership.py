"""Keep PDF readers and Docling conversion inside their existing native owners."""
import ast
from pathlib import Path
import shlex
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PDF_OWNER = "semantica/parse/pdf_parser.py"
DOCLING_OWNER = "semantica/parse/docling_parser.py"
READERS = {
    "pymupdf", "fitz", "pdfplumber", "pypdf", "PyPDF2", "pypdfium2",
    "pdfminer", "pdf2image", "pdfquery", "pikepdf", "pypoppler", "poppler",
    "pdf_oxide", "borb", "tika",
}
COMMANDS = {"pdftotext", "pdftoppm", "pdftocairo", "pdfinfo", "mutool"}


def _violations(source, path):
    violations = []
    for node in ast.walk(ast.parse(source)):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            modules = [node.module or ""]
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
            if name in {"__import__", "import_module", "safe_import"}:
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    modules = [node.args[0].value]
            # Reader commands must not become a subprocess escape hatch.
            if name in {"run", "Popen", "call", "check_call", "check_output", "system", "popen"}:
                try:
                    command = ast.literal_eval(node.args[0])
                    if isinstance(command, str):
                        command = shlex.split(command)
                except (ValueError, TypeError):
                    command = None
                if isinstance(command, (list, tuple)) and command and isinstance(command[0], str):
                    if Path(command[0]).name in COMMANDS and path != PDF_OWNER:
                        violations.append((node.lineno, command[0]))
        for module in modules:
            if module.split(".")[0] == "pdfplumber":
                violations.append((node.lineno, module))
            elif module.split(".")[0] in READERS and path != PDF_OWNER:
                violations.append((node.lineno, module))
            if (module == "docling" or module.startswith(("docling.backend", "docling.document_converter"))) and path != DOCLING_OWNER:
                violations.append((node.lineno, module))
    return violations


def test_tracked_code_uses_native_reader_owners():
    # Inspect the index too: this fork is often developed in a sparse checkout.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    failures = []
    for path in tracked:
        if path.startswith("tests/") or not path.endswith(".py"):
            continue
        local = ROOT / path
        source = local.read_bytes() if local.exists() else subprocess.check_output(
            ["git", "show", ":" + path], cwd=ROOT)
        failures.extend((path, line, module) for line, module in _violations(source, path))
    assert not failures, f"PDF reader bypasses: {failures}"


@pytest.mark.parametrize("source", [
    "import pymupdf as reader", "from pdfplumber import open as reader",
    "from pypdf import PdfReader", "import fitz", "import pypdfium2",
    "importlib.import_module('pdfminer.high_level')", "__import__('pymupdf')",
    "safe_import('pypdf')", "subprocess.run(['pdftotext', 'input.pdf', '-'])",
    "os.system('/usr/bin/pdfinfo input.pdf')",
    "from docling.document_converter import DocumentConverter",
    "from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend",
])
def test_gate_rejects_bypasses_in_builders_workers_and_examples(source):
    assert _violations(source, "semantica/semantic_artifact_builder.py")


def test_gate_allows_native_owners_and_unrelated_file_io():
    assert not _violations("import pymupdf; pymupdf.open('input.pdf')", PDF_OWNER)
    assert not _violations("from docling.document_converter import DocumentConverter", DOCLING_OWNER)
    assert not _violations("open('source.pdf', 'rb'); import pathlib", "semantica/source.py")


@pytest.mark.parametrize("source", [
    "import pdfplumber", "from pdfplumber import open",
    "importlib.import_module('pdfplumber')", "__import__('pdfplumber')",
    "safe_import('pdfplumber')",
])
def test_gate_rejects_pdfplumber_even_in_native_owner(source):
    assert _violations(source, PDF_OWNER)
