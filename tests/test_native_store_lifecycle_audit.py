"""G1 native exclusive ownership/crash probe; no production service or schema."""
import os
from pathlib import Path
import subprocess
import sys
import time
import tracemalloc

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_proposed_literal_admission_rejects_before_native_allocation():
    """G1 recipe probe, not production schema admission (that belongs to G4)."""
    # Required long content remains in the unique document carrier and is read
    # by address/range; it must not become a large RDF literal to begin with.
    def admit(value, cap=64 * 1024):
        # UTF-8 takes at least one byte per codepoint. Check length first,
        # then encode only a value whose allocation has a proven finite bound.
        if len(value) > cap or len(value.encode("utf-8")) > cap:
            raise ValueError("NATIVE_FIELD_BUDGET_EXCEEDED")
        return value

    giant = "🙂" * (2 * 1024 * 1024)
    tracemalloc.start()
    try:
        with pytest.raises(ValueError, match="NATIVE_FIELD_BUDGET_EXCEEDED"):
            admit(giant)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64 * 1024
    assert admit("🙂" * (16 * 1024)) == "🙂" * (16 * 1024)
    with pytest.raises(ValueError, match="NATIVE_FIELD_BUDGET_EXCEEDED"):
        admit("🙂" * (16 * 1024 + 1))
    print(f"literal-admission-extra-python-peak={peak}")


def test_native_expensive_read_has_enforceable_process_deadline(tmp_path):
    code = """
import sys
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=sys.argv[1])
store.execute_update('INSERT DATA {' + ' '.join(
    f'<urn:s:{i}> <urn:p> {i} .' for i in range(1000)) + '}')
print('ready', flush=True)
store.execute_sparql('SELECT (COUNT(*) AS ?n) WHERE { ?a <urn:p> ?x . ?b <urn:p> ?y . ?c <urn:p> ?z . FILTER(STRLEN(SHA256(CONCAT(STR(?x),STR(?y),STR(?z)))) > 0) }', max_rows=1, max_bytes=1024)
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "rdf")],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(subprocess.TimeoutExpired):
            child.communicate(timeout=0.2)
        # Deadline/cancel is an explicit error, never a partial successful page.
        started = time.perf_counter()
        child.terminate()
        try:
            child.communicate(timeout=0.25)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=0.5)
        stopped_ms = (time.perf_counter() - started) * 1000
        assert child.returncode != 0
        assert stopped_ms < 1000
        print(f"native-deadline-stop-ms={stopped_ms:.3f}")
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
    reopened = subprocess.run([sys.executable, "-c", """
import sys
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=sys.argv[1])
assert store.execute_sparql('ASK { <urn:s:999> <urn:p> 999 }')['metadata']['boolean']
""", str(tmp_path / "rdf")], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True,
        text=True, timeout=20)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr


def test_native_store_excludes_second_writer_and_reopens_after_crash(tmp_path):
    code = """
import sys
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=sys.argv[1])
store.execute_update('INSERT DATA { GRAPH <urn:project:p> { <urn:fact:1> <urn:predicate> "committed" } }')
print('durable', flush=True)
sys.stdin.read()
"""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    owner = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "rdf")],
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "durable"
        contender = subprocess.run([sys.executable, "-c", """
import sys
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError
try:
    OxigraphStore(path=sys.argv[1])
except ProcessingError as error:
    assert 'lock' in str(error).lower(), str(error)
else:
    raise AssertionError('second writer unexpectedly admitted')
""", str(tmp_path / "rdf")], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=20)
        assert contender.returncode == 0, contender.stdout + contender.stderr
        owner.kill()
        owner.communicate(timeout=5)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate(timeout=5)
    reopened = subprocess.run([sys.executable, "-c", """
import sys
from semantica.triplet_store.oxigraph_store import OxigraphStore
store = OxigraphStore(path=sys.argv[1])
result = store.execute_sparql('SELECT ?value WHERE { GRAPH <urn:project:p> { <urn:fact:1> <urn:predicate> ?value } }', max_rows=1, max_bytes=1024)
assert result['bindings'] == [{'value': {'type': 'literal', 'value': 'committed'}}], result
""", str(tmp_path / "rdf")], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=20)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
