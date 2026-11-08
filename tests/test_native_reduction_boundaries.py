"""Decision ownership and recovery checks; model generation is always offline."""
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as pipeline
from semantica.kg.community_summarizer import CommunitySummarizer, EvidenceBudgetError, DEFAULT_SYSTEM_PROMPT
from semantica.semantic_artifact_schema import ClassificationProfile, ClassificationAssignment, SourceClassification


@pytest.mark.parametrize("method", ["track_entity", "track_relationship"])
def test_native_provenance_uses_build_timestamp_without_result_cache(method):
    from semantica.provenance import ProvenanceManager
    recorded_at = "2026-10-18T01:00:00Z"
    lineages = []
    for _ in range(2):
        manager = ProvenanceManager()
        entry = getattr(manager, method)("fact", "source", timestamp=recorded_at)
        assert entry.timestamp == entry.first_seen == entry.last_updated == recorded_at
        lineages.append(manager.get_lineage("fact"))
    assert lineages[0] == lineages[1]
    assert lineages[0]["integrity_verified"] is True


@pytest.mark.parametrize("choices,cardinality,expected", [
    (["alpha", "beta"], "single", []),
    (["alpha", "alpha"], "single", ["alpha"]),
    (["alpha", "beta"], "multi", ["alpha", "beta"]),
])
def test_classification_never_votes_or_adds_adjudication(monkeypatch, choices, cardinality, expected):
    profile = ClassificationProfile(id="profile", version="1", label="Purpose", description="Purpose", dimensions=[{
        "id": "purpose", "label": "Purpose", "cardinality": cardinality,
        "vocabulary": [{"id": key, "label": key} for key in ("alpha", "beta")]}])
    spans = [SimpleNamespace(id="ev:" + str(i), quote="source") for i in range(2)]
    monkeypatch.setattr(pipeline, "_context_batches", lambda *args, **kwargs: [
        {"evidence": [{"id": span.id}]} for span in spans])
    calls = []
    def classify(built, profile, relay):
        i = len(calls)
        calls.append(built)
        return SourceClassification(source_id="source", profile_id="profile", profile_version="1",
            unclassified_dimension_ids=[], model_receipt_ids=[],
            assignments=[ClassificationAssignment(dimension_id="purpose", item_id=choices[i],
                confidence=[.9, .4][i], evidence_ids=["ev:" + str(i)])]), []
    monkeypatch.setattr(pipeline, "_classify_source_batch", classify)
    result, _ = pipeline._classify_source({"source": SimpleNamespace(source_id="source"),
                                          "passages": spans}, profile, SimpleNamespace(context_window_tokens=500000, max_output_tokens=32768))
    assert [item.item_id for item in result.assignments] == expected
    assert len(calls) == 2
    assert result.unclassified_dimension_ids == ([] if expected else ["purpose"])
    if choices == ["alpha", "alpha"]:
        assert result.assignments[0].confidence == .4
        assert result.assignments[0].evidence_ids == ["ev:0", "ev:1"]


def test_classification_completed_hit_only_returns_native_reference():
    def forbidden(*args, **kwargs):
        pytest.fail('completed classification must not hydrate, recover, flush or call model')
    store = SimpleNamespace(
        classification_operation_id=lambda _: 'operation',
        classification_receipt=lambda _: {'accepted_digest': 'digest'},
        read_classification=forbidden, read_classification_receipts=forbidden, flush=forbidden)
    cache = SimpleNamespace(accepted_digest=forbidden, has_accepted_body=forbidden,
                            release_accepted=forbidden)
    request = SimpleNamespace(project_id='project',
        parsed_sources=[SimpleNamespace(source_id='source', representation_revision='representation')])
    source = SimpleNamespace(source_id='source', material_revision='material')
    relay = SimpleNamespace(binding_id='binding', model_id='model', context_window_tokens=8192, max_output_tokens=1024)
    profile = SimpleNamespace(model_dump=lambda **k: {})
    built = {'source': source, 'passages': []}
    token = pipeline._native_build.set((request, store, cache))
    try:
        restored, receipts = pipeline._classify_source_batch(built, profile, relay)
    finally:
        pipeline._native_build.reset(token)
    assert restored is None and receipts == []
    assert built['native_operations'] == ['operation']


