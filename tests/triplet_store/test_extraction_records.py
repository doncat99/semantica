"""Lossless typed native fields; no retained extraction quote or opaque body."""
import gc

import pytest

from semantica.semantic_extract.schema import ExtractionSpecification
from semantica.semantic_extract.types import Entity, Relation
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.triplet_store.extraction_records import ExtractionRecords, F
from semantica.utils.exceptions import ProcessingError


TEXT = "Acme owns Engine in 2026."
RANGES = [dict(nativeRef='#/document/text', start=0, end=len(TEXT), windowStart=0, windowEnd=len(TEXT))]


def binding():
    return dict(project="p", source="s", material="m", representation="r", recipe="recipe", model="model", specification="spec", parser="parser", grounding="grounding", window_start=100, window_end=100 + len(TEXT))


def entity(name, offset, index):
    return Entity(name, "ORG", offset, offset + len(name), .7, {"mention_id": "mention:" + str(index), "span_occurrence": 0, "model": "model", "provider": "fixture", "extraction_method": "llm_typed"})


def test_extraction_write_and_restart_use_the_same_fact_byte_budget(tmp_path):
    from semantica.triplet_store.extraction_records import MAX_BYTES
    store = OxigraphStore(tmp_path / 'facts')
    bound = binding()
    records = ExtractionRecords(store, bound, 'entities')
    records.grounding(RANGES, TEXT)
    values = [entity('Acme', 0, index) for index in range(280)]
    for index, value in enumerate(values):
        records.write_entity(value, index, TEXT, None)
    records.add(records.operation, 'nativeGroundingDigest', records.grounding(RANGES, TEXT))
    facts = [quad for quad in records.quads if quad.subject != records.operation]
    triple_bytes = len(" .\n".join(str(q.subject) + " " + str(q.predicate) + " " + str(q.object) for q in records.quads).encode())
    quad_bytes = sum(len(str(q).encode()) for q in facts)
    assert triple_bytes < MAX_BYTES - 4096
    assert quad_bytes > MAX_BYTES
    receipt = records.commit(len(values), 'paid')
    assert receipt['count'] == len(values)
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.extraction_receipt(bound, 'entities') == receipt
    assert store.read_extraction(bound, 'entities', text=TEXT, native_ranges=RANGES) == values
    # A real missing fact remains corruption, independently of byte accounting.
    node = ExtractionRecords(store, bound, 'entities').entity_node(values[0])
    missing = next(store.store.quads_for_pattern(node, store._oxigraph.NamedNode(F+'name'), None, None))
    store.store.remove(missing)
    assert store.extraction_receipt(bound, 'entities') == receipt
    with pytest.raises(ProcessingError, match='facts missing or corrupt'):
        store.audit_extraction(bound, 'entities')
    with pytest.raises(ProcessingError, match='missing'):
        store.read_extraction(bound, 'entities', text=TEXT, native_ranges=RANGES)
    store.close()


def test_extraction_atomic_payload_budget_rejects_before_writing(tmp_path):
    store = OxigraphStore(tmp_path / 'facts')
    bound = binding()
    records = ExtractionRecords(store, bound, 'entities')
    records.grounding(RANGES, TEXT)
    for index in range(420):
        records.write_entity(entity('Acme', 0, index), index, TEXT, None)
    with pytest.raises(ProcessingError, match='atomic byte budget'):
        records.commit(420, 'paid')
    assert store.extraction_receipt(bound, 'entities') is None
    assert not list(store.store.quads_for_pattern(None, None, None, records.graph))
    store.close()


