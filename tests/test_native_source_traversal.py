"""Exact traversal oracles for native range-backed semantic source consumers."""
from bisect import bisect_left
import re

import pytest

from semantica import semantic_publication_builder as builder


@pytest.mark.parametrize('chunk_size', [1, 2, 7, 127, 12288])
def test_occurrence_ordinals_preserve_unicode_whitespace_and_unextracted_matches(chunk_size):
    text = ('İıſK IISK kK aaa aaaa αΑ ββ ß ss\n'
            'Alpha' + ' \t\n\u2003' * 4000 + 'Beta Alpha Beta ALPHA\tBETA\n') * 2
    names = ['i', 's', 'k', 'aa', 'α', 'β', 'ß', 'ss', 'Alpha Beta', 'ALPHA\tBETA']
    old = {name: [match.start() for match in re.finditer(
        r'\s+'.join(re.escape(part) for part in name.split()), text, re.IGNORECASE)] for name in names}
    targets = [(name, start) for name in names for start in
               (0, 1, 17, len(text)//2, len(text)-1, len(text))]
    reads = []

    def read(start, end):
        assert 0 < end-start <= chunk_size
        reads.append((start, end))
        return text[start:end]

    actual = builder._source_occurrence_ordinals(read, len(text), targets, chunk_size=chunk_size)
    assert actual == {(name, start): bisect_left(old[name], start) for name, start in targets}
    assert reads[0][0] == 0 and reads[-1][1] == len(text)
    assert all(left[1] == right[0] for left, right in zip(reads, reads[1:]))


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
