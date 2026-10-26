"""Only identical current processing inputs may resume a checkpoint."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


def test_representation_identity_ignores_producer(tmp_path):
    from types import SimpleNamespace
    from semantica.semantic_source_artifact import _representation_revision
    source = SimpleNamespace(material_revision="immutable")
    first = _representation_revision(source, False, "immutable", "old", "1", "local", {"text": "content"})
    assert first == _representation_revision(source, False, "immutable", "new", "2", "remote", {"text": "content"})


def test_document_checkpoint_rejects_legacy_key_after_profile_upgrade(tmp_path, monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    from semantica.semantic_source_artifact import _parse_source
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first")["params"]
    request = SemanticArtifactBuildRequest.model_validate(params)
    checkpoint = SnapshotCheckpoint(request)
    item = request.sources[0]
    key = {"sourceId": item.source_id, "contentHash": item.material_revision, "forceOcr": False,
           "documentProcessing": request.document_processing.model_dump(mode="json", by_alias=True)}
    saved = ["A source", {"text": "A source", "content_hash": item.material_revision, "mime_type": item.mime_type}, "local", item.material_revision, "old-parser", "1"]
    checkpoint.write("document", key, saved)
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "second")
    current["resumeCheckpointDirs"] = [str(checkpoint.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    calls = []
    monkeypatch.setattr("semantica.semantic_source_artifact.parse_source",
                        lambda *a, **k: calls.append(k) or type("Parsed", (), {
                            "text": "A source", "document": {"text": "A source"},
                            "origin": "remote", "parser": "new-parser", "parser_version": "2",
                        })())
    token = active_checkpoint.set(resumed)
    try:
        result = _parse_source(item, False, {"mode": "remote"})
        assert result[0] == "A source"
        assert calls
    finally:
        active_checkpoint.reset(token)


def test_document_checkpoint_reuses_matching_processing_revision(tmp_path, monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    from semantica.semantic_source_artifact import _parse_source
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first")["params"]
    request = SemanticArtifactBuildRequest.model_validate(params)
    checkpoint = SnapshotCheckpoint(request)
    item = request.sources[0]
    profile = request.document_processing.model_dump(mode="json", by_alias=True)
    processing_revision = profile["processingRevision"]
    key = {"sourceId": item.source_id, "contentHash": item.material_revision,
           "forceOcr": False, "processingRevision": processing_revision}
    saved = ["A source", {"text": "A source", "content_hash": item.material_revision,
                            "mime_type": item.mime_type}, "local", item.material_revision,
             "old-parser", "1"]
    checkpoint.write("document", key, saved)
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "second")
    current["resumeCheckpointDirs"] = [str(checkpoint.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    monkeypatch.setattr("semantica.semantic_source_artifact.parse_source", lambda *a, **k: pytest.fail("must reuse"))
    token = active_checkpoint.set(resumed)
    try:
        assert _parse_source(item, False, profile) == tuple(saved)
    finally:
        active_checkpoint.reset(token)


@pytest.mark.parametrize("change", ["schema", "recipe", "processing"])
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
    checkpoint.write("completed", "unit", {"text": "paid result"})
    if change == "recipe":
        with pytest.raises(SnapshotCheckpointError, match="different business content"):
            SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    else:
        resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
        assert resumed.read("completed", "unit") == {"text": "paid result"}


def test_removed_model_limit_migration_option_is_rejected(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "output")["params"]
    params["resumeCheckpointModelTokenLimits"] = {}
    with pytest.raises(ValidationError, match="Extra inputs"):
        SemanticArtifactBuildRequest.model_validate(params)


def test_unrelated_resume_candidate_does_not_poison_matching_work(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first")["params"]
    original = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    original.write("completed", "unit", {"text": "paid result"})
    unrelated = deepcopy(params)
    unrelated["outputDir"] = str(tmp_path / "unrelated")
    unrelated["projectId"] = "unrelated-project"
    unrelated["sources"][0]["sourceId"] = "unrelated-source"
    unrelated["parsedSources"][0]["sourceId"] = "unrelated-source"
    other = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(unrelated))
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "second")
    current["resumeCheckpointDirs"] = [str(other.root), str(original.root)]
    current["baseSnapshot"] = {"snapshotId": "new-base", "snapshotPath": str(tmp_path / "base.json"),
                               "artifactDigest": "sha256:" + "e" * 64,
                               "schemaDigest": params["release"]["schemaDigest"]}
    with pytest.raises(SnapshotCheckpointError, match="different business content"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    assert not (tmp_path / "second" / "checkpoint").exists()
    current["resumeCheckpointDirs"] = [str(original.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    assert resumed.read("completed", "unit") == {"text": "paid result"}


def test_source_rename_preserves_completed_work(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first")["params"]
    original = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    original.write("completed", "unit", {"text": "paid result"})
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "renamed")
    current["sources"][0]["name"] = "renamed.txt"
    current["resumeCheckpointDirs"] = [str(original.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    assert resumed.read("completed", "unit") == {"text": "paid result"}


def test_missing_legacy_window_plan_blocks_before_new_extraction(tmp_path, monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    from semantica import semantic_artifact_builder as builder
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "first")["params"]
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    checkpoint.write("extraction-entities", "legacy-key", {"paid": True})
    current = deepcopy(params)
    current["outputDir"] = str(tmp_path / "second")
    current["resumeCheckpointDirs"] = [str(checkpoint.root)]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    monkeypatch.setattr(builder, "_text_windows", lambda *_: pytest.fail("must not invent a legacy plan"))
    token = active_checkpoint.set(resumed)
    try:
        with pytest.raises(builder.SemanticArtifactError, match="historical extraction window plan"):
            builder._source_windows(SemanticArtifactBuildRequest.model_validate(current).sources[0], False, "A source")
        assert not list(resumed.root.glob("source-windows-*.json"))
    finally:
        active_checkpoint.reset(token)
