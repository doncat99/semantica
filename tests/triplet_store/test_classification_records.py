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


def test_classification_completion_uses_classification_binding_not_extraction_stage(tmp_path):
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.triplet_store.extraction_records import F, _hash
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / 'facts')
    store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'],
        accepted_digest='paid', receipts=[receipt])
    owner = ClassificationRecords(store, binding)
    ox = store._oxigraph
    # Classification's persisted contract has its own binding, not entities/relations stage.
    for field in ('extractionStage', 'operationDigest'):
        for quad in list(store.store.quads_for_pattern(owner.operation, ox.NamedNode(F + field), None, owner.graph)):
            store.store.remove(quad)
    facts = list(store.store.quads_for_pattern(owner.operation, None, None, owner.graph))
    store.store.add(ox.Quad(owner.operation, ox.NamedNode(F + 'operationDigest'), ox.Literal(_hash(facts)), owner.graph))
    before = set(store.store)
    assert owner.receipt()['accepted_digest'] == 'paid'
    assert owner.audit() == owner.receipt()
    assert store.read_classification(binding, profile=profile, allowed_evidence_ids=['evidence-1']) == value
    assert set(store.store) == before


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


def test_reduction_pages_distinct_items_and_preserves_evidence(tmp_path):
    from semantica.triplet_store.classification_records import ClassificationRecords
    profile, binding, receipt, value = inputs()
    profile_data = profile.model_dump(mode='json', by_alias=True)
    profile_data['dimensions'][1]['vocabulary'].extend([
        {'id': 'private', 'label': 'Private'}, {'id': 'research', 'label': 'Research'},
    ])
    profile = ClassificationProfile.model_validate(profile_data)
    binding['taxonomy'] = stable_digest(profile.model_dump(mode='json', by_alias=True))
    value = SourceClassification.model_validate(dict(source_id='source', profile_id='taxonomy', profile_version='1',
        assignments=[dict(dimension_id='audience', item_id=item, confidence=.8, evidence_ids=['evidence-1'])
            for item in ('public', 'private', 'research')], unclassified_dimension_ids=['sector'], model_receipt_ids=['receipt']))
    store = OxigraphStore(tmp_path / 'facts')
    batch = ClassificationRecords(store, binding)
    batch.adopt(value, profile=profile, allowed_evidence_ids=['evidence-1'], accepted_digest='paid', receipts=[receipt])
    reduction = ClassificationRecords(store, dict(binding, context_digest='reduced'))
    reduction.adopt_reduction([batch.operation.value], profile=profile)
    first = reduction.read_reduced_dimension('audience', limit=1)
    second = reduction.read_reduced_dimension('audience', after=first['nextCursor'], limit=1)
    third = reduction.read_reduced_dimension('audience', after=second['nextCursor'], limit=1)
    assert [page['assignments'][0]['itemId'] for page in (first, second, third)] == ['private', 'public', 'research']
    assert all(page['assignments'][0]['evidenceRefs'] == ['evidence-1'] for page in (first, second, third))
    assert third['nextCursor'] is None
    assert reduction.read_reduced_dimension('audience', after='research', limit=1) == dict(
        dimensionId='audience', unclassified=False, assignments=[], nextCursor=None)
    store.close()


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


def test_classification_offline_recipe_rebind_preserves_paid_nodes_after_restart(tmp_path):
    from semantica.triplet_store.classification_records import ClassificationRecords
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / 'facts')
    store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'],
                               accepted_digest='paid', receipts=[receipt])
    original = ClassificationRecords(store, binding)
    operation = original.operation.value
    owned = original.values(original.operation, 'ownedRecord')
    facts = {q for node in owned for q in store.store.quads_for_pattern(node, None, None, original.graph)}
    target = dict(binding, recipe='semantic-producer-recipe')
    result = store.rebind_classification(binding, target)
    assert result['operation_id'] == operation
    assert store.classification_operation_id(target) == operation
    assert original.one(original.operation, 'paidRecipe') == binding['recipe']
    assert store.classification_receipt(binding) is None
    assert store.rebind_classification(binding, target) == result
    assert facts == {q for node in owned for q in store.store.quads_for_pattern(node, None, None, original.graph)}
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.read_classification(target, profile=profile, allowed_evidence_ids=['evidence-1']) == value
    assert store.read_classification_receipts(target) == [receipt]
    assert store.classification_receipt(target)['accepted_digest'] == 'paid'
    assert store.classification_receipt(binding) is None
    store.close()


