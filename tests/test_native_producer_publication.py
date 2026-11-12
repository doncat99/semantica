"""The real build publishes references, never a second aggregate fact body."""
from tests.test_native_extraction_handoff import build_child
from semantica.triplet_store.oxigraph_store import OxigraphStore
import pytest


def test_deterministic_build_keeps_native_pattern_facts_without_aggregate(tmp_path, monkeypatch):
    from semantica.semantic_publication_builder import build_semantic_artifacts
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    from tests.test_semantic_artifact import _request
    source = tmp_path / 'source.txt'
    source.write_text('Ada Lovelace designed the Analytical Engine.')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'published')['params'])
    from semantica.triplet_store.publication_records import PublicationRecords
    stages = []
    for name in ('stage_communities', 'stage_topics'):
        original = getattr(PublicationRecords, name)
        def checked(self, generation, records, original=original):
            assert self._checkpoint['generation'] == generation
            stages.append(original.__name__)
            return original(self, generation, records)
        monkeypatch.setattr(PublicationRecords, name, checked)
    result = build_semantic_artifacts(request)
    assert 'stage_communities' in stages
    assert result['publication']['state'] == 'pending'
    assert result['publication']['source_count'] == 1
    assert result['publication']['canonical_count'] > 0
    assert not list((tmp_path / 'published').glob('*.json'))
    assert not list((tmp_path / 'published').glob('*.sqlite'))


@pytest.mark.parametrize('missing', ['unknown', 'scalar-proof', 'scalar-address', 'native-reference'])
def test_topic_publication_fails_closed_on_unmapped_citations(tmp_path, missing):
    from types import SimpleNamespace
    from semantica.semantic_publication_builder import _publish_native_topics, SemanticArtifactError
    from semantica.semantic_artifact_schema import EvidenceSpan, DocumentLocator, KnowledgeTopic
    from tests.triplet_store.test_publication_records import fixture, stage
    store, _, receipt, identity = fixture(tmp_path)
    generation = stage(store, receipt, identity)
    span = EvidenceSpan(id='span:one', representation_id='representation:one', quote='missing',
        locator=DocumentLocator(representation_id='representation:one', origin='native', quality='precise', quote='missing',
            **(dict(page=1) if missing == 'scalar-proof' else dict(start_char=5, end_char=12))))
    built = dict(source=SimpleNamespace(source_id='s'), evidence=[span], native_scalar_ranges=[dict(nativeRef='#/document/text',
            start=0, end=12, windowStart=0, windowEnd=12)])
    if missing == 'scalar-address':
        del built['native_scalar_ranges']
    topic = KnowledgeTopic(id='topic:one', title='Theme', entity_ids=['urn:canonical:acme'],
        evidence_ids=['span:unknown' if missing == 'unknown' else span.id],
        metadata=dict(organization=dict(report_id='report:one', input_digest='sha256:input')))
    with pytest.raises(SemanticArtifactError) as error:
        from semantica.triplet_store.publication_records import PublicationRecords
        _publish_native_topics(SimpleNamespace(project_id='p'), PublicationRecords(store, 'p'), generation, [built], [topic])
    assert error.value.code == 'NATIVE_TOPIC_GROUNDING_MISSING'
    assert error.value.diagnostic['topicGrounding']['topicId'] == 'topic:one'
    assert error.value.diagnostic['topicGrounding']['evidenceId'] == topic.evidence_ids[0]
    assert error.value.diagnostic['topicGrounding']['reason'] == missing
    if missing == 'native-reference':
        assert error.value.diagnostic['topicGrounding']['sourceId'] == 's'
        assert error.value.diagnostic['topicGrounding']['start'] == 5
        assert error.value.diagnostic['topicGrounding']['end'] == 12
    assert store.publication_status('p')['state'] == 'pending'
    store.close()


def test_actual_model_build_publishes_ready_native_references_without_aggregate(tmp_path):
    result = build_child(tmp_path, stop_before_publication=False)
    assert set(result) == {'publication', 'semantic_store', 'model_receipts', 'native_indexes'}
    assert result['publication']['state'] == 'ready'
    assert set(result['native_indexes']) == {'keyword','semantic'}
    assert result['native_indexes']['keyword']['receipt'] == result['publication']['indexes']['keyword']
    assert result['native_indexes']['semantic']['receipt'] == result['publication']['indexes']['semantic']
    assert result['publication']['source_count'] == 1
    assert result['publication']['canonical_count'] == 2
    assert not list((tmp_path / 'published').glob('*.json'))
    assert not list((tmp_path / 'published').glob('*.sqlite'))
    store = OxigraphStore(result['semantic_store']['path'])
    try:
        publication = [quad for quad in store.store if quad.graph_name.value.startswith('urn:semantica:publication:')]
        assert publication
        topics = store.read_publication_scene('project-1', result['publication']['generation'], dict(kind='topics'))
        assert topics['nodes'] and topics['nodes'][0]['organization']['basis'] == 'grounded-overview-section'
        assert topics['nodes'][0]['evidenceCount'] > 0
        topic_nodes = store.read_publication_scene('project-1', result['publication']['generation'],
            dict(kind='nodes', topicId=topics['nodes'][0]['id']))
        assert topic_nodes['nodes']
        assert not any(quad.object.value in {'Ada Lovelace', 'Analytical Engine'} for quad in publication)
        operations = [quad.object.value for quad in publication if quad.predicate.value.endswith(':operation')]
        assert len(operations) == 4  # extraction, relation, classification batch and reduction refs
        classification = store.read_native_classification_dimension('project-1', result['publication']['generation'], 'source-1')
        assert classification['dimensionIds'] == ['purpose', 'topic']
        assert sum(ref.startswith('urn:semantica:classification:') for ref in operations) == 2
        original = sorted(str(quad) for quad in store.store if quad.graph_name.value.startswith('urn:semantica:project:'))
    finally:
        store.close()
    calls = (tmp_path / 'build-calls.jsonl').read_bytes()
    next_result = build_child(tmp_path, stop_before_publication=False)
    assert (tmp_path / 'build-calls.jsonl').read_bytes() == calls
    assert next_result['publication']['generation'] == result['publication']['generation']
    store = OxigraphStore(result['semantic_store']['path'])
    try:
        assert sorted(str(quad) for quad in store.store if quad.graph_name.value.startswith('urn:semantica:project:')) == original
    finally:
        store.close()
