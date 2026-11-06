"""Durable accepted extraction handoff in the existing native cache owner."""
import importlib.util
import sqlite3
import subprocess
import sys
import threading
import time
import tracemalloc

import pytest

from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
from semantica.utils.exceptions import ProcessingError


def cache(path, **kwargs):
    return ExtractionCache(ttl=-1, backend=SqliteCacheBackend(str(path), **kwargs))


def test_accepted_survives_exit_expiry_eviction_clear_then_releases(tmp_path):
    path = tmp_path / "cache.db"
    code = '''
import os, sys
from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
c = ExtractionCache(ttl=-1, backend=SqliteCacheBackend(sys.argv[1], max_size=2))
receipt = c.accept('entities', 'source', [{'name':'paid'}], model='m')
print(receipt, flush=True)
os._exit(73)
'''
    writer = subprocess.run([sys.executable, "-c", code, str(path)],
                            capture_output=True, text=True, timeout=20)
    assert writer.returncode == 73, writer.stderr
    receipt = writer.stdout.strip()
    c = cache(path, max_size=2)
    for index in range(5):
        c.set("entities", str(index), [index])
    c.clear()
    assert c.get_accepted("entities", "source", model="m") == [{"name": "paid"}]
    # Generic writers cannot overwrite an accepted result.
    c.set("entities", "source", ["replacement"], model="m")
    assert c.accept("entities", "source", [{"name": "paid"}], model="m") == receipt
    with pytest.raises(ProcessingError, match="different"):
        c.accept("entities", "source", ["different"], model="m")
    with pytest.raises(ProcessingError, match="receipt"):
        c.release_accepted("entities", "source", "wrong", model="m")
    c.release_accepted("entities", "source", receipt, model="m")
    with pytest.raises(ProcessingError, match="missing"):
        c.get_accepted("entities", "source", model="m")
    c._backend.close()


def test_accepted_capacity_is_explicit_and_never_evicts_pending(tmp_path):
    c = cache(tmp_path / "cache.db", max_size=1)
    c.accept("entities", "one", [1])
    with pytest.raises(ProcessingError, match="capacity"):
        c.accept("entities", "two", [2])
    assert c.get_accepted("entities", "one") == [1]
    with pytest.raises(ProcessingError, match="byte"):
        c.accept("relations", "large", "x" * (1024 * 1024))
    c._backend.close()


def test_durable_accept_rejects_memory_disabled_and_serialization_failure(tmp_path):
    with pytest.raises(ProcessingError, match="persistent"):
        ExtractionCache().accept("entities", "source", [1])
    c = cache(tmp_path / "cache.db")
    c.enabled = False
    with pytest.raises(ProcessingError, match="disabled"):
        c.accept("entities", "source", [1])
    c.enabled = True
    with pytest.raises(ProcessingError, match="serializ"):
        c.accept("entities", "source", {object()})
    c._backend.close()


def test_accept_locked_write_is_explicit_and_rolls_back(tmp_path):
    path = tmp_path / "cache.db"
    c = cache(path, busy_timeout=0.01, max_retries=1)
    blocker = sqlite3.connect(path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ProcessingError, match="commit"):
            c.accept("entities", "source", [1])
    finally:
        blocker.rollback()
        blocker.close()
    assert c._backend._conn.in_transaction is False
    with pytest.raises(ProcessingError, match="missing"):
        c.get_accepted("entities", "source")
    c.accept("entities", "source", [1])
    c._backend.close()


def test_corrupt_accepted_value_is_not_a_miss_or_deleted(tmp_path):
    c = cache(tmp_path / "cache.db")
    c.accept("entities", "source", [1])
    c._backend._conn.execute("UPDATE cache SET value=?", (b"corrupt",))
    c._backend._conn.commit()
    with pytest.raises(ProcessingError, match="digest"):
        c.get_accepted("entities", "source")
    c.clear()
    assert c._backend.size("entities") == 1
    c._backend.close()


