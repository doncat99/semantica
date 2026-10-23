import json
import importlib.util
from pathlib import Path
from argparse import Namespace

import pytest


def test_all_worker_profiles_include_the_native_typed_schema_dependency():
    import tomllib
    from packaging.requirements import Requirement
    config = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    requirements = [Requirement(value) for value in config["project"]["optional-dependencies"]["semantic-worker-common"]]
    assert any(requirement.name == "openai" for requirement in requirements)

SCRIPT = Path(__file__).parents[1] / ".github/scripts/semantic_worker_release.py"
spec = importlib.util.spec_from_file_location("semantic_worker_release", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_release_tag_is_derived_from_full_revision():
    assert module.revision_tag("a" * 40) == "ontoscience-semantic-worker-aaaaaaaaaaaa"


def test_release_config_declares_all_supported_targets():
    config = json.loads((Path(__file__).parents[1] / ".github/semantic-worker-release.json").read_text())
    assert set(config["targets"]) == {"darwin-arm64", "linux-x64", "win-x64"}


@pytest.mark.parametrize(("target", "profile", "extra"), [
    ("linux-x64", "cuda", "semantic-worker-cuda"),
    ("win-x64", "directml", "semantic-worker-directml"),
    ("darwin-arm64", "cpu", "semantic-worker"),
])
def test_bundle_command_forwards_supported_profile(tmp_path, monkeypatch, target, profile, extra):
    commands = []
    monkeypatch.setenv("UV_CONSTRAINT", "original")
    monkeypatch.setenv("UV_TORCH_BACKEND", "original")
    monkeypatch.setattr(module, "run", commands.append)
    module.build_bundle(Namespace(target=target, acceleration=profile,
        native_inputs=tmp_path, wheel=tmp_path / "worker.whl", models=tmp_path,
        output=tmp_path / "out", source_revision="a" * 40))
    command = commands[0]
    assert command[command.index("--acceleration") + 1] == profile
    config = module.load_config()
    assert config["accelerationProfiles"][profile]["extra"] == extra


@pytest.mark.parametrize(("target", "profile", "ort", "torch"), [
    ("linux-x64", "cuda", "onnxruntime-gpu", "cu130"),
    ("win-x64", "cuda", "onnxruntime-gpu", "cu130"),
    ("win-x64", "directml", "onnxruntime-directml", "cpu"),
])
def test_gpu_lock_has_one_ort_distribution_and_matching_torch(target, profile, ort, torch):
    import re
    lock = (SCRIPT.parents[1] / f"requirements/semantic-worker-{target}-{profile}.lock").read_text()
    assert re.findall(r"^(onnxruntime(?:-gpu|-directml)?)==", lock, re.M) == [ort]
    assert re.search(rf"^torch==[^\n]+\+{torch}$", lock, re.M)


def test_unsupported_profile_rejected_before_build(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "run", lambda _: pytest.fail("must reject before build"))
    with pytest.raises(ValueError, match="not supported"):
        module.build_bundle(Namespace(target="linux-x64", acceleration="directml"))


def test_release_matrix_keeps_cpu_default_and_gpu_variants_separate():
    assert len(module.release_matrix(False)["include"]) == 3
    variants = module.release_matrix(True)["include"]
    assert len(variants) == 6
    assert {(v["target"], v["acceleration"]) for v in variants if v["acceleration"] == "directml"} == {("win-x64", "directml")}