def test_native_entity_attributes_profile_and_qualified_relation_roundtrip(tmp_path):
    store = OxigraphStore(tmp_path / "facts")
    spec = ExtractionSpecification.model_validate(dict(id="spec", version="1", entity_types=[dict(name="ORG", description="organization", attributes={
        "tags": dict(type="string_list", description="tags"),
        "amounts": dict(type="number_list", description="amounts"),
        "count": dict(type="integer", description="count"),
        "enabled": dict(type="boolean", description="enabled"),
    })]))
    acme, engine = entity("Acme", 0, 0), entity("Engine", 10, 1)
    acme.attributes = dict(tags=["same", "same", "third"], amounts=[1.25, 2.5], count=9007199254740993, enabled=True)
    acme.metadata["identity_profile"] = dict(description="source identity", evidence=TEXT, evidence_occurrence=0, referent_kind="institution", owner="Acme", instance="2026", evidence_start=0, evidence_end=len(TEXT))
    bound = binding()
    entity_receipt = store.adopt_extraction(bound, "entities", [acme, engine], text=TEXT, native_ranges=RANGES, accepted_digest="entities-paid", extraction_spec=spec)
    restored = store.read_extraction(bound, "entities", text=TEXT, native_ranges=RANGES, extraction_spec=spec)
    assert restored == [acme, engine]
    relation = Relation(acme, "owns", engine, .8, TEXT, dict(provider="fixture", model="model", extraction_method="llm_typed_grounded", subject_id="mention:0", object_id="mention:1", evidence_start=0, evidence_end=len(TEXT), evidence_occurrence=0, qualifiers=dict(polarity="negative", condition="under contract", time="2026", unit="shares", value="10"), supporting_refs=["ref-1", "ref-2"]))
    relation_receipt = store.adopt_extraction(bound, "relations", [relation], text=TEXT, native_ranges=RANGES, accepted_digest="relations-paid")
    assert store.read_extraction(bound, "relations", text=TEXT, native_ranges=RANGES, entities=restored) == [relation]
    persisted = "\n".join(str(quad) for quad in store.store)
    assert TEXT not in persisted
    assert '"9007199254740993"' in persisted
    assert "opaque" not in persisted
    assert "source identity" in persisted

    ids = [ExtractionRecords(store, bound, 'entities').entity_node(value).value for value in (acme, engine)]
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=2)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r', recipe='recipe',
        operation_count=2, operations=[entity_receipt['operation_id'], relation_receipt['operation_id']])])
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:'+str(index),
        representative=identity, members=[identity], selectors=[], member_count=len([identity]), selector_count=len([])) for index, identity in enumerate(ids)])
    relation_id = ExtractionRecords(store, bound, 'relations').node('relation:0').value
    store.stage_publication_facts('p', generation, [dict(id='urn:fact:owns', source='urn:canonical:0',
        target='urn:canonical:1', representative=relation_id, members=[relation_id], member_count=1, status='accepted')])
    indexes = dict(keyword=dict(kind='native-keyword', store_id='kw', recipe_digest='recipe'),
        semantic=dict(kind='native-vector', store_id='vectors', recipe_digest='recipe', space_id='space'))
    store.activate_publication('p', generation, indexes=indexes)
    before = store.read_native_records('p', generation, [ids[0]])[0]
    store.close()
    del store
    gc.collect()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.read_native_records('p', generation, [ids[0]]) == [before]
    restored = store.read_extraction(bound, 'entities', text=TEXT, native_ranges=RANGES, extraction_spec=spec)
    assert restored == [acme, engine]
    assert store.read_extraction(bound, 'relations', text=TEXT, native_ranges=RANGES, entities=restored) == [relation]
    links = store.read_publication_scene('p', generation,
        dict(kind='links', visibleIds=['urn:canonical:0', 'urn:canonical:1']))['links']
    assert len(links) == 1
    fields = links[0]['fields']
    assert fields[F+'polarity'] == [dict(type='iri', value=F+'negative')]
    for key, value in dict(condition='under contract', time='2026', unit='shares', qualifiedValue='10',
            provider='fixture', model='model', extractionMethod='llm_typed_grounded').items():
        assert fields[F+key][0]['value'] == value
    assert {item['value'] for item in fields[F+'supportingRef']} == {'ref-1', 'ref-2'}
    from semantica.triplet_store.publication_records import PublicationRecords
    reader = PublicationRecords(store, 'p')
    assert reader.record_binding(generation, relation_id) == dict(source='s', material='m', representation='r')
    assert reader.record_binding(generation, ids[0]) == dict(source='s', material='m', representation='r')
    profile = before['fields'][F+'identityProfile'][0]['value']
    assert store.read_native_records('p', generation, [profile])[0]['fields'][F+'description'][0]['value'] == 'source identity'
    evidence = fields[F+'evidence'][0]['value']
    evidence_fields = store.read_native_records('p', generation, [evidence])[0]['fields']
    assert evidence_fields[F+'origin'] == [dict(type='iri', value=F+'unknown')]
    native_range = evidence_fields[F+'nativeRange'][0]['value']
    range_fields = store.read_native_records('p', generation, [native_range])[0]['fields']
    assert range_fields[F+'nativeRef'][0]['value'] == '#/document/text'
    assert (range_fields[F+'start'][0]['value'], range_fields[F+'end'][0]['value']) == ('0', str(len(TEXT)))
    publication = [q for q in store.store if q.graph_name.value.startswith('urn:semantica:publication:')]
    assert not any(q.object.value in {TEXT, 'source identity', 'under contract', 'ref-1', 'Acme'} for q in publication)
    assert TEXT not in '\n'.join(str(q) for q in store.store)
    store.withdraw_publication('p', expected_generation=generation)
    with pytest.raises(ProcessingError, match='not ready'):
        store.read_native_records('p', generation, [ids[0]])
    store.close()


