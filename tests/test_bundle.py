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
    validate_acceleration_profile,
    parser_dependency_files,
)


@pytest.mark.parametrize("site_packages", ["lib/python3.12/site-packages", "Lib/site-packages"])
def test_worker_model_pruning_removes_only_unused_and_identical_models(tmp_path, site_packages):
    from semantica.bundle import prune_worker_models

    model_root = tmp_path / "models"
    table = model_root / "docling-project--docling-models/model_artifacts/tableformer"
    files = {
        table / "fast/tableformer_fast.safetensors": b"unused fast weights",
        table / "accurate/tableformer_accurate.safetensors": b"accurate weights",
        table / "accurate/tm_config.json": b"{}",
        model_root / "RapidOcr/PP-OCRv6_det_small.onnx": b"detector",
        model_root / "RapidOcr/PP-OCRv6_rec_small.onnx": b"recognizer",
        model_root / "RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx": b"classifier",
        model_root / "RapidOcr/fonts/FZYTK.TTF": b"font",
    }
    package = tmp_path / "python" / site_packages / "rapidocr/models"
    files.update({
        package / "PP-OCRv6_det_small.onnx": b"detector",
        package / "PP-OCRv6_rec_small.onnx": b"different recognizer",
        package / "another_model.onnx": b"keep",
        tmp_path / "python/include/header.h": b"keep header",
        tmp_path / "python" / site_packages / "numpy/tests/test_sample.py": b"keep test",
    })
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    prune_worker_models(tmp_path)
    prune_worker_models(tmp_path)  # Repeating the native step is harmless.
    assert not (table / "fast").exists()
    assert not (package / "PP-OCRv6_det_small.onnx").exists()
    for path, content in files.items():
        if path != package / "PP-OCRv6_det_small.onnx" and "fast" not in path.parts:
            assert path.read_bytes() == content


def test_worker_model_pruning_rejects_missing_canonical_weights_before_deletion(tmp_path):
    from semantica.bundle import prune_worker_models

    fast = tmp_path / "models/docling-project--docling-models/model_artifacts/tableformer/fast/model.bin"
    fast.parent.mkdir(parents=True)
    fast.write_bytes(b"keep until inputs are valid")
    with pytest.raises(ValueError, match="required offline model"):
        prune_worker_models(tmp_path)
    assert fast.is_file()


def test_parser_dependency_closure_tracks_selected_ort_without_rapidocr_requirement(tmp_path, monkeypatch):
    from importlib import metadata
    distributions = [SimpleNamespace(metadata={"Name": name}, requires=[],
        files=[Path(f"{name}/runtime.bin")], locate_file=lambda file: tmp_path / file)
        for name in ("docling", "rapidocr", "blake3", "pandas", "onnxruntime-gpu")]
    monkeypatch.setattr(metadata, "distributions", lambda: distributions)
    assert "onnxruntime-gpu/runtime.bin" in parser_dependency_files(tmp_path)


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


def test_cuda_bundle_validation_does_not_require_gpu_on_build_host():
    inventory = {"platform": "Linux", "torch": {"cudaBuild": "13.0", "cudaAvailable": False},
        "onnxruntime": {"availableProviders": ["CUDAExecutionProvider", "CPUExecutionProvider"]}}
    validate_acceleration_profile("cuda", inventory, [("onnxruntime-gpu", "1.31.0")])
    with pytest.raises(ValueError, match="exactly"):
        validate_acceleration_profile("cuda", inventory, [("onnxruntime-gpu", "1.31.0"), ("onnxruntime", "1.30.0")])
    inventory["torch"]["cudaBuild"] = None
    with pytest.raises(ValueError, match="CUDA Torch"):
        validate_acceleration_profile("cuda", inventory, [("onnxruntime-gpu", "1.31.0")])


