from pathlib import Path

import pytest

from semantica.project_document_quality import assess_document_quality
from semantica.source import SourceDocument
from semantica.project_checkpoint import active_checkpoint
from semantica.semantic_artifact_pipeline import DocumentQualityError, _build_source, parse_source_artifact
from semantica.semantic_artifact_schema import ParseSourceRequest, SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


def test_native_font_corruption_requires_review_with_exact_location():
    text = "Normal heading\nS N\u00acY'[fO\u4d4e\u8e53 N\u00ac\u3002S N\u00acY'[ff/Nb\u4059'[f\u3002"
    quality = assess_document_quality(text, {"pages": [{"page_number": 1, "text": text}]})
    assert quality["status"] == "needs_review"
    issue = quality["issues"][0]
    assert issue["code"] == "fragmented_cjk_encoding"
    assert issue["pageNumber"] == 1
    assert text[issue["startChar"]:issue["endChar"]] == issue["quote"]


@pytest.mark.parametrize("text", ["北京大学位于北京。", "The CJK parser supports 中文 and English.", "变量 x = y + z；结果为 42。", "東京大学 AI 研究 (2026) / version 2"])
def test_readable_multilingual_text_is_admitted(text):
    assert assess_document_quality(text, {})["status"] == "passed"


def test_encoding_loss_is_reported():
    quality = assess_document_quality("Broken \ufffd\ufffd text", {})
    assert quality["status"] == "needs_review"
    assert quality["issues"][0]["code"] == "unmapped_characters"


def test_ocr_recipe_and_text_revision_have_distinct_evidence_identity(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / "build")["params"])
    parsed = (source.read_text(), {"format": "docling", "text": source.read_text()}, "native", request.sources[0].material_revision, "docling", "2")
    native = _build_source(request.sources[0], False, parsed=parsed)
    repaired = _build_source(request.sources[0], True, parsed=(*parsed[:2], "ocr", *parsed[3:]))
    assert native["representation"].id != repaired["representation"].id
    assert native["representation"].metadata["representation_revision"] != repaired["representation"].metadata["representation_revision"]
    assert {item.id for item in native["evidence"]}.isdisjoint(item.id for item in repaired["evidence"])
    assert _build_source(request.sources[0], False, parsed=parsed)["representation"].id == native["representation"].id


def test_failed_quality_is_durable_and_never_enters_knowledge_extraction(tmp_path, monkeypatch):
    import semantica.semantic_artifact_pipeline as pipeline
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    request = _request(source, tmp_path / "build", prepare=False)
    request["params"]["sources"][0]["mimeType"] = "application/pdf"
    parse_request = ParseSourceRequest.model_validate({
        "source": request["params"]["sources"][0],
        "outputDir": str(tmp_path / "parsed"),
        "forceOcr": False,
        "documentProcessing": {"mode": "local"},
    })
    calls = []
    cache = {}

    class Checkpoint:
        def read(self, stage, key):
            return cache.get((stage, repr(key)))

        def write(self, stage, key, value):
            cache[(stage, repr(key))] = value

    def parse(*args, **kwargs):
        calls.append(kwargs["force_ocr"])
        return SourceDocument("Broken \ufffd\ufffd text", {"format": "docling"}, "native", "docling", "2")

    monkeypatch.setattr(pipeline, "parse_source", parse)
    monkeypatch.setattr(pipeline, "_build_source", lambda *args, **kwargs: pytest.fail("failed quality reached extraction"))
    token = active_checkpoint.set(Checkpoint())
    try:
        for _ in range(2):
            with pytest.raises(DocumentQualityError, match="explicit OCR repair"):
                parse_source_artifact(parse_request)
    finally:
        active_checkpoint.reset(token)
    assert calls == [False]
    assert next(iter(cache.values()))[1]["quality"]["status"] == "needs_review"
