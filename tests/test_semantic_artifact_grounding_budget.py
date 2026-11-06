"""Bound located context while preserving complete structural evidence."""
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as pipeline


def cell(row, col, *, header=False, section=False, quote=None):
    return {"ref": f"#/tables/0/r{row}:c{col}", "table_id": "table:0", "cell": f"r{row}:c{col}",
            "start": None, "end": None, "page": 1, "quote": quote or "value" * 80,
            "structure": {"start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                          "column_header": header, "row_section": section,
                          "captions": [{"$ref": "#/texts/0"}], "footnotes": [{"$ref": "#/texts/1"}]}}


def contexts():
    notes = [{"ref": f"#/texts/{i}", "start": i, "end": i + 1, "page": 1,
              "quote": "USD millions" if i == 0 else "Restated figures", "structure": {}} for i in range(2)]
    return notes + [cell(0, c, header=True) for c in range(3)] + [cell(1, 0, section=True)] + [
        cell(r, c) for r in range(2, 25) for c in range(3)]


class NativeUnitFixture:
    """Test double for the native index's row-unit query contract."""
    @property
    def reader(self):
        return self

    def context_units(self, start, end):
        records = list(self.context_addresses(start, end))
        for record in records:
            if not record.get('cell'):
                yield iter([record])
        for row in sorted({record['structure']['start_row_offset_idx'] for record in records
                           if record.get('cell') and not record['structure'].get('column_header')
                           and not record['structure'].get('row_section')}):
            yield iter([record for record in records if not record.get('cell')
                or record['structure'].get('column_header') or record['structure'].get('row_section')
                or record['structure']['start_row_offset_idx'] <= row < record['structure']['end_row_offset_idx']])



@pytest.fixture(autouse=True)
def native_query_test_double(monkeypatch):
    from semantica import semantic_document_context as query
    native = query.iter_source_context_units
    def units(reader, *, start, end):
        if isinstance(reader, NativeUnitFixture):
            yield from reader.context_units(start, end)
        else:
            yield from native(reader, start=start, end=end)
    monkeypatch.setattr(query, 'iter_source_context_units', units)


def test_large_context_preserves_rows_headers_notes_and_every_ref():
    context = contexts()
    batches = list(pipeline._extraction_context_batches("AEP report", context, max_bytes=6_000))
    assert len(batches) > 1
    assert {r["ref"] for batch in batches for r in batch} == {r["ref"] for r in context}
    required = {r["ref"] for r in context[:6]}
    for batch in batches:
        assert pipeline._context_size({"text": "AEP report", "structure": batch}) <= 6_000
        refs = {r["ref"] for r in batch}
        if any(r.get("cell") for r in batch):
            assert required <= refs
        for row in range(2, 25):
            row_refs = {f"#/tables/0/r{row}:c{c}" for c in range(3)}
            assert not refs.intersection(row_refs) or row_refs <= refs


def test_small_context_keeps_exact_checkpoint_input():
    context = contexts()[:6]
    assert list(pipeline._extraction_context_batches("report", context, 6000)) == [context]


def test_indivisible_row_has_typed_nonretryable_local_failure():
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        list(pipeline._extraction_context_batches("report", [cell(0, 0, quote="x" * 9_000)], max_bytes=2_000))
    assert failure.value.code == "EXTRACTION_CONTEXT_BUDGET_EXCEEDED"
    assert failure.value.retryable is False
    assert failure.value.diagnostic["limitBytes"] == 2_000


def test_batched_window_keeps_local_entity_ids_and_relation_endpoints_disjoint(monkeypatch):
    from semantica.semantic_extract.types import Entity, Relation
    context = contexts()
    monkeypatch.setattr(pipeline, "_window_grounding_context", lambda *_: context)
    calls = []
    def extract(text, relay, spec, item, context, formula_semantics):
        assert formula_semantics is False
        calls.append(context)
        a = Entity("AEP", "ORG", 0, 3, metadata={"mention_id": "a"})
        b = Entity("report", "CONCEPT", 4, 10, metadata={"mention_id": "b"})
        return {"entities": [a, b], "relations": [Relation(a, "describes", b, metadata={
            "subject_id": "a", "object_id": "b", "supporting_refs": [context[-1]["ref"]]})]}, [len(calls)], len(calls) == 1
    monkeypatch.setattr(pipeline, "_extract_window_context", extract)
    extracted, receipts, restored = pipeline._extract_window("AEP report", SimpleNamespace(context_window_tokens=7000, max_output_tokens=1000), None, [], (0, 10, "AEP report"))
    assert len(calls) > 1 and len(receipts) == len(calls)
    ids = [entity.metadata["mention_id"] for entity in extracted["entities"]]
    assert len(ids) == len(set(ids))
    assert all(r.subject.metadata["mention_id"] in ids and r.object.metadata["mention_id"] in ids for r in extracted["relations"])
    assert not restored


def test_spanning_row_label_is_repeated_without_joining_the_whole_table():
    context = contexts()
    label = cell(2, 0, quote="Scope 1 emissions")
    label['structure']['end_row_offset_idx'] = 25
    context = [label if r['ref'] == label['ref'] else r for r in context]
    batches = list(pipeline._extraction_context_batches("report", context, max_bytes=6_000))
    for batch in batches:
        if any(r.get('table_id') and r['structure'].get('start_row_offset_idx', 0) >= 2 for r in batch):
            assert label in batch