def test_directml_bundle_requires_windows_and_real_provider():
    inventory = {"platform": "Windows", "onnxruntime": {"availableProviders": ["DmlExecutionProvider", "CPUExecutionProvider"]}}
    validate_acceleration_profile("directml", inventory, [("onnxruntime-directml", "1.24.4")])
    inventory["platform"] = "Linux"
    with pytest.raises(ValueError, match="Windows"):
        validate_acceleration_profile("directml", inventory, [("onnxruntime-directml", "1.24.4")])


def manifest_for(path: Path) -> dict:
    return {"files": [{"path": path.name, "size": path.stat().st_size, "sha256": digest_file(path)}]}


def test_bundle_inventory_prunes_install_but_rejects_runtime_bytecode(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    bytecode = tmp_path / "python/lib/__pycache__/generated.cpython-312.pyc"
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b"installed")

    remove_generated_bytecode(tmp_path)
    manifest = manifest_for(tracked)
    bytecode.write_bytes(b"generated at runtime")
    with pytest.raises(ValueError, match="extra=.*generated.cpython-312.pyc"):
        verify_bundle_inventory(tmp_path, manifest)

    assert bytecode.exists()


def test_post_acceptance_inventory_rejects_other_untracked_files(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    (tmp_path / "unexpected.cache").write_bytes(b"generated")

    with pytest.raises(ValueError, match="extra=.*unexpected.cache"):
        verify_bundle_inventory(tmp_path, manifest_for(tracked))


def test_post_acceptance_inventory_rejects_changed_manifest_file(tmp_path: Path):
    tracked = tmp_path / "runtime.bin"
    tracked.write_bytes(b"runtime")
    manifest = manifest_for(tracked)
    tracked.write_bytes(b"changed")

    with pytest.raises(ValueError, match="runtime.bin"):
        verify_bundle_inventory(tmp_path, manifest)


def test_document_parser_digest_ignores_extraction_code_but_tracks_parser_inputs():
    files = [
        {"path": "models/layout/model.bin", "size": 1, "sha256": "sha256:" + "1" * 64},
        {"path": "python/lib/site-packages/docling/core.py", "size": 2, "sha256": "sha256:" + "2" * 64},
        {"path": "python/lib/site-packages/semantica/source.py", "size": 3, "sha256": "sha256:" + "3" * 64},
        {"path": "python/lib/site-packages/semantica/semantic_publication_builder.py", "size": 4, "sha256": "sha256:" + "4" * 64},
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
             item("semantica/semantic_worker.py", "protocol"), item("semantica/triplet_store/oxigraph_store.py", "knowledge"),
             item("openai/client.py", "llm")]
    closure = {files[1]["path"]}
    before = document_parser_digest(files, closure)
    changed = [dict(value) for value in files]
    for value in changed[2:]:
        value["sha256"] = "changed"
    assert document_parser_digest(changed, closure) == before
    changed[1]["sha256"] = "parser-changed"
    assert document_parser_digest(changed, closure) != before


@pytest.mark.parametrize("relative", [
    "python/lib/site-packages/docling-1.dist-info/RECORD",
    "python/lib/site-packages/docling-1.dist-info/direct_url.json",
    "python/lib/site-packages/docling-1.dist-info/uv_cache.json",
])
def test_parser_recipe_ignores_installation_location_and_time_metadata(relative):
    files = [{"path": "python/lib/site-packages/docling/core.py", "size": 4, "sha256": "runtime"},
             {"path": relative, "size": 10, "sha256": "installation-a"}]
    changed = [files[0], {**files[1], "size": 20, "sha256": "installation-b"}]
    assert document_parser_digest(files) == document_parser_digest(changed)


@pytest.mark.parametrize("script", ["python/bin/docling", "python/Scripts/docling.exe"])
def test_parser_recipe_ignores_only_declared_unused_console_wrappers(script):
    files = [{"path": "python/bin/python3", "size": 4, "sha256": "interpreter"},
             {"path": script, "size": 10, "sha256": "staging-path-a"},
             {"path": "python/bin/ffprobe", "size": 4, "sha256": "media-tool"}]
    changed = [files[0], {**files[1], "sha256": "staging-path-b"}, files[2]]
    assert document_parser_digest(files, console_script_files={script}) == document_parser_digest(changed, console_script_files={script})
    assert document_parser_digest(files) != document_parser_digest(changed)
    changed[2] = {**files[2], "sha256": "changed-media-tool"}
    assert document_parser_digest(files, console_script_files={script}) != document_parser_digest(changed, console_script_files={script})


@pytest.mark.parametrize("relative", [
    "python/bin/python3", "python/python.exe", "python/lib/python3.12/os.py",
    "python/lib/site-packages/docling/core.py", "python/lib/site-packages/docling-1.dist-info/METADATA",
    "python/lib/site-packages/docling-1.dist-info/entry_points.txt", "python/lib/site-packages/native/runtime.dylib",
    "models/layout/model.bin", "office/receipt.json", "office/soffice",
])
def test_parser_recipe_still_tracks_executed_bytes_dependencies_and_models(relative):
    files = [{"path": relative, "size": 4, "sha256": "before"}]
    assert document_parser_digest(files) != document_parser_digest([{**files[0], "sha256": "after"}])


@pytest.mark.parametrize("directory,suffix", [("bin", ""), ("Scripts", ".exe")])
def test_console_wrapper_selection_uses_entry_points_and_preserves_native_tools(tmp_path, monkeypatch, directory, suffix):
    from importlib import metadata
    from semantica.bundle import parser_console_script_files
    runtime = tmp_path / "python" / directory
    runtime.mkdir(parents=True)
    for name in ("docling", "python3", "python3.12", "ffprobe", "unregistered-tool"):
        (runtime / (name + suffix)).write_bytes(b"runtime")
    entries = [SimpleNamespace(group="console_scripts", name=name) for name in
               ("docling", "python3", "python3.12", "ffprobe")]
    entries.append(SimpleNamespace(group="other", name="unregistered-tool"))
    monkeypatch.setattr(metadata, "distributions", lambda: [SimpleNamespace(entry_points=entries, files=[])])
    assert parser_console_script_files(tmp_path) == {f"python/{directory}/docling{suffix}"}



def test_console_wrapper_selection_handles_wheel_script_files_without_dropping_native_tools(tmp_path, monkeypatch):
    from importlib import metadata
    from semantica.bundle import parser_console_script_files
    runtime = tmp_path / "python/bin"
    runtime.mkdir(parents=True)
    files = {"get_gprof": b"#!/bin/sh\n\'\'\'exec\' '/staging/python3' \"$0\" \"$@\"\n",
             "legacy-cli": b"#!/staging/python3\nimport sys\n", "native-tool": b"\x7fELF",
             "ffprobe": b"#!/staging/python3\nimport sys\n", "python3": b"binary"}
    for name, content in files.items():
        (runtime / name).write_bytes(content)
    wheel_scripts = ("get_objgraph", "mpire-dashboard", "pygrun", "undill", "vba_extract.py")
    for name in wheel_scripts:
        (runtime / name).write_bytes(files["get_gprof"])
    undeclared = runtime / "undeclared-python-cli"
    undeclared.write_bytes(files["legacy-cli"])
    escaped = tmp_path.parent / (tmp_path.name + "-outside")
    escaped.write_bytes(files["legacy-cli"])
    (runtime / "escape").symlink_to(escaped)
    distribution = SimpleNamespace(entry_points=[], files=[*files, *wheel_scripts, "escape"], locate_file=lambda name: runtime / name)
    monkeypatch.setattr(metadata, "distributions", lambda: [distribution])
    assert parser_console_script_files(tmp_path) == {"python/bin/" + name for name in ("get_gprof", "legacy-cli", *wheel_scripts)}
