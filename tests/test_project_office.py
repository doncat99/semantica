from pathlib import Path

import pytest

from semantica.project_office import flat_odf_document
from semantica.project_source import parse_source


def test_binary_office_routes_once_to_dedicated_owner(tmp_path, monkeypatch):
    calls = []
    def parse(path, *, name):
        calls.append(path)
        return {"format": "flat-odf", "source": name, "text": "Ada"}, "26.2.6"
    monkeypatch.setattr("semantica.project_office.parse_office", parse)
    result = parse_source(tmp_path / "source.doc", name="source.doc", mime_type="application/msword", force_ocr=False)
    assert result.text == "Ada" and result.parser == "semantica.libreoffice"
    assert len(calls) == 1


@pytest.mark.parametrize("body,expected,locator", [
    ('<office:text><text:h>Ada</text:h><text:p>A<text:s text:c="3"/>B<text:tab/>C</text:p></office:text>', 'Ada\n\nA   B\tC', {"kind": "paragraph", "paragraph": 1}),
    ('<office:presentation><draw:page><text:p>Ada</text:p></draw:page><draw:page><text:p>Engine</text:p></draw:page></office:presentation>', 'Ada\n\nEngine', {"kind": "slide-paragraph", "slide": 2, "paragraph": 0}),
    ('<office:spreadsheet><table:table table:name="Evidence"><table:table-row><table:table-cell table:number-columns-repeated="2"/><table:table-cell><text:p>Ada</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>', 'Ada', {"kind": "sheet-cell", "sheet": "Evidence", "row": 1, "column": 3, "row_repeat": 1, "column_repeat": 1}),
])
def test_flat_odf_preserves_exact_text_offsets_and_structural_locators(body, expected, locator):
    xml = ('<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"><office:body>' + body + '</office:body></office:document>').encode()
    result = flat_odf_document(xml, name="source")
    assert result["text"] == expected
    assert result["sections"][-1]["locator"] == locator
    for item in result["sections"]:
        assert result["text"][item["start_char"]:item["end_char"]] == item["text"]
