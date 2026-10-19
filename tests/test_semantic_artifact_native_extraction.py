from tests.artifact_helpers import extract_source
import inspect
from types import SimpleNamespace

import pytest
import re
from pydantic import BaseModel

from semantica import semantic_artifact_builder
from semantica.semantic_artifact_builder import SemanticArtifactError
from semantica.semantic_artifact_schema import ModelReceipt
from semantica.semantic_extract.types import Entity, Relation
from semantica.utils.exceptions import ProcessingError


def test_entity_occurrence_index_preserves_identity_and_scans_each_name_once(monkeypatch):
    text = "Roof roof rooftop ROOF Roof"
    original = re.finditer
    calls = []
    def scan(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(semantic_artifact_builder.re, "finditer", scan)
    cache = semantic_artifact_builder._entity_occurrence_index(text, ["Roof", "Roof"])
    for match in original("Roof", text, re.IGNORECASE):
        occurrence = sum(1 for prior in original("Roof", text[:match.end()], re.IGNORECASE) if prior.start() < match.start())
        expected = "mention:" + semantic_artifact_builder.stable_digest(["source", "object", "roof", occurrence]).split(":")[1][:32]
        assert semantic_artifact_builder._entity_id("source", "Roof", "object", match.start(), cache) == expected
    assert calls == []


def test_occurrence_index_uses_literal_search_without_changing_unicode_matching(monkeypatch):
    text = "I İ ı i S ſ s K K k Σ σ ς ß ẞ é É aaaa"
    names = ["I", "i", "S", "K", "Σ", "ß", "é", "aa"]
    original = re.finditer
    expected = {name: [m.start() for m in original(re.escape(name), text, re.IGNORECASE)] for name in names}
    scans = []
    def scan(pattern, source, flags=0):
        scans.append(flags)
        return original(pattern, source, flags)
    monkeypatch.setattr(semantic_artifact_builder.re, "finditer", scan)
    assert semantic_artifact_builder._entity_occurrence_index(text, names) == expected
    assert sum(flags == re.IGNORECASE for flags in scans) == 3


def test_worker_internal_failure_retains_code_location_without_source_content():
    from semantica.semantic_worker import _response
    try:
        raise SemanticArtifactError("private document contents", code="SEMANTIC_SELF_RELATION")
    except SemanticArtifactError as error:
        response = _response("request-1", False, error=error)
    diagnostic = response["error"]["diagnostic"]
    assert diagnostic["code"] == "SEMANTIC_SELF_RELATION"
    assert diagnostic["fault"]["function"] == "test_worker_internal_failure_retains_code_location_without_source_content"
    assert diagnostic["fault"]["line"] > 0
    assert "private document" not in str(diagnostic)


def test_parallel_extraction_failure_retains_task_and_window_context(monkeypatch):
    relay_failure = SemanticArtifactError(
        "structured_extraction relay returned HTTP 404",
        status=404,
        code="UPSTREAM_NOT_FOUND",
        retryable=True,
    )

    monkeypatch.setattr(
        semantic_artifact_builder,
        "_text_windows",
        lambda _text: [(12, 34, "window")],
    )

    def grounded(_text, **_kwargs):
        raise ProcessingError("grounded extraction failed") from relay_failure

    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", grounded)

    with pytest.raises(SemanticArtifactError) as failure:
        extract_source(
            "source", SimpleNamespace(model_id="model-1"), object(), parallelism=1
        )

    assert failure.value.status == 404
    assert failure.value.code == "UPSTREAM_NOT_FOUND"
    assert failure.value.diagnostic["parallelTask"] == {
        "taskId": "0",
        "sourceIndex": 0,
        "windowStart": 12,
        "windowEnd": 34,
        "errorType": "ProcessingError",
        "errorMessage": "grounded extraction failed",
    }


def test_worker_internal_failure_keeps_parallel_task_context():
    from semantica.semantic_worker import _response

    error = ProcessingError("parallel task 3 failed")
    error.parallel_context = {
        "taskId": "3",
        "windowStart": 100,
        "windowEnd": 200,
        "errorType": "ProcessingError",
        "errorMessage": "parallel task 3 failed",
    }
    response = _response("request-2", False, error=error)

    assert response["error"]["diagnostic"]["parallelTask"] == {
        "taskId": "3",
        "windowStart": 100,
        "windowEnd": 200,
        "errorType": "ProcessingError",
        "errorMessage": "parallel task 3 failed",
    }


def test_build_parallelism_accepts_host_ceiling_and_rejects_overflow():
    from pydantic import TypeAdapter, ValidationError
    from typing import Annotated
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    field = SemanticArtifactBuildRequest.model_fields["parallelism"]
    adapter = TypeAdapter(Annotated[int, *field.metadata])
    assert adapter.validate_python(16) == 16
    with pytest.raises(ValidationError):
        adapter.validate_python(17)


def test_semantic_artifact_extraction_uses_canonical_semantica_extractors(monkeypatch):
    calls = []

    class Provider:
        receipts = [ModelReceipt(
            id="receipt:extraction",
            operation="structured_extraction",
            provider="test",
            model="model-1",
            input_digest="sha256:" + "1" * 64,
            output_digest="sha256:" + "2" * 64,
        )]

    def grounded(text, **kwargs):
        calls.append(("grounded", text, kwargs))
        entities = [
            Entity("Reflective roofs", "measure", 0, 16, 0.9, {"mention_id": "mention:0", "span_occurrence": 0}),
            Entity("pedestrians", "population", 30, 41, 0.9, {"mention_id": "mention:1", "span_occurrence": 0}),
        ]
        relations = [Relation(
            entities[0], "shades", entities[1], 0.9,
            "Reflective roofs do not shade pedestrians.",
            {"qualifiers": {"polarity": "negative"}, "evidence_start": 0, "evidence_end": 42,
             "evidence_occurrence": 0, "subject_id": "mention:0", "object_id": "mention:1"},
        )]
        return entities, relations, Provider()

    monkeypatch.setattr(semantic_artifact_builder, "_project_model_provider", lambda _relay: Provider())
    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", grounded)
    monkeypatch.setattr(
        semantic_artifact_builder,
        "_embed_texts",
        lambda texts, _relay: ([[0.1, 0.2] for _ in texts], ModelReceipt(
            id="receipt:embedding",
            operation="embedding",
            provider="test",
            model="embedding-1",
            input_digest="sha256:" + "3" * 64,
            output_digest="sha256:" + "4" * 64,
        )),
    )

    result, embeddings, receipts = extract_source(
        "Reflective roofs do not shade pedestrians.", SimpleNamespace(model_id="model-1"), object()
    )

    assert [name for name, *_ in calls] == ["grounded"]
    assert calls[0][2]["extraction_spec"] is None
    assert result["entities"][0]["name"] == "Reflective roofs"
    assert result["relations"][0]["evidence"] == "Reflective roofs do not shade pedestrians."
    assert embeddings == [{"start_char": 0, "end_char": 42, "vector": [0.1, 0.2]}]
    assert {receipt.operation for receipt in receipts} == {"structured_extraction", "embedding"}


def test_semantic_artifact_has_no_parallel_structured_extractor():
    source = inspect.getsource(semantic_artifact_builder)
    assert "def _structured_extract" not in source
    assert "return _structured_extract" not in source
    assert "ThreadPoolExecutor" not in source
    assert "ParallelismManager" in source


def test_project_model_provider_uses_host_admitted_output_limit(monkeypatch):
    request = {}

    def relay_json(_relay, payload, operation):
        request.update(payload)
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"entities": []}'}}],
            "model": "model-1",
        }, ModelReceipt(
            id="receipt:extraction",
            operation=operation,
            provider="test",
            model="model-1",
            input_digest="sha256:" + "1" * 64,
            output_digest="sha256:" + "2" * 64,
        )

    monkeypatch.setattr(semantic_artifact_builder, "_relay_json", relay_json)
    provider = semantic_artifact_builder._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=32768)
    )

    assert provider.generate("prompt", max_tokens=2048) == '{"entities": []}'
    assert request["max_tokens"] == 32768


