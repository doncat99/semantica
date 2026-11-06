"""Classifications adopt typed fields into the same native RDF owner."""
import pytest

from semantica.semantic_artifact_schema import ClassificationProfile, SourceClassification, stable_digest
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError


def inputs():
    profile = ClassificationProfile.model_validate(dict(id="taxonomy", version="1", label="Taxonomy", description="source categories", dimensions=[dict(id="sector", label="Sector", cardinality="single", vocabulary=[dict(id="industry", label="Industry"), dict(id="finance", label="Finance")]), dict(id="audience", label="Audience", cardinality="multi", vocabulary=[dict(id="public", label="Public")])]))
    binding = dict(project="project", source="source", material="material", representation="representation", recipe="recipe", model="model", target="batch-0", taxonomy=stable_digest(profile.model_dump(mode="json", by_alias=True)), context_digest="evidence-identity")
    receipt = dict(id="receipt", operation="source_classification", provider="fixture", model="model", input_digest="input", output_digest="output", parameters=dict(temperature=.1, max_tokens=100), metadata=dict(extraction_stage="classification", usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15)))
    value = SourceClassification.model_validate(dict(source_id="source", profile_id="taxonomy", profile_version="1", assignments=[dict(dimension_id="sector", item_id="industry", confidence=.9, evidence_ids=["evidence-1"])], unclassified_dimension_ids=["audience"], model_receipt_ids=["receipt"]))
    return profile, binding, receipt, value


def test_classification_typed_roundtrip_and_receipts(tmp_path):
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / "facts")
    store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=["evidence-1"], accepted_digest="paid", receipts=[receipt])
    assert store.read_classification(binding, profile=profile, allowed_evidence_ids=["evidence-1"]) == value
    assert store.read_classification_receipts(binding) == [receipt]
    assert store.classification_receipt(binding)["accepted_digest"] == "paid"
    assert all("quote" not in q.predicate.value and "payload" not in q.predicate.value for q in store.store)


def test_native_reduction_references_batches_preserves_conflict_minimum_and_union(tmp_path):
    import gc
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.triplet_store.extraction_records import F
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / 'facts')
    operations = []
    for index, (confidence, evidence) in enumerate([(.9, 'evidence-1'), (.6, 'evidence-2')]):
        batch_binding = dict(binding, context_digest=f'batch-{index}')
        item = value.model_copy(deep=True)
        item.assignments[0].confidence = confidence
        item.assignments[0].evidence_ids = [evidence]
        owner = ClassificationRecords(store, batch_binding)
        owner.adopt(item, profile=profile, allowed_evidence_ids=[evidence], accepted_digest=f'paid-{index}', receipts=[receipt])
        operations.append(owner.operation.value)
    reduced_binding = dict(binding, context_digest='reduced')
    reduction = ClassificationRecords(store, reduced_binding)
    reduction.adopt_reduction(operations, profile=profile)
    result = reduction.read_reduced_dimension('sector')
    assert result['assignments'] == [dict(dimensionId='sector', itemId='industry', confidence=.6,
        evidenceRefs=['evidence-1', 'evidence-2'], method='model')]
    assert reduction.read_reduced_dimension('audience')['unclassified']
    owned = reduction.values(reduction.operation, 'ownedRecord')
    assert not any(q.predicate.value == F+'assignment' for node in owned for q in store.store.quads_for_pattern(node, None, None, None))
    store.close()
    del reduction, owner, store
    gc.collect()
    store = OxigraphStore(tmp_path / 'facts')
    reduction = ClassificationRecords(store, reduced_binding)
    assert reduction.read_reduced_dimension('sector') == result
    batch_binding = dict(binding, context_digest='conflict')
    conflict = value.model_copy(deep=True)
    conflict.assignments[0].item_id = 'finance'
    owner = ClassificationRecords(store, batch_binding)
    owner.adopt(conflict, profile=profile, allowed_evidence_ids=['evidence-1'], accepted_digest='conflict', receipts=[receipt])
    conflicting = ClassificationRecords(store, dict(binding, context_digest='reduced-conflict'))
    conflicting.adopt_reduction(operations + [owner.operation.value], profile=profile)
    assert conflicting.read_reduced_dimension('sector')['unclassified']
    assert conflicting.read_reduced_dimension('sector')['assignments'] == []


@pytest.mark.parametrize("defect", ["taxonomy", "source", "evidence", "cardinality", "unclassified", "receipt-model"])
def test_classification_bad_identity_or_assignment_never_publishes(tmp_path, defect):
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / "facts")
    allowed = ["evidence-1"]
    if defect == "taxonomy":
        binding["taxonomy"] = "wrong"
    elif defect == "source":
        value.source_id = "another"
    elif defect == "evidence":
        allowed = ["another-source-evidence"]
    elif defect == "cardinality":
        value.assignments.append(value.assignments[0].model_copy(update=dict(item_id="finance")))
    elif defect == "unclassified":
        value.unclassified_dimension_ids = []
    else:
        receipt["model"] = "other"
    with pytest.raises(ProcessingError):
        store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=allowed, accepted_digest="paid", receipts=[receipt])
    assert list(store.store) == []
    assert store.classification_receipt(binding) is None
