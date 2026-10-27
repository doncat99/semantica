"""Explicit offline recovery of hash-only extraction identities; never a runtime reader.

The original filename must match a reconstructed historical key before an entry
can acquire the canonical business key. This module performs no parsing or model
calls. Callers must commit and verify the canonical dataset before deleting inputs.
"""
from datetime import datetime
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from .project_checkpoint import _bytes, _digest

# Frozen historical layout before 34c995e8c; only offline hash reconstruction uses it.
_HISTORICAL_CONTEXT_BYTES = 48_000


def canonicalize_checkpoint(manifest, entries):
    """Prepare one verified canonical dataset without writing or deleting files.

    Historical extraction identities require verified parsed sources and exact
    original hash reconstruction. Installation uses the native checkpoint owner.
    """
    from .project_checkpoint import SnapshotCheckpoint, _canonical_inputs
    if manifest.get('entryIdentity') not in (None, 'business-content-v1'):
        raise ValueError('unknown checkpoint entry identity')
    inputs = manifest['inputs']
    if manifest['fence'] != _digest(_bytes(inputs)):
        raise ValueError('manifest digest mismatch')
    datetime.fromisoformat(manifest['createdAt'])
    origin = deepcopy(manifest.get('provenance', inputs))
    business_origin = deepcopy(inputs)
    # Old top-level recipe fields are interpreted only in this offline owner.
    for value in (origin, business_origin):
        if 'recipe' in value:
            nested = value.setdefault('provenance', {})
            if 'recipe' in nested and nested['recipe'] != value['recipe']:
                raise ValueError('ambiguous historical recipe provenance')
            nested['recipe'] = value['recipe']
    canonical_inputs = _canonical_inputs(business_origin)
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    owner.fence = _digest(_bytes(canonical_inputs))
    converted, renamed = {}, {}
    def admit(name, entry):
        if name in converted and converted[name] != entry:
            raise ValueError(f'conflicting canonical completed work: {name}')
        converted[name] = deepcopy(entry)
    extraction = {name: entry for name, entry in entries.items() if name.startswith(
        ('extraction-entities-', 'extraction-relations-', 'chunk-extraction-'))}
    recover = bool(extraction) and (manifest.get('entryIdentity') is None
        or any(entry.get('key') is None for entry in extraction.values())
        or any(name.startswith('chunk-extraction-') for name in extraction))
    parsed_sources = []
    for name, entry in entries.items():
        if name.startswith('rejected-'):
            continue
        if recover and name in extraction:
            continue
        if name.startswith('document-'):
            canonical_name, canonical_entry = recover_document(inputs, name, entry)
            canonical_entry = {**canonical_entry, 'fence': owner.fence}
            kind, old_hash = name.removesuffix('.json').rsplit('-', 1)
            renamed[(kind, 'sha256:' + old_hash)] = [(kind, _digest(_bytes(canonical_entry['key'])), canonical_entry['digest'], entry['digest'])]
            from .semantic_source_artifact import _validate_saved_source
            key = canonical_entry['key']
            sources = inputs.get('sources', [inputs.get('source', {})])
            source = next((s for s in sources if s['sourceId'] == key['sourceId']
                           and s['materialRevision'] == key['contentHash']), None)
            if source is None:
                raise ValueError('document does not belong to original source inputs')
            payload = _validate_saved_source(canonical_entry['payload'], source['materialRevision'], source['mimeType'])
            if recover:
                parsed_sources.append({'sourceId': source['sourceId'], 'materialRevision': source['materialRevision'],
                                       'document': payload[1]})
        else:
            canonical_name, canonical_entry = owner._import_entry(name, entry, manifest['fence'])
        # Use the same admission owner as runtime; never stamp a half-converted dataset.
        owner._import_entry(canonical_name, canonical_entry, owner.fence)
        admit(canonical_name, canonical_entry)
    if recover:
        native = {name: entry for name, entry in extraction.items() if not name.startswith('chunk-extraction-')}
        recovered, plans = recover_extractions(inputs, native, parsed_sources)
        chunks = {name: entry for name, entry in extraction.items() if name.startswith('chunk-extraction-')}
        recovered_chunks = recover_chunks(inputs, chunks, parsed_sources)
        def install_recovered(old_name, kind, entry):
            normalized = {k: deepcopy(v) for k, v in entry.items()
                          if k not in {'contextKey', 'contextBatches', 'entityKey', 'entityResultDigest'}}
            normalized['fence'] = owner.fence
            name = _locator(kind, entry['key'])
            owner._import_entry(name, normalized, owner.fence)
            admit(name, normalized)
            old_kind, old_hash = old_name.removesuffix('.json').rsplit('-', 1)
            renamed.setdefault((old_kind, 'sha256:' + old_hash), []).append(
                (kind, _digest(_bytes(entry['key'])), normalized['digest'], entries[old_name]['digest']))
            if 'contextKey' in entry:
                key, payload = entry['contextKey'], entry['contextBatches']
                admit(_locator('window-contexts', key), {'fence': owner.fence, 'key': key,
                      'payload': payload, 'digest': _digest(_bytes(payload))})
        for name, entry in recovered.items():
            install_recovered(name, 'extraction-entities' if name.startswith('extraction-entities-') else 'extraction-relations', entry)
        for name, values in recovered_chunks.items():
            for kind, entry in values:
                install_recovered(name, kind, entry)
        for key, windows in plans:
            for kind, payload in [('source-windows', windows), ('extraction-origin', True)]:
                admit(_locator(kind, key), {'fence': owner.fence, 'key': key,
                      'payload': payload, 'digest': _digest(_bytes(payload))})
    for name, entry in entries.items():
        if not name.startswith('rejected-'):
            continue
        owner._import_entry(name, entry, manifest['fence'])
        targets = renamed.get((entry['kind'], entry['keyDigest']),
                              [(entry['kind'], entry['keyDigest'], entry['payloadDigest'], entry['payloadDigest'])])
        for kind, key_digest, payload_digest, original_digest in targets:
            if kind == entry['kind']:
                # Key migration does not change which completed result was rejected.
                payload_digest = entry['payloadDigest']
            elif entry['payloadDigest'] != original_digest:
                raise ValueError('historical rejection cannot be mapped to a converted payload')
            canonical_entry = {'kind': kind, 'keyDigest': key_digest, 'payloadDigest': payload_digest}
            canonical_name = f'rejected-{kind}-{key_digest[7:]}-{payload_digest[7:]}.json'
            owner._import_entry(canonical_name, canonical_entry, owner.fence)
            admit(canonical_name, canonical_entry)
    return {**deepcopy(manifest), 'inputs': canonical_inputs, 'fence': owner.fence,
            'entryIdentity': 'business-content-v1', 'provenance': origin}, converted


