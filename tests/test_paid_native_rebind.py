"""Offline adoption preserves paid data without a normal-read compatibility path."""
import importlib.util
import ast
import hashlib
import copy
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/rebind_paid_native_results.py'
spec = importlib.util.spec_from_file_location('paid_rebind', SCRIPT)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


def test_span_certificate_accepts_only_exact_reviewed_function_and_source(tmp_path, monkeypatch):
    import semantica.semantic_publication_builder as builder
    old, new = tmp_path/'old', tmp_path/'new'
    for root in (old,new):
        (root/'semantic_extract').mkdir(parents=True)
    before='def extract_entities_llm(text):\n return text.strip()\n'
    after='def extract_entities_llm(text):\n return text\n'
    digest=lambda data:hashlib.sha256(ast.dump(ast.parse(data).body[0],include_attributes=False).encode()).hexdigest()
    monkeypatch.setattr(maintenance,'SPAN_REPAIR_AST',{'before':digest(before),'after':digest(after)})
    monkeypatch.setattr(builder,'_project_processing_digest',lambda root:'sha256:a0eb826dc1bd23a00f40a7ef6203a33968b2bdec9465480eb920bdafb291a4db' if root==old else 'new-reviewed')
    (old/'semantic_extract/methods.py').write_text(before)
    target=new/'semantic_extract/methods.py';target.write_text(after)
    assert maintenance.certify_span_repair(old,new)['newProcessing']=='new-reviewed'
    target.write_text(after+'\ndef another_producer():\n return 2\n')
    with pytest.raises(ValueError,match='another producer'):
        maintenance.certify_span_repair(old,new)
    target.write_text(after.replace('return text','return text.upper()'))
    with pytest.raises(ValueError,match='exact reviewed AST'):
        maintenance.certify_span_repair(old,new)
    target.write_text(after);(new/'other.py').write_text('SIDE_EFFECT = True\n')
    with pytest.raises(ValueError,match='inventory differs'):
        maintenance.certify_span_repair(old,new)


def test_embedding_target_permits_only_generation_and_derived_transport_changes():
    original = dict(projectId='project', inputRevision='input', recipe={'id': 'model'},
        sources=[{'material': 'fixed'}], parsedSources=[{'digest': 'fixed'}],
        documentProcessing={'mode': 'local'}, release={'digest': 'fixed'},
        nativeStoreDir='/native', nativeCacheDir='/cache', outputDir='/old-run',
        organizationReports={'recipeDigest': 'old', 'baseUrl': 'http://old'},
        relays={'model': {'bindingId': 'opencc', 'modelId': 'old-model',
            'capability': 'generate', 'authorizationEnv': 'KEY', 'receipts': 'required',
            'baseUrl': 'http://old', 'contextWindowTokens': 500000, 'maxOutputTokens': 32768},
            'embedding': {'bindingId': 'openrouter', 'modelId': 'same-embedding', 'baseUrl': 'http://old'}})
    changed = copy.deepcopy(original)
    changed['relays']['model'].update(bindingId='default', modelId='new-model', contextWindowTokens=128000)
    changed['organizationReports']['recipeDigest'] = 'new'
    changed['outputDir'] = '/new-run'
    changed['relays']['embedding']['baseUrl'] = 'http://new'
    wrap = lambda data: SimpleNamespace(model_dump=lambda **_: data)
    maintenance.validate_embedding_target(wrap(original), wrap(changed))
    for field, value in [('sources', []), ('recipe', {'id': 'changed'}), ('release', {'digest': 'changed'})]:
        invalid = copy.deepcopy(changed)
        invalid[field] = value
        with pytest.raises(ValueError, match='embedding inputs'):
            maintenance.validate_embedding_target(wrap(original), wrap(invalid))
    certified = copy.deepcopy(changed)
    certified['release'] = {'digest': 'new-reviewed'}
    certificate = {'sourceRelease': original['release'], 'targetRelease': certified['release']}
    maintenance.validate_embedding_target(wrap(original), wrap(certified), certificate)
    with pytest.raises(ValueError, match='certified artifact releases'):
        maintenance.validate_embedding_target(wrap(original), wrap(certified), {'sourceRelease': original['release'], 'targetRelease': {}})
    invalid = copy.deepcopy(changed)
    invalid['relays']['embedding']['modelId'] = 'changed-embedding'
    with pytest.raises(ValueError, match='embedding inputs'):
        maintenance.validate_embedding_target(wrap(original), wrap(invalid))