def test_unknown_metadata_and_attributes_never_partially_adopt(tmp_path):
    store, bound = OxigraphStore(tmp_path / "facts"), binding()
    value = entity("Acme", 0, 0)
    value.metadata["response_body"] = TEXT
    with pytest.raises(ProcessingError, match="Unknown"):
        store.adopt_extraction(bound, "entities", [value], text=TEXT, native_ranges=RANGES, accepted_digest="paid")
    assert store.extraction_receipt(bound, "entities") is None
    assert list(store.store) == []
    value.metadata.pop("response_body")
    value.attributes["unconfigured"] = "value"
    with pytest.raises(ProcessingError, match="specification"):
        store.adopt_extraction(bound, "entities", [value], text=TEXT, native_ranges=RANGES, accepted_digest="paid")
    assert list(store.store) == []


def test_missing_native_fact_is_a_recovery_error(tmp_path):
    store, bound = OxigraphStore(tmp_path / "facts"), binding()
    value = entity("Acme", 0, 0)
    store.adopt_extraction(bound, "entities", [value], text=TEXT, native_ranges=RANGES, accepted_digest="paid")
    quad = next(q for q in store.store if q.predicate.value == "urn:semantica:field:name")
    store.store.remove(quad)
    store.flush()
    assert store.extraction_receipt(bound, "entities") is not None
    with pytest.raises(ProcessingError, match="corrupt"):
        store.audit_extraction(bound, "entities")
    with pytest.raises(ProcessingError, match="missing"):
        store.read_extraction(bound, "entities", text=TEXT, native_ranges=RANGES)


def test_receipt_model_mismatch_does_not_publish(tmp_path):
    store, bound = OxigraphStore(tmp_path / "facts"), binding()
    receipt = dict(id="paid", operation="extract", provider="fixture", model="other-model", input_digest="input", output_digest="output")
    with pytest.raises(ProcessingError, match="model|Model"):
        store.adopt_extraction(bound, "entities", [], text=TEXT, native_ranges=RANGES, accepted_digest="paid", receipts=[receipt])
    assert list(store.store) == []


