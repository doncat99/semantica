"""Paid results survive unrelated material changes and producer upgrades."""
from copy import deepcopy
from pathlib import Path
import json
import shutil

import pytest

from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError, active_checkpoint, _bytes
from semantica.semantic_artifact_builder import _source_windows, build_semantic_artifacts
from semantica.semantic_artifact_errors import SemanticArtifactError
from semantica.semantic_artifact_schema import BindParsedSourceRequest, SemanticArtifactBuildRequest, stable_digest
from tests.test_semantic_artifact import _request, _parsed_ref
from semantica.source import source_content_revision


def test_recipe_provenance_is_imported_once_and_survives_later_requirements(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Durable source")
    params = _request(source, tmp_path / "first")["params"]
    request = SemanticArtifactBuildRequest.model_validate(params)
    original = SnapshotCheckpoint(request)
    recipe = request.recipe.lineage_payload()
    # Simulate a verified manifest written before recipe entries existed.
    for path in original.root.glob("recipe-provenance-*.json"):
        path.unlink()
    params["resumeCheckpointDirs"] = [str(original.root)]
    params["outputDir"] = str(tmp_path / "second")
    params["recipe"]["version"] = "2"
    second = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert second.read("recipe-provenance", stable_digest(recipe)) == recipe
    params["resumeCheckpointDirs"] = [str(second.root)]
    params["outputDir"] = str(tmp_path / "third")
    params["recipe"]["version"] = "3"
    third = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert third.read("recipe-provenance", stable_digest(recipe)) == recipe
    entry_path = third._path("recipe-provenance", stable_digest(recipe))
    entry = json.loads(entry_path.read_bytes())
    entry["payload"]["version"] = "tampered"
    entry["digest"] = stable_digest(entry["payload"])
    entry_path.write_bytes(_bytes(entry))
    with pytest.raises(SnapshotCheckpointError, match="recipe provenance identity mismatch"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))


@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize("rename", [False, True])
def test_rename_and_historical_v2_build_without_parse_or_identity_rewrite(tmp_path, monkeypatch, historical, rename):
    import semantica.semantic_source_artifact as owner
    source = tmp_path / "source.txt"
    source.write_text("Ada Lovelace designed the Analytical Engine.")
    if historical:
        monkeypatch.setattr(owner, "_representation_revision", lambda s, o, c, p, v, r, d: stable_digest({
            "sourceRevision": s.material_revision, "contentHash": c, "forceOcr": o,
            "parser": p, "parserVersion": v, "origin": r,
            "document": {k: val for k, val in d.items() if k not in {"metadata", "representation_revision"}}}))
    params = _request(source, tmp_path / "original")["params"]
    monkeypatch.undo()
    raw = Path(params["parsedSources"][0]["artifactPath"]).read_bytes()
    revision = json.loads(raw)["document"]["representation_revision"]
    if rename:
        params["sources"][0]["name"] = "renamed.txt"
    monkeypatch.setattr(owner, "parse_source", lambda *a, **kw: pytest.fail("must not reparse"))
    request = SemanticArtifactBuildRequest.model_validate(params)
    result = build_semantic_artifacts(request)
    assert result["snapshot"].document_representations[0].id.endswith(revision[7:])
    assert Path(params["parsedSources"][0]["artifactPath"]).read_bytes() == raw
    bound = owner.bind_parsed_source_artifact(BindParsedSourceRequest.model_validate({
        "source": {**params["sources"][0], "sourceId": "another-source"},
        "outputDir": str(tmp_path / "bound"),
        "documentProcessing": request.document_processing.model_dump(mode="json", by_alias=True),
        "forceOcr": False, "parsedArtifactPath": params["parsedSources"][0]["artifactPath"],
        "parsedArtifactDigest": params["parsedSources"][0]["artifactDigest"],
    }))
    assert bound["sourceId"] == "another-source"
    assert json.loads(Path(bound["artifactPath"]).read_bytes())["document"]["source"] == params["sources"][0]["name"]
    assert Path(params["parsedSources"][0]["artifactPath"]).read_bytes() == raw
    # Integrity remains mandatory even though producer identity is opaque.
    Path(params["parsedSources"][0]["artifactPath"]).write_bytes(raw + b" ")
    with pytest.raises(SemanticArtifactError, match="digest is invalid"):
        build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(params))