def test_native_extraction_preserves_retryable_relay_failure(monkeypatch):
    relay_failure = SemanticArtifactError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )

    def grounded(_text, **_kwargs):
        raise ProcessingError("typed extraction failed") from relay_failure

    monkeypatch.setattr(semantic_artifact_builder, "extract_grounded_window", grounded)

    with pytest.raises(SemanticArtifactError) as failure:
        extract_source(
            "Retryable source text", SimpleNamespace(model_id="model-1"), object()
        )

    assert failure.value.status == 500
    assert failure.value.code == "INTERNAL_ERROR"
    assert failure.value.retryable is True


def test_native_parallel_map_propagates_permanent_failure_for_fail_fast():
    calls = []

    def grounded(item):
        calls.append(item)
        if item == "permanent":
            raise SemanticArtifactError("unauthorized", status=401, retryable=False)
        return item

    with pytest.raises(ProcessingError) as failure:
        semantic_artifact_builder._native_parallel_map(
            ["permanent", "queued"], grounded, parallelism=1
        )

    assert failure.value.retryable is False
    assert calls == ["permanent"]


def test_provider_preserves_permanent_relay_failure_through_structured_wrapper():
    from semantica.semantic_extract.providers import BaseProvider

    class Provider(BaseProvider):
        def generate(self, _prompt, **_kwargs):
            raise SemanticArtifactError("unauthorized", status=401, retryable=False)

    with pytest.raises(ProcessingError) as failure:
        Provider().generate_structured("return JSON", max_retries=1)

    assert failure.value.retryable is False
    assert isinstance(failure.value.__cause__, SemanticArtifactError)