def upgrade_checkpoint(path):
    """Offline all-or-nothing conversion; no runtime fallback or model execution."""
    from .project_checkpoint import SnapshotCheckpoint, _directory_lock, _regular_directory
    owner = SnapshotCheckpoint.__new__(SnapshotCheckpoint)
    owner.root = Path(path).absolute()
    _regular_directory(owner.root)
    with _directory_lock(owner.root.parent / '.checkpoint.lock'):
        owner._finish_migration()
        manifest_path = owner.root / 'manifest.json'
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError('checkpoint manifest is not a regular file')
        entries = {}
        for file in owner.root.iterdir():
            if file == manifest_path:
                continue
            if file.is_symlink() or not file.is_file() or file.suffix != '.json':
                raise ValueError('unknown checkpoint file')
            entries[file.name] = json.loads(file.read_bytes())
        manifest, entries = canonicalize_checkpoint(json.loads(manifest_path.read_bytes()), entries)
        owner._install(manifest, entries)
    return manifest


def select_latest(candidates):
    """Select an entire verified result by original execution time, never copy time."""
    def rank(candidate):
        origin, created, entry = candidate
        payload = entry['payload']
        receipts = payload.get('receipts', [payload.get('receipt', {})]) if isinstance(payload, dict) else []
        dates = [datetime.fromisoformat(r['created_at']) for r in receipts if r.get('created_at')]
        return max(dates) if dates else datetime.fromisoformat(created), entry['digest'], origin
    return max(candidates, key=rank)