def test_target_release_binds_descriptor_runtime_inventory_and_bytes(tmp_path):
    runtime = tmp_path/'python/lib/python3.12/site-packages/semantica'
    runtime.mkdir(parents=True)
    module = runtime/'semantic_publication_builder.py'
    module.write_text('FIXED = True\n')
    source_release = {
        'artifactDigest': 'sha256:53739bc58a99e8b153429636d1eeff9603847b6755479d60107a38533bb7064f',
        'schemaDigest': 'sha256:d8f3bd61820b2df90c476e2cdef2ba74d3aa07f31064575d79480a1c82db286f',
        'mediaTypes': {'document-representation': 'application/vnd.semantica.document-representation+json'},
    }
    manifest = {'protocol': 'bundle', 'schemaDigest': source_release['schemaDigest'],
        'pythonPath': 'python/bin/python3', 'worker': {'path': 'python/bin/python3', 'args': ['worker']},
        'queryWorker': {'path': 'python/bin/python3', 'args': ['query']},
        'mediaTypes': source_release['mediaTypes'], 'files': [{'path': module.relative_to(tmp_path).as_posix(),
        'size': module.stat().st_size, 'sha256': 'sha256:' + hashlib.sha256(module.read_bytes()).hexdigest()}]}
    descriptor = ['bundle', manifest['schemaDigest'], None, 'python/bin/python3',
        ['python/bin/python3', ['worker']], ['python/bin/python3', ['query']],
        sorted([list(item) for item in manifest['mediaTypes'].items()]),
        [[item['path'], item['size'], item['sha256']] for item in manifest['files']]]
    manifest['artifactDigest'] = 'sha256:' + hashlib.sha256(json.dumps(descriptor, separators=(',', ':')).encode()).hexdigest()
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    release = {key: manifest[key] for key in ('artifactDigest', 'schemaDigest', 'mediaTypes')}
    wrap = lambda item: SimpleNamespace(model_dump=lambda **_: {'release': item})
    result = maintenance.certify_target_release(wrap(source_release), wrap(release), runtime)
    assert result == {'sourceRelease': source_release, 'targetRelease': release}
    module.write_text('FIXED = False\n')
    with pytest.raises(ValueError, match='runtime bytes'):
        maintenance.certify_target_release(wrap(source_release), wrap(release), runtime)
    module.write_text('FIXED = True\n')
    (runtime/'extra.py').write_text('EXTRA = True\n')
    with pytest.raises(ValueError, match='runtime inventory'):
        maintenance.certify_target_release(wrap(source_release), wrap(release), runtime)
    with pytest.raises(ValueError, match='reviewed immutable source artifact'):
        maintenance.certify_target_release(wrap(release), wrap(release), runtime)
    with pytest.raises(ValueError, match='installed artifact descriptor'):
        maintenance.certify_target_release(wrap(source_release), wrap({**release, 'artifactDigest': 'bad'}), runtime)


def test_certificate_rejects_changed_paid_producer_and_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, 'REVIEWED_PRODUCER_AST', {})
    roots = [tmp_path/'old', tmp_path/'new']
    for root in roots:
        root.mkdir()
        (root/'semantic_publication_builder.py').write_text('def paid_producer():\n return 1\n')
    (roots[1]/'semantic_publication_builder.py').write_text(
        'def paid_producer():\n return 1\ndef _read_source_projection_text():\n return 2\n')
    proof = maintenance.certify(*roots)
    assert proof['oldProcessing'] != proof['newProcessing']
    (roots[1]/'semantic_publication_builder.py').write_text('def paid_producer():\n return 2\n')
    with pytest.raises(ValueError, match='unapproved AST'):
        maintenance.certify(*roots)
    (roots[1]/'paid.py').write_text('CHANGED = True\n')
    with pytest.raises(ValueError, match='inventory'):
        maintenance.certify(*roots)


