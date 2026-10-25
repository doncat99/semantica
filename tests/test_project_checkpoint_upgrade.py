import pytest

from semantica.project_checkpoint import _bytes, _digest
from semantica.project_checkpoint_upgrade import recover_extractions, select_latest
from semantica.semantic_artifact_builder import _ProjectExtractionCache
from semantica.semantic_extract.cache import ExtractionCache


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
    canonical = _ProjectExtractionCache()._generate_key(text, **params)
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


def test_window_reuses_saved_context_after_projection_changes(tmp_path, monkeypatch):
    from semantica.project_checkpoint import SnapshotCheckpoint, active_checkpoint
    from semantica import semantic_artifact_builder as builder
    checkpoint = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    checkpoint._initialize(tmp_path / 'work', [], {'projectId': 'p', 'sources': [], 'recipe': {}})
    token = active_checkpoint.set(checkpoint)
    seen = []
    monkeypatch.setattr(builder, '_extraction_context_batches', lambda *args: [[{'ref': 'original'}]])
    monkeypatch.setattr(builder, '_window_grounding_context', lambda *args: [])
    monkeypatch.setattr(builder, '_extract_window_context', lambda *args:
                        (seen.append(args[4]) or {'entities': [], 'relations': []}, [], True))
    try:
        builder._extract_window('text', None, None, [], (0, 4, 'text'))
        monkeypatch.setattr(builder, '_extraction_context_batches', lambda *args: pytest.fail('replanned paid context'))
        builder._extract_window('text', None, None, [], (0, 4, 'text'))
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
