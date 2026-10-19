"""Admission and native-owner regressions; no remote models are used."""
import numpy as np
import pytest
from semantica.semantic_artifact_schema import KnowledgeEntity, KnowledgeRelation
from semantica.semantic_artifact_builder import _semantic_organization, _validate_embedding_projection
from semantica.vector_store.vector_store import VectorIndexer, VectorRetriever
from semantica.kg import CommunityDetector

def test_grounded_report_preserves_assertion_state_and_long_conditions(monkeypatch):
    from semantica import semantic_artifact_builder as pipeline
    condition = 'only when ' + 'explicit source condition ' * 8
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            assert condition in prompt
            assert '"polarity": "negative"' in prompt
            assert '"status": "contradicted"' in prompt
            return schema.model_validate({'title': 'Report', 'summary': 'Supported',
                'findings': [{'summary': 'Finding', 'explanation': 'Explanation',
                              'citations': [{'evidence_id': 'e1'}], 'native_metadata': {'rank': 1}}]},
                context=kwargs.get('validation_context'))
    monkeypatch.setattr(pipeline, '_project_model_provider', lambda *args: Provider())
    pipeline._grounded_explanation({'target': {'id': 'scope'}, 'entities': [], 'relations': [],
        'assertions': [{'id': 'assertion', 'subject_id': 'entity', 'predicate': 'works',
            'qualifiers': {'polarity': 'negative', 'condition': condition},
            'status': 'contradicted', 'evidence_ids': ['e1']}],
        'evidence': [{'id': 'e1', 'quote': 'Exact source'}]}, None)


def test_native_report_strict_schema_does_not_fallback_on_provider_failure():
    from semantica.kg.community_summarizer import CommunitySummarizer, CommunityReportLLMSchema
    class Provider:
        def generate_typed(self, *args, **kwargs):
            raise PermissionError('401 unauthorized')
        def generate(self, *args, **kwargs):
            pytest.fail('strict report must not send a fallback request')
    with pytest.raises(PermissionError, match='401'):
        CommunitySummarizer(llm=Provider()).summarize_community(
            {'id': 'scope', 'entity_ids': []}, use_cache=False,
            response_schema=CommunityReportLLMSchema)

def test_native_report_rejects_missing_prompt_evidence_before_model_call():
    from semantica.kg.community_summarizer import CommunitySummarizer, CommunityReportLLMSchema
    class Provider:
        def generate_typed(self, *args, **kwargs):
            pytest.fail('missing source must be rejected before model call')
    with pytest.raises(ValueError, match='omitted required source evidence'):
        CommunitySummarizer(llm=Provider()).summarize_community(
            {'id': 'scope', 'entity_ids': []}, use_cache=False,
            response_schema=CommunityReportLLMSchema,
            validation_context={'evidence': [{'id': 'missing', 'quote': 'Not in prompt'}]})


@pytest.mark.parametrize('finding', [
    {'summary': '', 'explanation': 'Text', 'citations': [{'evidence_id': 'e1'}]},
    {'summary': 'Title', 'explanation': '', 'citations': [{'evidence_id': 'e1'}]},
    {'summary': 'Title', 'explanation': 'Text', 'citations': []},
    {'summary': 'Title', 'explanation': 'Text', 'citations': [{'evidence_id': 'foreign'}]},
    {'summary': 'Title', 'explanation': 'Text', 'citations': [{'evidence_id': 'e1', 'quote': 'Invented'}]},
])
def test_native_report_rejects_invalid_findings_without_builder_parser(finding):
    from pydantic import ValidationError
    from semantica import semantic_artifact_builder as pipeline
    from semantica.kg.community_summarizer import CommunitySummarizer
    class Provider:
        def generate_typed(self, *args, **kwargs):
            return {'title': 'Report', 'summary': 'Supported', 'findings': [finding]}
        def generate(self, *args, **kwargs):
            pytest.fail('strict report must not fall back after validation failure')
    with pytest.raises(ValidationError):
        CommunitySummarizer(llm=Provider()).summarize_community(
            {'id': 'scope', 'entity_ids': []}, use_cache=False,
            text_chunks=[{'id': 'e1', 'text': 'Exact source'}],
            response_schema=pipeline._GroundedCommunityReport,
            validation_context={'evidence': [{'id': 'e1', 'quote': 'Exact source'}]})