def test_certificate_accepts_exact_module_rename_and_rejects_retained_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, 'REVIEWED_PRODUCER_AST', {})
    old, new = tmp_path/'old', tmp_path/'new'
    old.mkdir(); new.mkdir()
    retired = 'semantic_' + 'artifact_builder.py'
    (old/retired).write_text('def paid_producer():\n return 1\n')
    (new/'semantic_publication_builder.py').write_text('def paid_producer():\n return 1\n')
    (old/'worker.py').write_text('from .semantic_' + 'artifact_builder import paid_producer\n')
    (new/'worker.py').write_text('from .semantic_publication_builder import paid_producer\n')
    proof = maintenance.certify(old, new)
    assert proof['oldProcessing'] != proof['newProcessing']
    (new/'worker.py').write_text('from .semantic_publication_builder import paid_producer\nEXTRA = 1\n')
    with pytest.raises(ValueError, match='Uncertified runtime change'):
        maintenance.certify(old, new)
    (new/retired).write_text('raise RuntimeError("retired")\n')
    with pytest.raises(ValueError, match='Superseded builder module retained'):
        maintenance.certify(old, new)


def test_projection_normalization_preserves_producer_branch_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, 'REVIEWED_PRODUCER_AST', {})
    roots = [tmp_path/'old', tmp_path/'new']
    for root in roots:
        root.mkdir()
    old = 'def _build_source(parsed):\n text = parsed.text\n paid_producer()\n return text[0:4]\n'
    new = ('def _build_source(parsed):\n text = parsed.text\n'
        ' read = lambda start, end: _read_source_projection_text(parsed.reader, start, end)\n'
        ' paid_producer()\n return read(0,4)\n')
    (roots[0]/'semantic_publication_builder.py').write_text(old)
    path = roots[1]/'semantic_publication_builder.py'
    path.write_text(new)
    maintenance.certify(*roots)
    path.write_text(new.replace('paid_producer()', 'changed_paid_producer()'))
    with pytest.raises(ValueError, match='unapproved AST'):
        maintenance.certify(*roots)


def test_reviewed_producer_ast_is_exact_and_requires_both_inventories(tmp_path, monkeypatch):
    roots = [tmp_path/'old', tmp_path/'new']
    before = 'def _source_windows(parsed):\n return parsed.windows\n'
    after = 'def _source_windows(parsed):\n return bounded(parsed)\n'
    digest = lambda text: hashlib.sha256(ast.dump(ast.parse(text).body[0], include_attributes=False).encode()).hexdigest()
    monkeypatch.setattr(maintenance, 'REVIEWED_PRODUCER_AST', {
        '_source_windows': {'before': digest(before), 'after': digest(after)}})
    for root, body in zip(roots, [before, after]):
        root.mkdir()
        (root/'semantic_publication_builder.py').write_text(body)
    maintenance.certify(*roots)
    (roots[1]/'semantic_publication_builder.py').write_text(after.replace('bounded', 'unreviewed'))
    with pytest.raises(ValueError, match='differs from reviewed AST'):
        maintenance.certify(*roots)
    (roots[1]/'semantic_publication_builder.py').write_text('OTHER = 1\n')
    with pytest.raises(ValueError, match='AST inventory'):
        maintenance.certify(*roots)