@pytest.mark.parametrize("change", ["add", "remove", "revision", "ocr"])
def test_source_local_work_survives_material_set_changes(tmp_path, change):
    first_file = tmp_path / "first.txt"
    first_file.write_text("Original paid source")
    params = _request(first_file, tmp_path / "first")["params"]
    second_file = tmp_path / "second.txt"
    second_file.write_text("Other source")
    other = _request(second_file, tmp_path / "other")["params"]
    other["sources"][0]["sourceId"] = "other"
    params["checkpointDir"] = str(tmp_path / "work" / "checkpoint")
    if change == "remove":
        params["sources"].extend(other["sources"])
        params["parsedSources"].append(_parsed_ref(params, other["sources"][0]))
    original = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    token = active_checkpoint.set(original)
    try:
        _source_windows(SemanticArtifactBuildRequest.model_validate(params).sources[0], False, first_file.read_text())
    finally:
        active_checkpoint.reset(token)
    original.write("extraction-entities", "business-key", {"paid": True})
    current = deepcopy(params)
    if change == "add":
        current["sources"].extend(other["sources"])
        current["parsedSources"].append(_parsed_ref(current, other["sources"][0]))
    elif change == "remove":
        current["sources"] = current["sources"][:1]
        current["parsedSources"] = current["parsedSources"][:1]
    elif change == "revision":
        first_file.write_text("Changed source")
        current["sources"][0]["materialRevision"] = source_content_revision(first_file)
    else:
        current["recipe"]["forceOcrSourceIds"] = ["source-1"]
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    assert resumed.read("extraction-entities", "business-key") == {"paid": True}
    token = active_checkpoint.set(resumed)
    try:
        for item in SemanticArtifactBuildRequest.model_validate(current).sources:
            _source_windows(item, item.source_id in current["recipe"]["forceOcrSourceIds"], Path(item.file_path).read_text())
    finally:
        active_checkpoint.reset(token)


def test_removed_source_missing_plan_still_blocks_after_readdition(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Paid source")
    params = _request(source, tmp_path / "first")["params"]
    params["checkpointDir"] = str(tmp_path / "work" / "checkpoint")
    original = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    original.write("extraction-entities", "business-key", {"paid": True})
    other = tmp_path / "other.txt"
    other.write_text("Other source")
    current = _request(other, tmp_path / "other")["params"]
    current["sources"][0]["sourceId"] = "other"
    current["parsedSources"] = [_parsed_ref(current, current["sources"][0])]
    current["checkpointDir"] = params["checkpointDir"]
    SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(current))
    resumed = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    token = active_checkpoint.set(resumed)
    try:
        with pytest.raises(SemanticArtifactError, match="historical extraction window plan"):
            _source_windows(SemanticArtifactBuildRequest.model_validate(params).sources[0], False, source.read_text())
    finally:
        active_checkpoint.reset(token)


@pytest.mark.parametrize("stage", ["journal", "archived", "published"])
def test_relocated_dataset_finishes_transaction_and_nested_import_once(tmp_path, stage):
    source = tmp_path / "source.txt"
    source.write_text("Durable source")
    params = _request(source, tmp_path / "old-dataset")["params"]
    first = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    key = {"sourceId": "source-1", "materialRevision": params["sources"][0]["materialRevision"], "forceOcr": False}
    first.write("source-windows", key, [[0, 14, "Durable source"]])
    original = first._path("source-windows", key).read_bytes()
    nested_params = {**params, "outputDir": str(tmp_path / "nested")}
    nested = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(nested_params))
    nested.write("extraction-entities", "a" * 64, {"paid": True})
    staging = first.root.parent / ".checkpoint-next-interrupted"
    shutil.copytree(first.root, staging)
    archive = first.root.parent / "evidence" / "checkpoint-next-interrupted"
    (first.root.parent / ".checkpoint-migration.json").write_bytes(_bytes({"staging": staging.name, "archive": archive.name}))
    if stage in ("archived", "published"):
        archive.parent.mkdir()
        first.root.rename(archive)
    if stage == "published":
        staging.rename(first.root)
    imported = first.root.parent / "imports"
    imported.mkdir()
    nested.root.rename(imported / "nested-job")
    canonical = tmp_path / "project"
    (canonical / "imports").mkdir(parents=True)
    carrier = canonical / "imports" / "dataset-old"
    first.root.parent.rename(carrier)
    params["checkpointDir"] = str(canonical / "checkpoint")
    for _ in range(2):
        restored = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
        assert restored.read("source-windows", key) == [[0, 14, "Durable source"]]
        assert restored.read("extraction-entities", "a" * 64) == {"paid": True}
    assert not carrier.exists()
    evidence = canonical / "evidence" / "dataset-old"
    assert (evidence / "checkpoint" / first._path("source-windows", key).name).read_bytes() == original
    assert (evidence / "evidence" / archive.name / first._path("source-windows", key).name).read_bytes() == original
    assert not (evidence / ".checkpoint-migration.json").exists()
    # An archived carrier is never a runtime fallback.
    (evidence / "checkpoint" / "manifest.json").write_text("broken")
    assert SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params)).read("extraction-entities", "a" * 64) == {"paid": True}


def test_conflicting_material_set_datasets_preserve_all_originals(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Durable source")
    params = _request(source, tmp_path / "unused")["params"]
    canonical = tmp_path / "project"
    key = {"sourceId": "source-1", "materialRevision": params["sources"][0]["materialRevision"], "forceOcr": False}
    originals = []
    for index in range(2):
        previous = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate({**params,
            "outputDir": str(canonical / "imports" / f"dataset-{index}")}))
        previous.write("source-windows", key, [[0, index + 1, "D" * (index + 1)]])
        file = previous._path("source-windows", key)
        originals.append((file, file.read_bytes()))
    params["checkpointDir"] = str(canonical / "checkpoint")
    with pytest.raises(SnapshotCheckpointError, match="conflicting completed work"):
        SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(params))
    assert not (canonical / "checkpoint").exists()
    assert all(file.read_bytes() == original for file, original in originals)
