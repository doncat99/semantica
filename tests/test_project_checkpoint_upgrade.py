import pytest

from semantica.project_checkpoint import _bytes, _digest
from semantica.project_checkpoint_upgrade import recover_extractions, select_latest
from semantica.semantic_extract.cache import ExtractionCache


@pytest.mark.parametrize('name', ['checkpoint', 'imports', 'evidence'])
def test_checkpoint_rejects_symlinked_managed_directories(tmp_path, name):
    from semantica.project_checkpoint import SnapshotCheckpoint, SnapshotCheckpointError
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'keep'
    sentinel.write_text('untouched')
    work = tmp_path / 'work'
    work.mkdir()
    (work / name).symlink_to(outside, target_is_directory=True)
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    with pytest.raises(SnapshotCheckpointError, match='regular directory'):
        owner._initialize(work, [], {'projectId': 'p', 'sources': []})
    assert sentinel.read_text() == 'untouched'


def test_successful_switch_removes_superseded_dataset_and_restarts(tmp_path):
    from semantica.project_checkpoint import SnapshotCheckpoint
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    inputs = {'protocol': 'semantica.project-checkpoint.v1', 'projectId': 'p', 'sources': [], 'provenance': {'recipe': {}}}
    owner._initialize(tmp_path, [], inputs)
    owner.write('completed', 'paid', {'value': 'saved'})
    # A provenance change installs a new canonical directory, preserving work.
    owner._initialize(tmp_path, [], {**inputs, 'provenance': {'recipe': {'description': 'updated'}}})
    assert owner.read('completed', 'paid') == {'value': 'saved'}
    assert not list((tmp_path / 'evidence').glob('checkpoint-next-*'))
    owner._initialize(tmp_path, [], inputs)
    assert owner.read('completed', 'paid') == {'value': 'saved'}
    assert not (tmp_path / '.checkpoint-migration.json').exists()


def test_import_cleanup_resumes_after_interruption(tmp_path, monkeypatch):
    import shutil
    from semantica.project_checkpoint import SnapshotCheckpoint
    inputs = {'projectId': 'p', 'sources': []}
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    owner._initialize(tmp_path / 'original', [], inputs)
    owner.write('completed', 'paid', {'saved': True})
    carrier = tmp_path / 'target' / 'imports' / 'one'
    carrier.parent.mkdir(parents=True)
    shutil.copytree(owner.root, carrier)
    delete = shutil.rmtree
    def interrupted(path, *args, **kwargs):
        if path == carrier:
            (carrier / 'manifest.json').unlink()
            raise OSError('interrupted cleanup')
        return delete(path, *args, **kwargs)
    monkeypatch.setattr(shutil, 'rmtree', interrupted)
    with pytest.raises(OSError, match='interrupted cleanup'):
        owner._initialize(tmp_path / 'target', [], inputs)
    monkeypatch.setattr(shutil, 'rmtree', delete)
    owner._initialize(tmp_path / 'target', [], inputs)
    assert owner.read('completed', 'paid') == {'saved': True}
    assert not carrier.exists()
    assert not (tmp_path / 'target' / '.checkpoint-migration.json').exists()


@pytest.mark.parametrize('identity', [None, 'business-content-v1'])
@pytest.mark.parametrize('rejected', [False, True, 'prior'])
def test_offline_dataset_conversion_restarts_without_rebuying_documents(tmp_path, monkeypatch, identity, rejected):
    import json
    from copy import deepcopy
    from semantica.project_checkpoint import SnapshotCheckpoint
    from semantica.project_checkpoint_upgrade import canonicalize_checkpoint, _locator
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    from tests.test_semantic_artifact import _request

    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('migration made a network call'))
    source = tmp_path / 'source.txt'
    source.write_text('Already parsed content')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'work')['params'])
    checkpoint = SnapshotCheckpoint(request)
    manifest = json.loads((checkpoint.root / 'manifest.json').read_bytes())
    # Historical inputs mixed execution provenance and business requirements.
    inputs = deepcopy(manifest['provenance'])
    inputs['recipe'] = inputs.pop('provenance')['recipe']
    manifest.update(inputs=inputs, fence=_digest(_bytes(inputs)))
    if identity is None:
        manifest.pop('entryIdentity')
    key = {'sourceId': request.sources[0].source_id, 'contentHash': request.sources[0].material_revision,
           'forceOcr': False, 'documentProcessing': inputs['documentProcessing']}
    payload = ['Already parsed content', {'text': 'Already parsed content',
               'content_hash': request.sources[0].material_revision, 'mime_type': 'text/plain'},
               'original', request.sources[0].material_revision, 'text', '1']
    entries = {_locator('document', key): {'fence': manifest['fence'],
               'digest': _digest(_bytes(payload)), 'payload': payload}}
    if rejected:
        marker = {'kind': 'document', 'keyDigest': _digest(_bytes(key)),
                  'payloadDigest': _digest(_bytes('previously rejected')) if rejected == 'prior' else _digest(_bytes(payload))}
        entries[f"rejected-document-{marker['keyDigest'][7:]}-{marker['payloadDigest'][7:]}.json"] = marker
    original = deepcopy((manifest, entries))
    converted, converted_entries = canonicalize_checkpoint(manifest, entries)
    assert (manifest, entries) == original
    assert converted['entryIdentity'] == 'business-content-v1'
    assert converted['createdAt'] == manifest['createdAt']
    destination = tmp_path / 'canonical'
    destination.mkdir()
    (destination / 'manifest.json').write_bytes(_bytes(converted))
    for name, entry in converted_entries.items():
        (destination / name).write_bytes(_bytes(entry))
    checkpoint = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    checkpoint._initialize(tmp_path / 'restored', [str(destination)], manifest['provenance'])
    canonical_key = {k: v for k, v in key.items() if k != 'documentProcessing'}
    assert checkpoint.read('document', canonical_key) == (None if rejected is True else payload)
    assert converted_entries[_locator('document', canonical_key)]['digest'] == entries[_locator('document', key)]['digest']


