import json
import importlib.util
from pathlib import Path

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
