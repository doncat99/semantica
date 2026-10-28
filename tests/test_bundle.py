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
