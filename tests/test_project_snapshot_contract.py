import io
import json

import pytest
from pydantic import ValidationError

from semantica.project_snapshot_schema import (
    ProjectSnapshot,
    ProjectSnapshotBuildRequest,
    WorkerRequest,
    project_snapshot_json_schema,
)
from semantica.project_snapshot_worker import serve

H1 = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64
H4 = "sha256:" + "4" * 64
H5 = "sha256:" + "5" * 64
H6 = "sha256:" + "6" * 64
H7 = "sha256:" + "7" * 64
H8 = "sha256:" + "8" * 64


def _snapshot_payload():
    return {
        "snapshot_id": "snapshot:one",
        "project_id": "project-1",
        "artifact_manifest": [
            {"id": "artifact-repr", "artifact_type": "representation", "artifact_ref": "object://repr", "artifact_hash": H1},
            {"id": "artifact-retrieval", "artifact_type": "retrieval", "artifact_ref": "object://retrieval", "artifact_hash": H2, "depends_on": ["artifact-repr"]},
        ],
        "lineage": {
            "schema_digest": H3,
            "recipe_id": "recipe:default",
            "recipe_digest": H4,
            "rule_version": "rules-v1",
            "rule_digest": H5,
            "ontology_version": "ontology-v1",
            "ontology_digest": H6,
            "model_receipt_ids": ["model-1"],
        },
        "document_representations": [
            {
                "id": "repr-1",
                "source_id": "source-1",
                "material_revision_id": "b3-" + "7" * 64,
                "input_revision": "b3-" + "7" * 64,
                "media_type": "application/pdf",
                "content_hash": "b3-" + "7" * 64,
                "parser": "docling",
                "parser_version": "1",
                "recipe_id": "recipe:default",
                "recipe_digest": H4,
                "origin": "mixed",
                "artifact_ref_id": "artifact-repr",
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
            {"id": "entity-ada", "canonical_name": "Ada", "type": "PERSON", "evidence_ids": ["ev-1"], "status": "accepted"},
            {"id": "entity-engine", "canonical_name": "Engine", "type": "CONCEPT", "status": "accepted"},
        ],
        "assertions": [
            {"id": "assertion-1", "subject_id": "entity-ada", "predicate": "designed", "object": "Engine", "object_entity_id": "entity-engine", "evidence_ids": ["ev-1"], "status": "accepted"}
        ],
        "relations": [
            {"id": "relation-1", "source_entity_id": "entity-ada", "target_entity_id": "entity-engine", "type": "designed", "evidence_ids": ["ev-1"], "status": "accepted"}
        ],
        "identity_decisions": [
            {"id": "decision-1", "decision_type": "accept", "to_entity_id": "entity-ada", "reason": "single mention accepted", "evidence_ids": ["ev-1"]}
        ],
        "communities": [
            {"id": "community-1", "level": 0, "title": "Design", "entity_ids": ["entity-ada", "entity-engine"], "relation_ids": ["relation-1"]}
        ],
        "topics": [
            {"id": "topic-1", "title": "Design history", "community_ids": ["community-1"], "entity_ids": ["entity-ada"], "assertion_ids": ["assertion-1"], "evidence_ids": ["ev-1"]}
        ],
        "model_receipts": [
            {"id": "model-1", "operation": "community_report", "provider": "test", "model": "deterministic", "input_digest": H1, "output_digest": H2}
        ],
        "conflicts": [
            {"id": "conflict-1", "conflict_type": "identity", "reason": "same label appears twice", "entity_ids": ["entity-ada"]}
        ],
        "retrieval_manifests": [
            {"id": "retrieval-1", "retrieval_type": "graph", "artifact_hash": H8, "artifact_ref_id": "artifact-retrieval", "record_count": 1, "entity_ids": ["entity-ada"], "relation_ids": ["relation-1"], "community_ids": ["community-1"], "evidence_ids": ["ev-1"], "model_receipt_ids": ["model-1"]}
        ],
        "reports": [
            {"id": "report-1", "report_type": "community", "title": "Design", "summary": "Ada is connected to the engine.", "community_id": "community-1", "topic_id": "topic-1", "conflict_id": "conflict-1", "retrieval_manifest_id": "retrieval-1", "evidence_ids": ["ev-1"], "model_receipt_ids": ["model-1"], "content_hash": H2}
        ],
        "change_delta": {"base_snapshot_id": "snapshot-base", "changed_representation_ids": ["repr-1"], "added_ids": ["entity-ada"], "affected_report_ids": ["report-1"], "affected_retrieval_manifest_ids": ["retrieval-1"], "reason": "initial import"},
    }


def _build_request_payload():
    return {
        "projectId": "project-1",
        "baseSnapshot": {"snapshotId": "snapshot:base", "snapshotPath": "/tmp/base.json", "artifactDigest": H8, "schemaDigest": H3},
        "inputRevision": H1,
        "outputDir": "/tmp/semantica-output",
        "sources": [{"filePath": "/tmp/source.pdf", "materialRevision": "b3-" + "7" * 64, "mimeType": "application/pdf", "name": "source.pdf", "sourceId": "source-1"}],
        "recipe": {"forceOcrSourceIds": [], "id": "deterministic", "version": "1"},
        "relays": {
            "embedding": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/embeddings", "capability": "knowledge.snapshot.embed", "modelId": "embedding-1", "receipts": "required"},
            "model": {"authorizationEnv": "OPENAI_API_KEY", "baseUrl": "http://127.0.0.1:9021/v1/chat/completions", "capability": "knowledge.snapshot.generate", "modelId": "model-1", "receipts": "required"},
        },
        "release": {"artifactDigest": H2, "schemaDigest": H3, "mediaTypes": {"document-representation": "application/vnd.semantica.document-representation+json", "retrieval-index": "application/vnd.semantica.retrieval+json", "snapshot": "application/vnd.semantica.project-snapshot+json"}},
    }


def test_project_snapshot_contract_covers_kernel_sections():
    props = project_snapshot_json_schema()["properties"]
    for key in ["lineage", "artifact_manifest", "document_representations", "evidence_spans", "entities", "assertions", "relations", "identity_decisions", "communities", "topics", "reports", "conflicts", "retrieval_manifests", "change_delta", "model_receipts"]:
        assert key in props


def test_project_snapshot_validates_complete_cross_references():
    snapshot = ProjectSnapshot.model_validate(_snapshot_payload())
    assert snapshot.protocol == "semantica.project-snapshot.v1"
    assert snapshot.id == "snapshot:one"
    assert snapshot.model_dump()["snapshot_id"] == "snapshot:one"
    assert snapshot.reports[0].retrieval_manifest_id == "retrieval-1"


def test_project_snapshot_rejects_bad_hash_and_duplicate_ids():
    bad = _snapshot_payload()
    bad["document_representations"][0]["content_hash"] = "not-a-hash"
    with pytest.raises(ValidationError, match="b3-"):
        ProjectSnapshot.model_validate(bad)

    dup = _snapshot_payload()
    dup["entities"].append(dict(dup["entities"][0]))
    with pytest.raises(ValidationError, match="duplicate entity id"):
        ProjectSnapshot.model_validate(dup)


def test_project_snapshot_rejects_unavailable_or_empty_locator():
    bad = _snapshot_payload()
    locator = bad["evidence_spans"][0]["locator"]
    locator.pop("start_char")
    locator.pop("end_char")
    with pytest.raises(ValidationError, match="locator requires"):
        ProjectSnapshot.model_validate(bad)


def test_project_snapshot_rejects_unknown_community_topic_conflict_retrieval_refs():
    bad = _snapshot_payload()
    bad["retrieval_manifests"][0]["community_ids"] = ["missing-community"]
    with pytest.raises(ValidationError, match="unknown community"):
        ProjectSnapshot.model_validate(bad)

    bad = _snapshot_payload()
    bad["reports"][0]["topic_id"] = "missing-topic"
    with pytest.raises(ValidationError, match="unknown topic_id"):
        ProjectSnapshot.model_validate(bad)


def test_build_request_accepts_sources_not_semantic_objects():
    request = ProjectSnapshotBuildRequest.model_validate(_build_request_payload())
    assert request.sources[0].source_id == "source-1"
    assert request.base_snapshot.artifact_digest == H8

    bad = _build_request_payload()
    bad["entities"] = [{"id": "host-entity"}]
    with pytest.raises(ValidationError):
        ProjectSnapshotBuildRequest.model_validate(bad)


def test_build_request_rejects_unsafe_release_and_source_boundaries():
    bad = _build_request_payload()
    bad["sources"][0]["filePath"] = "relative/source.pdf"
    with pytest.raises(ValidationError, match="absolute"):
        ProjectSnapshotBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["sources"][0]["mimeType"] = "pdf"
    with pytest.raises(ValidationError, match="MIME type"):
        ProjectSnapshotBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["release"]["artifactDigest"] = "not-a-digest"
    with pytest.raises(ValidationError, match="sha256"):
        ProjectSnapshotBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["authorizationEnv"] = "secret-token-value"
    with pytest.raises(ValidationError, match="environment variable name"):
        ProjectSnapshotBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["baseUrl"] = "https://api.example.com/v1"
    with pytest.raises(ValidationError, match="loopback"):
        ProjectSnapshotBuildRequest.model_validate(bad)

    bad = _build_request_payload()
    bad["relays"]["model"]["baseUrl"] = "http://127.0.0.1:9021/v1/responses"
    with pytest.raises(ValidationError, match="chat/completions"):
        ProjectSnapshotBuildRequest.model_validate(bad)


def test_jsonl_worker_build_requires_a_real_source_file():
    request = {"protocol": "semantica.project-worker.v1", "id": "req-1", "method": "build_project_snapshot", "params": _build_request_payload()}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is False
    assert response["error"]["type"] in {"SnapshotBuildError", "FileNotFoundError"}


def test_jsonl_worker_validate_snapshot_method():
    request = {"protocol": "semantica.project-worker.v1", "id": "validate-1", "method": "validate_snapshot", "params": _snapshot_payload()}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert response["result"] == {"valid": True, "snapshot_id": "snapshot:one"}


def test_jsonl_worker_schema_method_returns_snapshot_and_build_request_schema():
    request = {"protocol": "semantica.project-worker.v1", "id": "schema-1", "method": "schema"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert "document_representations" in response["result"]["snapshot"]["properties"]
    assert "sources" in response["result"]["build_request"]["properties"]


def test_worker_request_rejects_unknown_method():
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate({"id": "bad", "method": "fallback"})
