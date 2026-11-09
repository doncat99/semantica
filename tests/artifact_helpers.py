"""Exercise the production project queue with one in-memory source."""
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager

from semantica.semantic_publication_builder import _extract_project_sources


@contextmanager
def organization_report_owner(monkeypatch):
    """Bind algorithm-only specs to the paid product boundary; recovery has HTTP subprocess coverage."""
    from semantica import semantic_publication_builder as pipeline
    request = SimpleNamespace(input_revision='fixture-input', organization_reports=SimpleNamespace(recipe_digest='sha256:' + 'a' * 64))
    def product(action, identity, *, report=None, receipts=None):
        return None if action == 'read' else (report, receipts)
    with monkeypatch.context() as patch:
        patch.setattr(pipeline, '_organization_report_product', product)
        token = pipeline._native_build.set((request, None, None))
        try:
            yield
        finally:
            pipeline._native_build.reset(token)


@contextmanager
def native_extraction_owner(root, *, request=None, text=None):
    """Exercise the production owner contexts with persistent native stores."""
    from semantica import semantic_publication_builder as pipeline
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    backend = SqliteCacheBackend(str(root / 'accepted.sqlite'))
    store = OxigraphStore(root / 'facts')
    token = pipeline._native_build.set((request, store, ExtractionCache(backend=backend, ttl=None)))
    binding = pipeline._native_source_binding.set(dict(project='fixture-project', source='source',
        material='material', representation='representation', recipe='recipe', specification='none', parser='parser'))
    ranges = pipeline._native_source_ranges.set(
        pipeline._native_grounding_ranges(dict(format='text', text=text), text) if text is not None else None)
    try:
        yield store
    finally:
        pipeline._native_source_ranges.reset(ranges)
        pipeline._native_source_binding.reset(binding)
        pipeline._native_build.reset(token)
        backend.close()


def native_docling_fixture(raw):
    """Complete compact test inputs using the installed native schema."""
    from copy import deepcopy
    from docling_core.types.doc import DoclingDocument
    value = DoclingDocument(name='fixture').export_to_dict()
    raw = deepcopy(raw)
    for item in raw.get('texts', []):
        item.setdefault('orig', item['text'])
    for item in [*raw.get('texts', []), *raw.get('tables', [])]:
        item.setdefault('parent', {'$ref': '#/body'})
        for prov in item.get('prov', []):
            prov.setdefault('bbox', {'l': 1, 't': 1, 'r': 10, 'b': 10})
            prov.setdefault('charspan', [0, len(item.get('text', ''))])
    for table in raw.get('tables', []):
        data = table['data']
        for cell in data['table_cells']:
            for axis in ('row', 'col'):
                cell.setdefault(f'end_{axis}_offset_idx', cell[f'start_{axis}_offset_idx'] + cell.get(f'{axis}_span', 1))
        for axis, key in [('row', 'num_rows'), ('col', 'num_cols')]:
            data[key] = max(c[f'end_{axis}_offset_idx'] for c in data['table_cells'])
    value.update({key: val for key, val in raw.items() if key != 'body'})
    value['body'].update(raw.get('body', {}))
    return DoclingDocument.model_validate(value).export_to_dict()


def docling_fixture_text(document):
    from semantica.semantic_source_artifact import _native_text
    return _native_text(document)


def native_parsed_fixture(source, force_ocr=False, parsed=None, profile=None):
    """Serialize compact algorithm fixtures, then exercise actual native admission."""
    from copy import deepcopy
    from semantica import semantic_source_artifact as owner
    from semantica.semantic_artifact_schema import DocumentProcessingProfile, ParseSourceRequest, ParsedSourceRef
    from semantica.source import source_content_revision, source_processing_revision
    if isinstance(parsed, owner.NativeParsedSource):
        return parsed
    temporary = TemporaryDirectory(prefix='native-parsed-fixture-')
    path = Path(getattr(source, 'file_path', Path(temporary.name) / 'source.txt'))
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(parsed[0], encoding='utf-8')
    source.material_revision = source_content_revision(path)
    source.name = getattr(source, 'name', path.name)
    profile = DocumentProcessingProfile.model_validate(profile or {'mode': 'local'})
    if not hasattr(source, 'file_path'):
        source = SimpleNamespace(**vars(source), file_path=str(path))
    request = ParseSourceRequest(source=dict(sourceId=source.source_id, filePath=str(path.resolve()),
        materialRevision=source.material_revision, name=source.name, mimeType=source.mime_type),
        outputDir=temporary.name, forceOcr=force_ocr, documentProcessing=profile)
    if parsed is None:
        result = owner.parse_source_artifact(request)
    else:
        text, document, origin, _, parser, version = parsed
        document = deepcopy(document)
        document.setdefault('format', 'text')
        if document['format'] == 'docling' and 'document' not in document:
            from docling_core.types.doc import DoclingDocument
            native = DoclingDocument(name=source.name)
            native.add_text(label='text', text=text)
            document.pop('text', None)
            document['document'] = native.export_to_dict()
        if document['format'] == 'docling':
            for key in ('text', 'plain_text', 'doctags'):
                document.pop(key, None)
        elif document['format'] == 'text':
            document['text'] = text
        document.update(content_hash=source.material_revision, mime_type=source.mime_type)
        document['representation_revision'] = owner._representation_revision(
            source, force_ocr, source.material_revision, parser, version, origin, document)
        processing = profile.model_dump(mode='json', by_alias=True)
        result = owner._write_parsed_source_artifact(request, dict(protocol='semantica.parsed-source.v3',
            materialRevision=source.material_revision, mimeType=source.mime_type, forceOcr=force_ocr,
            documentProcessing=processing, processingRevision=source_processing_revision(path,
                name=source.name, mime_type=source.mime_type, force_ocr=force_ocr, document_processing=processing),
            parser=parser, parserVersion=version, origin=origin, document=document))
    ref = ParsedSourceRef.model_validate({key: result[key] for key in
        ('sourceId', 'artifactPath', 'artifactDigest', 'representationRevision', 'readerIndexPath', 'readerIndexDigest')})
    admitted = owner._load_parsed_source(source, ref, force_ocr, profile.model_dump(mode='json', by_alias=True))
    admitted._fixture_directory = temporary
    admitted.text._fixture_directory = temporary
    return admitted


