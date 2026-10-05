from semantica.semantic_extract import grounded_window


def test_grounded_window_delegates_to_native_extractors(monkeypatch):
    calls = []

    class Provider:
        pass

    provider = Provider()

    def entities(text, **kwargs):
        calls.append(("entities", text, kwargs))
        return ["entity"]

    def relations(text, found, **kwargs):
        calls.append(("relations", text, found, kwargs))
        return ["relation"]

    monkeypatch.setattr(grounded_window, "extract_entities_llm", entities)
    monkeypatch.setattr(grounded_window, "extract_relations_llm", relations)

    result = grounded_window.extract_grounded_window(
        "source text", model="model-a", provider_instance=provider,
    )

    assert result == (["entity"], ["relation"], provider)
    assert [call[0] for call in calls] == ["entities", "relations"]
    assert calls[0][2]["grounding"] == "strict"
    assert calls[1][3]["grounding"] == "strict"


def test_grounded_window_recreates_provider_for_each_retry(monkeypatch):
    providers = []
    attempts = []

    class Provider:
        pass

    def factory():
        provider = Provider()
        providers.append(provider)
        return provider

    def entities(text, **kwargs):
        attempts.append(kwargs["provider_instance"])
        if len(attempts) == 1:
            raise grounded_window.ProcessingError("retry")
        return []

    def relations(text, found, **kwargs):
        return []

    monkeypatch.setattr(grounded_window, "extract_entities_llm", entities)
    monkeypatch.setattr(grounded_window, "extract_relations_llm", relations)

    result = grounded_window.extract_grounded_window(
        "source text", model="model-a", provider_instance=Provider(),
        provider_factory=factory, retries=1,
    )

    assert result[0:2] == ([], [])
    assert attempts[0] is not attempts[1]
    assert attempts[1] is providers[0]


def test_grounded_window_records_candidate_rejections_on_model_receipt(monkeypatch):
    from types import SimpleNamespace

    provider = SimpleNamespace(rejections=[], receipts=[SimpleNamespace(metadata={})])
    monkeypatch.setattr(grounded_window, "extract_entities_llm", lambda *_args, **_kwargs: [])

    def relations(_text, _entities, **kwargs):
        kwargs["rejection_receipts"].append({"candidate_index": 0, "reason": "ungrounded condition"})
        return []

    monkeypatch.setattr(grounded_window, "extract_relations_llm", relations)
    _, _, actual_provider = grounded_window.extract_grounded_window(
        "source text", model="model-a", provider_instance=provider,
    )

    assert actual_provider.receipts[-1].metadata["rejected_candidates"] == [
        {"candidate_index": 0, "reason": "ungrounded condition"},
    ]