@pytest.mark.parametrize('defect', ['invalid-payload', 'foreign-source'])
def test_document_only_migration_rejects_unusable_saved_data_without_changes(tmp_path, defect):
    from semantica.semantic_artifact_errors import SemanticArtifactError
    from semantica.project_checkpoint_upgrade import upgrade_checkpoint, _locator
    inputs = {'protocol': 'semantica.project-checkpoint.v1', 'projectId': 'p',
              'sources': [{'sourceId': 's', 'materialRevision': 'r', 'mimeType': 'text/plain'}]}
    root = tmp_path / 'checkpoint'
    root.mkdir()
    manifest = {'inputs': inputs, 'fence': _digest(_bytes(inputs)), 'createdAt': '2026-10-27T00:00:00Z'}
    key = {'sourceId': 'other' if defect == 'foreign-source' else 's', 'contentHash': 'r', 'forceOcr': False}
    payload = ['saved', {'text': 'saved', 'content_hash': 'r', 'mime_type': 'text/plain'}, 'original', 'r', 'text', '1']
    if defect == 'invalid-payload':
        payload = {'text': 'cannot be consumed by native parser'}
    files = {'manifest.json': manifest, _locator('document', key): {
        'fence': manifest['fence'], 'key': key, 'payload': payload, 'digest': _digest(_bytes(payload))}}
    for name, value in files.items():
        (root / name).write_bytes(_bytes(value))
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises((ValueError, SemanticArtifactError), match='saved parsed source|original source inputs'):
        upgrade_checkpoint(root)
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert not (tmp_path / '.checkpoint-migration.json').exists()


def test_offline_dataset_conversion_rejects_unproved_inputs_without_mutation():
    from copy import deepcopy
    from semantica.project_checkpoint_upgrade import canonicalize_checkpoint, _locator
    inputs = {'protocol': 'semantica.project-checkpoint.v1', 'projectId': 'p',
              'sources': [], 'recipe': {}}
    manifest = {'inputs': inputs, 'fence': _digest(_bytes(inputs)), 'createdAt': '2026-10-27T00:00:00Z'}
    entry = {'fence': manifest['fence'], 'key': 'paid', 'digest': _digest(_bytes({'result': 'paid'})),
             'payload': {'result': 'tampered'}}
    entries = {_locator('completed', 'paid'): entry}
    original = deepcopy((manifest, entries))
    with pytest.raises(ValueError, match='digest'):
        canonicalize_checkpoint(manifest, entries)
    assert (manifest, entries) == original
    manifest['entryIdentity'] = 'unknown-layout'
    with pytest.raises(ValueError, match='identity'):
        canonicalize_checkpoint(manifest, {})
    manifest.pop('entryIdentity')
    with pytest.raises(ValueError, match='digest'):
        canonicalize_checkpoint(manifest, {_locator('extraction-entities', 'unproved'): entry})
    inputs['provenance'] = {'recipe': {'forceOcrSourceIds': ['different']}}
    manifest['fence'] = _digest(_bytes(inputs))
    with pytest.raises(ValueError, match='ambiguous historical recipe'):
        canonicalize_checkpoint(manifest, {})