def test_provider_does_not_retry_or_raw_fallback_permanent_relay_failure():
    from semantica.semantic_extract.providers import BaseProvider

    calls = []

    class Provider(BaseProvider):
        def generate(self, _prompt, **_kwargs):
            calls.append("generate")
            raise SemanticArtifactError("quota unavailable", status=503, retryable=False)

    with pytest.raises(ProcessingError) as failure:
        Provider().generate_typed("return JSON", dict, max_retries=3)

    assert calls == ["generate"]
    assert failure.value.retryable is False
    assert isinstance(failure.value.__cause__, SemanticArtifactError)


def test_provider_treats_relay_error_body_as_permanent_before_sdk_retry():
    from semantica.semantic_extract.providers import BaseProvider

    calls = []

    class Provider(BaseProvider):
        def generate(self, _prompt, **_kwargs):
            calls.append("generate")
            error = RuntimeError("gateway rejected request")
            error.status_code = 503
            error.body = {"error": {"code": "DEFAULT_SERVICE_QUOTA_UNAVAILABLE", "retryable": False}}
            raise error

    with pytest.raises(ProcessingError) as failure:
        Provider().generate_typed("return JSON", dict, max_retries=3)

    assert calls == ["generate"]
    assert failure.value.retryable is False


def test_provider_does_not_manual_fallback_for_unauthorized_sdk_error():
    from semantica.semantic_extract.providers import BaseProvider

    calls = []

    class Provider(BaseProvider):
        def generate(self, _prompt, **_kwargs):
            calls.append("generate")
            error = RuntimeError("unauthorized")
            error.status_code = 401
            raise error

    with pytest.raises(ProcessingError) as failure:
        Provider().generate_typed("return JSON", dict, max_retries=3)

    assert calls == ["generate"]
    assert failure.value.retryable is False


def test_typed_provider_keeps_relay_failure_as_its_cause(monkeypatch):
    class Output(BaseModel):
        entities: list = []

    relay_failure = SemanticArtifactError(
        "structured_extraction relay returned HTTP 500: INTERNAL_ERROR",
        status=500,
        code="INTERNAL_ERROR",
        retryable=True,
    )
    monkeypatch.setattr(
        semantic_artifact_builder,
        "_relay_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(relay_failure),
    )
    provider = semantic_artifact_builder._project_model_provider(
        SimpleNamespace(model_id="model-1", max_output_tokens=393216)
    )

    with pytest.raises(ProcessingError) as failure:
        provider.generate_typed("extract entities", Output, max_retries=1)

    assert failure.value.__cause__ is relay_failure


def test_native_empty_result_cache_restores_rejections_and_receipts(tmp_path, monkeypatch):
    from tests.artifact_helpers import stub_native_provider
    from tests.test_semantic_artifact import _request
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest

    text = "The committee supervises reporting."
    path = tmp_path / "source.txt"
    path.write_text(text)
    checkpoint = SnapshotCheckpoint(SemanticArtifactBuildRequest.model_validate(
        _request(path, tmp_path / "output")["params"]))
    calls = []
    def respond(stage, prompt):
        calls.append(stage)
        return {"entities": [{"text": " committee ", "label": "ORG", "occurrence": 0,
                              "confidence": 0.9, "attributes": {}}]}
    stub_native_provider(monkeypatch, respond)
    token = active_checkpoint.set(checkpoint)
    try:
        args = (text, SimpleNamespace(model_id="test"), None, (0, len(text), text), [])
        first, first_receipts, reused = semantic_artifact_builder._extract_window_context(*args)
        second, receipts, restored = semantic_artifact_builder._extract_window_context(*args)
    finally:
        active_checkpoint.reset(token)
    assert first == second == {"entities": [], "relations": []}
    assert calls == ["entities"] and not reused and restored
    assert receipts[0].id == first_receipts[0].id
    assert receipts[0].metadata["rejected_candidates"]
    assert len(list(checkpoint.root.glob("extraction-entities-*.json"))) == 1
    assert not list(checkpoint.root.glob("relay-*.json"))


