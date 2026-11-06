"""Admission metadata must not hydrate a source body."""
from pathlib import Path
import sqlite3
from threading import Event

import pytest

from semantica.semantic_document_reader import read_source_header, write_reader_artifact, DocumentReaderIndexError
from semantica.semantic_worker_context import query_cancellation
from semantica.utils.exceptions import ProcessingError
from tests.test_native_document_reader import request, payload


def test_header_is_complete_without_reading_native_body(tmp_path, monkeypatch):
    path = tmp_path / 'source.json'
    text = 'Unicode 😀 漢\n' * 20_000
    value = payload({'format': 'text', 'text': text, 'mime_type': 'text/plain',
        'content_hash': 'material:m'})
    value.update(mimeType='text/plain', forceOcr=False, documentProcessing={'mode': 'local'},
        processingRevision='processing:p', parser='TextParser', parserVersion='1', origin='source.txt')
    digests = write_reader_artifact(path, value)
    selected = request(path, digests, 'source_windows')
    original_open = Path.open

    class BodyGuard:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def read(self, *args):
            raise AssertionError('header admission read canonical body')

    def guarded_open(file, *args, **kwargs):
        stream = original_open(file, *args, **kwargs)
        return BodyGuard(stream) if file == path else stream

    monkeypatch.setattr(Path, 'open', guarded_open)
    result = read_source_header(selected)
    header = result['header']
    assert result['readBytes'] == 0
    assert header['sourceCharCount'] == len(text)
    assert header['sourceWindowCount'] > 1
    assert header['documentMimeType'] == header['mimeType'] == 'text/plain'
    assert header['contentHash'] == 'material:m'
    for key in ('forceOcr', 'documentProcessing', 'processingRevision', 'parser', 'parserVersion', 'origin'):
        assert header[key] == value[key]


def test_header_checks_current_binding_installation_and_cancellation(tmp_path):
    path = tmp_path / 'source.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'bounded'}))
    selected = request(path, digests, 'source_windows')
    selected.material_revision = 'wrong'
    with pytest.raises(ValueError, match='requested representation'):
        read_source_header(selected)
    selected.material_revision = 'material:m'
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            read_source_header(selected)
    finally:
        query_cancellation.reset(token)
    path.touch()
    with pytest.raises(ValueError, match='installation changed'):
        read_source_header(selected)


def test_obsolete_header_index_fails_with_typed_rebuild_state(tmp_path):
    path = tmp_path / 'source.json'
    digests = write_reader_artifact(path, payload({'format': 'text', 'text': 'bounded'}))
    with sqlite3.connect(path.with_suffix('.reader.sqlite')) as db:
        db.execute('DROP TABLE metadata')
    with pytest.raises(DocumentReaderIndexError, match='rebuild'):
        read_source_header(request(path, digests, 'source_windows'))
