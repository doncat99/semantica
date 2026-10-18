"""Only identical current processing inputs may resume a checkpoint."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


@pytest.mark.parametrize("change", ["artifact", "schema", "revision", "tokens", "recipe", "processing"])
def test_changed_checkpoint_inputs_are_rejected(tmp_path, monkeypatch, change):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first", recipe="model")["params"]
    params["relays"]["model"]["maxOutputTokens"] = 32768
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "second")
    current["resumeCheckpointDirs"] = [str(checkpoint.root)]
    if change in ("artifact", "schema"):
        current["release"][change + "Digest"] = "sha256:" + "f" * 64
    elif change == "revision":
        current["inputRevision"] = "sha256:" + "f" * 64
    elif change == "tokens":
        current["relays"]["model"]["maxOutputTokens"] = 16384
    elif change == "processing":
        monkeypatch.setattr("semantica.project_checkpoint.PROCESSING_CONTRACTS", {})
    else:
        current["recipe"]["forceOcrSourceIds"] = ["source-1"]
    with pytest.raises(SnapshotCheckpointError, match="inputs changed"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))


def test_removed_model_limit_migration_option_is_rejected(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "output")["params"]
    params["resumeCheckpointModelTokenLimits"] = {}
    with pytest.raises(ValidationError, match="Extra inputs"):
        SemanticArtifactBuildRequest.model_validate(params)