def build_source_fixture(source, force_ocr, model_result=None, parsed=None):
    from copy import deepcopy
    from semantica import semantic_publication_builder as pipeline
    admitted = native_parsed_fixture(source, force_ocr, parsed)
    if model_result is not None:
        model_result = deepcopy(model_result)
        text = None
        for kind in ('entities', 'relations'):
            for item in model_result.get(kind, []):
                if '_start' not in item or '_end' not in item:
                    if text is None:
                        text = admitted.text[:]
                    quote = item['name'] if kind == 'entities' else item['evidence']
                    occurrence = item.get('occurrence' if kind == 'entities' else 'evidence_occurrence', 0)
                    item['_start'], item['_end'], _ = pipeline._exact_occurrence(text, quote, occurrence)
    result = pipeline._build_source(source, force_ocr, model_result, admitted)
    # Test-only public expression oracle; production retains one source fact.
    from semantica.semantic_artifact_schema import KnowledgeRelation
    result['assertions'] = result['facts']
    result['relations'] = [KnowledgeRelation(id='relation:'+item.id.split(':')[1],
        source_entity_id=item.subject_id,target_entity_id=item.object_entity_id,
        type=item.predicate,qualifiers=item.qualifiers,evidence_ids=item.evidence_ids,
        support_ids=item.support_ids,status=item.status) for item in result['facts']]
    return result


def extract_source(text, model, embedding, *, extraction_spec=None, progress=None,
                   parallelism=1, document=None):
    if isinstance(model, SimpleNamespace):
        model = SimpleNamespace(**{"context_window_tokens": 500000, "max_output_tokens": 32768, "binding_id": None, **vars(model)})
    from semantica.semantic_artifact_schema import RecipeRef, DocumentProcessingProfile
    from semantica.semantic_publication_builder import stable_digest
    with TemporaryDirectory(prefix='native-extraction-fixture-') as root:
        source_path = Path(root) / 'source.txt'
        source_path.write_text(text)
        source = SimpleNamespace(source_id="source", material_revision=stable_digest(text),
            file_path=str(source_path), mime_type='text/plain', name=source_path.name)
        parsed = native_parsed_fixture(source, parsed=(text, document or {}, 'native', '', 'text', '1'))
        request = SimpleNamespace(parallelism=parallelism, project_id='fixture-project',
            recipe=RecipeRef(id='model', version='1', extractionSpec=extraction_spec),
            parsed_sources=[SimpleNamespace(source_id='source', representation_revision=parsed.document['representation_revision'])],
            document_processing=DocumentProcessingProfile(mode='local'),
            relays={"model": model, "embedding": embedding})
        return _extract_project_sources([(source, False, parsed)], request, progress)[0]


def stub_native_provider(monkeypatch, respond):
    """Stub only generation; retain native schemas, grounding and extraction cache."""
    from semantica import semantic_publication_builder as pipeline
    from semantica.semantic_artifact_schema import ModelReceipt

    class Provider:
        def __init__(self):
            self.receipts, self.rejections = [], []

        def is_available(self):
            return True

        def generate_typed(self, prompt, schema, **kwargs):
            stage = kwargs['extraction_stage']
            result = respond(stage, prompt)
            digest = pipeline.stable_digest([stage, prompt, result])
            self.receipts.append(ModelReceipt(id='receipt:' + digest, operation='structured_extraction',
                provider='test', model='test', input_digest=pipeline.stable_digest(prompt),
                output_digest=pipeline.stable_digest(result), metadata={'extraction_stage': stage}))
            return schema.model_validate(result)

    monkeypatch.setattr(pipeline, '_project_model_provider', lambda _: Provider())
