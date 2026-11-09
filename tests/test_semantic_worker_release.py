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
    assert any(requirement.name == "semantica" and "tripletstore-oxigraph" in requirement.extras
               for requirement in requirements)


def test_all_worker_locks_pin_the_native_store_dependency():
    import re
    locks = sorted((Path(__file__).parents[1] / ".github/requirements").glob("semantic-worker-*.lock"))
    assert len(locks) == 6
    for lock in locks:
        assert re.search(r"^pyoxigraph==\S+$", lock.read_text(), re.M), lock.name

SCRIPT = Path(__file__).parents[1] / ".github/scripts/semantic_worker_release.py"


def test_worker_model_lock_admits_only_accurate_tableformer():
    lock = json.loads((SCRIPT.parent.parent / "requirements/semantic-worker-models.json").read_text())
    table_paths = [file["path"] for file in lock["files"] if "/tableformer/" in file["path"]]
    assert len(table_paths) == 2
    assert all("/accurate/" in path for path in table_paths)


def test_offline_acceptance_sets_model_environment_before_dependency_imports(tmp_path, monkeypatch):
    import ast
    import os
    import sys

    monkeypatch.setattr(sys, "argv", ["acceptance.py", str(tmp_path), str(tmp_path / "receipt.json")])
    keys = ("DOCLING_ARTIFACTS_PATH", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DOCLING_DEVICE", "ORT_DISABLE_TELEMETRY")
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    tree = ast.parse(SCRIPT.with_name("semantic_worker_acceptance.py").read_text())
    boundary = next(index for index, node in enumerate(tree.body)
                    if isinstance(node, ast.ImportFrom) and node.module == "docx")
    exec(compile(ast.Module(body=tree.body[:boundary], type_ignores=[]), str(SCRIPT), "exec"), {})
    assert os.environ["DOCLING_ARTIFACTS_PATH"] == str(tmp_path / "models")
    assert [os.environ[key] for key in keys[1:]] == ["1", "1", "cpu", "1"]


def test_offline_acceptance_uses_the_installed_parser_recipe(tmp_path):
    import ast
    from semantica.bundle import document_parser_digest

    files = [
        {"path": "python/bin/python3", "size": 10, "sha256": "interpreter"},
        {"path": "python/bin/docling", "size": 20, "sha256": "installation-path"},
    ]
    scripts = {"python/bin/docling"}
    manifest = {"files": files, "documentParserDigest": document_parser_digest(files, set(), scripts)}
    tree = ast.parse(SCRIPT.with_name("semantic_worker_acceptance.py").read_text())
    start = next(index for index, node in enumerate(tree.body)
                 if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "parser_files" for target in node.targets))
    end = next(index for index in range(start, len(tree.body)) if isinstance(tree.body[index], ast.Assert))
    exec(compile(ast.Module(body=tree.body[start:end + 1], type_ignores=[]), str(SCRIPT), "exec"), {
        "root": tmp_path, "manifest": manifest, "document_parser_digest": document_parser_digest,
        "parser_dependency_files": lambda root: set(),
        "parser_console_script_files": lambda root: scripts,
    })


spec = importlib.util.spec_from_file_location("semantic_worker_release", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_acceptance_checks_selected_package_versions():
    import ast
    tree = ast.parse(SCRIPT.with_name("semantic_worker_acceptance.py").read_text())
    start = next(index for index, node in enumerate(tree.body)
                 if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "selected_packages" for target in node.targets))
    check = compile(ast.Module(body=tree.body[start:start + 2], type_ignores=[]), str(SCRIPT), "exec")
    selected = {"docling": "2.141.0", "docling-slim": "2.149.0+ontoscience.1", "docling-ibm-models": "4.0.4+ontoscience.3"}
    scope = {"release": {"packages": list(selected.items())}, "version": selected.__getitem__}
    exec(check, scope)
    with pytest.raises(AssertionError, match="docling-slim"):
        exec(check, {**scope, "version": lambda name: "wrong" if name == "docling-slim" else selected[name]})


