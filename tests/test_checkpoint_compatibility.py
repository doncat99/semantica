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

LEGACY_SCHEMA = 'sha256:8a854744a4d9c27c911509b010fd5c1330ae49b63d64313f21ca405c3311e93b'
REFLEXIVITY_SCHEMA = 'sha256:300ace367257438ced05c790042721db3da818f5f94c0ed3dab5a5290e90801a'

def test_additive_reflexivity_schema_preserves_completed_stages():
    previous = inputs()
    previous['release']['schemaDigest'] = LEGACY_SCHEMA
    current = deepcopy(previous)
    current['release'].update(artifactDigest='new-package', schemaDigest=REFLEXIVITY_SCHEMA)
    current['inputRevision'] = 'new-input'
    assert _resume_compatible(previous, current)
    current['recipe']['version'] = '2'
    assert not _resume_compatible(previous, current)

def test_reflexivity_schema_migration_has_exact_direction_and_shape():
    from semantica.semantic_artifact_schema import artifact_schema_compatible, semantic_artifact_json_schema, stable_digest
    assert stable_digest(semantic_artifact_json_schema()) == REFLEXIVITY_SCHEMA
    assert artifact_schema_compatible(LEGACY_SCHEMA, REFLEXIVITY_SCHEMA)
    assert not artifact_schema_compatible(REFLEXIVITY_SCHEMA, LEGACY_SCHEMA)
    assert not artifact_schema_compatible(LEGACY_SCHEMA, 'future-schema')


def test_explicit_processing_contract_admits_only_known_legacy_and_rejects_semantic_changes():
    from semantica.project_checkpoint import LEGACY_PROCESSING_CONTRACTS
    previous = inputs()
    previous["release"]["schemaDigest"] = LEGACY_SCHEMA
    current = deepcopy(previous)
    current["release"].update(artifactDigest="new-package", schemaDigest=REFLEXIVITY_SCHEMA)
    current["inputRevision"] = "new-input"
    current["processingContracts"] = deepcopy(LEGACY_PROCESSING_CONTRACTS)
    assert _resume_compatible(previous, current)
    current["processingContracts"]["chunkExtraction"] = "changed-prompt-v2"
    assert not _resume_compatible(previous, current)
    current["processingContracts"] = deepcopy(LEGACY_PROCESSING_CONTRACTS)
    previous["release"]["schemaDigest"] = "unknown-schema"
    assert not _resume_compatible(previous, current)


@pytest.mark.parametrize('explicit', [False, True])
def test_text_only_checkpoints_cannot_resume_structured_binding(explicit):
    from semantica.project_checkpoint import PROCESSING_CONTRACTS, LEGACY_PROCESSING_CONTRACTS
    previous = inputs()
    previous['release']['schemaDigest'] = LEGACY_SCHEMA
    if explicit:
        previous['processingContracts'] = deepcopy(LEGACY_PROCESSING_CONTRACTS)
    current = deepcopy(previous)
    current['release'].update(artifactDigest='new-package', schemaDigest=REFLEXIVITY_SCHEMA)
    current['inputRevision'] = 'new-input'
    current['processingContracts'] = deepcopy(PROCESSING_CONTRACTS)
    assert not _resume_compatible(previous, current)
