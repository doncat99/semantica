"""Original-text keyword recall and location regression, without model calls."""
from semantica.explorer.search_index import GraphSearchIndex


def test_original_occurrences_are_not_limited_to_knowledge_records_or_one_per_document():
    text = "ESG " * 1205
    page = GraphSearchIndex.document_matches(text, "esg", offset=0, limit=1000)
    assert page["total"] == 1205
    assert page["nextOffset"] == 1000
    assert len(page["matches"]) == 1000
    rest = GraphSearchIndex.document_matches(text, "ESG", offset=1000, limit=1000)
    assert rest["nextOffset"] is None
    assert rest["matches"][0] == (4000, 4003)
    assert len(rest["matches"]) == 205


def test_literal_phrase_unicode_and_char_offsets():
    text = "İ ESG-risk esg RISK ESG-risk"
    assert GraphSearchIndex.document_matches(text, "ESG-risk", offset=0, limit=1000)["matches"] == [(2, 10), (20, 28)]
    assert GraphSearchIndex.document_matches(text, ".*", offset=0, limit=1000)["total"] == 0