def _locator(kind, key):
    return kind + '-' + sha256(_bytes(key)).hexdigest() + '.json'


def recover_document(inputs, name, entry):
    """Offline identity conversion, proved by original locator and payload digest."""
    if entry.get('fence') != _digest(_bytes(inputs)) or entry.get('digest') != _digest(_bytes(entry['payload'])):
        raise ValueError('document entry digest or fence mismatch')
    key = entry.get('key')
    if key is None:
        recipe = inputs.get('recipe', inputs.get('provenance', {}).get('recipe', {}))
        candidates = []
        for source in inputs.get('sources', [inputs.get('source', {})]):
            candidate = {'sourceId': source.get('sourceId'), 'contentHash': source.get('materialRevision'),
                         'forceOcr': source.get('sourceId') in recipe.get('forceOcrSourceIds', [])}
            for identity in (candidate, {**candidate, 'documentProcessing': inputs.get('documentProcessing')},
                    {**candidate, 'processingRevision': inputs.get('documentProcessing', {}).get('processingRevision')}):
                if name == _locator('document', identity):
                    candidates.append(identity)
        if len(candidates) != 1:
            raise ValueError('historical document identity cannot be recovered')
        key = candidates[0]
    if not isinstance(key, dict) or name != _locator('document', key):
        raise ValueError('document identity does not match original locator')
    canonical = {k: v for k, v in key.items() if k not in {'documentProcessing', 'processingRevision'}}
    if set(canonical) != {'sourceId', 'contentHash', 'forceOcr'}:
        raise ValueError('unknown document identity')
    return _locator('document', canonical), {**entry, 'key': canonical}


def _params(text, start, end, context, relay, spec, formula):
    return dict(provider='bifrost', model=relay.get('modelId'), max_text_length=None,
        structured_output_mode='typed', entity_types=None, grounding_context=context,
        grounding='strict', extraction_spec_digest=spec,
        **({'formula_semantics': True} if formula else {}),
        provider_scope={'source': _digest(text.encode()), 'window': [start, end],
            'binding': relay.get('bindingId'), 'contextWindowTokens': relay.get('contextWindowTokens'),
            'maxOutputTokens': relay.get('maxOutputTokens')})


def _relation_params(params, entities):
    from .semantic_extract.methods import _stable_fingerprint
    return {**{k: v for k, v in params.items() if k != 'entity_types'},
        'max_retries': 1, 'relation_types': None, 'extract_temporal_bounds': False,
        'entities_hash': _stable_fingerprint([
            json.dumps(dict(text=e.text, label=e.label, start=e.start_char, end=e.end_char,
                            metadata=e.metadata, attributes=e.attributes), sort_keys=True, ensure_ascii=False)
            for e in entities]) if entities else ''}


def _historical_keys(text, params):
    from .semantic_extract.cache import ExtractionCache
    cache = ExtractionCache()
    yield cache._generate_key(text, **params)
    intermediate = {k: v for k, v in params.items() if k != 'model'}
    intermediate['provider_scope'] = {k: v for k, v in params['provider_scope'].items()
        if k not in {'binding', 'contextWindowTokens', 'maxOutputTokens'}}
    yield cache._generate_key(text, **intermediate)
    yield ExtractionCache(identity_policy="content")._generate_key(text, **params)