def test_grounded_report_uses_native_packing_and_output(monkeypatch):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.kg.community_summarizer import CommunitySummarizer
    seen = []
    native = CommunitySummarizer.summarize_community
    def summarize(self, *args, **kwargs):
        seen.append(kwargs['text_chunks'])
        return native(self, *args, **kwargs)
    class Provider:
        receipts = []
        def generate_typed(self, prompt, schema, **kwargs):
            assert '[e1]: Exact source' in prompt
            return schema.model_validate({'title': 'Native report', 'summary': 'Supported',
                'findings': [{'summary': 'Native finding', 'explanation': 'Native explanation',
                              'citations': [{'evidence_id': 'e1'}]}]},
                context=kwargs.get('validation_context'))
    monkeypatch.setattr(CommunitySummarizer, 'summarize_community', summarize)
    monkeypatch.setattr(pipeline, '_project_model_provider', lambda *args: Provider())
    validations = []
    native_validate = pipeline._GroundedFinding.model_validate
    def validate(cls, value, **kwargs):
        validations.append(value)
        return native_validate(value, **kwargs)
    monkeypatch.setattr(pipeline._GroundedFinding, 'model_validate', classmethod(validate))
    context = {'target': {'id': 'scope', 'title': 'Topic'}, 'entities': [],
               'assertions': [], 'relations': [], 'evidence': [{'id': 'e1', 'quote': 'Exact source'}]}
    sections, _ = pipeline._grounded_explanation(context, SimpleNamespace())
    assert len(validations) == 1
    assert seen == [[{'id': 'e1', 'text': 'Exact source'}]]
    assert sections[0].title == 'Native finding'
    assert sections[0].text == 'Native explanation'
    assert sections[0].evidence_ids == ['e1']

@pytest.mark.parametrize('vectors', [[[1., 0.], [1.]], [[1., float('nan')]], [[0., 0.]], [[[1., 2.]]]])
def test_native_index_rejects_invalid_vector_space(vectors):
    with pytest.raises(ValueError):
        VectorIndexer(dimension=2).create_index(vectors)

def test_native_query_rejects_dimension_coercion():
    with pytest.raises(ValueError):
        VectorRetriever().search_similar([1., 0.], [[1., 0., 1.]], ['one'])

def test_embedding_admission_does_not_search_every_stored_vector(monkeypatch):
    from semantica.vector_store import VectorStore
    monkeypatch.setattr(VectorStore, 'search_vectors', lambda *_args, **_kwargs: pytest.fail('quadratic self-search'))
    from types import SimpleNamespace
    _validate_embedding_projection([{'source': SimpleNamespace(source_id='one'), 'embeddings': [
        {'vector': [1., 0.], 'start_char': 0, 'end_char': 5},
        {'vector': [0., 1.], 'start_char': 5, 'end_char': 10}]}])

def test_organization_does_not_reinterpret_admitted_identity():
    entities = [KnowledgeEntity(id='person', canonical_name='Jordan', type='Person', metadata={'source_ids': ['one']}),
                KnowledgeEntity(id='country', canonical_name='Jordan', type='Country', metadata={'source_ids': ['two']})]
    communities, topics = _semantic_organization(entities, [], [], [])
    assert {entity for community in communities for entity in community.entity_ids} == {"person", "country"}

def test_native_community_algorithm_and_isolates_are_explicit():
    import networkx as nx
    graph = nx.Graph()
    graph.add_nodes_from(['a', 'b', 'c'])
    result = CommunityDetector().detect_communities(graph, algorithm='greedy_modularity')
    assert result['algorithm'] == 'greedy_modularity'
    assert {frozenset(group) for group in result['communities']} == {frozenset([node]) for node in graph}

def test_native_delta_covers_conflict_and_identity_deletion():
    from semantica.change_management.managers import TemporalVersionManager
    result = TemporalVersionManager().compare_collections(
        {'conflicts': [{'id': 'conflict', 'status': 'open'}], 'identity': [{'id': 'split'}]},
        {'conflicts': [], 'identity': []})
    assert result['removed_ids'] == ['conflict', 'split']

def test_native_conflict_respects_recorded_conditions():
    from semantica.conflicts import ConflictDetector
    facts = [{'id': 'a', 'subject': 's', 'predicate': 'p', 'object': 'o',
              'qualifiers': {'polarity': 'positive', 'time': '2025'}},
             {'id': 'b', 'subject': 's', 'predicate': 'p', 'object': 'o',
              'qualifiers': {'polarity': 'negative', 'time': '2026'}}]
    assert ConflictDetector.qualified_polarity_groups(facts) == []

