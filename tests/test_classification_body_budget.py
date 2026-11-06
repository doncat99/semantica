"""Classification visits all references without retaining all source quotes."""
import weakref
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as builder
from semantica.semantic_artifact_schema import ClassificationProfile, SourceClassification


def test_context_batches_consume_only_current_batch_and_lookahead():
    consumed = []

    def records():
        for index in range(20):
            consumed.append(index)
            yield 'evidence', {'id': str(index), 'quote': 'x' * 500}

    batches = iter(builder._context_batches({}, records(), 700))
    first = next(batches)
    assert len(consumed) == 2
    assert first['evidence'][0]['id'] == '0'
    assert [item['id'] for batch in [first, *batches] for item in batch['evidence']] == [str(i) for i in range(20)]


def test_classification_releases_other_batches_and_preflights_before_requests(monkeypatch):
    live = []
    reads = []

    class Quote(str):
        pass

    class Passage:
        def __init__(self, index):
            self.id = str(index)

        @property
        def quote(self):
            reads.append(self.id)
            value = Quote('漢字' * 200)
            live.append(weakref.ref(value))
            return value

    profile = ClassificationProfile(id='profile', version='1', label='Profile', description='Profile', dimensions=[])
    passages = [Passage(index) for index in range(20)]
    monkeypatch.setattr(builder, '_input_token_budget', lambda _: 2500)
    monkeypatch.setattr(builder, '_generation_payload', lambda _relay, prompt, _schema: prompt)
    seen = []

    def classify(built, _profile, _relay):
        assert set(reads) == {span.id for span in passages}, 'preflight must finish before any request'
        assert sum(ref() is not None for ref in live) <= 3, 'other batch quotes remain live'
        seen.extend(span.id for span in built['passages'])
        return SourceClassification(source_id='source', profile_id='profile', profile_version='1',
                                    assignments=[], unclassified_dimension_ids=[], model_receipt_ids=[]), []

    monkeypatch.setattr(builder, '_classify_source_batch', classify)
    builder._classify_source({'source': SimpleNamespace(source_id='source'), 'passages': passages}, profile, object())
    assert seen == [span.id for span in passages]


def test_late_oversize_is_rejected_before_any_classification_request(monkeypatch):
    profile = ClassificationProfile(id='profile', version='1', label='Profile', description='Profile', dimensions=[])
    monkeypatch.setattr(builder, '_input_token_budget', lambda _: 2000)
    monkeypatch.setattr(builder, '_generation_payload', lambda _relay, prompt, _schema: prompt)
    monkeypatch.setattr(builder, '_classify_source_batch', lambda *_: pytest.fail('must preflight every reference'))
    passages = [SimpleNamespace(id='small', quote='small'), SimpleNamespace(id='large', quote='x' * 10000)]
    with pytest.raises(builder.SemanticArtifactError, match='indivisible') as error:
        builder._classify_source({'source': SimpleNamespace(source_id='source'), 'passages': passages}, profile, object())
    assert error.value.code == 'MODEL_CONTEXT_BUDGET_EXCEEDED'
    assert error.value.retryable is False
