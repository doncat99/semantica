"""Immutable-byte admission must honor cancellation between bounded reads."""
from hashlib import sha256
from pathlib import Path
from threading import Event

from blake3 import blake3
import pytest

from semantica.semantic_source_artifact import _digest_file
from semantica.semantic_worker_context import query_cancellation
from semantica.source import source_content_revision
from semantica.utils.exceptions import ProcessingError


@pytest.mark.parametrize('hash_file', [source_content_revision, _digest_file])
def test_hash_cancels_before_opening_material(tmp_path, monkeypatch, hash_file):
    path = tmp_path / 'material'
    path.write_bytes(b'immutable')
    event = Event()
    event.set()
    token = query_cancellation.set(event)
    opened = []
    original = Path.open

    def observe(self, *args, **kwargs):
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', observe)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            hash_file(path)
    finally:
        query_cancellation.reset(token)
    assert opened == []


@pytest.mark.parametrize('hash_file', [source_content_revision, _digest_file])
def test_hash_stops_after_inflight_block_and_closes_stream(tmp_path, monkeypatch, hash_file):
    path = tmp_path / 'material'
    path.write_bytes(b'x' * (3 * 1024 * 1024))
    event, reads, streams = Event(), [], []
    original = Path.open

    class CancelAfterRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            reads.append(size)
            value = self.stream.read(size)
            event.set()
            return value

        def readable(self):
            return True

        def readinto(self, buffer):
            value = self.read(len(buffer))
            buffer[:len(value)] = value
            return len(value)

    def observe(self, *args, **kwargs):
        stream = original(self, *args, **kwargs)
        streams.append(stream)
        return CancelAfterRead(stream)

    monkeypatch.setattr(Path, 'open', observe)
    token = query_cancellation.set(event)
    try:
        with pytest.raises(ProcessingError, match='canceled'):
            hash_file(path)
    finally:
        query_cancellation.reset(token)
    assert len(reads) == 1
    assert all(stream.closed for stream in streams)


def test_hashes_preserve_immutable_byte_contract(tmp_path):
    path = tmp_path / 'material'
    body = ('immutable 😀\n' * 100000).encode()
    path.write_bytes(body)
    assert source_content_revision(path) == 'b3-' + blake3(body).hexdigest()
    assert _digest_file(path) == 'sha256:' + sha256(body).hexdigest()
