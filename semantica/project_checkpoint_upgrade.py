"""Explicit offline recovery of hash-only extraction identities; never a runtime reader.

The original filename must match a reconstructed historical key before an entry
can acquire the canonical business key. This module performs no parsing or model
calls. Callers must commit and verify the canonical dataset before deleting inputs.
"""
from datetime import datetime
from hashlib import sha256
import json

from .project_checkpoint import _bytes, _digest


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
    from .semantic_artifact_builder import _ProjectExtractionCache
    cache = ExtractionCache()
    yield cache._generate_key(text, **params)
    intermediate = {k: v for k, v in params.items() if k != 'model'}
    intermediate['provider_scope'] = {k: v for k, v in params['provider_scope'].items()
        if k not in {'binding', 'contextWindowTokens', 'maxOutputTokens'}}
    yield cache._generate_key(text, **intermediate)
    yield _ProjectExtractionCache()._generate_key(text, **params)


def recover_extractions(inputs, entries, parsed_sources):
    """Recover exact source/window keys, retaining original payloads and dependencies.

    Unknown identities fail closed. Hash matching is the proof: different parsed
    text, window plans or grounding cannot accidentally admit an unrelated result.
    """
    from .semantic_artifact_builder import (_ProjectExtractionCache, _docling_locations,
        _text_windows, _window_grounding_context, _extraction_context_batches, _decode_value, _window_context_key)
    from .semantic_extract.schema import ExtractionSpecification
    fence = _digest(_bytes(inputs))
    for entry in entries.values():
        if entry.get('fence') != fence or entry.get('digest') != _digest(_bytes(entry['payload'])):
            raise ValueError('extraction entry digest or fence mismatch')
    provenance = inputs.get('provenance', inputs)
    recipe = provenance.get('recipe', {})
    relay = provenance.get('relays', {}).get('model', {})
    spec = recipe.get('extractionSpec')
    spec = ExtractionSpecification.model_validate(spec).digest if spec else None
    cache = _ProjectExtractionCache()
    recovered, plans = {}, []
    def admit(kind, window, params):
        for key in _historical_keys(window, params):
            name = _locator(kind, key)
            if name in entries:
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
            batches = _extraction_context_batches(window, context)
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
    from .semantic_artifact_builder import (_ProjectExtractionCache, _docling_locations,
        _text_windows, _window_grounding_context, _extraction_context_batches, stable_digest, _window_context_key)
    from .semantic_extract.cache import _encode_value
    from .semantic_extract.types import Entity
    from .semantic_extract.methods import _exact_occurrence, _parse_grounded_relation_result, _prompt_grounding_context
    fence = _digest(_bytes(inputs))
    for entry in entries.values():
        if entry.get('fence') != fence or entry.get('digest') != _digest(_bytes(entry['payload'])):
            raise ValueError('chunk entry digest or fence mismatch')
    provenance = inputs.get('provenance', inputs)
    recipe = provenance.get('recipe', {})
    if recipe.get('extractionSpec'):
        raise ValueError('chunk specification identity requires recovery')
    relay = provenance.get('relays', {}).get('model', {})
    cache = _ProjectExtractionCache()
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
                plan = _extraction_context_batches(window, context)
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
