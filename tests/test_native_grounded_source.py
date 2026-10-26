import pytest
from types import SimpleNamespace

from semantica import semantic_artifact_builder as pipeline
from semantica import semantic_source_artifact as source_artifact
from semantica.source import source_content_revision
from semantica.semantic_artifact_schema import SourceBuildInput, stable_digest
from tests.test_semantic_artifact_long_context import _stub_canonical_extraction, receipt


def test_grounded_source_reuses_native_owners_without_embedding(tmp_path, monkeypatch):
    path = tmp_path / 'original.txt'
    text = 'Ada builds Engine.'
    path.write_text(text)
    _stub_canonical_extraction(monkeypatch, lambda *_: ({
        'entities': [{'id': name, 'name': name, 'type': 'CONCEPT', 'occurrence': 0}
                     for name in ('Ada', 'Engine')],
        'relations': [{'subject': 'Ada', 'predicate': 'builds', 'object': 'Engine',
                       'evidence': text, 'evidence_occurrence': 0,
                       'qualifiers': {'polarity': 'positive'}}]}, receipt('structured_extraction', 1)))
    monkeypatch.setattr(pipeline, '_embed_texts', lambda *_: pytest.fail('unexpected embedding'))
    source = SourceBuildInput(filePath=str(path), sourceId='source:original',
        materialRevision=source_content_revision(path), name=path.name, mimeType='text/plain')
    arguments = dict(scope_id='scope:project', model='test', provider_instance=SimpleNamespace(receipts=[]),
                     artifact_ref='objects/representation.json', created_at='2026-10-19T00:00:00Z')
    artifact = pipeline.build_grounded_source_snapshot(source, **arguments)
    assert artifact == pipeline.build_grounded_source_snapshot(source, **arguments)
    assert len(artifact.assertions) == 1
    assert {e.canonical_name for e in artifact.entities} == {'Ada', 'Engine'}
    assert artifact.artifact_manifest[0].artifact_hash == stable_digest(
        artifact.document_representations[0].metadata['document'])
    for span in artifact.evidence_spans:
        assert text[span.locator.start_char:span.locator.end_char] == span.quote
    path.write_text('different bytes')
    with pytest.raises(pipeline.SemanticArtifactError, match='immutable bytes'):
        pipeline.build_grounded_source_snapshot(source, **arguments)


def test_grounded_source_consumes_verified_parsed_artifact_without_parsing(tmp_path, monkeypatch):
    path = tmp_path / 'original.txt'
    text = 'Ada builds Engine.'
    path.write_text(text)
    source = SourceBuildInput(filePath=str(path), sourceId='source:original',
        materialRevision=source_content_revision(path), name=path.name, mimeType='text/plain')
    parsed = pipeline.parse_source_artifact(pipeline.ParseSourceRequest.model_validate({
        'source': source.model_dump(mode='json', by_alias=True), 'outputDir': str(tmp_path / 'parsed'),
        'forceOcr': False, 'documentProcessing': {'mode': 'local'},
    }))
    _stub_canonical_extraction(monkeypatch, lambda *_: ({
        'entities': [{'id': 'Ada', 'name': 'Ada', 'type': 'CONCEPT', 'occurrence': 0}],
        'relations': []}, receipt('structured_extraction', 1)))
    monkeypatch.setattr(pipeline, '_parse_source', lambda *_args, **_kwargs: pytest.fail('unexpected parse'))
    artifact = pipeline.build_grounded_source_snapshot(source, scope_id='scope:project', model='test',
        provider_instance=SimpleNamespace(receipts=[]), artifact_ref='objects/representation.json',
        created_at='2026-10-19T00:00:00Z', parsed_source=pipeline.ParsedSourceRef.model_validate({
            key: parsed[key] for key in ('artifactPath', 'artifactDigest', 'sourceId')}))
    assert artifact.document_representations[0].metadata['document']['text'] == text


