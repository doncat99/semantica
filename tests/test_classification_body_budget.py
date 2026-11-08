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


def test_native_classification_warm_reuse_reads_no_quotes_or_payloads(tmp_path, monkeypatch):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.triplet_store.classification_records import ClassificationRecords
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.semantic_artifact_schema import ModelReceipt

    profile = ClassificationProfile(id='profile', version='1', label='Profile', description='Profile',
        dimensions=[dict(id='purpose', label='Purpose', cardinality='single', vocabulary=[])])
    reads, calls = [], []
    class Passage:
        def __init__(self, identity):
            self.id = identity
        @property
        def quote(self):
            reads.append(self.id)
            return 'source evidence ' * 20
    passages = [Passage(str(index)) for index in range(20)]
    source = SimpleNamespace(source_id='source', material_revision='material')
    request = SimpleNamespace(project_id='project',
        parsed_sources=[SimpleNamespace(source_id='source', representation_revision='representation')])
    relay = SimpleNamespace(binding_id='binding', model_id='model', context_window_tokens=6000, max_output_tokens=1000)
    store = OxigraphStore(tmp_path / 'facts')
    backend = SqliteCacheBackend(str(tmp_path / 'accepted.sqlite'))
    cache = ExtractionCache(backend=backend)
    def produce(context, profile, relay, source_id):
        calls.append(context)
        receipt = ModelReceipt(id=f'receipt-{len(calls)}', operation='source_classification',
            provider='fixture', model='model', input_digest='sha256:' + 'a' * 64, output_digest='sha256:' + 'b' * 64,
            parameters={}, metadata={})
        return SourceClassification(source_id=source_id, profile_id=profile.id, profile_version=profile.version,
            assignments=[], unclassified_dimension_ids=['purpose'], model_receipt_ids=[receipt.id]), [receipt]
    monkeypatch.setattr(builder, '_produce_source_classification', produce)
    def run():
        built = dict(source=source, passages=passages, native_operations=[])
        token = builder._native_build.set((request, store, cache))
        try:
            result = builder._classify_source(built, profile, relay)
            return result, built['native_classification_reduction']
        finally:
            builder._native_build.reset(token)
    try:
        (_, receipts), reduction = run()
        assert receipts and calls
        before = set(store.store)
        calls.clear()
        reads.clear()
        def forbidden(*args, **kwargs):
            pytest.fail('warm classification hydrated, recovered or repurchased data')
        monkeypatch.setattr(store, 'read_classification', forbidden)
        monkeypatch.setattr(store, 'read_classification_receipts', forbidden)
        monkeypatch.setattr(ClassificationRecords, 'read_reduced_dimension', forbidden)
        monkeypatch.setattr(cache, 'accepted_digest', forbidden)
        (value, receipts), restored = run()
        assert value is None and receipts == [] and restored == reduction and calls == []
        assert reads == []
        assert set(store.store) == before
    finally:
        store.close()
        backend.close()


def test_context_batch_boundaries_match_greedy_with_linear_serialized_work(monkeypatch):
    records=[('evidence',dict(id=str(i),quote='漢字"\\'*(1+i%17))) for i in range(2000)]
    base={'source':'source','evidence':[]}
    budget=8000
    expected=[]
    current={**base,'evidence':[]}
    for key,record in records:
        candidate={**current,key:[*current[key],record]}
        if builder._context_size(candidate)>budget:
            expected.append(current)
            current={**base,'evidence':[record]}
        else:
            current=candidate
    expected.append(current)
    original=builder._context_size
    serialized=0
    def observed(value):
        nonlocal serialized
        amount=original(value)
        serialized+=amount
        return amount
    monkeypatch.setattr(builder,'_context_size',observed)
    actual=list(builder._context_batches(base,iter(records),budget))
    assert actual==expected
    assert serialized<30*sum(original(row) for row in records)


def test_classification_native_addresses_are_selected_per_planned_batch(monkeypatch):
    profile=ClassificationProfile(id='profile',version='1',label='Profile',description='Profile',dimensions=[])
    passages=[SimpleNamespace(id=str(i),quote='context '*100) for i in range(20)]
    iterations,selections,seen=[],[],[]
    class Projected:
        def __iter__(self):
            iterations.append(True)
            return iter(passages)
        def select(self,identities):
            selections.append(list(identities))
            return (span for span in reversed(passages) if span.id in identities)
    monkeypatch.setattr(builder,'_ProjectionEvidence',Projected)
    monkeypatch.setattr(builder,'_input_token_budget',lambda _:2500)
    monkeypatch.setattr(builder,'_generation_payload',lambda _relay,prompt,_schema:prompt)
    def classify(built,*_):
        seen.extend(span.id for span in built['passages'])
        return None,[]
    monkeypatch.setattr(builder,'_classify_source_batch',classify)
    builder._classify_source({'source':SimpleNamespace(source_id='source'),'passages':Projected()},profile,object())
    assert len(iterations)==1
    assert len(selections)>1
    assert seen==[span.id for span in passages]