def test_release_tag_is_derived_from_full_revision():
    assert module.revision_tag("a" * 40) == "ontoscience-semantic-worker-aaaaaaaaaaaa"


def test_model_acceptance_queries_the_worker_artifact(tmp_path, monkeypatch):
    import subprocess

    script = SCRIPT.with_name("semantic_worker_model_acceptance.py")
    acceptance_spec = importlib.util.spec_from_file_location("model_acceptance", script)
    acceptance = importlib.util.module_from_spec(acceptance_spec)
    acceptance_spec.loader.exec_module(acceptance)
    run = subprocess.run

    def source_run(command, **kwargs):
        # Local tests use source; release acceptance retains installed-only isolation.
        return run([arg for arg in command if arg != "-I"], **kwargs)

    monkeypatch.setattr(acceptance.subprocess, "run", source_run)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "artifactDigest": "sha256:" + "2" * 64,
        "schemaDigest": "sha256:" + "3" * 64,
        "mediaTypes": {
            "document-representation": "application/vnd.semantica.document-representation+json",
        },
    }))
    result = acceptance.verify_model_paths(tmp_path, tmp_path / "acceptance.json")
    assert result["queryModes"] == ["keyword", "semantic"]
    assert result["modelReceipts"] > 0


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


def test_single_platform_qualification_keeps_exact_target_and_rejects_unknown():
    assert [(item["target"], item["acceleration"]) for item in
            module.release_matrix(False, "win-x64")["include"]] == [("win-x64", "cpu")]
    with pytest.raises(ValueError, match="unsupported qualification target"):
        module.release_matrix(False, "typo")


def test_single_platform_qualification_cannot_publish():
    import yaml
    workflow = yaml.safe_load((SCRIPT.parent.parent / "workflows/semantic-worker-native.yml").read_text())
    assert workflow["jobs"]["publish"]["if"] == "${{ !inputs.qualification_target || inputs.qualification_target == 'all' }}"


def test_query_acceptance_preserves_primary_exception_and_closes_diagnostics(monkeypatch):
    from io import StringIO
    script = SCRIPT.with_name("semantic_worker_model_acceptance.py")
    acceptance_spec = importlib.util.spec_from_file_location("query_acceptance", script)
    acceptance = importlib.util.module_from_spec(acceptance_spec)
    acceptance_spec.loader.exec_module(acceptance)
    class Process:
        stdin, stdout = StringIO(), StringIO()
        returncode = 1
        def wait(self, **_kwargs): return self.returncode
        def poll(self): return self.returncode
    process = Process()
    monkeypatch.setattr(acceptance.subprocess, "Popen", lambda *args, **kwargs: process)
    diagnostic = None
    with pytest.raises(RuntimeError, match="primary query failure"):
        with acceptance.QuerySession() as session:
            diagnostic = session.diagnostics
            raise RuntimeError("primary query failure")
    assert diagnostic.closed and process.stdout.closed


def test_query_acceptance_empty_response_identifies_mode_and_stderr(monkeypatch):
    from io import StringIO
    script = SCRIPT.with_name("semantic_worker_model_acceptance.py")
    acceptance_spec = importlib.util.spec_from_file_location("query_acceptance", script)
    acceptance = importlib.util.module_from_spec(acceptance_spec)
    acceptance_spec.loader.exec_module(acceptance)
    class Process:
        stdin, stdout = StringIO(), StringIO()
        returncode = 1
        def wait(self, **_kwargs): return self.returncode
        def poll(self): return self.returncode
    def popen(*args, **kwargs):
        kwargs["stderr"].write("native stack evidence")
        process = Process()
        process.kill = lambda: None
        return process
    monkeypatch.setattr(acceptance.subprocess, "Popen", popen)
    with pytest.raises(AssertionError, match="query.*semantic.*knowledge.*native stack evidence"):
        with acceptance.QuerySession() as session:
            session.call("query", {"mode": "semantic", "target": "knowledge"})
