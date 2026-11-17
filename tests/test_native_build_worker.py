"""Worker transports native publication identity without aggregate artifacts."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from semantica.semantic_artifact_schema import WorkerRequest
from semantica import semantic_publication_builder, semantic_worker


def test_build_worker_returns_pending_native_publication_without_materialization(monkeypatch):
    monkeypatch.setattr(semantic_worker.SemanticArtifactBuildRequest, 'model_validate',
        lambda value: SimpleNamespace())
    publication = {'project': 'project-1', 'generation': 'generation-1', 'state': 'pending'}
    monkeypatch.setattr(semantic_publication_builder, 'build_semantic_artifacts',
        lambda request, progress: {'publication': publication,
            'semantic_store': {'path': '/native/store', 'projectId': 'project-1',
                'generationId': 'generation-1'}, 'completion_input': 'sha256:' + 'a' * 64, 'model_receipts': [],
            'native_indexes': {'keyword': {'store_id': 'keyword'}, 'semantic': {'store_id': 'vector'}}})
    response = semantic_worker._dispatch(WorkerRequest.model_validate({
        'id': 'build', 'protocol': semantic_worker.PROTOCOL,
        'method': 'build_semantic_artifacts', 'params': {}}), None)
    assert response['result'] == {'publication': publication,
        'completionInput': 'sha256:' + 'a' * 64,
        'nativeIndexes': {'keyword': {'store_id': 'keyword'}, 'semantic': {'store_id': 'vector'}},
        'semanticStore': {'path': '/native/store', 'project': 'project-1',
            'generation': 'generation-1'}, 'relayReceipts': {'embedding': [], 'model': []},
        'relayReceiptManifest': []}


def test_schema_does_not_offer_retired_aggregate_validation():
    response = semantic_worker._dispatch(WorkerRequest.model_validate({
        'id': 'schema', 'protocol': semantic_worker.PROTOCOL, 'method': 'schema', 'params': {}}), None)
    assert set(response['result']) == {'build_request'}
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate({'id': 'old', 'protocol': semantic_worker.PROTOCOL,
            'method': 'validate_artifact', 'params': {}})
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate({'id': 'old', 'protocol': semantic_worker.PROTOCOL,
            'method': 'generate_reading_reports', 'params': {}})


def test_activation_protocol_is_explicit_and_validated(monkeypatch):
    from semantica import semantic_artifact_schema
    activation = {'projectId': 'project-1', 'generation': 'generation-1',
        'nativeStorePath': '/native/store', 'completionInput': 'sha256:' + 'a' * 64,
        'nativeIndexes': {'keyword': {}, 'semantic': {}}}
    monkeypatch.setattr(semantic_worker, '_activate_publication', lambda value: {
        'publication': {'project': value.project_id, 'generation': value.generation, 'state': 'ready'}})
    response = semantic_worker._dispatch(WorkerRequest.model_validate({
        'id': 'activate', 'protocol': semantic_worker.PROTOCOL,
        'method': 'activate_publication', 'params': activation}), None)
    assert response['result']['publication']['state'] == 'ready'
    with pytest.raises(ValidationError):
        semantic_artifact_schema.SemanticPublicationActivationRequest.model_validate(
            {**activation, 'nativeIndexes': {'keyword': {}}})


def test_activation_dispatches_exact_generation_to_native_owner(monkeypatch):
    calls = []
    monkeypatch.setattr(semantic_worker, '_activate_publication', lambda request: calls.append(request) or {
        'publication': {'project': request.project_id, 'generation': request.generation, 'state': 'ready'}})
    response = semantic_worker._dispatch(WorkerRequest.model_validate({
        "id": "activate", "protocol": semantic_worker.PROTOCOL,
        "method": "activate_publication", "params": {
            "projectId": "project-1", "generation": "generation-1",
            "nativeStorePath": "/native/store", "completionInput": "sha256:" + "a" * 64,
            "nativeIndexes": {"keyword": {}, "semantic": {}}}}), None)
    assert response["result"]["publication"]["state"] == "ready"
    assert len(calls) == 1
    assert (calls[0].project_id, calls[0].generation) == ("project-1", "generation-1")


@pytest.mark.parametrize("params", [
    {},
    {"projectId": "p", "generation": "g", "nativeStorePath": "relative",
     "nativeIndexes": {"keyword": {}, "semantic": {}}},
    {"projectId": "p", "generation": "g", "nativeStorePath": "/store",
     "nativeIndexes": {"keyword": {"receipt": {}}, "semantic": {}}},
])
def test_activation_rejects_incomplete_identity_or_receipts(monkeypatch, params):
    with pytest.raises(ValueError):
        semantic_worker._dispatch(WorkerRequest.model_validate({
            "id": "activate", "protocol": semantic_worker.PROTOCOL,
            "method": "activate_publication", "params": params}), None)

