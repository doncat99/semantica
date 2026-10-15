"""Bound located context without dropping table evidence or invalidating old chunks."""
from types import SimpleNamespace

import pytest

from semantica import semantic_artifact_builder as pipeline


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


def test_large_context_preserves_rows_headers_notes_and_every_ref():
    context = contexts()
    batches = pipeline._extraction_context_batches("AEP report", context, max_bytes=6_000)
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
    assert pipeline._extraction_context_batches("report", context) == [context]


def test_indivisible_row_has_typed_nonretryable_local_failure():
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        pipeline._extraction_context_batches("report", [cell(0, 0, quote="x" * 9_000)], max_bytes=2_000)
    assert failure.value.code == "EXTRACTION_CONTEXT_BUDGET_EXCEEDED"
    assert failure.value.retryable is False
    assert failure.value.diagnostic["limitBytes"] == 2_000


def test_batched_window_keeps_local_entity_ids_and_relation_endpoints_disjoint(monkeypatch):
    context = contexts()
    monkeypatch.setattr(pipeline, "_window_grounding_context", lambda *_: context)
    monkeypatch.setattr(pipeline, "MODEL_CONTEXT_BYTES", 6_000)
    calls = []
    def extract(*args):
        calls.append(args[-1])
        return {"entities": [{"id": "a", "name": "AEP"}, {"id": "b", "name": "report"}],
                "relations": [{"subject": "a", "object": "b", "supporting_refs": [args[-1][-1]["ref"]]}]}, [len(calls)], len(calls) == 1
    monkeypatch.setattr(pipeline, "_extract_window_context", extract)
    extracted, receipts, restored = pipeline._extract_window("AEP report", SimpleNamespace(), None, [], (0, 10, "AEP report"))
    assert len(calls) > 1 and len(receipts) == len(calls)
    ids = [entity["id"] for entity in extracted["entities"]]
    assert len(ids) == len(set(ids))
    assert all(r["subject"] in ids and r["object"] in ids for r in extracted["relations"])
    assert not restored


def test_spanning_row_label_is_repeated_without_joining_the_whole_table():
    context = contexts()
    label = cell(2, 0, quote="Scope 1 emissions")
    label['structure']['end_row_offset_idx'] = 25
    context = [label if r['ref'] == label['ref'] else r for r in context]
    batches = pipeline._extraction_context_batches("report", context, max_bytes=6_000)
    for batch in batches:
        if any(r.get('table_id') and r['structure'].get('start_row_offset_idx', 0) >= 2 for r in batch):
            assert label in batch


def test_interrupted_evidence_batches_restore_completed_passes(monkeypatch):
    from semantica.project_checkpoint import active_checkpoint
    from semantica.semantic_artifact_schema import ModelReceipt
    context = contexts()
    monkeypatch.setattr(pipeline, '_window_grounding_context', lambda *_: context)
    monkeypatch.setattr(pipeline, 'MODEL_CONTEXT_BYTES', 6_000)
    stored, calls = {}, []
    class Checkpoint:
        created_at = "2026-10-15T00:00:00Z"
        def read(self, kind, key):
            return stored.get(pipeline.stable_digest(key))
        def write(self, kind, key, value):
            stored[pipeline.stable_digest(key)] = value
    class Provider:
        def __init__(self): self.receipts = []
    def extract(_window, **kwargs):
        calls.append(kwargs['grounding_context'])
        if len(calls) == 2:
            raise RuntimeError('interrupted')
        provider = kwargs['provider_instance']
        provider.receipts.append(ModelReceipt(id=f'receipt:{len(calls)}', operation='structured_extraction',
            provider='test', model='test', input_digest='sha256:' + '1'*64, output_digest='sha256:' + '2'*64))
        return [], [], provider
    monkeypatch.setattr(pipeline, '_project_model_provider', lambda _: Provider())
    monkeypatch.setattr(pipeline, 'extract_grounded_window', extract)
    token = active_checkpoint.set(Checkpoint())
    args = ('AEP report', SimpleNamespace(model_id='test'), None, [], (0, 10, 'AEP report'))
    try:
        with pytest.raises(RuntimeError, match='interrupted'):
            pipeline._extract_window(*args)
        assert len(stored) == 1
        pipeline._extract_window(*args)
        expected = len(pipeline._extraction_context_batches('AEP report', context))
        assert len(calls) == expected + 1  # one failed call; saved first pass was restored
        before = len(calls)
        assert pipeline._extract_window(*args)[2] is True
        assert len(calls) == before
    finally:
        active_checkpoint.reset(token)


def test_oversize_text_without_structure_fails_before_model_request():
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        pipeline._extraction_context_batches('x' * 100, [], max_bytes=50)
    assert failure.value.code == 'EXTRACTION_CONTEXT_BUDGET_EXCEEDED'
    assert failure.value.diagnostic['upstreamRequestSent'] is False