def test_classification_offline_rebind_admits_legacy_only_through_explicit_migration(tmp_path):
    from semantica.triplet_store.classification_records import ClassificationRecords
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / 'facts')
    store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'],
                               accepted_digest='paid', receipts=[receipt])
    original = ClassificationRecords(store, binding)
    store.store.clear_graph(original.index_graph)
    assert store.classification_receipt(binding) is None
    with pytest.raises(ProcessingError, match='offline identity migration'):
        store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'],
                                   accepted_digest='paid', receipts=[receipt])
    with pytest.raises(ProcessingError, match='only recipe'):
        store.rebind_classification(binding, dict(binding, recipe='new', context_digest='wrong-context'))
    target = dict(binding, recipe='new')
    store.rebind_classification(binding, target)
    assert store.read_classification(target, profile=profile, allowed_evidence_ids=['evidence-1']) == value
    store.close()


@pytest.mark.parametrize('defect', ['stale-handle', 'wrong-binding', 'orphan'])
def test_classification_identity_proofs_fail_closed(tmp_path, defect):
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.triplet_store.extraction_records import F, ExtractionIdentityStaleError
    profile, binding, receipt, value = inputs()
    store = OxigraphStore(tmp_path / 'facts')
    store.adopt_classification(binding, value, profile=profile, allowed_evidence_ids=['evidence-1'],
        accepted_digest='paid', receipts=[receipt])
    original = ClassificationRecords(store, binding)
    accepted = original.receipt()
    current = dict(binding, recipe='current-producer')
    if defect == 'stale-handle':
        store.rebind_classification(binding, current)
        assert store.classification_receipt(current) == accepted
        with pytest.raises(ExtractionIdentityStaleError):
            original.receipt()
    elif defect == 'wrong-binding':
        forged = ClassificationRecords(store, current)
        store.store.add(store._oxigraph.Quad(forged.logical,
            store._oxigraph.NamedNode(F+'physicalOperation'), original.operation, forged.index_graph))
        assert original.receipt() == accepted
        with pytest.raises(ExtractionIdentityStaleError, match='binding differs'):
            store.classification_receipt(current)
    else:
        store.store.update('DELETE WHERE { GRAPH ' + str(original.graph)
            + ' { ' + str(original.operation) + ' ?p ?o } }')
        with pytest.raises(ProcessingError, match='missing paid operation'):
            store.classification_receipt(binding)
    store.close()


def test_source_completion_survives_restart_and_rejects_corrupt_link(tmp_path):
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.triplet_store.extraction_records import F
    profile,binding,receipt,value=inputs()
    store=OxigraphStore(tmp_path/'facts')
    batch=ClassificationRecords(store,binding)
    batch.adopt(value,profile=profile,allowed_evidence_ids=['evidence-1'],accepted_digest='paid',receipts=[receipt])
    reduction=ClassificationRecords(store,dict(binding,context_digest='reduced'))
    reduction.adopt_reduction([batch.operation.value],profile=profile)
    source={key:value for key,value in binding.items() if key!='context_digest'}
    expected=reduction.operation.value
    assert ClassificationRecords.source_completion(store,source,reduction=reduction)==expected
    before=set(store.store)
    store.close()
    store=OxigraphStore(tmp_path/'facts')
    assert ClassificationRecords.source_completion(store,source)==expected
    assert set(store.store)==before
    assert ClassificationRecords.source_completion(store,dict(source,model='another')) is None
    quad=next(store.store.quads_for_pattern(None,store._oxigraph.NamedNode(F+'completedReduction'),None,None))
    store.store.remove(quad)
    store.store.add(store._oxigraph.Quad(quad.subject,quad.predicate,store._oxigraph.Literal('broken'),quad.graph_name))
    with pytest.raises(ProcessingError):
        ClassificationRecords.source_completion(store,source)
    store.close()
