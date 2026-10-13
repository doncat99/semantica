"""Package upgrades preserve results when the processing contract is unchanged."""
from copy import deepcopy

import pytest

from semantica.project_checkpoint import _resume_compatible


def inputs():
    return {"protocol": "semantica.project-checkpoint.v1", "projectId": "project-1",
            "inputRevision": "old-input", "sources": [{"actualDigest": "source-digest"}],
            "baseSnapshot": None, "documentProcessing": {"mode": "local"},
            "recipe": {"id": "model", "version": "1"},
            "release": {"artifactDigest": "old-package", "schemaDigest": "schema",
                        "mediaTypes": {"semantic-graph": "graph"}},
            "relays": {"model": {"modelId": "model", "bindingId": "default", "maxOutputTokens": 32768}}}


def test_package_upgrade_preserves_results_and_original_manifest():
    previous = inputs()
    original = deepcopy(previous)
    current = deepcopy(previous)
    current["release"]["artifactDigest"] = "new-package"
    current["inputRevision"] = "new-input"
    assert _resume_compatible(previous, current)
    assert previous == original


@pytest.mark.parametrize("field,value", [
    ("sources", [{"actualDigest": "different-source"}]),
    ("recipe", {"id": "model", "version": "2"}),
    ("projectId", "different-project"),
    ("documentProcessing", {"mode": "remote"}),
    ("baseSnapshot", {"artifactDigest": "new-snapshot"}),
    ("relays", {"model": {"modelId": "other", "bindingId": "default", "maxOutputTokens": 32768}}),
])
def test_package_upgrade_does_not_admit_changed_processing_inputs(field, value):
    previous = inputs()
    current = deepcopy(previous)
    current["release"]["artifactDigest"] = "new-package"
    current["inputRevision"] = "new-input"
    current[field] = value
    assert not _resume_compatible(previous, current)


def test_package_upgrade_rejects_changed_schema():
    previous = inputs()
    current = deepcopy(previous)
    current["release"] = {**current["release"], "artifactDigest": "new-package", "schemaDigest": "new-schema"}
    assert not _resume_compatible(previous, current)


def test_unchanged_package_rejects_changed_input_revision():
    previous = inputs()
    current = {**previous, "inputRevision": "unknown-change"}
    assert not _resume_compatible(previous, current)
