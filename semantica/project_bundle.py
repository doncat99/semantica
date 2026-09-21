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


def build_bundle(*, python_root: Path, wheel: Path, models_root: Path, output: Path, uv: str) -> dict:
    """Inputs are release artifacts, never a Semantica source checkout or venv."""
    if output.exists():
        raise ValueError("bundle output must not already exist")
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise ValueError("an immutable Semantica wheel is required")
    if (python_root / "pyvenv.cfg").exists():
        raise ValueError("a relocatable CPython distribution is required, not a venv")
    python_name = "python.exe" if os.name == "nt" else "bin/python3"
    if not (python_root / python_name).is_file():
        raise ValueError("CPython distribution has no interpreter")
    model_names = ("RapidOcr", "docling-project--docling-layout-heron", "docling-project--docling-models")
    for name in model_names:
        if not (models_root / name).is_dir():
            raise ValueError(f"required offline Docling model is absent: {name}")
    shutil.copytree(python_root, output / "python", symlinks=False)
    python = output / "python" / python_name
    subprocess.run([uv, "pip", "install", "--python", str(python), "--system", f"{wheel.resolve()}[project-worker]"], check=True)
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
    for item in sorted(output.rglob("*")):
        if item.is_file():
            manifest["files"].append({"path": item.relative_to(output).as_posix(), "size": item.stat().st_size, "sha256": digest_file(item)})
    descriptor = [manifest["protocol"], schema_digest, manifest["pythonPath"],
                  [manifest["worker"]["path"], manifest["worker"]["args"]],
                  [manifest["queryWorker"]["path"], manifest["queryWorker"]["args"]],
                  sorted([key, value] for key, value in manifest["mediaTypes"].items()),
                  [[item["path"], item["size"], item["sha256"]] for item in manifest["files"]]]
    manifest["artifactDigest"] = "sha256:" + hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--models-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    manifest = build_bundle(**vars(args))
    print(json.dumps({"artifactDigest": manifest["artifactDigest"], "files": len(manifest["files"])}))


if __name__ == "__main__":
    main()
