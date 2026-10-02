import hashlib
import importlib.util
import io
from pathlib import Path
import urllib.error


SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "project_worker_native.py"
SPEC = importlib.util.spec_from_file_location("project_worker_native", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_download_retries_without_leaving_partial_file(tmp_path, monkeypatch):
    content = b"immutable input"
    destination = tmp_path / "input.tar.gz"
    attempts = 0

    def open_url(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise urllib.error.URLError("temporary failure")
        return io.BytesIO(content)

    monkeypatch.setattr(MODULE.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    MODULE.download("https://example.invalid/input", destination, hashlib.sha256(content).hexdigest())

    assert attempts == 3
    assert destination.read_bytes() == content
    assert not destination.with_name("input.tar.gz.partial").exists()


def test_core_prepare_does_not_fetch_office_inputs(tmp_path, monkeypatch):
    downloads = []

    class Archive:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def extractall(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(MODULE, "download", lambda url, *_args: downloads.append(url))
    monkeypatch.setattr(MODULE.tarfile, "open", lambda *_args: Archive())

    MODULE.prepare("linux-x64", tmp_path)

    assert len(downloads) == 1
    assert "python-build-standalone" in downloads[0]
