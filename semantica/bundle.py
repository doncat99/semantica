"""Assemble an immutable semantic worker bundle from independently built inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess


def acceleration_inventory() -> dict:
    """Report installed capabilities, never claim that a provider executed work."""
    import onnxruntime
    import torch

    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "torch": {
            "version": torch.__version__,
            "cudaBuild": torch.version.cuda,
            "cudaAvailable": torch.cuda.is_available(),
            "cudaDeviceCount": torch.cuda.device_count(),
            "mpsAvailable": torch.backends.mps.is_available(),
        },
        "onnxruntime": {
            "version": onnxruntime.__version__,
            "availableProviders": onnxruntime.get_available_providers(),
        },
    }


def validate_acceleration_profile(profile: str, inventory: dict, packages: list) -> None:
    """Check artifact capabilities, never label a CPU build host as GPU acceptance."""
    ort_distributions = {name.lower().replace("_", "-") for name, _ in packages} & {
        "onnxruntime", "onnxruntime-gpu", "onnxruntime-directml",
    }
    expected = {"cpu": "onnxruntime", "cuda": "onnxruntime-gpu", "directml": "onnxruntime-directml"}
    if profile not in expected:
        raise ValueError(f"unknown acceleration profile: {profile}")
    if ort_distributions != {expected[profile]}:
        raise ValueError(f"{profile} requires exactly {expected[profile]}, found {sorted(ort_distributions)}")
    providers = inventory["onnxruntime"]["availableProviders"]
    if profile == "cuda" and (
        not inventory["torch"]["cudaBuild"] or "CUDAExecutionProvider" not in providers
    ):
        raise ValueError("CUDA artifact requires CUDA Torch and CUDAExecutionProvider")
    if profile == "directml" and (
        inventory["platform"] != "Windows" or "DmlExecutionProvider" not in providers
    ):
        raise ValueError("DirectML artifact requires Windows and DmlExecutionProvider")


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


_PARSER_MODULES = {
    "project_document_quality.py",
    "project_office.py",
    "project_remote_docling.py",
    "source.py",
    "utils/exceptions.py",
    "utils/helpers.py",
    "utils/logging.py",
    "utils/progress_tracker.py",
}


def document_parser_digest(files: list[dict], dependency_files: set[str] | None = None,
                           console_script_files: set[str] | None = None) -> str:
    """Hash parser execution inputs, separately from the complete artifact inventory."""
    selected = []
    for item in files:
        path = item["path"]
        if console_script_files and path in console_script_files:
            continue
        # These installer records describe location/time, not import semantics.
        # METADATA, entry_points.txt and all actual dependency bytes remain inputs.
        if ".dist-info/" in path and path.rsplit(".dist-info/", 1)[1] in {
            "RECORD", "direct_url.json", "uv_cache.json",
        }:
            continue
        marker = "/site-packages/semantica/"
        if path == "release.json" or ("/site-packages/semantica-" in path and ".dist-info/" in path):
            continue
        if marker in path:
            relative = path.split(marker, 1)[1]
            if relative not in _PARSER_MODULES and not relative.startswith("parse/"):
                continue
        elif "/site-packages/" in path and dependency_files is not None and path not in dependency_files:
            continue
        selected.append([path, item["size"], item["sha256"]])
    if not selected:
        raise ValueError("bundle has no document parser inputs")
    payload = json.dumps(sorted(selected), ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def parser_dependency_files(root: Path) -> set[str]:
    """Installed parser dependency closure, including native libraries and metadata."""
    from importlib import metadata
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    installed = {canonicalize_name(d.metadata["Name"]): d for d in metadata.distributions()}
    pending = ["docling", "rapidocr", "blake3", "pandas"]
    # RapidOCR does not require an ORT distribution: the selected worker extra owns it.
    pending.extend(name for name in ("onnxruntime", "onnxruntime-gpu", "onnxruntime-directml") if name in installed)
    seen, files = set(), set()
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        distribution = installed.get(name)
        if distribution is None:
            raise ValueError(f"parser dependency is absent: {name}")
        for file in distribution.files or []:
            absolute = Path(distribution.locate_file(file)).resolve()
            if absolute.is_relative_to(root):
                files.add(absolute.relative_to(root).as_posix())
        # Keep installed optional dependencies as a conservative closure.
        for raw in distribution.requires or []:
            dependency = canonicalize_name(Requirement(raw).name)
            if dependency in installed:
                pending.append(dependency)
    return files


def parser_console_script_files(root: Path) -> set[str]:
    """Generated CLI wrappers unused by the isolated worker's library calls.

    Identify wrappers through installed entry-point metadata, never by dropping
    all bin files: Python interpreters and native tools are execution inputs.
    """
    from importlib import metadata
    protected = {"python", "python3", "pythonw", "ffprobe"}
    scripts = set()
    for distribution in metadata.distributions():
        # Wheels can declare script-files without entry_points (e.g. dill's
        # profiling CLI). Identify installed Python scripts from their RECORD
        # path and Python launcher; do not exclude arbitrary native bin tools.
        for file in distribution.files or []:
            candidate = Path(distribution.locate_file(file)).resolve()
            if candidate.parent not in {root / "python/bin", root / "python/Scripts"}:
                continue
            if candidate.name in protected or candidate.name.startswith("python") or not candidate.is_file():
                continue
            with candidate.open("rb") as stream:
                header = stream.read(512)
            first_line = header.split(b"\n", 1)[0]
            if ((first_line.startswith(b"#!") and b"python" in first_line)
                    or (header.startswith(b"#!/bin/sh\n'''exec' ")
                        and b"python" in header.split(b"\n", 2)[1])):
                scripts.add(candidate.relative_to(root).as_posix())
        for entry in distribution.entry_points:
            if entry.group not in {"console_scripts", "gui_scripts"}:
                continue
            name = entry.name
            if Path(name).name != name or name in protected or name.startswith("python"):
                continue
            candidates = [root / "python/bin" / name,
                          *(root / "python/Scripts" / (name + suffix)
                            for suffix in (".exe", "-script.py", "-script.pyw"))]
            for candidate in candidates:
                if candidate.is_file() and not candidate.is_symlink():
                    scripts.add(candidate.relative_to(root).as_posix())
    return scripts


def remove_generated_bytecode(root: Path) -> None:
    for path in root.rglob("*.pyc"):
        if "__pycache__" in path.relative_to(root).parts:
            path.unlink()


def prune_worker_models(root: Path) -> None:
    """Keep ACCURATE tables and one canonical copy of identical OCR weights."""
    models = root / "models"
    tableformer = models / "docling-project--docling-models/model_artifacts/tableformer"
    ocr_names = (
        "PP-OCRv6_det_small.onnx",
        "PP-OCRv6_rec_small.onnx",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    )
    required = [tableformer / "accurate" / name for name in (
        "tableformer_accurate.safetensors", "tm_config.json",
    )] + [models / "RapidOcr" / name for name in ocr_names]
    for path in required:
        if not path.is_file():
            raise ValueError(f"required offline model is absent: {path.relative_to(root)}")
    fast = tableformer / "fast"
    if fast.exists():
        shutil.rmtree(fast)
    for pattern in ("lib/python*/site-packages/rapidocr/models", "Lib/site-packages/rapidocr/models"):
        for directory in (root / "python").glob(pattern):
            for name in ocr_names:
                duplicate = directory / name
                if duplicate.is_file() and digest_file(duplicate) == digest_file(models / "RapidOcr" / name):
                    duplicate.unlink()


def verify_bundle_inventory(root: Path, manifest: dict) -> None:
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
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    if missing or extra:
        raise ValueError(f"bundle inventory differs from manifest: missing={missing[:10]}, extra={extra[:10]}")
    for relative, item in expected.items():
        path = actual[relative]
        if path.stat().st_size != item["size"] or digest_file(path) != item["sha256"]:
            raise ValueError(f"bundle file differs from manifest: {relative}")


def build_office_bundle(*, office_root: Path, office_receipt: Path, output: Path, target: str) -> dict:
    if output.exists():
        raise ValueError("Office bundle output must not already exist")
    release = json.loads(office_receipt.read_text(encoding="utf-8"))
    executable = release.get("executable")
    if not isinstance(executable, str) or not (office_root / executable).is_file():
        raise ValueError("Office receipt does not identify an immutable executable")
    shutil.copytree(office_root, output / "office", symlinks=False)
    shutil.copy2(office_receipt, output / "office-release.json")
    files = []
    for item in sorted(output.rglob("*"), key=lambda path: path.relative_to(output).as_posix()):
        if item.is_symlink():
            target_path = item.resolve(strict=True)
            item.unlink()
            shutil.copytree(target_path, item, symlinks=False) if target_path.is_dir() else shutil.copy2(target_path, item)
        if item.is_file():
            files.append({"path": item.relative_to(output).as_posix(), "size": item.stat().st_size, "sha256": digest_file(item)})
    manifest = {
        "protocol": "ontoscience.semantica-office-bundle.v1",
        "target": target,
        "version": release["version"],
        "executable": executable,
        "files": files,
    }
    descriptor = [manifest["protocol"], target, manifest["version"], executable,
                  [[item["path"], item["size"], item["sha256"]] for item in files]]
    manifest["artifactDigest"] = "sha256:" + hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify_bundle_inventory(output, manifest)
    return manifest


def build_bundle(*, python_root: Path, wheel: Path, models_root: Path, output: Path, uv: str, source_revision: str, acceleration: str = "cpu", office_root: Path | None = None, office_receipt: Path | None = None) -> dict:
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
    if (office_root is None) != (office_receipt is None):
        raise ValueError("office_root and office_receipt must be provided together")
    if office_root is not None and office_receipt is not None:
        office_release = json.loads(office_receipt.read_text(encoding="utf-8"))
        if not (office_root / office_release["executable"]).is_file():
            raise ValueError("the dedicated Office adapter requires its immutable executable")
    model_names = ("RapidOcr", "docling-project--docling-layout-heron", "docling-project--docling-models")
    for name in model_names:
        if not (models_root / name).is_dir():
            raise ValueError(f"required offline Docling model is absent: {name}")
    shutil.copytree(python_root, output / "python", symlinks=False)
    if office_root is not None and office_receipt is not None:
        shutil.copytree(office_root, output / "office", symlinks=False)
        shutil.copy2(office_receipt, output / "office-release.json")
    python = output / "python" / python_name
    # This interpreter is our private copy, not the managed source distribution.
    extra = {"cpu": "semantic-worker", "cuda": "semantic-worker-cuda", "directml": "semantic-worker-directml"}[acceleration]
    subprocess.run([uv, "pip", "install", "--python", str(python), "--system", "--break-system-packages", f"{wheel.resolve()}[{extra}]"], check=True)
    packages = subprocess.run([str(python), "-I", "-B", "-c",
        "import importlib.metadata as m, json; print(json.dumps(sorted((d.metadata['Name'], d.version) for d in m.distributions())))"],
        capture_output=True, text=True, check=True)
    capabilities = subprocess.run([str(python), "-I", "-B", "-c",
        "import json; from semantica.bundle import acceleration_inventory; print(json.dumps(acceleration_inventory()))"],
        capture_output=True, text=True, check=True)
    inventory = json.loads(capabilities.stdout)
    validate_acceleration_profile(acceleration, inventory, json.loads(packages.stdout))
    (output / "release.json").write_text(json.dumps({
        "sourceRevision": source_revision, "wheel": wheel.name, "wheelDigest": digest_file(wheel),
        "packages": json.loads(packages.stdout),
        "accelerationProfile": acceleration,
        "accelerationCapabilities": inventory,
    }, indent=2) + "\n", encoding="utf-8")
    for name in model_names:
        shutil.copytree(models_root / name, output / "models" / name, symlinks=False,
                        ignore=shutil.ignore_patterns(".cache", ".git"))
    prune_worker_models(output)
    # CPython -I removes ambient Python paths; -B keeps the immutable tree clean.
    probe = subprocess.run([str(python), "-I", "-B", "-c",
        "import json; from semantica.semantic_artifact_schema import build_request_json_schema; print(json.dumps(build_request_json_schema(), sort_keys=True, separators=(',', ':')))"],
        capture_output=True, text=True, check=True)
    schema_digest = "sha256:" + hashlib.sha256(probe.stdout.strip().encode()).hexdigest()
    manifest = {
        "protocol": "ontoscience.semantica-bundle.v1",
        "pythonPath": f"python/{python_name}",
        "schemaDigest": schema_digest,
        "worker": {"path": f"python/{python_name}", "args": ["-I", "-B", "-m", "semantica.semantic_worker"]},
        "queryWorker": {"path": f"python/{python_name}", "args": ["-I", "-B", "-m", "semantica.semantic_query_worker"]},
        "mediaTypes": {
            "document-representation": "application/vnd.semantica.document-representation+json",
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
    closure = subprocess.run([str(python), "-I", "-B", "-c",
        "import json,sys; from pathlib import Path; from semantica.bundle import parser_dependency_files,parser_console_script_files; "
        "root=Path(sys.argv[1]).resolve(); print(json.dumps(dict(dependencies=sorted(parser_dependency_files(root)),"
        "scripts=sorted(parser_console_script_files(root)))))", str(output)],
        capture_output=True, text=True, check=True)
    parser_inputs = json.loads(closure.stdout)
    manifest["documentParserDigest"] = document_parser_digest(manifest["files"],
        set(parser_inputs["dependencies"]), set(parser_inputs["scripts"]))
    descriptor = [manifest["protocol"], schema_digest, manifest["documentParserDigest"], manifest["pythonPath"],
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
    parser.add_argument("--office-root", type=Path)
    parser.add_argument("--office-receipt", type=Path)
    parser.add_argument("--office-output", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--acceleration", choices=["cpu", "cuda", "directml"], default="cpu")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    values = vars(args)
    office_output = values.pop("office_output")
    target = values.pop("target")
    office_root = values.pop("office_root")
    office_receipt = values.pop("office_receipt")
    manifest = build_bundle(**values)
    result = {"artifactDigest": manifest["artifactDigest"], "files": len(manifest["files"])}
    if office_output is not None:
        if office_root is None or office_receipt is None or not target:
            raise ValueError("Office output requires office inputs and target")
        office_manifest = build_office_bundle(office_root=office_root, office_receipt=office_receipt, output=office_output, target=target)
        result["officeArtifactDigest"] = office_manifest["artifactDigest"]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
