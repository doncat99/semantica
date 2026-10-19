from copy import deepcopy

import pytest

from semantica.semantic_artifact_builder import extend_semantic_snapshot, reconcile_qualified_facts
from semantica.semantic_artifact_schema import SemanticArtifact
from tests.test_semantic_artifact_contract import _snapshot_payload


def observation(identifier, value, evidence_id):
    data = _snapshot_payload()
    for field in ('entities', 'assertions', 'relations', 'communities', 'topics',
                  'conflicts', 'entity_mentions', 'identity_registry', 'source_relations',
                  'source_classifications', 'retrieval_manifests'):
        data[field] = []
    data['snapshot_id'] = identifier
    data['base_snapshot_id'] = None
    data['change_delta'] = {}
    data['created_at'] = '2026-10-19T00:00:00Z'
    for item in [*data['document_representations'], *data['model_receipts']]:
        item['created_at'] = data['created_at']
    data['entities'] = [{'id': 'entity:company', 'type': 'Company', 'canonical_name': 'Example'}]
    span = deepcopy(data['evidence_spans'][0])
    span['id'] = evidence_id
    data['evidence_spans'] = [span]
    data['assertions'] = [{'id': 'input:' + evidence_id, 'subject_id': 'entity:company',
        'predicate': 'website', 'object': value, 'qualifiers': {'polarity': 'positive'},
        'evidence_ids': [evidence_id], 'status': 'accepted'}]
    artifact = SemanticArtifact.model_validate(data)
    artifact.assertions = reconcile_qualified_facts(artifact.project_id, artifact.assertions, [])[0]
    return artifact


def test_observation_replay_cannot_mask_different_content_or_withdrawal():
    first = observation('snapshot:1', 'one', 'evidence:1')
    second = observation('snapshot:2', 'two', 'evidence:2')
    result = extend_semantic_snapshot(first, second, functional_predicates=['website'])
    assert len(result.conflicts) == 1
    assert extend_semantic_snapshot(result, second, functional_predicates=['website']) == result
    changed = second.model_copy(deep=True)
    changed.entities[0].canonical_name = 'Different'
    with pytest.raises(ValueError, match='immutable_observation_id_reused'):
        extend_semantic_snapshot(result, changed, functional_predicates=['website'])


def test_withdrawal_retains_evidence_and_resolves_derived_conflict():
    first = observation('snapshot:1', 'one', 'evidence:1')
    second = observation('snapshot:2', 'two', 'evidence:2')
    conflicted = extend_semantic_snapshot(first, second, functional_predicates=['website'])
    third = observation('snapshot:3', 'three', 'evidence:3')
    result = extend_semantic_snapshot(conflicted, third, functional_predicates=['website'],
                                     retract_evidence_ids=['evidence:1', 'evidence:2'])
    assert not result.conflicts
    assert len(result.evidence_spans) == 3
    assert [(item.object, item.status) for item in result.assertions if item.status != 'retracted'] == [('three', 'accepted')]
    assert first.assertions[0].status == 'accepted'
    with pytest.raises(ValueError, match='withdrawn_evidence_not_found'):
        extend_semantic_snapshot(first, second, retract_evidence_ids=['absent'])
    with pytest.raises(ValueError, match='withdrawn_evidence_reintroduced'):
        extend_semantic_snapshot(result, first)


def test_initial_observation_replay_after_withdrawal_is_inert():
    first = observation('snapshot:initial', 'one', 'evidence:initial')
    initial = extend_semantic_snapshot(None, first, functional_predicates=['website'])
    assert extend_semantic_snapshot(initial, first, functional_predicates=['website']) == initial
    second = observation('snapshot:new', 'two', 'evidence:new')
    result = extend_semantic_snapshot(initial, second, functional_predicates=['website'],
                                     retract_evidence_ids=['evidence:initial'])
    assert extend_semantic_snapshot(result, first, functional_predicates=['website']) == result
    assert first.metadata.get('applied_observations') is None
    changed = first.model_copy(deep=True)
    changed.assertions[0].object = 'changed'
    with pytest.raises(ValueError, match='immutable_observation_id_reused'):
        extend_semantic_snapshot(result, changed, functional_predicates=['website'])