@pytest.mark.parametrize('order,sort', [('coordinates', True), ('content', False)])
def test_native_pdf_profile_uses_pdf_parser_not_docling(tmp_path, monkeypatch, order, sort):
    import json
    path = tmp_path / 'original.pdf'
    path.write_bytes(b'%PDF fixture')
    source = SourceBuildInput(filePath=str(path), sourceId='source:pdf',
        materialRevision=source_content_revision(path), name=path.name, mimeType='application/pdf')
    class Parser:
        def parse(self, actual, **options):
            assert actual == path and options == {
                'extract_tables': False, 'extract_images': False,
                'extract_links': True, 'sort': sort}
            return {'full_text': 'Native PDF text',
                    'pages': [{'page_number': 1, 'text': 'Native PDF text'}],
                    'metadata': {'page_count': 1}}
    monkeypatch.setattr('semantica.parse.pdf_parser.PDFParser', Parser)
    monkeypatch.setattr('semantica.parse.docling_parser.DoclingParser',
                        lambda **_kwargs: pytest.fail('unexpected Docling'))
    parsed = pipeline.parse_source_artifact(pipeline.ParseSourceRequest.model_validate({
        'source': source.model_dump(mode='json', by_alias=True), 'outputDir': str(tmp_path / 'parsed'),
        'forceOcr': False, 'documentProcessing': {'mode': 'native', 'pdfTextOrder': order},
    }))
    payload = json.loads(__import__('pathlib').Path(parsed['artifactPath']).read_bytes())
    assert payload['parser'] == 'semantica.PDFParser'
    assert payload['document']['text'] == 'Native PDF text'


def test_source_retry_restores_entities_and_receipts_before_retrying_relations(tmp_path, monkeypatch):
    from semantica.utils.exceptions import ProcessingError
    path = tmp_path / 'original.txt'
    path.write_text('Ada builds Engine.')
    source = SourceBuildInput(filePath=str(path), sourceId='source:original',
        materialRevision=source_content_revision(path), name=path.name, mimeType='text/plain')
    calls = []
    parses = []
    original_parse = source_artifact.parse_source
    def counted_parse(*args, **kwargs):
        parses.append(True)
        return original_parse(*args, **kwargs)
    monkeypatch.setattr(source_artifact, 'parse_source', counted_parse)

    class Provider:
        def __init__(self, fail=False):
            self.receipts, self.rejections, self.fail = [], [], fail

        def is_available(self):
            return True

        def generate_typed(self, prompt, schema, **kwargs):
            stage = 'entities' if schema.__name__ == 'GroundedEntitiesWire' else 'relations'
            calls.append(stage)
            self.receipts.append({'call_id': str(len(calls)), 'metadata': {}, 'cost_usd': 0.01})
            if stage == 'relations' and self.fail:
                raise ProcessingError('interrupted relations')
            return schema.model_validate({'entities': [{'text': 'Ada', 'label': 'PERSON',
                'occurrence': 0, 'confidence': 0.9, 'attributes': {}}]} if stage == 'entities'
                else {'relations': []})

    arguments = dict(scope_id='scope:project', model='test',
        artifact_ref='objects/representation.json', created_at='2026-10-19T00:00:00Z',
        checkpoint_dir=str(tmp_path / 'checkpoint'))
    with pytest.raises(ProcessingError, match='interrupted relations'):
        pipeline.build_grounded_source_snapshot(source, provider_instance=Provider(True), **arguments)
    monkeypatch.setattr(pipeline, '_text_windows', lambda *_: pytest.fail('must resume saved window plan'))
    arguments['model'] = 'replacement-model'
    resumed = Provider()
    result = pipeline.build_grounded_source_snapshot(source, provider_instance=resumed, **arguments)
    assert calls == ['entities', 'relations', 'relations']
    assert len(parses) == 1
    assert {item['call_id'] for item in resumed.receipts} == {'1', '3'}
    assert result.entities[0].canonical_name == 'Ada'
    third = Provider()
    arguments['model'] = 'replacement-model'
    assert pipeline.build_grounded_source_snapshot(source, provider_instance=third, **arguments) == result
    assert calls == ['entities', 'relations', 'relations']
    assert third.receipts == resumed.receipts