def test_old_schema_rejected_without_modifying_paid_rows(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE cache(namespace TEXT,key TEXT,value BLOB,expires_at REAL,last_access REAL,PRIMARY KEY(namespace,key))")
    db.execute("INSERT INTO cache VALUES('entities','k',?,NULL,0)", (b"paid",))
    db.commit()
    with pytest.raises(ProcessingError, match="offline"):
        SqliteCacheBackend(str(path))
    assert db.execute("SELECT value FROM cache").fetchone() == (b"paid",)
    db.close()


@pytest.mark.skipif(importlib.util.find_spec("pyoxigraph") is None, reason="native Oxigraph extra missing")
@pytest.mark.parametrize("adopt_before_exit", [False, True])
def test_restart_before_or_after_native_adoption_does_not_repay(tmp_path, adopt_before_exit):
    code = '''
import os, sys
from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
from pyoxigraph import Store
c = ExtractionCache(backend=SqliteCacheBackend(sys.argv[1]))
# A model fixture returns once; only its accepted minimal extraction is cached.
print('model_calls=1', flush=True)
c.accept('entities', 'source', [{'name':'paid'}])
if sys.argv[3] == 'True':
    store = Store(sys.argv[2])
    store.update('INSERT DATA { <urn:e1> <urn:name> "paid" }')
    store.flush()
# Crash before adoption, or after native commit but before cache release.
os._exit(73)
'''
    path, native = tmp_path / "cache.db", tmp_path / "native"
    writer = subprocess.run([sys.executable, "-c", code, str(path), str(native), str(adopt_before_exit)],
                            capture_output=True, text=True, timeout=20)
    assert writer.returncode == 73, writer.stderr
    assert writer.stdout.strip() == "model_calls=1"
    reader = subprocess.run([sys.executable, "-c", '''
import sys
from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
from pyoxigraph import Store
c = ExtractionCache(backend=SqliteCacheBackend(sys.argv[1]))
value = c.get_accepted('entities', 'source')
assert value == [{'name':'paid'}]
store = Store(sys.argv[2])
present = bool(store.query('ASK { <urn:e1> <urn:name> "paid" }'))
if not present:
    store.update('INSERT DATA { <urn:e1> <urn:name> "paid" }')
    store.flush()
assert bool(store.query('ASK { <urn:e1> <urn:name> "paid" }'))
receipt = c.accept('entities', 'source', value)
c.release_accepted('entities', 'source', receipt)
assert c._backend.size('entities') == 0
assert len(list(store.quads_for_pattern(None,None,None,None))) == 1
print('model_calls=0')
''', str(path), str(native)], capture_output=True, text=True, timeout=20)
    assert reader.returncode == 0, reader.stderr
    assert reader.stdout.strip() == "model_calls=0"


def test_release_failure_preserves_result_and_read_failure_is_explicit(tmp_path):
    path = tmp_path / "cache.db"
    c = cache(path, busy_timeout=0.01, max_retries=1)
    receipt = c.accept("entities", "source", [1])
    blocker = sqlite3.connect(path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ProcessingError, match="commit"):
            c.release_accepted("entities", "source", receipt)
    finally:
        blocker.rollback()
        blocker.close()
    assert c.get_accepted("entities", "source") == [1]
    c._backend.close()
    with pytest.raises(ProcessingError, match="read failed"):
        c.get_accepted("entities", "source")


def test_protected_read_never_uses_ordinary_cache_miss_contract(tmp_path):
    c = cache(tmp_path / "cache.db")
    c.accept("entities", "source", [1])
    with pytest.raises(ProcessingError, match="get_accepted"):
        c.get("entities", "source")
    c._backend._conn.execute("UPDATE cache SET value=zeroblob(2097152)")
    c._backend._conn.commit()
    with pytest.raises(ProcessingError, match="stored byte"):
        c.get_accepted("entities", "source")
    assert c._backend.size("entities") == 1
    c._backend.close()


@pytest.mark.parametrize("value", ["x" * (4 * 1024 * 1024), [0] * 100000])
def test_accept_preflight_rejects_large_inputs_before_full_copy(tmp_path, value):
    c = cache(tmp_path / "cache.db")
    tracemalloc.start()
    try:
        with pytest.raises(ProcessingError, match="budget"):
            c.accept("entities", "source", value)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        c._backend.close()
    assert peak < 256 * 1024


def test_accept_cancellation_and_python_owner_lock_are_bounded(tmp_path):
    c = cache(tmp_path / "cache.db", busy_timeout=5)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ProcessingError, match="cancelled"):
        c.accept("entities", "cancel", [1], cancel_event=cancelled)
    with pytest.raises(ProcessingError, match="cancelled"):
        c.get_accepted("entities", "cancel", cancel_event=cancelled)
    c._backend._lock.acquire()
    try:
        start = time.monotonic()
        with pytest.raises(ProcessingError, match="deadline"):
            c.accept("entities", "locked", [1])
        assert time.monotonic() - start < 1
    finally:
        c._backend._lock.release()
    c._backend._read_lock.acquire()
    try:
        start = time.monotonic()
        with pytest.raises(ProcessingError, match="deadline"):
            c.get_accepted("entities", "locked")
        assert time.monotonic() - start < 1
    finally:
        c._backend._read_lock.release()
    blocker = sqlite3.connect(c._backend.db_path)
    blocker.execute("BEGIN IMMEDIATE")
    threading.Timer(0.02, cancelled.set).start()
    cancelled.clear()
    start = time.monotonic()
    try:
        with pytest.raises(ProcessingError, match="commit"):
            c.accept("entities", "db-locked", [1], cancel_event=cancelled)
        assert time.monotonic() - start < 1
    finally:
        blocker.rollback()
        blocker.close()
    assert c._backend.size("entities") == 0
    c._backend.close()
    with pytest.raises(ProcessingError, match="commit"):
        c.accept("entities", "closed", [1])