def test_dry_run_then_native_adoption_reuses_extraction_and_vectors(tmp_path, monkeypatch):
    from semantica.semantic_artifact_schema import stable_digest
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.semantic_extract.grounded_window import extract_grounded_window
    from semantica.semantic_extract.providers import BaseProvider
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    fixture = runpy.run_path(str(Path(__file__).with_name("test_native_extraction_handoff.py")))
    run, TEXT = fixture["run_child"], fixture["TEXT"]

    relay = SimpleNamespace(binding_id='binding-1', model_id='model-1', context_window_tokens=8192, max_output_tokens=1024)
    recipe = SimpleNamespace(lineage_payload=lambda: {'id': 'model'}, extraction_spec=None, force_ocr_source_ids=[])
    source = SimpleNamespace(source_id='source-1', material_revision='material-1', file_path='original.pdf', name='original.pdf', mime_type='application/pdf')
    request = SimpleNamespace(project_id='project-1', sources=[source], recipe=recipe,
        parsed_sources=[SimpleNamespace(source_id='source-1', representation_revision='representation-1')],
        relays={'model': relay, 'embedding': relay}, native_store_dir=str(tmp_path/'facts'),
        native_cache_dir=str(tmp_path), document_processing=SimpleNamespace(model_dump=lambda **_: {}),
        model_dump=lambda **_: {'project': 'project-1', 'recipe': 'fixed',
            'relays': {'model': {'bindingId': 'binding-1', 'modelId': 'model-1'},
                       'embedding': {'bindingId': 'binding-1', 'modelId': 'model-1'}}})
    certificate = {'oldProcessing': 'old', 'newProcessing': 'new'}
    old_recipe = maintenance.source_recipe(request, 'old')
    new_recipe = maintenance.source_recipe(request, 'new')
    child = run(tmp_path, recipe=old_recipe)
    assert child.returncode == 0, child.stderr
    native_ranges = [dict(nativeRef='#/document/text', start=0, end=len(TEXT), windowStart=0, windowEnd=len(TEXT))]
    parsed = SimpleNamespace(text=TEXT, windows=[(0, len(TEXT), TEXT)], native_ranges=native_ranges)
    monkeypatch.setattr('semantica.semantic_source_artifact._load_parsed_source', lambda *_: parsed)
    monkeypatch.setattr('semantica.semantic_publication_builder._source_windows', lambda parsed: parsed.windows)
    monkeypatch.setattr('semantica.source.source_processing_revision', lambda *_, **__: 'parser-1')
    space = {'binding': stable_digest({'binding': relay.binding_id, 'model': relay.model_id, 'recipe': old_recipe}), 'model': relay.model_id, 'recipe': old_recipe}
    binding = dict(project='project-1', source='source-1', material='material-1', representation='representation-1',
        recipe=old_recipe, parser='parser-1', model='model-1', space=space['binding'], ranges=[[0, len(TEXT)]], input_digest=stable_digest([TEXT]))
    backend = SqliteCacheBackend(str(tmp_path/'accepted.sqlite'))
    cache = ExtractionCache(backend=backend)
    receipt = dict(id='paid-embedding', operation='embedding', provider='fixture', model='model-1', input_digest='input', output_digest='output')
    key = SQLiteVecStore.embedding_operation_id(binding)
    pending = {'vectors': [[1., 0., 0.]], 'receipt': receipt}
    digest = cache.accept('embedding', key, pending)
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/('embedding-'+space['binding'].removeprefix('sha256:')+'.sqlite')), space, 3)
    owner.adopt_embedding(binding, pending['vectors'], receipt, accepted_digest=digest)
    cache.release_accepted('embedding', key, digest)
    owner.close()
    backend.close()
    before = (tmp_path/'calls.jsonl').read_bytes()
    dry = maintenance.adopt(request, certificate)
    assert (dry['extractions'], dry['embeddings']) == (2, 1)
    assert len(list(tmp_path.glob('embedding-*.sqlite'))) == 1
    monkeypatch.setattr('semantica.semantic_publication_builder._source_windows', lambda parsed: [])
    with pytest.raises(ValueError, match='preserve every existing paid vector'):
        maintenance.adopt(request, certificate)
    monkeypatch.setattr('semantica.semantic_publication_builder._source_windows', lambda parsed: parsed.windows)
    for _ in range(2):
        result = maintenance.adopt(request, certificate, apply=True)
        assert (result['extractions'], result['embeddings']) == (2, 1)
    target_space = {**space, 'recipe': new_recipe,
        'binding': stable_digest({'binding': relay.binding_id, 'model': relay.model_id, 'recipe': new_recipe})}
    target_binding = {**binding, 'recipe': new_recipe, 'space': target_space['binding']}
    target_owner = SQLiteVecStore.open_embedding_space(
        str(tmp_path/('embedding-'+target_space['binding'].removeprefix('sha256:')+'.sqlite')), target_space)
    adopted = target_owner.read_embedding(target_binding)
    assert adopted['vectors'] == pending['vectors']
    assert adopted['receipt'] == receipt
    target_owner.close()
    store = OxigraphStore(tmp_path/'facts')
    backend = SqliteCacheBackend(str(tmp_path/'accepted.sqlite'))
    cache = ExtractionCache(backend=backend)
    new_binding = dict(project='project-1', source='source-1', material='material-1', representation='representation-1',
        recipe=new_recipe, model='model-1', specification='specification-1', parser='parser-1', grounding='grounding-1', window_start=0, window_end=len(TEXT))
    class NoCalls(BaseProvider):
        def __init__(self):
            super().__init__(model='model-1')
            self.receipts = []
        def generate(self, *_, **__):
            raise AssertionError('Valid paid extraction was recomputed')
    entities, relations, _ = extract_grounded_window(TEXT, model='model-1', provider_instance=NoCalls(),
        native_store=store, accepted_cache=cache, extraction_binding=new_binding, native_ranges=native_ranges)
    assert [e.text for e in entities] == ['Acme', 'Engine'] and len(relations) == 1
    assert (tmp_path/'calls.jsonl').read_bytes() == before
    store.close()
    backend.close()
    generation = SimpleNamespace(binding_id='default', model_id='other-generation',
        context_window_tokens=8192, max_output_tokens=1024)
    target = SimpleNamespace(**vars(request))
    target.relays = {'model': generation, 'embedding': relay}
    target.model_dump = lambda **_: {**request.model_dump(), 'relays': {
        'model': {'bindingId': 'default', 'modelId': 'other-generation'},
        'embedding': {'bindingId': 'binding-1', 'modelId': 'model-1'}}}
    vector_only = maintenance.adopt(request, certificate, embedding_target_request=target)
    assert (vector_only['extractions'], vector_only['embeddings'], vector_only['embeddingVectors']) == (0, 1, 1)
    for _ in range(2):
        maintenance.adopt(request, certificate, embedding_target_request=target, apply=True)
    default_recipe = maintenance.source_recipe(target, 'new')
    default_space = {**space, 'recipe': default_recipe,
        'binding': stable_digest({'binding': relay.binding_id, 'model': relay.model_id, 'recipe': default_recipe})}
    vector_owner = SQLiteVecStore.open_embedding_space(
        str(tmp_path/('embedding-'+default_space['binding'].removeprefix('sha256:')+'.sqlite')), default_space)
    default_binding = {**binding, 'recipe': default_recipe, 'space': default_space['binding']}
    adopted = vector_owner.read_embedding(default_binding)
    assert adopted['vectors'] == pending['vectors'] and adopted['receipt'] == receipt
    vector_owner.close()
    store = OxigraphStore(tmp_path/'facts')
    assert list(maintenance.source_bindings(store, 'project-1', 'source-1', default_recipe)) == []
    store.close()
    assert (tmp_path/'calls.jsonl').read_bytes() == before


