"""Dedicated binary Office/WordPerfect import into one flat ODF representation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET


OFFICE_SUFFIXES = {".doc", ".ppt", ".xls", ".wpd", ".wp", ".wp4", ".wp5", ".wp6"}
_NS = {"office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0", "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0", "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0", "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"}


def bundled_office() -> tuple[Path, str]:
    root = Path(sys.executable).resolve().parents[1 if os.name == "nt" else 2]
    receipt = json.loads((root / "office-release.json").read_text(encoding="utf-8"))
    executable = (root / "office" / receipt["executable"]).resolve(strict=True)
    if not executable.is_relative_to(root / "office") or not executable.is_file():
        raise ValueError("the bundled Office executable is outside its immutable runtime")
    return executable, receipt["version"]


def convert_office(path: Path, output: Path, profile: Path, executable: Path, target: str) -> Path:
    profile.mkdir()
    (profile / "user").mkdir()
    # Disable document macros and external-link updates in the isolated profile.
    (profile / "user/registrymodifications.xcu").write_text(
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Common/Load"><prop oor:name="UpdateDocMode" oor:op="fuse"><value>0</value></prop></item></oor:items>', encoding="utf-8")
    subprocess.run([str(executable), "--headless", "--nologo", "--nodefault", "--norestore", "--nofirststartwizard",
        f"-env:UserInstallation={profile.resolve().as_uri()}", "--convert-to", target, "--outdir", str(output), str(path.resolve())],
        capture_output=True, text=True, check=True, timeout=180)
    converted = output / (path.stem + "." + target.split(":", 1)[0])
    if not converted.is_file():
        raise ValueError(f"bundled Office did not produce {converted.name}")
    return converted


def _paragraph_text(node: ET.Element) -> str:
    parts = [node.text or ""]
    for child in node:
        if child.tag == "{" + _NS["text"] + "}s":
            parts.append(" " * min(int(child.get("{" + _NS["text"] + "}c", "1")), 10000))
        elif child.tag == "{" + _NS["text"] + "}tab":
            parts.append("\t")
        elif child.tag == "{" + _NS["text"] + "}line-break":
            parts.append("\n")
        else:
            parts.append(_paragraph_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def flat_odf_document(xml: bytes, *, name: str) -> dict:
    root = ET.fromstring(xml)
    body = root.find("office:body", _NS)
    if body is None:
        raise ValueError("Office representation has no document body")
    sections, text_parts = [], []
    position = 0

    def append(text: str, locator: dict) -> None:
        nonlocal position
        if not text.strip():
            return
        if text_parts:
            position += 2
        sections.append({"text": text, "start_char": position, "end_char": position + len(text), "locator": locator})
        text_parts.append(text)
        position += len(text)

    spreadsheet = body.find("office:spreadsheet", _NS)
    slides = body.find("office:presentation", _NS)
    if spreadsheet is not None:
        for sheet in spreadsheet.findall("table:table", _NS):
            sheet_name = sheet.get("{" + _NS["table"] + "}name", "")
            row_index = 1
            for row in sheet.findall("table:table-row", _NS):
                column = 1
                repeats = int(row.get("{" + _NS["table"] + "}number-rows-repeated", "1"))
                for cell in row:
                    count = int(cell.get("{" + _NS["table"] + "}number-columns-repeated", "1"))
                    text = "\n".join(_paragraph_text(p) for p in cell.findall("text:p", _NS))
                    append(text, {"kind": "sheet-cell", "sheet": sheet_name, "row": row_index, "column": column, "row_repeat": repeats, "column_repeat": count})
                    column += count
                row_index += repeats
    elif slides is not None:
        for number, slide in enumerate(slides.findall("draw:page", _NS), 1):
            for index, paragraph in enumerate(slide.iter("{" + _NS["text"] + "}p")):
                append(_paragraph_text(paragraph), {"kind": "slide-paragraph", "slide": number, "paragraph": index})
    else:
        content = body.find("office:text", _NS)
        if content is None:
            raise ValueError("unsupported flat ODF document body")
        for index, paragraph in enumerate(node for node in content.iter() if node.tag in {"{" + _NS["text"] + "}p", "{" + _NS["text"] + "}h"}):
            append(_paragraph_text(paragraph), {"kind": "paragraph", "paragraph": index})
    if not text_parts:
        raise ValueError("Office source has no readable document text")
    return {"format": "flat-odf", "source": name, "text": "\n\n".join(text_parts), "sections": sections, "flat_odf": xml.decode("utf-8")}


def parse_office(path: Path, *, name: str) -> tuple[dict, str]:
    executable, version = bundled_office()
    suffix = path.suffix.lower()
    if suffix not in OFFICE_SUFFIXES:
        raise ValueError(f"unsupported dedicated Office source: {suffix}")
    target = "fods" if suffix == ".xls" else "fodp" if suffix == ".ppt" else "fodt"
    with tempfile.TemporaryDirectory(prefix="semantica-office-") as directory:
        scratch = Path(directory)
        converted = convert_office(path, scratch, scratch / "profile", executable, target)
        return flat_odf_document(converted.read_bytes(), name=name), version