@pytest.mark.parametrize('opaque', [True, False])
def test_document_identity_conversion_is_offline_and_preserves_payload(opaque):
    from semantica.project_checkpoint_upgrade import recover_document, _locator
    inputs = {'sources': [{'sourceId': 's', 'materialRevision': 'r'}],
              'recipe': {}, 'documentProcessing': {'mode': 'native'}}
    key = {'sourceId': 's', 'contentHash': 'r', 'forceOcr': False,
           'documentProcessing': inputs['documentProcessing']}
    payload = {'text': 'already paid'}
    entry = {'fence': _digest(_bytes(inputs)), 'digest': _digest(_bytes(payload)), 'payload': payload}
    if not opaque:
        entry['key'] = key
    name, converted = recover_document(inputs, _locator('document', key), entry)
    assert converted['payload'] is payload
    assert converted['digest'] == entry['digest']
    assert converted['key'] == {'sourceId': 's', 'contentHash': 'r', 'forceOcr': False}
    assert name == _locator('document', converted['key'])
    with pytest.raises(ValueError):
        recover_document(inputs, 'document-wrong.json', entry)


@pytest.mark.parametrize('policy', ['model', 'intermediate', 'business'])
def test_recover_original_key_without_generation(tmp_path, policy, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('migration made a network call'))
    text = 'A source without locations.'
    inputs = {'sources': [{'sourceId': 's', 'materialRevision': 'r'}],
              'recipe': {}, 'relays': {'model': {'modelId': 'old'}}}
    scope = {'source': _digest(text.encode()), 'window': [0, len(text)],
             'binding': None, 'contextWindowTokens': None, 'maxOutputTokens': None}
    params = dict(provider='bifrost', model='old', max_text_length=None,
                  structured_output_mode='typed', entity_types=None, grounding_context=[],
                  grounding='strict', extraction_spec_digest=None, provider_scope=scope)
    canonical = ExtractionCache(identity_policy='content')._generate_key(text, **params)
    if policy == 'intermediate':
        params.pop('model')
        params['provider_scope'] = {k: v for k, v in scope.items() if k in {'source', 'window'}}
    key = canonical if policy == 'business' else ExtractionCache()._generate_key(text, **params)
    name = 'extraction-entities-' + _digest(_bytes(key))[7:] + '.json'
    payload = {'result': [], 'receipts': [], 'rejections': []}
    entry = {'digest': _digest(_bytes(payload)), 'fence': _digest(_bytes(inputs)), 'payload': payload}
    recovered, plans = recover_extractions(inputs, {name: entry}, [{'sourceId': 's', 'materialRevision': 'r', 'document': {'text': text}}])
    assert recovered[name]['key'] == canonical
    assert recovered[name]['payload'] == payload
    assert plans[0][1] == [[0, len(text), text]]
    entry['payload']['result'] = ['corruption']
    with pytest.raises(ValueError, match='digest'):
        recover_extractions(inputs, {name: entry}, [])


def test_selection_uses_original_receipt_time_and_whole_payload():
    def item(time, result):
        payload = {'result': result, 'receipts': [{'created_at': time}], 'rejections': []}
        return {'payload': payload, 'digest': _digest(_bytes(payload))}
    old = item('2026-01-01T00:00:00Z', ['old'])
    latest = item('2026-01-02T00:00:00Z', ['latest'])
    assert select_latest([('copied-later', '2026-02-01T00:00:00Z', old),
                          ('original', '2026-01-02T00:00:00Z', latest)])[2] == latest


