from pathlib import Path

import pytest

from semantica.bundle import (
    document_parser_digest,
    digest_file,
    remove_generated_bytecode,
    verify_bundle_inventory,
)


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