def test_context_certificate_pins_exact_methods_source_and_all_other_producers(tmp_path, monkeypatch):
    import semantica.semantic_publication_builder as builder
    monkeypatch.setattr(maintenance, 'CONTEXT_REPAIR_NEW_FILES', {})
    old,new=tmp_path/'old',tmp_path/'new';old.mkdir();new.mkdir()
    before='class Locations:\n def addresses(self):\n  return [1]\n'
    after='class Locations:\n def addresses(self):\n  yield 1\n def units(self):\n  yield [1]\n'
    def methods(data):
        return {node.name:hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest() for node in ast.parse(data).body[0].body}
    a,b=methods(before),methods(after)
    monkeypatch.setattr(maintenance,'CONTEXT_REPAIR_AST',{'reader.py':{'Locations.addresses':dict(before=a['addresses'],after=b['addresses']),'Locations.units':dict(before=None,after=b['units'])}})
    monkeypatch.setattr(builder,'_project_processing_digest',lambda root:maintenance.CONTEXT_SOURCE_PROCESSING if root==old else 'new-reviewed')
    (old/'reader.py').write_text(before);target=new/'reader.py';target.write_text(after)
    assert maintenance.certify_context_repair(old,new)['repair']=='exact-native-context-unit-stream'
    target.write_text(after+'\nPROMPT = "changed"\n')
    with pytest.raises(ValueError,match='another producer'):
        maintenance.certify_context_repair(old,new)
    target.write_text(after.replace('yield [1]','yield [2]'))
    with pytest.raises(ValueError,match='exact reviewed AST'):
        maintenance.certify_context_repair(old,new)
    target.write_text(after);(new/'unreviewed.py').write_text('NEW = True\n')
    with pytest.raises(ValueError,match='runtime inventory'):
        maintenance.certify_context_repair(old,new)
    (new/'unreviewed.py').unlink()
    extra=new/'native_query.py';extra.write_text('def context():\n yield 1\n')
    monkeypatch.setattr(maintenance,'CONTEXT_REPAIR_NEW_FILES',{'native_query.py':hashlib.sha256(extra.read_bytes()).hexdigest()})
    assert maintenance.certify_context_repair(old,new)['changedFiles']['native_query.py']['before'] is None
    extra.write_text('def context():\n yield 2\n')
    with pytest.raises(ValueError,match='exact reviewed bytes'):
        maintenance.certify_context_repair(old,new)
    extra.unlink();monkeypatch.setattr(maintenance,'CONTEXT_REPAIR_NEW_FILES',{})
    monkeypatch.setattr(builder,'_project_processing_digest',lambda root:'other-source')
    with pytest.raises(ValueError,match='fixed c8cd source'):
        maintenance.certify_context_repair(old,new)