def test_interrupted_evidence_batches_restore_completed_passes(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from tests.artifact_helpers import native_extraction_owner
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    context = contexts()
    monkeypatch.setattr(pipeline, '_window_grounding_context', lambda *_: context)
    source = tmp_path / "source.txt"
    source.write_text("AEP report")
    calls = []
    def respond(stage, prompt):
        calls.append(prompt)
        if len(calls) == 2:
            raise RuntimeError('interrupted')
        return {"entities": []}
    stub_native_provider(monkeypatch, respond)
    args = ('AEP report', SimpleNamespace(model_id='test', context_window_tokens=7000, max_output_tokens=1000), None, [], (0, 10, 'AEP report'))
    with native_extraction_owner(tmp_path / 'native', text='AEP report') as store:
        with pytest.raises(Exception, match='interrupted'):
            pipeline._extract_window(*args)
        assert store.store is not None
        pipeline._extract_window(*args)
        expected = len(list(pipeline._extraction_context_batches('AEP report', context, 6000)))
        assert len(calls) == expected + 1
        before = len(calls)
        assert pipeline._extract_window(*args)[2] is True
        assert len(calls) == before


def test_oversize_text_without_structure_fails_before_model_request():
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        list(pipeline._extraction_context_batches('x' * 100, [], max_bytes=50))
    assert failure.value.code == 'EXTRACTION_CONTEXT_BUDGET_EXCEEDED'
    assert failure.value.diagnostic['upstreamRequestSent'] is False


def test_complete_request_overhead_refines_only_unsatisfied_evidence_batches(monkeypatch):
    context = contexts()
    monkeypatch.setattr(pipeline, '_window_grounding_context', lambda *_: context)
    admitted, rejected = [], []
    def extract(text, relay, spec, item, records, formula):
        size = pipeline._context_size({'text': item[2], 'structure': records}) + 3000
        if size > 10000:
            rejected.append(records)
            raise pipeline.SemanticArtifactError('schema overhead', code='MODEL_CONTEXT_BUDGET_EXCEEDED',
                retryable=False, diagnostic={'estimatedInputTokens': size, 'inputTokenBudget': 10000})
        admitted.append(records)
        return {'entities': [], 'relations': []}, [], False
    monkeypatch.setattr(pipeline, '_extract_window_context', extract)
    pipeline._extract_window('report', SimpleNamespace(context_window_tokens=11000, max_output_tokens=1000),
                             None, [], (0, 6, 'report'))
    assert rejected and len(admitted) > len(rejected)
    assert {r['ref'] for batch in admitted for r in batch} == {r['ref'] for r in context}


def test_context_planning_never_hydrates_the_complete_closure():
    """Metadata planning is bounded; model batches hydrate on demand."""
    from copy import deepcopy
    records = contexts()
    class Locations(NativeUnitFixture):
        def context_addresses(self, start, end):
            for index, record in enumerate(records):
                item = deepcopy(record)
                item.pop('quote')
                item['sourceLocationOrdinal'] = index
                yield item
        def hydrate(self, address):
            self.reads.append(address['sourceLocationOrdinal'])
            return deepcopy(records[address['sourceLocationOrdinal']])
        reads = []
    locations = Locations()
    context = pipeline._window_grounding_context(locations, 0, 10)
    assert locations.reads == []
    batches = iter(pipeline._extraction_context_batches('AEP report', context, 6000))
    first = next(batches)
    assert len(set(locations.reads)) < len(records)
    assert pipeline._context_size({'text': 'AEP report', 'structure': first}) <= 6000
    refs = {r['ref'] for r in first}
    for batch in batches:
        refs.update(r['ref'] for r in batch)
    assert refs == {r['ref'] for r in records}


def test_oversized_address_plan_streams_without_retaining_all_metadata():
    class Locations(NativeUnitFixture):
        def context_addresses(self, start, end):
            for index in range(1000):
                yield {'ref': str(index), 'sourceLocationOrdinal': index, 'structure': {'metadata': 'x' * 1024}}
        def hydrate(self, address):
            return dict(address, quote='value')
    context = pipeline._window_grounding_context(Locations(), 0, 10)
    batches = list(pipeline._extraction_context_batches('report', context, 6000))
    assert {item['ref'] for batch in batches for item in batch} == {str(i) for i in range(1000)}
    assert all(pipeline._context_size({'text': 'report', 'structure': batch}) <= 6000 for batch in batches)


def test_oversized_indivisible_row_stops_hydration_before_its_tail():
    records = [cell(0, col) for col in range(100)]
    class Locations(NativeUnitFixture):
        reads = 0
        def context_addresses(self, start, end):
            return [dict(record, quote='', sourceLocationOrdinal=index) for index, record in enumerate(records)]
        def hydrate(self, address):
            self.reads += 1
            return records[int(address['cell'].split(':c')[1])]
    locations = Locations()
    with pytest.raises(pipeline.SemanticArtifactError):
        next(pipeline._extraction_context_batches('report',
            pipeline._window_grounding_context(locations, 0, 10), 2000))
    assert locations.reads < len(records)
