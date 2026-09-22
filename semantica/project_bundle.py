"""Assemble an immutable project-worker bundle from independently built inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def remove_generated_bytecode(root: Path) -> None:
    for path in root.rglob("*.pyc"):
        if "__pycache__" in path.relative_to(root).parts:
            path.unlink()


def verify_bundle_inventory(root: Path, manifest: dict, *, remove_untracked_bytecode: bool = False) -> None:
    """Verify that the bundle contains exactly the immutable manifest files."""
    expected = {item["path"]: item for item in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise ValueError("bundle manifest contains duplicate file paths")

    def inventory() -> dict[str, Path]:
        files = {}
        for item in root.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"bundle contains a symlink: {item.relative_to(root).as_posix()}")
            if item.is_file() and item != root / "manifest.json":
                files[item.relative_to(root).as_posix()] = item
        return files

    actual = inventory()
    if remove_untracked_bytecode:
        remove_generated_bytecode(root)
        actual = inventory()

    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    if missing or extra:
        raise ValueError(f"bundle inventory differs from manifest: missing={missing[:10]}, extra={extra[:10]}")
    for relative, item in expected.items():
        path = actual[relative]
        if path.stat().st_size != item["size"] or digest_file(path) != item["sha256"]:
            raise ValueError(f"bundle file differs from manifest: {relative}")


def build_bundle(*, python_root: Path, wheel: Path, models_root: Path, office_root: Path, office_receipt: Path, output: Path, uv: str, source_revision: str) -> dict:
    """Inputs are release artifacts, never a Semantica source checkout or venv."""
    if output.exists():
        raise ValueError("bundle output must not already exist")
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise ValueError("an immutable Semantica wheel is required")
    if len(source_revision) != 40 or any(char not in "0123456789abcdef" for char in source_revision):
        raise ValueError("source revision must be a complete Git commit")
    if (python_root / "pyvenv.cfg").exists():
        raise ValueError("a relocatable CPython distribution is required, not a venv")
    python_name = "python.exe" if os.name == "nt" else "bin/python3"
    if not (python_root / python_name).is_file():
        raise ValueError("CPython distribution has no interpreter")
    office_release = json.loads(office_receipt.read_text(encoding="utf-8"))
    if not (office_root / office_release["executable"]).is_file():
        raise ValueError("the dedicated Office adapter requires its immutable executable")
    model_names = ("RapidOcr", "docling-project--docling-layout-heron", "docling-project--docling-models")
    for name in model_names:
        if not (models_root / name).is_dir():
            raise ValueError(f"required offline Docling model is absent: {name}")
    shutil.copytree(python_root, output / "python", symlinks=False)
    shutil.copytree(office_root, output / "office", symlinks=False)
    shutil.copy2(office_receipt, output / "office-release.json")
    python = output / "python" / python_name
    # This interpreter is our private copy, not the managed source distribution.
    subprocess.run([uv, "pip", "install", "--python", str(python), "--system", "--break-system-packages", f"{wheel.resolve()}[project-worker]"], check=True)
    packages = subprocess.run([str(python), "-I", "-B", "-c",
        "import importlib.metadata as m, json; print(json.dumps(sorted((d.metadata['Name'], d.version) for d in m.distributions())))"],
        capture_output=True, text=True, check=True)
    (output / "release.json").write_text(json.dumps({
        "sourceRevision": source_revision, "wheel": wheel.name, "wheelDigest": digest_file(wheel),
        "packages": json.loads(packages.stdout),
    }, indent=2) + "\n", encoding="utf-8")
    for name in model_names:
        shutil.copytree(models_root / name, output / "models" / name, symlinks=False,
                        ignore=shutil.ignore_patterns(".cache", ".git"))
    # CPython -I removes ambient Python paths; -B keeps the immutable tree clean.
    probe = subprocess.run([str(python), "-I", "-B", "-c",
        "import json; from semantica.project_snapshot_schema import project_snapshot_json_schema; print(json.dumps(project_snapshot_json_schema(), sort_keys=True, separators=(',', ':')))"],
        capture_output=True, text=True, check=True)
    schema_digest = "sha256:" + hashlib.sha256(probe.stdout.strip().encode()).hexdigest()
    manifest = {
        "protocol": "ontoscience.semantica-bundle.v1",
        "pythonPath": f"python/{python_name}",
        "schemaDigest": schema_digest,
        "worker": {"path": f"python/{python_name}", "args": ["-I", "-B", "-m", "semantica.project_snapshot_worker"]},
        "queryWorker": {"path": f"python/{python_name}", "args": ["-I", "-B", "-m", "semantica.project_query_worker"]},
        "mediaTypes": {
            "document-representation": "application/vnd.semantica.document-representation+json",
            "retrieval-index": "application/vnd.semantica.retrieval+json",
            "snapshot": "application/vnd.semantica.project-snapshot+json",
        },
        "files": [],
    }
    # Installed console scripts are not worker entrypoints. Dereference any
    # package symlinks so the complete runtime is contained in this artifact.
    for item in output.rglob("*"):
        if item.is_symlink():
            target = item.resolve(strict=True)
            item.unlink()
            if target.is_dir():
                shutil.copytree(target, item, symlinks=False)
            else:
                shutil.copy2(target, item)
    remove_generated_bytecode(output)
    for item in sorted(output.rglob("*"), key=lambda path: path.relative_to(output).as_posix()):
        if item.is_file():
            manifest["files"].append({"path": item.relative_to(output).as_posix(), "size": item.stat().st_size, "sha256": digest_file(item)})
    descriptor = [manifest["protocol"], schema_digest, manifest["pythonPath"],
                  [manifest["worker"]["path"], manifest["worker"]["args"]],
                  [manifest["queryWorker"]["path"], manifest["queryWorker"]["args"]],
                  sorted([key, value] for key, value in manifest["mediaTypes"].items()),
                  [[item["path"], item["size"], item["sha256"]] for item in manifest["files"]]]
    manifest["artifactDigest"] = "sha256:" + hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify_bundle_inventory(output, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--models-root", required=True, type=Path)
    parser.add_argument("--office-root", required=True, type=Path)
    parser.add_argument("--office-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    manifest = build_bundle(**vars(args))
    print(json.dumps({"artifactDigest": manifest["artifactDigest"], "files": len(manifest["files"])}))


if __name__ == "__main__":
    main()