def test_native_report_batches_cover_evidence_and_scope_citations(monkeypatch):
    summarizer = CommunitySummarizer(max_tokens=2000, token_counter=len, cache_enabled=False)
    chunks = [{"id": str(i), "text": str(i) * 350} for i in range(3)]
    calls = []
    def summarize(comm, **kwargs):
        calls.append(kwargs)
        return object()
    monkeypatch.setattr(summarizer, "summarize_community", summarize)
    reports = summarizer.summarize_evidence({"id": "c", "entity_ids": []}, text_chunks=chunks,
        validation_context={"evidence": [{"id": item["id"], "quote": item["text"]} for item in chunks]})
    assert len(reports) == len(calls) == 3
    assert [chunk for call in calls for chunk in call["text_chunks"]] == chunks
    for call in calls:
        assert {item["id"] for item in call["validation_context"]["evidence"]} == {
            item["id"] for item in call["text_chunks"]}


def test_native_report_preflights_all_chunks_before_any_request(monkeypatch):
    summarizer = CommunitySummarizer(max_tokens=2000, token_counter=len, cache_enabled=False)
    monkeypatch.setattr(summarizer, "summarize_community", lambda *a, **k: pytest.fail("must not send"))
    with pytest.raises(EvidenceBudgetError):
        summarizer.summarize_evidence({"id": "c", "entity_ids": []}, text_chunks=[
            {"id": "small", "text": "small"}, {"id": "large", "text": "x" * 2000}])


