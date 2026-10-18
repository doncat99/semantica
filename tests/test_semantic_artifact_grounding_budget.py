"""Bound located context while preserving complete structural evidence."""
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
    from semantica.semantic_extract.types import Entity, Relation
    context = contexts()
    monkeypatch.setattr(pipeline, "_window_grounding_context", lambda *_: context)
    monkeypatch.setattr(pipeline, "MODEL_CONTEXT_BYTES", 6_000)
    calls = []
    def extract(*args):
        calls.append(args[-1])
        a = Entity("AEP", "ORG", 0, 3, metadata={"mention_id": "a"})
        b = Entity("report", "CONCEPT", 4, 10, metadata={"mention_id": "b"})
        return {"entities": [a, b], "relations": [Relation(a, "describes", b, metadata={
            "subject_id": "a", "object_id": "b", "supporting_refs": [args[-1][-1]["ref"]]})]}, [len(calls)], len(calls) == 1
    monkeypatch.setattr(pipeline, "_extract_window_context", extract)
    extracted, receipts, restored = pipeline._extract_window("AEP report", SimpleNamespace(), None, [], (0, 10, "AEP report"))
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
    batches = pipeline._extraction_context_batches("report", context, max_bytes=6_000)
    for batch in batches:
        if any(r.get('table_id') and r['structure'].get('start_row_offset_idx', 0) >= 2 for r in batch):
            assert label in batch


def test_interrupted_evidence_batches_restore_completed_passes(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    context = contexts()
    monkeypatch.setattr(pipeline, '_window_grounding_context', lambda *_: context)
    monkeypatch.setattr(pipeline, 'MODEL_CONTEXT_BYTES', 6_000)
    source = tmp_path / "source.txt"
    source.write_text("AEP report")
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(
        _request(source, tmp_path / "output")["params"]))
    calls = []
    def respond(stage, prompt):
        calls.append(prompt)
        if len(calls) == 2:
            raise RuntimeError('interrupted')
        return {"entities": []}
    stub_native_provider(monkeypatch, respond)
    token = active_checkpoint.set(checkpoint)
    args = ('AEP report', SimpleNamespace(model_id='test'), None, [], (0, 10, 'AEP report'))
    try:
        with pytest.raises(Exception, match='interrupted'):
            pipeline._extract_window(*args)
        assert len(list(checkpoint.root.glob("extraction-entities-*.json"))) == 1
        pipeline._extract_window(*args)
        expected = len(pipeline._extraction_context_batches('AEP report', context))
        assert len(calls) == expected + 1
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
