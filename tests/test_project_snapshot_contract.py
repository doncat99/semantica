import io
import json

import pytest
from pydantic import ValidationError

from semantica.project_snapshot_schema import ProjectSnapshot, WorkerRequest, project_snapshot_json_schema
from semantica.project_snapshot_worker import serve


def _snapshot_payload():
    return {
        "project_id": "project-1",
        "document_representations": [
            {
                "id": "repr-1",
                "source_id": "source-1",
                "material_revision_id": "material-rev-1",
                "media_type": "application/pdf",
                "content_hash": "sha256:doc",
                "parser": "docling",
                "parser_version": "1",
                "origin": "mixed",
            }
        ],
        "evidence_spans": [
            {
                "id": "ev-1",
                "representation_id": "repr-1",
                "quote": "Ada",
                "origin": "observed",
                "locator": {
                    "representation_id": "repr-1",
                    "origin": "native",
                    "quote": "Ada",
                    "start_char": 0,
                    "end_char": 3,
                    "quality": "precise",
                },
            }
        ],
        "entities": [
            {
                "id": "entity-ada",
                "canonical_name": "Ada",
                "type": "PERSON",
                "evidence_ids": ["ev-1"],
                "status": "accepted",
            },
            {
                "id": "entity-engine",
                "canonical_name": "Engine",
                "type": "CONCEPT",
                "status": "accepted",
            },
        ],
        "assertions": [
            {
                "id": "assertion-1",
                "subject_id": "entity-ada",
                "predicate": "designed",
                "object": "Engine",
                "object_entity_id": "entity-engine",
                "evidence_ids": ["ev-1"],
                "status": "accepted",
            }
        ],
        "relations": [
            {
                "id": "relation-1",
                "source_entity_id": "entity-ada",
                "target_entity_id": "entity-engine",
                "type": "designed",
                "evidence_ids": ["ev-1"],
                "status": "accepted",
            }
        ],
        "identity_decisions": [
            {
                "id": "decision-1",
                "decision_type": "accept",
                "to_entity_id": "entity-ada",
                "reason": "single mention accepted",
                "evidence_ids": ["ev-1"],
            }
        ],
        "communities": [
            {"id": "community-1", "level": 0, "title": "Design", "entity_ids": ["entity-ada", "entity-engine"]}
        ],
        "topics": [
            {"id": "topic-1", "title": "Design history", "community_ids": ["community-1"], "evidence_ids": ["ev-1"]}
        ],
        "model_receipts": [
            {
                "id": "model-1",
                "operation": "community_report",
                "provider": "test",
                "model": "deterministic",
                "input_digest": "sha256:input",
                "output_digest": "sha256:output",
            }
        ],
        "reports": [
            {
                "id": "report-1",
                "report_type": "community",
                "title": "Design",
                "summary": "Ada is connected to the engine.",
                "community_id": "community-1",
                "evidence_ids": ["ev-1"],
                "model_receipt_ids": ["model-1"],
            }
        ],
        "conflicts": [
            {"id": "conflict-1", "conflict_type": "identity", "reason": "same label appears twice"}
        ],
        "retrieval_manifests": [
            {
                "id": "retrieval-1",
                "retrieval_type": "graph",
                "artifact_hash": "sha256:retrieval",
                "record_count": 1,
                "evidence_ids": ["ev-1"],
                "model_receipt_ids": ["model-1"],
            }
        ],
        "change_delta": {
            "base_snapshot_id": "snapshot-base",
            "changed_representation_ids": ["repr-1"],
            "added_ids": ["entity-ada"],
            "affected_report_ids": ["report-1"],
            "affected_retrieval_manifest_ids": ["retrieval-1"],
            "reason": "initial import",
        },
    }


def test_project_snapshot_contract_covers_kernel_sections():
    schema = project_snapshot_json_schema()
    props = schema["properties"]
    for key in [
        "document_representations",
        "evidence_spans",
        "entities",
        "assertions",
        "relations",
        "identity_decisions",
        "communities",
        "topics",
        "reports",
        "conflicts",
        "retrieval_manifests",
        "change_delta",
        "model_receipts",
    ]:
        assert key in props


def test_project_snapshot_validates_cross_references():
    payload = _snapshot_payload()
    payload["snapshot_id"] = "snapshot-1"

    snapshot = ProjectSnapshot.model_validate(payload)

    assert snapshot.protocol == "semantica.project-snapshot.v1"
    assert snapshot.relations[0].source_entity_id == "entity-ada"


def test_project_snapshot_rejects_unknown_evidence_reference():
    payload = _snapshot_payload()
    payload["snapshot_id"] = "snapshot-1"
    payload["entities"][0]["evidence_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="unknown evidence"):
        ProjectSnapshot.model_validate(payload)


def test_jsonl_worker_builds_snapshot_without_fallback():
    request = {
        "protocol": "semantica.project-worker.v1",
        "id": "req-1",
        "method": "build_project_snapshot",
        "params": _snapshot_payload(),
    }
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())

    assert response["protocol"] == "semantica.project-worker.v1"
    assert response["ok"] is True
    assert response["result"]["snapshot_id"].startswith("snapshot:")
    assert response["result"]["document_representations"][0]["id"] == "repr-1"
    assert response["result"]["model_receipts"][0]["operation"] == "community_report"


def test_jsonl_worker_schema_method_returns_schema():
    request = {"protocol": "semantica.project-worker.v1", "id": "schema-1", "method": "schema"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())

    assert response["ok"] is True
    assert "document_representations" in response["result"]["properties"]


def test_worker_request_rejects_unknown_method():
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate({"id": "bad", "method": "fallback"})