def test_relay_budgets_complete_serialized_request_without_sending(monkeypatch):
    import json
    monkeypatch.setenv("TEST_RELAY_TOKEN", "offline")
    monkeypatch.setattr(pipeline.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not send"))
    payload = {"messages": [{"role": "user", "content": '漢字"\\' * 20_000}],
               "response_format": {"type": "json_object"}}
    expected = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        pipeline._relay_uncached(SimpleNamespace(authorization_env="TEST_RELAY_TOKEN", context_window_tokens=100000, max_output_tokens=10000), payload,
                                 "structured_extraction")
    assert failure.value.code == "MODEL_CONTEXT_BUDGET_EXCEEDED"
    assert failure.value.retryable is False
    assert failure.value.diagnostic['requestBytes'] == expected
    assert failure.value.diagnostic['inputTokenBudget'] == 90000
    assert failure.value.diagnostic['upstreamRequestSent'] is False


def test_builder_reports_local_budget_failure_without_sending(monkeypatch):
    monkeypatch.setattr(pipeline, "_project_model_provider", lambda *a: SimpleNamespace(receipts=[]))
    with pytest.raises(pipeline.SemanticArtifactError) as failure:
        pipeline._grounded_explanation({"target": {"id": "c"}, "entities": [], "relations": [],
            "assertions": [], "evidence": [{"id": "e", "quote": "source"}]}, SimpleNamespace(model_id='test', context_window_tokens=1100, max_output_tokens=1000))
    assert failure.value.code == "REPORT_CONTEXT_BUDGET_EXCEEDED"
    assert failure.value.retryable is False
    assert failure.value.diagnostic["upstreamRequestSent"] is False


@pytest.mark.parametrize("options", [{}, {"max_tokens": None}])
def test_native_report_preflight_counts_default_system_prompt(monkeypatch, options):
    summarizer = CommunitySummarizer(max_tokens=2000, token_counter=len, cache_enabled=False)
    budgets = []
    def pack(comm, graph, *, max_tokens, text_chunks):
        budgets.append(max_tokens)
        return "".join(summarizer._evidence_line(item) for item in text_chunks)
    monkeypatch.setattr(summarizer, "_pack_context", pack)
    monkeypatch.setattr(summarizer, "summarize_community", lambda *a, **k: None)
    summarizer.summarize_evidence({"id": "c", "entity_ids": []}, text_chunks=[{"id": "e", "text": "source"}], **options)
    assert budgets[0] == 2000 - len(DEFAULT_SYSTEM_PROMPT + "\n\nContext Information:\n\n\nReturn ONLY the structured JSON report.")


def test_native_cache_reuses_entities_after_relation_transport_retry(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from tests.artifact_helpers import native_extraction_owner
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    text = "Fund owns Bond."
    path = tmp_path / "source.txt"
    path.write_text(text)
    calls = []
    def respond(stage, prompt):
        calls.append(stage)
        if calls == ["entities", "relations"]:
            raise pipeline.SemanticArtifactError("transport unavailable", status=503,
                code="UPSTREAM_UNAVAILABLE", retryable=True)
        if stage == "entities":
            return {"entities": [{"text": name, "label": "Concept", "occurrence": 0,
                                  "confidence": 1.0, "attributes": {}}
                                  for name in ("Fund", "Bond")]}
        return {"relations": []}
    stub_native_provider(monkeypatch, respond)
    with native_extraction_owner(tmp_path / "native", text=text) as store:
        args = (text, SimpleNamespace(model_id="test"), None, (0, len(text), text), [])
        first, receipts, reused = pipeline._extract_window_context(*args)
        second, restored_receipts, restored = pipeline._extract_window_context(*args)
    assert calls == ["entities", "relations", "relations"]
    assert len(receipts) == len({item.id for item in receipts}) == 2
    assert not reused and restored
    assert [item.id for item in receipts] == [item.id for item in restored_receipts]
    assert [(item.text, item.start_char, item.end_char) for item in first["entities"]] == [
        (item.text, item.start_char, item.end_char) for item in second["entities"]]


def test_formula_semantics_opt_in_invalidates_only_selected_extraction(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from tests.artifact_helpers import native_extraction_owner
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    text = "C = E / R"
    path = tmp_path / "source.txt"
    path.write_text(text)
    calls = []

    def respond(stage, prompt):
        calls.append((stage, "Identify explicitly stated formulas" in prompt))
        return {"entities": []}

    stub_native_provider(monkeypatch, respond)
    with native_extraction_owner(tmp_path / "native", text=text) as store:
        args = (text, SimpleNamespace(model_id="test"), None, (0, len(text), text),
                [{"kind": "formula", "text": text, "start": 0, "end": len(text)}])
        pipeline._extract_window_context(*args)
        pipeline._extract_window_context(*args, formula_semantics=False)
        pipeline._extract_window_context(*args, formula_semantics=True)
        pipeline._extract_window_context(*args, formula_semantics=True)
    assert calls == [("entities", False), ("entities", True)]


@pytest.mark.parametrize("field,value", [("max_output_tokens", 4096), ("binding_id", "other"),
                                        ("context_window_tokens", 65536)])
def test_direct_native_window_receipt_ignores_nonbinding_transport_configuration(tmp_path, monkeypatch, field, value):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from tests.artifact_helpers import native_extraction_owner
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    path = tmp_path / "source.txt"
    path.write_text("source")
    calls = []
    def respond(stage, prompt):
        calls.append(stage)
        return {"entities": []}
    stub_native_provider(monkeypatch, respond)
    with native_extraction_owner(tmp_path / "native", text="source") as store:
        relay = SimpleNamespace(model_id="test")
        args = ("source", relay, None, (0, 6, "source"), [])
        pipeline._extract_window_context(*args)
        pipeline._extract_window_context(*args)
        assert calls == ["entities"]
        setattr(relay, field, value)
        pipeline._extract_window_context(*args)
        assert calls == ["entities"]