def test_query_uses_native_vector_ranking(monkeypatch, tmp_path):
    from tests.test_semantic_query_worker import _semantic_request, _serve
    original = VectorRetriever.search_similar
    calls = []
    def search(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(VectorRetriever, 'search_similar', search)
    assert _serve(_semantic_request(tmp_path))['ok']
    assert calls

def test_query_uses_native_keyword_ranking_after_source_admission(monkeypatch, tmp_path):
    from semantica.context.context_retriever import ContextRetriever
    from tests.test_semantic_query_worker import _build, _request, _serve
    original = ContextRetriever._keyword_match_entities
    calls = []
    def search(self, entities, query, max_results):
        calls.append([item['id'] for item in entities])
        return original(self, entities, query, max_results)
    monkeypatch.setattr(ContextRetriever, '_keyword_match_entities', search)
    request = _request(_build(tmp_path))
    assert _serve(request)['ok']
    assert calls and calls[0]
    calls.clear()
    request['params']['sourceIds'] = []
    response = _serve(request)
    assert response['ok'] and not response['result']['contexts']
    assert not calls or calls == [[]]

def test_query_hashes_and_parses_same_bytes(monkeypatch, tmp_path):
    from hashlib import sha256
    from pathlib import Path
    from semantica.semantic_query import _load_json
    artifact = tmp_path / 'artifact.json'
    artifact.write_bytes(b'{"value":1}')
    monkeypatch.setattr(Path, 'read_text', lambda *_args, **_kwargs: pytest.fail('second read may differ from hashed bytes'))
    assert _load_json(artifact, 'sha256:' + sha256(artifact.read_bytes()).hexdigest()) == {'value': 1}

def test_native_store_rejects_bad_space_before_mutation():
    from semantica.vector_store import VectorStore
    store = VectorStore(backend='inmemory', dimension=2)
    with pytest.raises(ValueError):
        store.store_vectors([[1., 0., 1.]])
    assert store.vectors == {} and store.metadata == {}
    ids = store.store_vectors([[1., 0.]])
    with pytest.raises(ValueError):
        store.update_vectors(ids, [[0., 0.]])
    assert list(store.get_vector(ids[0])) == [1., 0.]

@pytest.mark.parametrize('reflexive,expected', [(None, 0), (False, 0), (True, 1)])
def test_reflexive_relation_requires_semantic_permission(reflexive, expected):
    from semantica.semantic_extract.schema import ExtractionSpecification, ExtractionSchema
    from semantica.semantic_extract.types import Entity
    from semantica.semantic_extract.methods import _parse_grounded_relation_result
    relation_type = {'name': 'equals', 'description': 'identity equality'}
    if reflexive is not None:
        relation_type['reflexive'] = reflexive
    spec = ExtractionSpecification(id='test', version='1', entity_types=[{'name': 'Thing', 'description': 'thing'}],
                                   relation_types=[relation_type])
    entity = Entity('A', 'Thing', 0, 1, 1., {'mention_id': 'a'})
    result = {'relations': [{'subject_id': 'a', 'object_id': 'a', 'predicate': 'equals',
                            'evidence': 'A equals itself.', 'evidence_occurrence': 0,
                            'qualifiers': {'polarity': 'positive'}, 'confidence': 1.}]}
    relations = _parse_grounded_relation_result(result, [entity], 'A equals itself.', 'test', None,
                                                reject_invalid=True, extraction_schema=ExtractionSchema.from_specification(spec))
    assert len(relations) == expected

def test_reflexivity_extension_preserves_legacy_spec_digest():
    import json
    from hashlib import sha256
    from semantica.semantic_extract.schema import ExtractionSpecification
    spec = ExtractionSpecification(id='test', version='1', entity_types=[{'name': 'Thing', 'description': 'thing'}],
                                   relation_types=[{'name': 'equals', 'description': 'equality'}])
    legacy = spec.model_dump(mode='json')
    for relation in legacy['relation_types']:
        relation.pop('reflexive', None)
    digest = 'sha256:' + sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert spec.digest == digest

@pytest.mark.parametrize('fail_fast', [False, True])
def test_native_task_duration_measures_handler_not_future_collection(monkeypatch, fail_fast):
    from semantica.pipeline import parallelism_manager as native
    clock = [100.]
    monkeypatch.setattr(native.time, 'perf_counter', lambda: clock[0])
    def handler():
        clock[0] += 7.
        return 'done'
    results = native.ParallelismManager(max_workers=1).execute_parallel([
        native.Task('one', handler)], fail_fast_permanent=fail_fast)
    assert results[0].execution_time == 7.

def test_native_louvain_calls_louvain_not_greedy(monkeypatch):
    import networkx as nx
    called = []
    def louvain(graph, **kwargs):
        called.append(kwargs)
        return [set(graph.nodes)]
    monkeypatch.setattr(nx.algorithms.community, 'louvain_communities', louvain)
    monkeypatch.setattr(nx.algorithms.community, 'greedy_modularity_communities', lambda *a, **k: pytest.fail('wrong algorithm'))
    graph = nx.path_graph(4)
    assert CommunityDetector().detect_communities_louvain(graph, resolution=2.)['algorithm'] == 'louvain'
    assert called[0]['resolution'] == 2.

def test_leiden_uses_existing_native_refinement_not_louvain(monkeypatch):
    import networkx as nx
    from semantica.kg.community_hierarchy import CommunityHierarchyBuilder
    original = CommunityHierarchyBuilder.detect_leiden_partition
    calls = []
    def partition(self, *args, **kwargs):
        calls.append(kwargs)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CommunityHierarchyBuilder, 'detect_leiden_partition', partition)
    monkeypatch.setattr(nx.algorithms.community, 'louvain_communities', lambda *a, **k: pytest.fail('wrong algorithm'))
    result = CommunityDetector().detect_communities_leiden(nx.path_graph(4), resolution=2.)
    assert result['algorithm'] == 'leiden'
    assert set(result['node_assignments']) == set(range(4))
    assert calls[0]['resolution'] == 2.