def test_context_paid_inventory_cannot_be_replaced_or_truncated(tmp_path):
    path=tmp_path/'untrusted.jsonl';path.write_text('{}\n')
    with pytest.raises(ValueError,match='Original paid context inventory changed'):
        maintenance.verify_context_paid_inputs(None,path)


def test_cache_owner_certificate_rejects_codec_key_producer_or_inventory_changes(tmp_path, monkeypatch):
    import semantica.semantic_publication_builder as builder
    old, new = tmp_path/'old', tmp_path/'new'
    for root in (old,new):
        (root/'semantic_extract').mkdir(parents=True)
        (root/'producer.py').write_text('MODEL = "same"\n')
    before, after = b'old-reviewed-cache', b'new-reviewed-cache'
    (old/'semantic_extract/cache.py').write_bytes(before)
    target = new/'semantic_extract/cache.py';target.write_bytes(after)
    monkeypatch.setattr(maintenance,'CACHE_REPAIR_BYTES',dict(before=hashlib.sha256(before).hexdigest(),after=hashlib.sha256(after).hexdigest()))
    monkeypatch.setattr(builder,'_project_processing_digest',lambda root: maintenance.CACHE_SOURCE_PROCESSING if root==old else 'new')
    assert maintenance.certify_cache_owner_repair(old,new)['repair']=='exact-cache-wal-read-owner'
    target.write_bytes(after+b' changed codec/key')
    with pytest.raises(ValueError,match='exact reviewed bytes'):
        maintenance.certify_cache_owner_repair(old,new)
    target.write_bytes(after);(new/'producer.py').write_text('MODEL = "changed"\n')
    with pytest.raises(ValueError,match='another producer'):
        maintenance.certify_cache_owner_repair(old,new)
    (new/'producer.py').write_text('MODEL = "same"\n');(new/'extra.py').write_text('EXTRA = True\n')
    with pytest.raises(ValueError,match='runtime inventory'):
        maintenance.certify_cache_owner_repair(old,new)
    (new/'extra.py').unlink()
    monkeypatch.setattr(builder,'_project_processing_digest',lambda root:'not-18e')
    with pytest.raises(ValueError,match='fixed 18e'):
        maintenance.certify_cache_owner_repair(old,new)