def test_native_dataclass_accepted_and_custom_codec_rejected(tmp_path):
    from semantica.semantic_extract.types import Entity
    c = cache(tmp_path / "cache.db")
    value = [Entity(text="Acme", label="ORG", start_char=0, end_char=4)]
    c.accept("entities", "source", value)
    assert c.get_accepted("entities", "source") == value
    c._backend.close()
    backend = SqliteCacheBackend(str(tmp_path / "custom.db"), serializer=lambda value: b"{}")
    with pytest.raises(ProcessingError, match="native JSON codec"):
        ExtractionCache(backend=backend).accept("entities", "source", [1])
    backend.close()


def test_sixteen_restored_identities_do_not_queue_behind_writer_commit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    owner = SqliteCacheBackend(str(tmp_path / 'cache.db'))
    digest = owner.accept('entities', 'seed', [1])
    owner.release_accepted('entities', 'seed', digest)
    entered, release = threading.Event(), threading.Event()

    class CommitGate:
        def __init__(self, conn): self.conn = conn
        def __getattr__(self, name): return getattr(self.conn, name)
        def commit(self):
            entered.set()
            assert release.wait(3)
            return self.conn.commit()

    owner._conn = CommitGate(owner._conn)
    try:
        with ThreadPoolExecutor(max_workers=17) as pool:
            writer = pool.submit(owner.accept, 'entities', 'new', [2])
            assert entered.wait(2)
            readers = [pool.submit(owner.accepted_digest, 'entities', 'seed') for _ in range(16)]
            try:
                assert [future.result(timeout=1) for future in readers] == [digest] * 16
            finally:
                release.set()
            writer.result(timeout=2)
    finally:
        release.set()
        owner.close()


def test_paid_decode_does_not_hold_identity_reader_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    owner = SqliteCacheBackend(str(tmp_path / 'cache.db'))
    digest = owner.accept('entities', 'seed', [1])
    entered, release = threading.Event(), threading.Event()
    deserialize = owner._deserialize
    def gated_decode(blob):
        entered.set()
        assert release.wait(3)
        return deserialize(blob)
    owner._deserialize = gated_decode
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            body = pool.submit(owner.get_accepted, 'entities', 'seed')
            assert entered.wait(2)
            identity = pool.submit(owner.accepted_digest, 'entities', 'seed')
            try:
                assert identity.result(timeout=1) == digest
            finally:
                release.set()
            assert body.result(timeout=2) == [1]
    finally:
        release.set()
        owner.close()


def test_pending_capacity_accounting_skips_generic_bodies_and_retired_receipts(tmp_path):
    owner = SqliteCacheBackend(str(tmp_path / 'cache.db'))
    try:
        owner._conn.executemany(
            'INSERT INTO cache VALUES(?,?,?,NULL,0,NULL)',
            [('entities', 'ordinary-' + str(i), b'x' * 8192) for i in range(2000)])
        owner._conn.executemany('INSERT INTO accepted_receipts VALUES(?,?,?)',
            [('entities', 'retired-' + str(i), 'digest') for i in range(10000)])
        owner._conn.commit()
        owner.accept('entities', 'pending', [1])
        steps = []
        owner._conn.set_progress_handler(lambda: steps.append(1) or 0, 1)
        assert owner._conn.execute('SELECT COUNT(*) FROM cache WHERE namespace=? AND accepted_digest IS NOT NULL', ('entities',)).fetchone() == (1,)
        assert owner._conn.execute('SELECT COALESCE(SUM(length(value)),0) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] > 0
        owner._conn.set_progress_handler(None, 0)
        assert len(steps) < 100
    finally:
        owner.close()