def test_retrieval_index_references_canonical_snapshot_without_copying_records(tmp_path):
    import json
    from tests.test_semantic_query_worker import _build, _request, _serve
    built = _build(tmp_path)
    retrieval = json.loads(built['retrieval_path'].read_text())
    assert retrieval['format'] == 'semantica.retrieval-reference.v1'
    assert not set(retrieval).intersection({'entities', 'relations', 'assertions', 'evidence', 'conflicts', 'topics'})
    assert _serve(_request(built))['ok']


@pytest.mark.parametrize('target_ids, expected_calls, expected_reports', [
    (None, ['overview'], 1),
    (['project'], ['overview'], 1),
    (['entity'], ['concept'], 1),
    (['community'], ['community'], 1),
    (['topic'], ['topic'], 1),
    (['community', 'topic'], ['community'], 2),
])
def test_report_targets_bound_calls_and_reuse_community_report(
        monkeypatch, target_ids, expected_calls, expected_reports):
    from types import SimpleNamespace
    from semantica import semantic_artifact_builder as pipeline
    from semantica.semantic_artifact_schema import KnowledgeCommunity, KnowledgeTopic, EvidenceSpan, DocumentLocator, ReportSection
    span = EvidenceSpan(id='ev', representation_id='rep', quote='Supported source.', locator=DocumentLocator(
        representation_id='rep', origin='native', quote='Supported source.', quality='precise', start_char=0, end_char=17))
    entity = KnowledgeEntity(id='entity', canonical_name='Concept', type='Concept', evidence_ids=['ev'])
    community = KnowledgeCommunity(id='community', level=0, title='Concept', entity_ids=['entity'])
    topic = KnowledgeTopic(id='topic', title='Concept', entity_ids=['entity'], community_ids=['community'], evidence_ids=['ev'])
    calls = []
    def explain(context, relay):
        calls.append(context['target']['type'])
        return [ReportSection(title='Meaning', text='Supported explanation.', evidence_ids=['ev'])], []
    monkeypatch.setattr(pipeline, '_grounded_explanation', explain)
    reports, receipts = pipeline._explanation_reports('project', [{'passages': [span]}], [entity], [], [],
        [community], [topic], [span], SimpleNamespace(model_id='model'), target_ids=target_ids)
    assert calls == expected_calls
    assert len(reports) == expected_reports
    if target_ids == ['community', 'topic']:
        assert reports[-1].sections == reports[-2].sections
        assert reports[-1].metadata['derived_from_report_id'] == reports[-2].id


def test_query_process_cache_reuses_admitted_bytes_and_rejects_file_changes(tmp_path, monkeypatch):
    import json
    from hashlib import sha256
    from pathlib import Path
    from semantica.semantic_query import _load_json, QueryError
    file = tmp_path / 'snapshot.json'
    original = b'{"value":1}'
    file.write_bytes(original)
    digest = 'sha256:' + sha256(original).hexdigest()
    reads = []
    read_bytes = Path.read_bytes
    def read(path):
        reads.append(path)
        return read_bytes(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    assert _load_json(file, digest) == {'value': 1}
    assert _load_json(file, digest) == {'value': 1}
    assert len(reads) == 1
    file.write_bytes(b'{"value":2}')
    with pytest.raises(QueryError, match='digest'):
        _load_json(file, digest)
    assert len(reads) == 2
