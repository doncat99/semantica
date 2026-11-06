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
                'generationId': 'generation-1'}, 'model_receipts': [],
            'native_indexes': {'keyword': {'store_id': 'keyword'}, 'semantic': {'store_id': 'vector'}}})
    response = semantic_worker._dispatch(WorkerRequest.model_validate({
        'id': 'build', 'protocol': semantic_worker.PROTOCOL,
        'method': 'build_semantic_artifacts', 'params': {}}), None)
    assert response['result'] == {'publication': publication,
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
