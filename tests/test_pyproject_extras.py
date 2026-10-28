"""Guard for the aggregate ``all`` extras in pyproject.toml.

Review of #1508 caught ``parse-pdf`` missing from every ``all`` bundle:
``semantica[all]`` installed the package without its PDF reader, so the default
PDFParser raised ProcessingError on first use. tomllib is stdlib only from
Python 3.11, so the bundle block is parsed textually — the repo still
supports 3.9/3.10.
"""

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_worker_sdk_profiles_exclude_incompatible_llm_bundles():
    import tomllib

    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    conflicts = {frozenset(item["extra"] for item in group)
                 for group in config["tool"]["uv"]["conflicts"]}
    for worker in ("semantic-worker-common", "semantic-worker", "semantic-worker-cuda", "semantic-worker-directml"):
        for provider in ("llm-instructor", "llm-litellm", "llm-all", "all"):
            assert frozenset((worker, provider)) in conflicts


def test_optional_analytics_dependencies_belong_to_their_capabilities():
    import tomllib
    from packaging.requirements import Requirement

    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    names = lambda entries: {Requirement(entry).name for entry in entries}
    assert not names(project["dependencies"]) & {"pyarrow", "grpcio", "scikit-learn"}
    extras = project["optional-dependencies"]
    for extra in ("viz", "explorer"):
        assert "scikit-learn" in names(extras[extra])
    for extra in ("db-arrow", "ingest-arrow", "ingest-parquet"):
        assert "pyarrow" in names(extras[extra])


def _extras_in_all_bundles():
    """Collect every extra name referenced inside the ``all = [...]`` block."""
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r"^all = \[\n(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert match, "pyproject.toml must define an aggregate 'all' extra"

    names = set()
    for bundle in re.findall(r"semantica\[([^\]]+)\]", match.group(1)):
        names.update(part.strip() for part in bundle.split(","))
    assert names, "'all' bundles must reference at least one extra"
    return names


def test_all_bundles_include_parse_pdf():
    """An all-features install must include built-in PDF parsing support."""
    assert "parse-pdf" in _extras_in_all_bundles()


def test_native_pdf_extras_use_one_reader():
    text = PYPROJECT.read_text(encoding="utf-8")
    def requirements(extra, seen=None):
        seen = set() if seen is None else seen
        if extra in seen:
            return ""
        seen.add(extra)
        match = re.search(r"^" + re.escape(extra) + r" = \[(.*?)\]$", text, re.MULTILINE | re.DOTALL)
        assert match, extra
        block = match.group(1)
        nested = re.findall(r"semantica\[([^\]]+)\]", block)
        return block + "".join(requirements(name.strip(), seen)
                              for group in nested for name in group.split(","))

    for extra in ("parse-pdf", "semantic-worker", "semantic-worker-cuda", "semantic-worker-directml"):
        assert "pymupdf" in requirements(extra)
    assert "pdfplumber" not in text.lower()


def test_ci_requirements_do_not_install_pdfplumber():
    text = (PYPROJECT.parent / "requirements-ci.txt").read_text(encoding="utf-8")
    assert not re.search(r"^pdfplumber(?:\[|[=<>!~ @])", text, re.MULTILINE | re.IGNORECASE)


def test_all_bundle_extraction_finds_known_extra():
    """Control: the extraction reads the right block (parse-docling is in)."""
    assert "parse-docling" in _extras_in_all_bundles()


def test_all_bundles_include_langdetect():
    """#1807: without langdetect, LanguageDetector reports every text as the
    default language, so ``semantica[all]`` has to pull it in."""
    assert "nlp-langdetect" in _extras_in_all_bundles()
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r"^nlp-langdetect = \[\n(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert match and "langdetect" in match.group(1)