def recover_extractions(inputs, entries, parsed_sources):
    """Recover exact source/window keys, retaining original payloads and dependencies.

    Unknown identities fail closed. Hash matching is the proof: different parsed
    text, window plans or grounding cannot accidentally admit an unrelated result.
    """
    from .semantic_extract.cache import ExtractionCache
    from .semantic_artifact_builder import (_docling_locations,
        _text_windows, _window_grounding_context, _extraction_context_batches, _decode_value, _window_context_key)
    from .semantic_extract.schema import ExtractionSpecification
    fence = _digest(_bytes(inputs))
    for entry in entries.values():
        if entry.get('fence') != fence or entry.get('digest') != _digest(_bytes(entry['payload'])):
            raise ValueError('extraction entry digest or fence mismatch')
    provenance = {**inputs, **inputs.get('provenance', {})}
    recipe = provenance.get('recipe', {})
    relay = provenance.get('relays', {}).get('model', {})
    spec = recipe.get('extractionSpec')
    spec = ExtractionSpecification.model_validate(spec).digest if spec else None
    cache = ExtractionCache(identity_policy="content")
    recovered, plans = {}, []
    def admit(kind, window, params):
        for key in _historical_keys(window, params):
            name = _locator(kind, key)
            if name in entries:
                if entries[name].get('key') not in (None, key):
                    raise ValueError('extraction key does not match original locator')
                entry = {**entries[name], 'key': cache._generate_key(window, **params)}
                if name in recovered and recovered[name] != entry:
                    raise ValueError('ambiguous extraction identity')
                recovered[name] = entry
                yield entry
    sources = {s['sourceId']: s for s in inputs['sources']}
    for parsed in parsed_sources:
        source = sources[parsed['sourceId']]
        if parsed['materialRevision'] != source['materialRevision']:
            raise ValueError('parsed source revision mismatch')
        text = parsed['document']['text']
        locations = _docling_locations(parsed['document'], text)
        windows = [list(w) for w in _text_windows(text)]
        plans.append(({'sourceId': source['sourceId'], 'materialRevision': source['materialRevision'],
                       'forceOcr': source['sourceId'] in recipe.get('forceOcrSourceIds', [])}, windows))
        for start, end, window in windows:
            context = _window_grounding_context(locations, start, end)
            batches = _extraction_context_batches(window, context, _HISTORICAL_CONTEXT_BYTES)
            for batch in batches:
                params = _params(text, start, end, batch, relay, spec,
                    source['sourceId'] in recipe.get('formulaSemanticsSourceIds', []))
                for entry in admit('extraction-entities', window, params):
                    entry['contextKey'] = _window_context_key(text, (start, end),
                        ExtractionSpecification.model_validate(recipe['extractionSpec']) if recipe.get('extractionSpec') else None,
                        source['sourceId'] in recipe.get('formulaSemanticsSourceIds', []))
                    entry['contextBatches'] = batches
                    entities = _decode_value(entry['payload']['result'])
                    for relation in admit('extraction-relations', window, _relation_params(params, entities)):
                        relation['entityKey'] = entry['key']
                        relation['entityResultDigest'] = _digest(_bytes(entry['payload']['result']))
    missing = set(entries) - set(recovered)
    if missing:
        raise ValueError(f'{len(missing)} extraction identities not recovered: {sorted(missing)[:3]}')
    return recovered, plans