def test_source_assembly_preserves_relations_when_distinct_refs_share_identity(tmp_path):
    from semantica.semantic_artifact_schema import SourceBuildInput
    from semantica.source import source_content_revision
    path = tmp_path / 'source.txt'
    text = 'Fund owns Bond.'
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId='source-1',
        materialRevision=source_content_revision(path), name=path.name, mimeType='text/plain')
    result = {'entities': [
        {'id': 'a', 'name': 'Fund', 'type': 'organization', 'occurrence': 0},
        {'id': 'duplicate', 'name': 'Fund', 'type': 'organization', 'occurrence': 0},
        {'id': 'b', 'name': 'Bond', 'type': 'asset', 'occurrence': 0},
    ], 'relations': [
        {'subject': 'a', 'object': 'duplicate', 'predicate': 'owns', 'evidence': text,
         'evidence_occurrence': 0, 'qualifiers': {'polarity': 'positive'}},
        {'subject': 'a', 'object': 'b', 'predicate': 'owns', 'evidence': text,
         'evidence_occurrence': 0, 'qualifiers': {'polarity': 'positive'}},
    ]}
    built = semantic_artifact_builder._build_source(source, False, result,
        (text, {'format': 'text'}, 'native', source.material_revision, 'text', '1'))
    assert len(built['entities']) == 2
    assert len(built['relations']) == len(built['assertions']) == 2
    assert built['relations'][0].source_entity_id == built['relations'][0].target_entity_id
    assert not built['representation'].metadata.get('rejected_candidates')


def test_whitespace_variants_share_occurrence_numbers_before_identity_resolution():
    text = 'Paris Agreement and Paris  Agreement and Paris\nAgreement'
    names = ['Paris Agreement', 'Paris  Agreement', 'Paris\nAgreement']
    positions = [0, 20, 41]
    index = semantic_artifact_builder._entity_occurrence_index(text, names)
    assert all(index[name] == positions for name in names)
    ids = [semantic_artifact_builder._entity_id('source', name, 'EVENT', start, index)
           for name, start in zip(names, positions)]
    assert len(set(ids)) == 3
    assert semantic_artifact_builder._entity_id('source', names[0], 'EVENT', positions[1], index) == ids[1]


def test_identity_remap_preserves_collapsed_facts_through_native_graph(monkeypatch):
    from semantica.kg import GraphBuilder
    from semantica.semantic_artifact_schema import KnowledgeEntity
    calls = []
    original = GraphBuilder._remap_relationship_endpoints
    def tracked(self, relationships, entities):
        calls.append(True)
        return original(self, relationships, entities)
    monkeypatch.setattr(GraphBuilder, '_remap_relationship_endpoints', tracked)
    assertions = [SimpleNamespace(id='a1', subject_id='first', object_entity_id='second', evidence_ids=['proof'])]
    relations = [SimpleNamespace(id='r1', source_entity_id='first', target_entity_id='second', evidence_ids=['proof'])]
    entities = [KnowledgeEntity(id='canonical', canonical_name='Example', type='CONCEPT', evidence_ids=['proof'],
                               metadata={'mention_ids': ['first', 'second']})]
    kept_assertions, kept_relations = semantic_artifact_builder._remap_identity_facts(
        assertions, relations, {'first': 'canonical', 'second': 'canonical'}, entities)
    assert [item.id for item in kept_assertions] == ['a1']
    assert [item.id for item in kept_relations] == ['r1']
    assert kept_relations[0].source_entity_id == kept_relations[0].target_entity_id == 'canonical'
    assert kept_assertions[0].subject_id == kept_assertions[0].object_entity_id == 'canonical'
    assert calls
