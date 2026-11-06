"""Project-scale semantic bodies must not all survive source processing."""
import gc
import hashlib
import json
import weakref

import pytest

from semantica import semantic_publication_builder as builder
from tests.test_native_build_body_budget import project_request


class ProbeComplete(Exception):
    pass


def span_probe(monkeypatch):
    references = {}
    source_passages = builder._source_passages
    build_source = builder._build_source

    def remember(spans):
        for span in spans:
            references[span.id] = (weakref.ref(span), len(span.quote.encode('utf-8')), fingerprint(span))

    def passages(built):
        spans = source_passages(built)
        remember(spans)
        return spans

    def source(*args, **kwargs):
        built = build_source(*args, **kwargs)
        remember(built['evidence'])
        return built

    monkeypatch.setattr(builder, '_source_passages', passages)
    monkeypatch.setattr(builder, '_build_source', source)
    return references


def quote_bytes(references):
    gc.collect()
    live = [ref() for ref, _size, _fingerprint in references.values() if ref() is not None]
    return len(live), sum(len(span.quote.encode('utf-8')) for span in live)


def fingerprint(span):
    # Retain only a digest: keeping oracle strings would invalidate the budget probe.
    encoded = json.dumps(span.model_dump(mode='json', by_alias=True),
                         sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def assert_complete_equivalent_references(evidence, references):
    assert {item.id for item in evidence} == set(references), 'reference projection changed evidence coverage'

    def no_quotes(value):
        if isinstance(value, dict):
            assert 'quote' not in value, 'reference payload retained a quote field'
            for child in value.values():
                no_quotes(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                no_quotes(child)

    # Traverse twice so a one-shot iterator or stale mutable hydration cannot pass.
    for _ in range(2):
        for item in evidence:
            assert fingerprint(item) == references[item.id][2], f'evidence projection changed {item.id}'
            no_quotes(item.fields)


def assert_not_project_bodies_retained(references, phase):
    live_count, live_bytes = quote_bytes(references)
    expected_bytes = sum(size for _ref, size, _fingerprint in references.values())
    assert live_count == 0, (
        f'{phase}: {live_count} original passage/evidence objects remain live; '
        f'{live_bytes} of {expected_bytes} captured UTF-8 quote bytes are retained across the project'
    )


def test_deterministic_global_organization_does_not_retain_all_quote_bodies(tmp_path, monkeypatch):
    request = project_request(tmp_path, recipe='deterministic', count=8, repeats=128)
    references = span_probe(monkeypatch)
    captured = []

    def inspect(topology):
        captured.append((len(references), sum(size for _ref, size, _fingerprint in references.values())))
        assert set(topology) == {'entities', 'relationships'}
        assert all(set(row) == {'id', 'name'} for row in topology['entities'])
        assert all(set(row) == {'id', 'source', 'target', 'type'} for row in topology['relationships'])
        assert_not_project_bodies_retained(references, 'deterministic semantic_organization input')
        raise ProbeComplete('organization boundary observed')

    monkeypatch.setattr(builder, '_semantic_organization', inspect)
    with pytest.raises(ProbeComplete, match='boundary observed'):
        builder.build_semantic_artifacts(request)
    assert len(captured) == 1
    assert captured[0][1] > 20_000


def test_model_report_input_does_not_retain_all_project_quote_bodies(tmp_path, monkeypatch):
    request = project_request(tmp_path, recipe='model', count=8, repeats=128)
    references = span_probe(monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-token')
    monkeypatch.setattr(builder, '_organization_report_product', lambda action, *_args, **_kwargs: None)
    from semantica.semantic_extract.providers import BaseProvider

    class EmptyProvider(BaseProvider):
        def __init__(self):
            super().__init__(model=request.relays['model'].model_id)
            self.receipts, self.rejections = [], []

        def generate(self, prompt, **kwargs):
            self.receipts.append(dict(id='receipt:empty:' + str(len(self.receipts)),
                provider='fixture', model=request.relays['model'].model_id, operation='structured_extraction',
                metadata={'extraction_stage': kwargs['extraction_stage']},
                input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64))
            return '{"entities": []}'

    # Keep native admission and handoff real; replace only the offline model.
    monkeypatch.setattr(builder, '_project_model_provider', lambda *_args: EmptyProvider())
    def embedding_response(relay, payload, operation, **_kwargs):
        assert operation == 'embedding'
        receipt = builder.ModelReceipt(id='receipt:embedding', provider='fixture',
            model=relay.model_id, operation='embedding', metadata={},
            input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64)
        return dict(model=relay.model_id, data=[dict(index=index, embedding=[1.0, 0.0])
            for index, _ in enumerate(payload['input'])]), receipt

    monkeypatch.setattr(builder, '_relay_json', embedding_response)
    observed = []
    explanation_reports = builder._explanation_reports

    def inspect_references(project_id, source_builds, entities, assertions, relations,
                           communities, topics, evidence, *args, **kwargs):
        # Every native reference remains available on its source. The report
        # boundary receives only the evidence needed by its admitted knowledge.
        assert_complete_equivalent_references(
            [span for built in source_builds for span in built['evidence']], references)
        assert not isinstance(evidence, (list, tuple, dict))
        evidence = list(evidence)
        assert {span.id for span in evidence} == {
            ref for values in (entities, assertions, relations) for item in values for ref in item.evidence_ids}
        assert_not_project_bodies_retained(references, 'model report reference selection')
        return explanation_reports(project_id, source_builds, entities, assertions, relations,
                                   communities, topics, evidence, *args, **kwargs)

    monkeypatch.setattr(builder, '_explanation_reports', inspect_references)

    def inspect(context, _relay):
        observed.append([item['quote'] for item in context['evidence']])
        assert_not_project_bodies_retained(references, 'model grounded-report input')
        raise ProbeComplete('report boundary observed before relay')

    monkeypatch.setattr(builder, '_grounded_explanation', inspect)
    with pytest.raises(ProbeComplete, match='before relay'):
        builder.build_semantic_artifacts(request)
    assert len(observed) == 1
    assert sorted(observed[0]) == [f'Source {index}.' for index in range(8)]
    assert sum(size for _ref, size, _fingerprint in references.values()) > 20_000
