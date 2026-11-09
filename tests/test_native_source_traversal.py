"""Exact traversal oracles for native range-backed semantic source consumers."""
import re

import pytest

from semantica import semantic_publication_builder as builder


def test_mention_addresses_use_accepted_revision_and_coordinates():
    address = builder._entity_id('source', 'parse:one', 'PERSON', 10, 14)
    assert builder._entity_id('source', 'parse:one', 'PERSON', 10, 14) == address
    assert builder._entity_id('source', 'parse:one', 'PERSON', 30, 34) != address
    assert builder._entity_id('source', 'parse:two', 'PERSON', 10, 14) != address

@pytest.mark.parametrize('chunk_size', [1, 3, 1599, 1600, 1601, 12288])
def test_passage_addresses_preserve_long_lines_empty_lines_and_tail(chunk_size):
    text = '\n\n' + 'a'*3200 + '\n' + ' '*1601 + '\n尾' + '界'*1602 + '\nlast'
    expected = [(start, min(start+1600, match.end()))
                for match in re.finditer(r'[^\n]+', text)
                for start in range(match.start(), match.end(), 1600)]
    actual = list(builder._source_passage_ranges(lambda start, end: text[start:end],
                                               len(text), chunk_size=chunk_size))
    assert actual == [(start, end, text[start:end]) for start, end in expected]
    assert actual[-1][2] == 'last'


def test_passage_projection_reads_each_native_window_once(monkeypatch):
    from types import SimpleNamespace
    text = ('a\n\n界\n' * 4000) + 'tail' * 900
    reads = []
    def read(reader, start, end):
        reads.append((start, end))
        return text[start:end]
    monkeypatch.setattr(builder, '_read_source_projection_text', read)
    class Text:
        reader = object()
        def __len__(self):
            return len(text)
    built = dict(text=Text(), representation=SimpleNamespace(id='rep', origin='native'),
                 source_locations=SimpleNamespace(locate=lambda start, end: None))
    passages = builder._source_passages(built)
    expected = list(builder._source_passage_ranges(lambda start, end: text[start:end], len(text)))
    assert [(span.locator.start_char, span.locator.end_char, span.quote) for span in passages] == expected
    assert reads == [(start, min(len(text), start+builder.TEXT_WINDOW_CHARS))
                     for start in range(0, len(text), builder.TEXT_WINDOW_CHARS)]
