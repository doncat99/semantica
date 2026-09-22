from pathlib import Path
from zipfile import ZipFile

import pytest

from semantica.project_source import UnsupportedSourceFormatError, parse_source, source_content_revision


def test_material_revision_matches_shared_blake3_known_vector(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"abc")
    assert source_content_revision(source) == "b3-6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"


def test_worker_rejects_changed_bytes_before_parsing(tmp_path, monkeypatch):
    from semantica.project_snapshot_pipeline import _parse_source, SnapshotBuildError
    from semantica.project_snapshot_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_bytes(b"abc")
    revision = source_content_revision(source)
    request = SourceBuildInput(filePath=str(source), sourceId="s1", materialRevision=revision, name=source.name, mimeType="text/plain")
    source.write_bytes(b"changed")
    monkeypatch.setattr("semantica.project_snapshot_pipeline.parse_source", lambda *args, **kwargs: pytest.fail("changed source reached parser"))
    with pytest.raises(SnapshotBuildError, match="material revision"):
        _parse_source(request, False)


def test_worker_preserves_material_identity_in_representation(tmp_path):
    from semantica.project_snapshot_pipeline import _build_source
    from semantica.project_snapshot_schema import SourceBuildInput
    source = tmp_path / "source.txt"
    source.write_bytes(b"Ada Lovelace designed the Analytical Engine.")
    revision = source_content_revision(source)
    request = SourceBuildInput(filePath=str(source), sourceId="s1", materialRevision=revision, name=source.name, mimeType="text/plain")
    representation = _build_source(request, False)["representation"]
    assert representation.content_hash == representation.material_revision_id == revision
    assert representation.metadata["document"]["content_hash"] == revision


def test_text_source_uses_the_canonical_adapter_contract(tmp_path: Path):
    source = tmp_path / "notes.md"
    source.write_text("# Evidence\nOne source, one representation.", encoding="utf-8")

    parsed = parse_source(
        source,
        name=source.name,
        mime_type="text/markdown",
        force_ocr=False,
    )

    assert parsed.parser == "semantica.text"
    assert parsed.origin == "native"
    assert parsed.document["format"] == "markdown"
    assert parsed.text.endswith("one representation.")


def test_known_format_rejects_a_mismatched_manifest_mime(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("text", encoding="utf-8")

    with pytest.raises(UnsupportedSourceFormatError, match="does not match"):
        parse_source(
            source,
            name=source.name,
            mime_type="application/pdf",
            force_ocr=False,
        )


def test_force_ocr_cannot_claim_non_docling_provenance(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("text", encoding="utf-8")

    with pytest.raises(UnsupportedSourceFormatError, match="only supported by the Docling adapter"):
        parse_source(source, name=source.name, mime_type="text/plain", force_ocr=True)


def test_epub_adapter_reads_spine_without_a_second_parser(tmp_path: Path):
    source = tmp_path / "book.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr("META-INF/container.xml", """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>""")
        archive.writestr("OPS/package.opf", """<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="chapter-1" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter-1"/></spine></package>""")
        archive.writestr("OPS/chapter.xhtml", "<html><body><h1>Knowledge</h1><p>One source, one representation.</p></body></html>")

    parsed = parse_source(source, name=source.name, mime_type="application/epub+zip", force_ocr=False)

    assert parsed.parser == "semantica.epub"
    assert parsed.origin == "adapter"
    assert parsed.document["format"] == "epub"
    assert parsed.document["sections"][0]["href"] == "OPS/chapter.xhtml"
    assert "One source, one representation." in parsed.text


@pytest.mark.parametrize("suffix", [".doc", ".wpd"])
def test_special_formats_validate_mime_before_dedicated_adapter(tmp_path: Path, suffix: str):
    source = tmp_path / f"legacy{suffix}"
    source.write_bytes(b"fixture")

    with pytest.raises(UnsupportedSourceFormatError, match="does not match"):
        parse_source(
            source,
            name=source.name,
            mime_type="application/octet-stream",
            force_ocr=False,
        )