@pytest.mark.parametrize('rejected', [False, True])
def test_offline_install_is_consumed_by_native_parser_and_extractor_after_restart(tmp_path, monkeypatch, rejected):
    import json
    import subprocess
    import sys
    from copy import deepcopy
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica.project_checkpoint_upgrade import upgrade_checkpoint, _locator, _params, _relation_params
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, ModelReceipt
    from semantica import semantic_artifact_builder as builder
    from semantica.semantic_source_artifact import _parse_source
    from tests.test_semantic_artifact import _request, H1
    from semantica.semantic_extract.types import Entity, Relation
    from semantica.semantic_extract.cache import _encode_value

    source = tmp_path / 'source.txt'
    source.write_text('Already parsed paid content.')
    request = SemanticArtifactBuildRequest.model_validate(_request(source, tmp_path / 'work')['params'])
    owner = SnapshotCheckpoint(request)
    parsed = _parse_source(request.sources[0], False)
    manifest = json.loads((owner.root / 'manifest.json').read_bytes())
    inputs = deepcopy(manifest['provenance'])
    inputs.update(inputs.pop('provenance'))
    old_fence = _digest(_bytes(inputs))
    manifest.update(inputs=inputs, fence=old_fence)
    manifest.pop('entryIdentity')
    for file in owner.root.iterdir():
        if file.name != 'manifest.json':
            file.unlink()
    entries = {}
    key = {'sourceId': 'source-1', 'contentHash': request.sources[0].material_revision,
           'forceOcr': False, 'processingRevision': inputs['documentProcessing']['processingRevision']}
    entries[_locator('document', key)] = {'fence': old_fence, 'digest': _digest(_bytes(parsed)), 'payload': parsed}
    text = parsed[0]
    parameters = _params(text, 0, len(text), [], inputs['relays']['model'], None, False)
    receipt = ModelReceipt(id='paid', operation='structured_extraction', provider='original',
                          model='old', input_digest=H1, output_digest=H1).model_dump(mode='json')
    entities = [Entity('Already', 'WORD', 0, 7), Entity('content', 'WORD', 20, 27)]
    relations = [Relation(entities[0], 'mentions', entities[1], context=text)]
    for kind, params, values in [('extraction-entities', parameters, entities),
                         ('extraction-relations', _relation_params(parameters, entities), relations)]:
        old_key = ExtractionCache()._generate_key(text, **params)
        payload = {'result': _encode_value(values), 'receipts': [receipt], 'rejections': []}
        entries[_locator(kind, old_key)] = {'fence': old_fence, 'digest': _digest(_bytes(payload)), 'payload': payload}
        if rejected and kind == 'extraction-entities':
            marker = {'kind': kind, 'keyDigest': _digest(_bytes(old_key)), 'payloadDigest': _digest(_bytes(payload))}
            entries[f"rejected-{kind}-{marker['keyDigest'][7:]}-{marker['payloadDigest'][7:]}.json"] = marker
    (owner.root / 'manifest.json').write_bytes(_bytes(manifest))
    for name, entry in entries.items():
        (owner.root / name).write_bytes(_bytes(entry))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('unexpected network'))
    monkeypatch.setattr('semantica.semantic_source_artifact.parse_source', lambda *a, **k: pytest.fail('reparsed content'))
    monkeypatch.setattr(builder._ProjectModelProvider, 'generate', lambda *a, **k: pytest.fail('paid cache missed'))
    upgrade_checkpoint(owner.root)
    request.relays['model'].model_id = 'different-model'
    for _ in range(2):
        owner = SnapshotCheckpoint(request)
        token = active_checkpoint.set(owner)
        try:
            assert _parse_source(request.sources[0], False) == parsed
            windows = builder._source_windows(request.sources[0], False, text)
            if rejected:
                canonical = ExtractionCache(identity_policy='content')._generate_key(text, **parameters)
                assert owner.read('extraction-entities', canonical) is None
            else:
                result, receipts, restored = builder._extract_window(text, request.relays['model'], None, [], windows[0])
                assert result == {'entities': entities, 'relations': relations}
                assert restored and [item.id for item in receipts] == ['paid']
        finally:
            active_checkpoint.reset(token)
    # A fresh interpreter must use the same native paths without parsing or buying work.
    child = r'''
import json, sys
from unittest.mock import patch
from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from semantica.semantic_source_artifact import _parse_source
from semantica import semantic_artifact_builder as builder
from semantica.semantic_extract.cache import ExtractionCache
request = SemanticArtifactBuildRequest.model_validate(json.loads(sys.stdin.read()))
def forbidden(*args, **kwargs):
    raise AssertionError('restart reparsed or regenerated paid content')
with patch('urllib.request.urlopen', forbidden), patch('semantica.semantic_source_artifact.parse_source', forbidden), patch.object(builder._ProjectModelProvider, 'generate', forbidden):
    owner = SnapshotCheckpoint(request)
    token = active_checkpoint.set(owner)
    try:
        parsed = _parse_source(request.sources[0], False)
        windows = builder._source_windows(request.sources[0], False, parsed[0])
        if sys.argv[1] == 'True':
            params = json.loads(sys.argv[2])
            key = ExtractionCache(identity_policy='content')._generate_key(parsed[0], **params)
            assert owner.read('extraction-entities', key) is None
        else:
            result, receipts, restored = builder._extract_window(parsed[0], request.relays['model'], None, [], windows[0])
            assert [e.text for e in result['entities']] == ['Already', 'content']
            assert result['relations'][0].subject == result['entities'][0]
            assert result['relations'][0].object == result['entities'][1]
            assert result['relations'][0].predicate == 'mentions'
            assert restored and [r.id for r in receipts] == ['paid']
    finally:
        active_checkpoint.reset(token)
'''
    completed = subprocess.run([sys.executable, '-c', child, str(rejected), json.dumps(parameters)],
                               input=request.model_dump_json(by_alias=True), text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    assert not list((owner.root.parent / 'evidence').glob('checkpoint-next-*'))
    assert not (owner.root.parent / '.checkpoint-migration.json').exists()
    assert set(p.name for p in owner.root.iterdir()).isdisjoint(set(entries) - set(
        p.name for p in owner.root.iterdir() if p.name.startswith('rejected-')))


def test_window_reuses_saved_context_after_projection_changes(tmp_path, monkeypatch):
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica import semantic_artifact_builder as builder
    checkpoint = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    checkpoint._initialize(tmp_path / 'work', [], {'projectId': 'p', 'sources': [], 'provenance': {'recipe': {}}})
    token = active_checkpoint.set(checkpoint)
    seen = []
    monkeypatch.setattr(builder, '_extraction_context_batches', lambda *args: [[{'ref': 'original'}]])
    monkeypatch.setattr(builder, '_window_grounding_context', lambda *args: [])
    monkeypatch.setattr(builder, '_extract_window_context', lambda *args:
                        (seen.append(args[4]) or {'entities': [], 'relations': []}, [], True))
    try:
        from types import SimpleNamespace
        relay = SimpleNamespace(context_window_tokens=500000, max_output_tokens=32768)
        builder._extract_window('text', relay, None, [], (0, 4, 'text'))
        monkeypatch.setattr(builder, '_extraction_context_batches', lambda *args: pytest.fail('replanned paid context'))
        builder._extract_window('text', relay, None, [], (0, 4, 'text'))
        assert seen == [[{'ref': 'original'}], [{'ref': 'original'}]]
    finally:
        active_checkpoint.reset(token)


@pytest.mark.parametrize('located', [True, False, 'recorded', 'unversioned-context', 'projected'])
def test_chunk_conversion_preserves_grounding_and_relation_dependency(monkeypatch, located):
    from semantica.project_checkpoint_upgrade import recover_chunks, _locator
    from semantica.semantic_artifact_builder import stable_digest
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('migration made a network call'))
    text = 'Acme hired Alice.'
    inputs = {'sources': [{'sourceId': 's', 'materialRevision': 'r'}],
              'recipe': {}, 'relays': {'model': {'modelId': 'old'}}}
    context = [{'ref': 'original', 'quote': 'Acme', 'start': 0, 'end': 4}] if located in {'recorded', 'unversioned-context', 'projected'} else []
    if located == 'projected':
        monkeypatch.setattr('semantica.semantic_artifact_builder._docling_locations', lambda *args: context)
    key = {'promptVersion': 'located-spans-v2', 'sourceText': _digest(text.encode()),
           'window': {'start': 0, 'end': len(text), 'digest': _digest(text.encode())},
           'model': 'old', 'bindingId': None, 'contextWindowTokens': None,
           'maxOutputTokens': None, 'spec': None, 'groundingContext': stable_digest(context)}
    if not located:
        key = {k: v for k, v in key.items() if k not in {'promptVersion', 'groundingContext'}}
    if located == 'unversioned-context':
        key.pop('promptVersion')
    payload = {'extracted': {'entities': [{'id': 'a', 'name': 'Acme', 'type': 'ORG', 'occurrence': 1,
                'attributes': {'original': 'kept'}}], 'relations': []}, 'receipts': []}
    entry = {'fence': _digest(_bytes(inputs)), 'digest': _digest(_bytes(payload)), 'payload': payload}
    name = _locator('chunk-extraction', key)
    kwargs = {'recorded_windows': [(text, context)]} if located in {'recorded', 'unversioned-context'} else {}
    if located == 'projected':
        from semantica.semantic_extract.methods import _prompt_grounding_context
        kwargs = {'recorded_windows': [(text, _prompt_grounding_context(text, context))]}
    result = recover_chunks(inputs, {name: entry}, [
        {'sourceId': 's', 'materialRevision': 'r', 'document': {'text': text}}], **kwargs)[name]
    entity, relation = result[0][1], result[1][1]
    assert relation['entityKey'] == entity['key']
    assert relation['entityResultDigest'] == _digest(_bytes(entity['payload']['result']))
    from semantica.semantic_extract.cache import _decode_value
    decoded = _decode_value(entity['payload']['result'])[0]
    assert decoded.text == 'Acme' and decoded.start_char == 0 and decoded.end_char == 4
    assert decoded.attributes == {'original': 'kept'}