def recover_chunks(inputs, entries, parsed_sources, *, recorded_windows=()):
    """Convert completed window carriers into the same entity/relation cache format."""
    from .semantic_extract.cache import ExtractionCache
    from .semantic_artifact_builder import (_docling_locations,
        _text_windows, _window_grounding_context, _extraction_context_batches, stable_digest, _window_context_key)
    from .semantic_extract.cache import _encode_value
    from .semantic_extract.types import Entity
    from .semantic_extract.methods import _exact_occurrence, _parse_grounded_relation_result, _prompt_grounding_context
    fence = _digest(_bytes(inputs))
    for entry in entries.values():
        if entry.get('fence') != fence or entry.get('digest') != _digest(_bytes(entry['payload'])):
            raise ValueError('chunk entry digest or fence mismatch')
    provenance = {**inputs, **inputs.get('provenance', {})}
    recipe = provenance.get('recipe', {})
    if recipe.get('extractionSpec'):
        raise ValueError('chunk specification identity requires recovery')
    relay = provenance.get('relays', {}).get('model', {})
    cache = ExtractionCache(identity_policy="content")
    recovered = {}
    for parsed in parsed_sources:
        if not any(s['sourceId'] == parsed['sourceId'] and s['materialRevision'] == parsed['materialRevision']
                   for s in inputs['sources']):
            raise ValueError('parsed source revision mismatch')
        text = parsed['document']['text']
        locations = _docling_locations(parsed['document'], text)
        windows = {(start, end, window): [] for start, end, window in _text_windows(text)}
        for window, context in recorded_windows:
            cursor = 0
            while window and (start := text.find(window, cursor)) >= 0:
                windows.setdefault((start, start + len(window), window), []).append(context)
                cursor = start + 1
        for (start, end, window), recorded in windows.items():
            by_ref = {item['ref']: item for item in locations}
            for projected in list(recorded):
                if projected and all(item.get('ref') in by_ref for item in projected):
                    canonical = [by_ref[item['ref']] for item in projected]
                    if _prompt_grounding_context(window, canonical) == projected:
                        recorded.append(canonical)
            overlapping = [p for p in locations if p['start'] is not None and p['start'] < end and p['end'] > start]
            pages = {p['page'] for p in overlapping if p.get('page') is not None}
            adjacent = [dict(p) for p in locations if p in overlapping or
                        (p.get('page') is not None and any(abs(p['page'] - page) <= 1 for page in pages))]
            contexts = [_window_grounding_context(locations, start, end), adjacent, [], *recorded]
            batches = {}
            for context in contexts:
                plan = _extraction_context_batches(window, context, _HISTORICAL_CONTEXT_BYTES)
                for batch in plan:
                    batches.setdefault(_bytes(batch), (batch, plan))
            for batch in recorded:
                batches.setdefault(_bytes(batch), (batch, [batch]))
            for batch, plan in batches.values():
                key = {'promptVersion': 'located-spans-v2', 'sourceText': _digest(text.encode()),
                    'window': {'start': start, 'end': end, 'digest': _digest(window.encode())},
                    'model': relay.get('modelId'), 'bindingId': relay.get('bindingId'),
                    'contextWindowTokens': relay.get('contextWindowTokens'),
                    'maxOutputTokens': relay.get('maxOutputTokens'), 'spec': None,
                    'groundingContext': stable_digest(batch)}
                name = _locator('chunk-extraction', key)
                if name not in entries:
                    name = _locator('chunk-extraction', {k: v for k, v in key.items()
                                    if k != 'promptVersion'})
                if name not in entries and not batch:
                    name = _locator('chunk-extraction', {k: v for k, v in key.items()
                                    if k not in {'promptVersion', 'groundingContext'}})
                if name not in entries:
                    continue
                payload = entries[name]['payload']
                entities = []
                for item in payload['extracted']['entities']:
                    begin, finish, occurrence = _exact_occurrence(window, item['name'], item.get('occurrence'))
                    entities.append(Entity(item['name'], item['type'], begin, finish,
                        item.get('confidence', 0.9), {'mention_id': item['id'], 'span_occurrence': occurrence},
                        attributes=item.get('attributes', {})))
                names = {e.metadata['mention_id']: e.text for e in entities}
                raw = {'relations': [{**r, 'subject_id': r['subject'], 'object_id': r['object'],
                                     'subject': names[r['subject']], 'object': names[r['object']]}
                                    for r in payload['extracted']['relations']]}
                rejections = []
                relations = _parse_grounded_relation_result(raw, entities, window, 'bifrost',
                    relay.get('modelId'), reject_invalid=True, rejections=rejections, grounding_context=batch)
                if rejections:
                    raise ValueError(f'completed chunk no longer grounds losslessly: {name}')
                params = _params(text, start, end, batch, relay, None, False)
                recovered[name] = []
                for kind, result, parameters in [('extraction-entities', entities, params),
                    ('extraction-relations', relations, _relation_params(params, entities))]:
                    value = {'result': _encode_value(result), 'receipts': payload['receipts'], 'rejections': []}
                    recovered[name].append((kind, {'key': cache._generate_key(window, **parameters),
                        'payload': value, 'digest': _digest(_bytes(value))}))
                entity = recovered[name][0][1]
                entity['contextKey'] = _window_context_key(text, (start, end), None)
                entity['contextBatches'] = plan
                relation = recovered[name][1][1]
                relation['entityKey'] = entity['key']
                relation['entityResultDigest'] = _digest(_bytes(entity['payload']['result']))
    if set(entries) != set(recovered):
        raise ValueError(f'chunk identities not recovered: {sorted(set(entries) - set(recovered))}')
    return recovered
