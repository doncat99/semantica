from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from semantica.bundle import (
    document_parser_digest,
    digest_file,
    remove_generated_bytecode,
    verify_bundle_inventory,
    acceleration_inventory,
)


def test_acceleration_inventory_does_not_confuse_build_with_available_hardware(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        __version__="test-cuda-build", version=SimpleNamespace(cuda="13.0"),
        cuda=SimpleNamespace(is_available=lambda: False, device_count=lambda: 0),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    ))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        __version__="test-ort", get_available_providers=lambda: ["CPUExecutionProvider"],
    ))
    evidence = acceleration_inventory()
    assert evidence["torch"]["cudaBuild"] == "13.0"
    assert evidence["torch"]["cudaAvailable"] is False
    assert evidence["onnxruntime"]["availableProviders"] == ["CPUExecutionProvider"]
    assert "gpuValidated" not in evidence


def manifest_for(path: Path) -> dict:
    return {"files": [{"path": path.name, "size": path.stat().st_size, "sha256": digest_file(path)}]}


def test_bundle_inventory_excludes_install_and_runtime_bytecode(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    bytecode = tmp_path / "python/lib/__pycache__/generated.cpython-312.pyc"
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b"installed")

    remove_generated_bytecode(tmp_path)
    manifest = manifest_for(tracked)
    bytecode.write_bytes(b"generated at runtime")
    verify_bundle_inventory(tmp_path, manifest, remove_untracked_bytecode=True)

    assert not bytecode.exists()


def test_post_acceptance_inventory_rejects_other_untracked_files(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    (tmp_path / "unexpected.cache").write_bytes(b"generated")

    with pytest.raises(ValueError, match="extra=.*unexpected.cache"):
        verify_bundle_inventory(tmp_path, manifest_for(tracked), remove_untracked_bytecode=True)


def test_post_acceptance_inventory_rejects_changed_manifest_file(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    manifest = manifest_for(tracked)
    tracked.write_bytes(b"changed")

    with pytest.raises(ValueError, match="runtime.bin"):
        verify_bundle_inventory(tmp_path, manifest, remove_untracked_bytecode=True)


def test_document_parser_digest_ignores_extraction_code_but_tracks_parser_inputs():
    files = [
        {"path": "models/layout/model.bin", "size": 1, "sha256": "sha256:" + "1" * 64},
        {"path": "python/lib/site-packages/docling/core.py", "size": 2, "sha256": "sha256:" + "2" * 64},
        {"path": "python/lib/site-packages/semantica/source.py", "size": 3, "sha256": "sha256:" + "3" * 64},
        {"path": "python/lib/site-packages/semantica/semantic_artifact_builder.py", "size": 4, "sha256": "sha256:" + "4" * 64},
    ]
    original = document_parser_digest(files)
    extraction_only = [*files[:3], {**files[3], "sha256": "sha256:" + "5" * 64}]
    parser_change = [files[0], files[1], {**files[2], "sha256": "sha256:" + "6" * 64}, files[3]]

    assert document_parser_digest(extraction_only) == original
    assert document_parser_digest(parser_change) != original


def test_parser_digest_excludes_protocol_and_nonparser_dependencies():
    def item(name, digest):
        return {"path": "python/lib/site-packages/" + name, "size": 1, "sha256": digest}
    files = [item("semantica/source.py", "source"), item("docling/core.py", "parser"),
             item("semantica/semantic_worker.py", "protocol"), item("semantica/project_checkpoint.py", "checkpoint"),
             item("openai/client.py", "llm")]
    closure = {files[1]["path"]}
    before = document_parser_digest(files, closure)
    changed = [dict(value) for value in files]
    for value in changed[2:]:
        value["sha256"] = "changed"
    assert document_parser_digest(changed, closure) == before
    changed[1]["sha256"] = "parser-changed"
    assert document_parser_digest(changed, closure) != before
