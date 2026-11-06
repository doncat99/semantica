"""The native CLI cannot start server work before its host records the child."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("admission,started", [
    (b"", False),
    (b"invalid\n", False),
    (b"SEMANTICA_NATIVE_EXPLORER_ADMIT\n", True),
])
def test_native_cli_process_requires_stdin_admission(tmp_path, admission, started):
    marker = tmp_path / "server-imported"
    # A real child runs the actual CLI. Mark the first server import without
    # constructing a graph, binding a socket or changing production handles.
    script = '''
import builtins
import pathlib
import sys
from semantica.explorer import main
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "uvicorn":
        pathlib.Path(sys.argv[1]).write_text("started")
        raise SystemExit(0)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
print("waiting", flush=True)
main(["--native-endpoint", "http://127.0.0.1:1/scene", "--no-browser"])
'''
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen([sys.executable, "-B", "-c", script, str(marker)],
        cwd=Path(__file__).resolve().parents[2], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert child.stdout.readline() == b"waiting\n"
        assert child.poll() is None
        assert not marker.exists()
        _, stderr = child.communicate(admission, timeout=10)
        assert child.returncode == (0 if started else 2), stderr.decode()
        assert marker.exists() == started
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_native_cli_host_crash_before_admission_exits_without_server_work(tmp_path):
    marker = tmp_path / "server-imported"
    child_script = '''
import builtins, pathlib, sys
from semantica.explorer import main
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "uvicorn":
        pathlib.Path(sys.argv[1]).write_text("started")
        raise SystemExit(0)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
print("waiting", flush=True)
main(["--native-endpoint", "http://127.0.0.1:1/scene", "--no-browser"])
'''
    host_script = '''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-B", "-c", sys.argv[1], sys.argv[2]], stdin=subprocess.PIPE)
print("pid=" + str(child.pid), flush=True)
time.sleep(30)
'''
    host = subprocess.Popen([sys.executable, "-B", "-c", host_script, child_script, str(marker)],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child_pid = None
    try:
        lines = [host.stdout.readline(), host.stdout.readline()]
        assert b"waiting\n" in lines
        child_pid = int(next(line for line in lines if line.startswith(b"pid=")).split(b"=")[1])
        assert not marker.exists()
        host.kill()
        # Child inherits these pipes; EOF proves it exited after losing host stdin.
        _, stderr = host.communicate(timeout=10)
        assert b"requires host stdin admission" in stderr
        assert not marker.exists()
    finally:
        if host.poll() is None:
            host.kill()
            host.wait(timeout=10)
        if child_pid:
            try:
                os.kill(child_pid, 9)
            except ProcessLookupError:
                pass
