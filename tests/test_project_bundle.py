from pathlib import Path

import pytest

from semantica.project_bundle import digest_file, remove_generated_bytecode, verify_bundle_inventory


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
