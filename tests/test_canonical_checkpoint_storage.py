"""Business data has one owner across job and producer changes."""
from copy import deepcopy
import json

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError, _bytes, _digest
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


def test_new_jobs_share_checkpoint_without_resume_candidates(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job-one", recipe="model")["params"]
    params["checkpointDir"] = str(tmp_path / "work" / "checkpoint")
    first = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    first.write("completed", {"unit": "one"}, {"paid": "result"})
    changed = deepcopy(params)
    changed["outputDir"] = str(tmp_path / "job-two")
    changed["relays"]["model"]["modelId"] = "new-model"
    changed["release"]["schemaDigest"] = "sha256:" + "e" * 64
    second = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(changed))
    assert second.root == first.root
    assert second.read("completed", {"unit": "one"}) == {"paid": "result"}
    assert not hasattr(second, "resume_roots")
    assert not hasattr(second, "legacy_inputs")


def test_import_is_verified_once_and_duplicate_carrier_is_removed(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    historical = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    historical.write("completed", {"unit": "one"}, {"paid": "result"})
    dataset = tmp_path / "dataset"
    imported = dataset / "imports" / "old-job"
    imported.parent.mkdir(parents=True)
    historical.root.rename(imported)
    params["checkpointDir"] = str(dataset / "checkpoint")
    canonical = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert canonical.read("completed", {"unit": "one"}) == {"paid": "result"}
    assert not imported.exists()
    assert not (dataset / "evidence" / "old-job").exists()
    assert not list((dataset / "evidence").glob("checkpoint-next-*"))
    assert SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params)).read("completed", {"unit": "one"}) == {"paid": "result"}


@pytest.mark.parametrize("has_key", [False, True])
def test_opaque_old_work_stops_before_any_paid_call(tmp_path, has_key):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    historical = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    historical.write("extraction-entities", "opaque-key", {"paid": "result"})
    manifest_path = historical.root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest.pop("entryIdentity")
    manifest["inputs"]["release"] = {"artifactDigest": "old"}
    manifest["fence"] = _digest(_bytes(manifest["inputs"]))
    manifest_path.write_bytes(_bytes(manifest))
    entry_path = next(historical.root.glob("extraction-*.json"))
    entry = json.loads(entry_path.read_bytes())
    if not has_key:
        entry.pop("key")
    entry["fence"] = manifest["fence"]
    entry_path.write_bytes(_bytes(entry))
    params["outputDir"] = str(tmp_path / "new-job")
    params["resumeCheckpointDirs"] = [str(historical.root)]
    with pytest.raises(SnapshotCheckpointError, match="offline checkpoint manifest migration required"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert entry_path.read_bytes() == _bytes(entry)
    assert not (tmp_path / "new-job" / "checkpoint").exists()


@pytest.mark.parametrize("stage", ["journal", "archived", "published"])
def test_interrupted_import_resumes_and_cleans_verified_duplicate(tmp_path, stage):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    first = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    first.write("completed", "one", {"paid": "result"})
    original = first._path("completed", "one").read_bytes()
    import shutil
    staging = first.root.parent / ".checkpoint-next-interrupted"
    shutil.copytree(first.root, staging)
    archive = first.root.parent / "evidence" / "checkpoint-next-interrupted"
    _plan = {"staging": staging.name, "archive": archive.name}
    (first.root.parent / ".checkpoint-migration.json").write_bytes(_bytes(_plan))
    if stage in ("archived", "published"):
        archive.parent.mkdir()
        first.root.rename(archive)
    if stage == "published":
        staging.rename(first.root)
    restored = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert restored.read("completed", "one") == {"paid": "result"}
    assert restored._path("completed", "one").read_bytes() == original
    assert not archive.exists()
    assert not staging.exists()
    assert not (first.root.parent / ".checkpoint-migration.json").exists()


def test_rejected_result_can_be_replaced_but_original_evidence_is_preserved(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    checkpoint.write("completed", "one", {"invalid": True})
    original = checkpoint._path("completed", "one").read_bytes()
    checkpoint.reject("completed", "one", {"invalid": True})
    checkpoint.write("completed", "one", {"valid": True})
    assert checkpoint.read("completed", "one") == {"valid": True}
    assert any(file.read_bytes() == original for file in (checkpoint.root.parent / "evidence").glob("*.json"))
    assert SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params)).read("completed", "one") == {"valid": True}


@pytest.mark.parametrize("raw", [b"null", b"{broken", b"[]"])
def test_corrupt_journal_preserves_completed_work_and_reports_repair(tmp_path, raw):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    checkpoint.write("completed", "one", {"paid": "result"})
    original = checkpoint._path("completed", "one").read_bytes()
    journal = checkpoint.root.parent / ".checkpoint-migration.json"
    journal.write_bytes(raw)
    with pytest.raises(SnapshotCheckpointError, match="migration journal"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert journal.read_bytes() == raw
    assert checkpoint._path("completed", "one").read_bytes() == original


def test_import_preserves_unrelated_evidence_without_a_second_payload(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("A source")
    params = _request(source, tmp_path / "job")["params"]
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    checkpoint.write("completed", "one", {"paid": "result"})
    dataset = tmp_path / "dataset"
    imported = dataset / "imports" / "job"
    imported.parent.mkdir(parents=True)
    checkpoint.root.rename(imported)
    evidence = dataset / "evidence" / "job"
    evidence.mkdir(parents=True)
    (evidence / "original.json").write_bytes(b"preserved")
    params["checkpointDir"] = str(dataset / "checkpoint")
    canonical = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert canonical.read("completed", "one") == {"paid": "result"}
    assert not imported.exists()
    assert not (evidence / "manifest.json").exists()
    assert (evidence / "original.json").read_bytes() == b"preserved"
