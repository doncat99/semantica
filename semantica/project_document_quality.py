"""Explainable admission checks on the one already parsed document."""
from __future__ import annotations

import re
import unicodedata


def assess_document_quality(text: str, document: dict) -> dict:
    issues = []
    for line in re.finditer(r"[^\n]+", text):
        value = line.group()
        visible = [character for character in value if not character.isspace()]
        invalid = sum(character == "\ufffd" or unicodedata.category(character) in {"Co", "Cs", "Cn", "Cc"} for character in visible)
        cjk = sum("\u3400" <= character <= "\u9fff" for character in visible)
        latin = re.findall(r"[A-Za-z]+", value)
        punctuation = sum(character in "[]'`/\\\u00ac" for character in visible)
        code = None
        if invalid >= 2 or (invalid and len(visible) < 8):
            code = "unmapped_characters"
        # This flags fragmented font mappings, not CJK text or ordinary code.
        # It is an admission heuristic, not a proof that every readable string is correct.
        elif cjk >= 2 and len(latin) >= 4 and max(map(len, latin)) <= 3 and punctuation >= 5:
            code = "fragmented_cjk_encoding"
        if code:
            page = next((page for page in document.get("pages", []) if value in page.get("text", "")), None)
            issues.append({"code": code, "startChar": line.start(), "endChar": line.end(), "quote": value,
                **({"pageNumber": page["page_number"]} if page and "page_number" in page else {})})
    return {"version": "1", "status": "needs_review" if issues else "passed", "issues": issues}