def test_receipt_link_loss_cannot_silently_drop_model_audit(tmp_path):
    store, bound = OxigraphStore(tmp_path / "facts"), binding()
    receipt = dict(id="paid", operation="extract", provider="fixture", model="model", input_digest="input", output_digest="output")
    store.adopt_extraction(bound, "entities", [], text=TEXT, native_ranges=RANGES, accepted_digest="paid", receipts=[receipt])
    quad = next(q for q in store.store if q.predicate.value == "urn:semantica:field:modelReceipt")
    store.store.remove(quad)
    store.flush()
    with pytest.raises(ProcessingError, match="model receipt links missing or corrupt"):
        store.read_extraction_receipts(bound, "entities")


def test_build_input_pages_projected_fields_without_hydrating_source(tmp_path):
    store, bound = OxigraphStore(tmp_path / 'facts'), binding()
    values = [entity('Acme', 0, index) for index in range(5)]
    store.adopt_extraction(bound, 'entities', values, text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    cursor, ids = None, []
    while True:
        page = store.read_extraction_records(bound, 'entities', after=cursor, limit=2, fields=[F+'name'])
        assert 0 < len(page['records']) <= 2
        assert all(record['fields'] == {F+'name': [dict(type='literal', value='Acme', datatype='http://www.w3.org/2001/XMLSchema#string')]} for record in page['records'])
        ids.extend(record['id'] for record in page['records'])
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert ids == [ExtractionRecords(store, bound, 'entities').entity_node(value).value for value in values]
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.read_extraction_records(bound, 'entities', limit=2, fields=[F+'name'])['records'][0]['id'] == ids[0]
    store.close()


def test_build_input_scope_cursor_and_record_ownership_are_strict(tmp_path):
    store, bound = OxigraphStore(tmp_path / 'facts'), binding()
    store.adopt_extraction(bound, 'entities', [entity('Acme', 0, 0), entity('Engine', 10, 1)], text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    first = store.read_extraction_records(bound, 'entities', limit=1)
    other = dict(bound, representation='other')
    store.adopt_extraction(other, 'entities', [entity('Acme', 0, 0)], text=TEXT, native_ranges=RANGES, accepted_digest='other')
    with pytest.raises(ProcessingError, match='cursor'):
        store.read_extraction_records(other, 'entities', after=first['next_cursor'])
    with pytest.raises(ProcessingError, match='owned'):
        store.read_extraction_nodes(other, 'entities', [first['records'][0]['id']])
    with pytest.raises(ProcessingError, match='missing'):
        store.read_extraction_records(dict(bound, material='missing'), 'entities')
    store.close()


def test_build_input_pages_linked_records_and_byte_budgets_fail_closed(tmp_path):
    store, bound = OxigraphStore(tmp_path / 'facts'), binding()
    value = entity('Acme', 0, 0)
    store.adopt_extraction(bound, 'entities', [value], text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    page = store.read_extraction_records(bound, 'entities', fields=[F+'mention'])
    mention = page['records'][0]['fields'][F+'mention'][0]['value']
    record = store.read_extraction_nodes(bound, 'entities', [mention], fields=[F+'start', F+'end'])[0]
    assert set(record['fields']) == {F+'start', F+'end'}
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_extraction_records(bound, 'entities', max_bytes=1)
    with pytest.raises(ProcessingError, match='byte budget'):
        store.read_extraction_nodes(bound, 'entities', [mention], max_bytes=1)
    for options in (dict(limit=129), dict(limit=True), dict(fields=[]), dict(fields=['evil']), dict(after='other:cursor:0')):
        with pytest.raises(ProcessingError):
            store.read_extraction_records(bound, 'entities', **options)
    store.close()


def test_build_relation_page_keeps_qualifiers_supports_and_native_evidence(tmp_path):
    store, bound = OxigraphStore(tmp_path / 'facts'), binding()
    acme, engine = entity('Acme', 0, 0), entity('Engine', 10, 1)
    store.adopt_extraction(bound, 'entities', [acme, engine], text=TEXT, native_ranges=RANGES, accepted_digest='entities')
    relation = Relation(acme, 'owns', engine, .8, TEXT, dict(provider='fixture', model='model', extraction_method='llm_typed_grounded', subject_id='mention:0', object_id='mention:1', evidence_start=0, evidence_end=len(TEXT), evidence_occurrence=0, qualifiers=dict(polarity='negative', condition='under contract', time='2026', unit='shares', value='10'), supporting_refs=['ref-1', 'ref-2']))
    store.adopt_extraction(bound, 'relations', [relation], text=TEXT, native_ranges=RANGES, accepted_digest='relation')
    page = store.read_extraction_records(bound, 'relations', limit=1)
    fields = page['records'][0]['fields']
    assert page['next_cursor'] is None
    assert fields[F+'polarity'] == [dict(type='iri', value=F+'negative')]
    assert {v['value'] for v in fields[F+'supportingRef']} == {'ref-1', 'ref-2'}
    assert fields[F+'qualifiedValue'][0]['value'] == '10'
    evidence = store.read_extraction_nodes(bound, 'relations', [fields[F+'evidence'][0]['value']])[0]
    assert evidence['fields'][F+'start'][0]['value'] == '0'
    ranges = store.read_extraction_nodes(bound, 'relations', [v['value'] for v in evidence['fields'][F+'nativeRange']])
    assert ranges[0]['fields'][F+'nativeRef'][0]['value'] == '#/document/text'
    assert TEXT not in str(page) + str(evidence) + str(ranges)
    bad = next(q for q in store.store if q.predicate.value == F+'predicateName')
    store.store.remove(bad)
    with pytest.raises(ProcessingError, match='corrupt'):
        store.read_extraction_records(bound, 'relations')
    store.close()


def test_recipe_rebind_preserves_owned_facts_and_paid_identity(tmp_path):
    store = OxigraphStore(tmp_path / 'facts')
    previous = binding()
    current = dict(previous, recipe='producer-only')
    receipt = store.adopt_extraction(previous, 'entities', [entity('Acme', 0, 0)],
        text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    records = ExtractionRecords(store, previous, 'entities')
    before = {q for node in records.values(records.operation, 'ownedRecord')
              for q in store.store.quads_for_pattern(node, None, None, records.graph)}
    assert store.rebind_extraction(previous, current, 'entities') == receipt
    assert store.rebind_extraction(previous, current, 'entities') == receipt
    assert store.extraction_operation_id(current, 'entities') == receipt['operation_id']
    assert store.read_extraction(current, 'entities', text=TEXT, native_ranges=RANGES) == [entity('Acme', 0, 0)]
    after = {q for node in records.values(records.operation, 'ownedRecord')
             for q in store.store.quads_for_pattern(node, None, None, records.graph)}
    assert before == after
    assert store.extraction_receipt(previous, 'entities') is None
    with pytest.raises(ProcessingError, match='recipe'):
        store.rebind_extraction(current, dict(current, model='different'), 'entities')
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.extraction_receipt(current, 'entities') == receipt
    store.close()


def test_rebind_relations_and_publication_keep_physical_references(tmp_path):
    from semantica.triplet_store.publication_records import PublicationRecords
    store = OxigraphStore(tmp_path / 'facts')
    previous, current = binding(), dict(binding(), recipe='paid-producer')
    acme, engine = entity('Acme', 0, 0), entity('Engine', 10, 1)
    er = store.adopt_extraction(previous, 'entities', [acme, engine], text=TEXT, native_ranges=RANGES, accepted_digest='entities')
    relation = Relation(acme, 'owns', engine, .8, TEXT, dict(subject_id='mention:0', object_id='mention:1', evidence_start=0, evidence_end=len(TEXT), evidence_occurrence=0, qualifiers=dict(polarity='positive'), supporting_refs=[]))
    rr = store.adopt_extraction(previous, 'relations', [relation], text=TEXT, native_ranges=RANGES, accepted_digest='relations')
    ids = [ExtractionRecords(store, previous, 'entities').entity_node(value).value for value in (acme, engine)]
    generation = store.begin_publication('p', expected_generation=None, source_count=1, canonical_count=2)['generation']
    store.stage_publication_sources('p', generation, [dict(source='s', material='m', representation='r',
        recipe=previous['recipe'], operation_count=2, operations=[er['operation_id'], rr['operation_id']])])
    store.stage_publication_canonical('p', generation, [dict(id='urn:canonical:'+str(i),
        representative=identity, members=[identity], selectors=[], member_count=1, selector_count=0)
        for i, identity in enumerate(ids)])
    relation_id = ExtractionRecords(store, previous, 'relations').node('relation:0').value
    store.stage_publication_facts('p', generation, [dict(id='urn:fact:owns', source='urn:canonical:0',
        target='urn:canonical:1', representative=relation_id, members=[relation_id], member_count=1, status='accepted')])
    indexes = dict(keyword=dict(kind='native-keyword', store_id='kw', recipe_digest='recipe'),
        semantic=dict(kind='native-vector', store_id='vectors', recipe_digest='recipe', space_id='space'))
    store.activate_publication('p', generation, indexes=indexes)
    before = store.read_native_records('p', generation, ids)
    for stage in ('entities', 'relations'):
        store.rebind_extraction(previous, current, stage)
    assert store.read_extraction(current, 'relations', text=TEXT, native_ranges=RANGES, entities=[acme, engine]) == [relation]
    source = {k: current[k] for k in ('source', 'material', 'representation')}
    assert PublicationRecords(store, 'p').verify_operation(er['operation_id'], source).receipt() == er
    assert PublicationRecords(store, 'p').verify_operation(rr['operation_id'], source).receipt() == rr
    assert store.read_native_records('p', generation, ids) == before
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    assert store.read_native_records('p', generation, ids) == before
    store.close()


def test_rebind_collision_does_not_change_source(tmp_path):
    store = OxigraphStore(tmp_path / 'facts')
    previous, current = binding(), dict(binding(), recipe='different-paid-computation')
    for bound in (previous, current):
        store.adopt_extraction(bound, 'entities', [], text=TEXT, native_ranges=RANGES, accepted_digest=bound['recipe'])
    before = set(store.store)
    with pytest.raises(ProcessingError, match='another paid result'):
        store.rebind_extraction(previous, current, 'entities')
    assert set(store.store) == before
    store.close()


def test_preindex_results_require_explicit_migration_without_copy(tmp_path):
    store = OxigraphStore(tmp_path / 'facts')
    previous, current = binding(), dict(binding(), recipe='producer-only')
    receipt = store.adopt_extraction(previous, 'entities', [], text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    records = ExtractionRecords(store, previous, 'entities')
    store.store.update('CLEAR GRAPH ' + str(records.index_graph))
    assert store.extraction_receipt(previous, 'entities') is None
    with pytest.raises(ProcessingError, match='offline identity migration'):
        store.adopt_extraction(previous, 'entities', [], text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    assert store.rebind_extraction(previous, current, 'entities') == receipt
    store.close()


@pytest.mark.parametrize('defect', ['stale-handle', 'wrong-binding', 'orphan'])
def test_identity_proof_cache_never_accepts_stale_or_orphan_bindings(tmp_path, defect):
    from semantica.triplet_store.extraction_records import ExtractionIdentityStaleError
    store = OxigraphStore(tmp_path / 'facts')
    previous, current = binding(), dict(binding(), recipe='current-producer')
    receipt = store.adopt_extraction(previous, 'entities', [], text=TEXT,
        native_ranges=RANGES, accepted_digest='paid')
    original = ExtractionRecords(store, previous, 'entities')
    if defect == 'stale-handle':
        store.rebind_extraction(previous, current, 'entities')
        assert store.extraction_receipt(current, 'entities') == receipt
        with pytest.raises(ExtractionIdentityStaleError):
            original.receipt()
    elif defect == 'wrong-binding':
        forged = ExtractionRecords(store, current, 'entities')
        store.store.add(store._oxigraph.Quad(forged.logical,
            store._oxigraph.NamedNode(F+'physicalOperation'), original.operation, forged.index_graph))
        # Prime the physical proof with its legitimate logical binding.
        assert original.receipt() == receipt
        with pytest.raises(ExtractionIdentityStaleError, match='binding differs'):
            store.extraction_receipt(current, 'entities')
    else:
        store.store.update('DELETE WHERE { GRAPH ' + str(original.graph)
            + ' { ' + str(original.operation) + ' ?p ?o } }')
        with pytest.raises(ProcessingError, match='missing paid operation'):
            store.extraction_receipt(previous, 'entities')
    store.close()


def test_completion_lookup_after_restart_never_scans_owned_facts(tmp_path, monkeypatch):
    store = OxigraphStore(tmp_path / 'facts')
    bound = binding()
    expected = store.adopt_extraction(bound, 'entities', [entity('Acme', 0, 0)],
        text=TEXT, native_ranges=RANGES, accepted_digest='paid')
    store.close()
    store = OxigraphStore(tmp_path / 'facts')
    original = store.store.quads_for_pattern
    def point_reads_only(subject, predicate, value, graph):
        assert predicate is not None, 'completion lookup scanned fact payloads'
        assert predicate.value != F+'ownedRecord', 'completion lookup enumerated owned records'
        return original(subject, predicate, value, graph)
    monkeypatch.setattr(store.store, 'quads_for_pattern', point_reads_only)
    assert store.extraction_receipt(bound, 'entities') == expected
    # An unrelated write must not make the next hit scan facts either.
    store.begin_publication('p', expected_generation=None, source_count=0, canonical_count=0)
    assert store.extraction_receipt(bound, 'entities') == expected
    store.close()


@pytest.mark.parametrize('defect',['cancel','missing-address','invalid-address'])
def test_source_projection_completion_is_durable_and_rejects_corruption(tmp_path,monkeypatch,defect):
    from semantica.semantic_artifact_schema import DocumentRepresentation
    key='sha256:'+'a'*64
    revision='b3-'+'a'*64
    header=dict(representation=DocumentRepresentation(id='rep',source_id='ss',material_revision_id=revision,
        input_revision=revision,media_type='text/plain',content_hash=revision,parser='fixture',parser_version='1',
        recipe_id='fixture',recipe_digest='a'*64,origin='native',artifact_ref_id='artifact').model_dump(),
        artifact_id='artifact',operations=[])
    store=OxigraphStore(tmp_path/'projection')
    if defect=='cancel':
        def interrupted():
            yield header
            raise ProcessingError('canceled')
        with pytest.raises(ProcessingError,match='canceled'):
            ExtractionRecords.source_projection(store,'p',key,interrupted())
        assert ExtractionRecords.source_projection(store,'p',key) is None
        ExtractionRecords.source_projection(store,'p',key,[header])
    else:
        ExtractionRecords.source_projection(store,'p',key,[header])
    store.close()
    store=OxigraphStore(tmp_path/'projection')
    try:
        assert list(ExtractionRecords.source_projection(store,'p',key))==[header]
        if defect!='cancel':
            ox=store._oxigraph
            address=next(store.store.quads_for_pattern(None,ox.NamedNode(F+'address'),None,None))
            store.store.remove(address)
            if defect=='invalid-address':
                store.store.add(ox.Quad(address.subject,address.predicate,ox.Literal('{}'),address.graph_name))
            with pytest.raises(ProcessingError):
                list(ExtractionRecords.source_projection(store,'p',key))
    finally:
        store.close()
