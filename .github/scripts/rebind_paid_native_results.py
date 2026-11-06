"""Offline, no-model adoption after a certified native-window budget repair.

Run with the target artifact Python while its project worker is stopped. A dry
run is mandatory; the returned certificate must be supplied verbatim to apply.
Normal builds never import this maintenance entry or read superseded recipes.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import sqlite3
from pathlib import Path

ALLOWED = {
    'semantic_publication_builder.py': {'_read_source_projection_text', '_source_passages',
        '_EvidenceReference.quote', '_build_semantic_artifacts.hydrate_entity'},
}

# Exact Python 3.12 ASTs of the independently tested producer-window repair.
# A future producer edit must never be accepted by removing its name.
REVIEWED_PRODUCER_AST = {
    '_bounded_native_source_end': {'before': None,
        'after': 'a3cd1b24f18d3ed181ec44bfc9aef2ff82e77620bb4efe9095d54339b3aed3f3'},
    '_source_window_addresses': {'before': None,
        'after': 'bd8b41fb92985d41d24c2627c48f0ffa38be62e6ac35ca40c4706da2067fd573'},
    '_source_windows': {'before': 'ff07f8e0c07f21b7f4db68518bde92941c523610d57f1a97ddbebaa75db1bdaf',
        'after': '0c60d85ee9b51be84e73d55f5068bee055e28aff1feff93604a9cd9e5ce5fce6'},
}

# Only the reviewed source-slice repair is eligible. Successful native records
# already passed the strict writer; failed accepted envelopes are not adopted.
SPAN_REPAIR_AST = {
    'before': '07feef20de164d8d418dc1078592981aa68acbbe04a71bef62a9208a7169593e',
    'after': '6062e7646639793cb03e2f3809366f8e48f4e436f2613abb0b224b4d529dcd55',
}


# Filled only with the final independently reviewed c8cd context-stream repair.
# Missing or future ASTs fail closed; this is not a producer allowlist.
CONTEXT_REPAIR_AST = {
    'semantic_publication_builder.py': {
        '_GroundingContext.addresses': {
            'before': '5121431d223641530d172e9796ecf91bde93b4e31ad1f57dce7a44c588fe8eda',
            'after': '66c9524359bca8711c7d1e180bc6125db7026acbb4af5dd489b65b3698fb2563',
        },
        '_extraction_context_batches': {
            'before': '53151f81a5596536ee23b8a81186d05fd77a1e4af5a07ebbef9d113f5468817d',
            'after': '5fb36b11e33df060d58dab8f9dc5fe8de3bab178e28961ca911aa46eb0893589',
        },
    },
}
CONTEXT_REPAIR_NEW_FILES = {
    'semantic_document_context.py': '68786f79d5cfc040d1c10dbeb5f49a5bee56eab51a208bb5e66c24f6bb18fc4b',
}
CONTEXT_SOURCE_PROCESSING = 'sha256:fc06237244bbba8c49dff2db8d1ec5291ac9682285d1d1a5e5302f843181d2b3'
CONTEXT_PAID_INVENTORY_SHA256 = 'ddcfe805f2250f26f445e7bd2a8f6b99c240ce570f2a7ecc0263613ba678395c'


CACHE_SOURCE_PROCESSING = 'sha256:36b721dd4741276eea6cc701e69c0a46157edf81dcd0ad4ded9a099dac06ad05'
CACHE_REPAIR_BYTES = {
    'before': '6d01acd5c67a61b2285ab6b662d38de0f4247c52428fe3022a7fbd050b642877',
    'after': 'bd96ef1def3ea228e397aaa5cbe397b5e9b9aba8a940afc72550f08bf2b3b60f',
}


def certify_cache_owner_repair(old_root, new_root):
    """Only the exact reviewed 18e WAL lock/codec/capacity repair is admissible."""
    from semantica.semantic_publication_builder import _project_processing_digest
    files = lambda root: {p.relative_to(root).as_posix(): p for p in root.rglob('*.py') if '__pycache__' not in p.parts}
    old, new = files(old_root), files(new_root)
    if set(old) != set(new):
        raise ValueError('Cache repair requires exact reviewed runtime inventory')
    changed = {}
    for name in sorted(old):
        left, right = old[name].read_bytes(), new[name].read_bytes()
        if left == right:
            continue
        if name != 'semantic_extract/cache.py':
            raise ValueError('Cache repair changed another producer: ' + name)
        hashes = dict(before=hashlib.sha256(left).hexdigest(), after=hashlib.sha256(right).hexdigest())
        if hashes != CACHE_REPAIR_BYTES:
            raise ValueError('Cache owner differs from exact reviewed bytes')
        changed[name] = hashes
    if set(changed) != {'semantic_extract/cache.py'} or _project_processing_digest(old_root) != CACHE_SOURCE_PROCESSING:
        raise ValueError('Cache repair requires fixed 18e source processing and reviewed change')
    return dict(oldProcessing=CACHE_SOURCE_PROCESSING,newProcessing=_project_processing_digest(new_root),
                changedFiles=changed,repair='exact-cache-wal-read-owner')


def verify_cache_paid_inputs(request, inventory):
    # The fixed inventory predates the certified context adoption. Only the
    # release differs; all paid-input fields must still match its exact digest.
    original = request.model_copy(update={'release': request.release.model_copy(update={
        'artifact_digest': 'sha256:c8cd9c16e9f91564b7517709d3f47e6c4921a3be7bbca6849751f35ceae860bf'})})
    return verify_context_paid_inputs(original, inventory)


def certify_context_repair(old_root, new_root):
    from semantica.semantic_publication_builder import _project_processing_digest
    files = lambda root: {p.relative_to(root).as_posix(): p for p in root.rglob('*.py')
                          if '__pycache__' not in p.parts}
    old, new = files(old_root), files(new_root)
    if set(old) | set(CONTEXT_REPAIR_NEW_FILES) != set(new) or set(old) & set(CONTEXT_REPAIR_NEW_FILES) or not CONTEXT_REPAIR_AST:
        raise ValueError('Context repair requires exact reviewed runtime inventory')
    changed = {}
    for name, expected in CONTEXT_REPAIR_NEW_FILES.items():
        actual = hashlib.sha256(new[name].read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('New native query owner differs from exact reviewed bytes: ' + name)
        changed[name] = dict(before=None, after=actual)
    for name in sorted(old):
        left, right = old[name].read_bytes(), new[name].read_bytes()
        if left == right:
            continue
        if name not in CONTEXT_REPAIR_AST:
            raise ValueError('Uncertified context repair runtime change: ' + name)
        normalized = []
        for side, data in [('before', left), ('after', right)]:
            found = set()
            class Reviewed(ast.NodeTransformer):
                def __init__(self): self.scope = []
                def visit_ClassDef(self, node):
                    self.scope.append(node.name); self.generic_visit(node); self.scope.pop(); return node
                def visit_FunctionDef(self, node):
                    qualified = '.'.join([*self.scope, node.name])
                    if qualified in CONTEXT_REPAIR_AST[name]:
                        expected = CONTEXT_REPAIR_AST[name][qualified][side]
                        actual = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                        if actual != expected:
                            raise ValueError('Context producer differs from exact reviewed AST: ' + qualified)
                        found.add(qualified); return None
                    return self.generic_visit(node)
            tree = Reviewed().visit(ast.parse(data))
            expected = {key for key, value in CONTEXT_REPAIR_AST[name].items() if value[side] is not None}
            if found != expected:
                raise ValueError('Context reviewed function inventory differs')
            normalized.append(ast.dump(tree, include_attributes=False))
        if normalized[0] != normalized[1]:
            raise ValueError('Context repair changed another producer in ' + name)
        changed[name] = dict(before=hashlib.sha256(left).hexdigest(), after=hashlib.sha256(right).hexdigest())
    if set(changed) != set(CONTEXT_REPAIR_AST) | set(CONTEXT_REPAIR_NEW_FILES) or _project_processing_digest(old_root) != CONTEXT_SOURCE_PROCESSING:
        raise ValueError('Context repair requires fixed c8cd source processing and all reviewed changes')
    return dict(oldProcessing=CONTEXT_SOURCE_PROCESSING,newProcessing=_project_processing_digest(new_root),
        changedFiles=changed,repair='exact-native-context-unit-stream')


def verify_context_paid_inputs(request, inventory):
    """Prove every successful c8cd input and ordered context under the repaired owner."""
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest,stable_digest
    from semantica.semantic_publication_builder import (_read_source_projection_text,_window_grounding_context,_extraction_context_batches,_input_token_budget,_project_processing_digest)
    from semantica.semantic_source_artifact import _load_parsed_source,_window_native_ranges
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    expected = CONTEXT_PAID_INVENTORY_SHA256
    if hashlib.sha256(inventory.read_bytes()).hexdigest() != expected:
        raise ValueError("Original paid context inventory changed")
    counts=dict(entities=0,relations=0,embeddings=0,vectors=0,windows=0)
    current_source=None;previous_binding=None;context_proof=None
    hasher=hashlib.sha256()
    with inventory.open() as stream:
     for line in stream:
      item=json.loads(line)
      if item['kind']=='identity':
       if item['requestDigest']!=stable_digest(request.model_dump(mode='json',by_alias=True)):raise ValueError('Fixed request differs')
       continue
      binding=item['binding'];source_id=binding['source']
      if source_id!=current_source:
       source=next(s for s in request.sources if s.source_id==source_id)
       ref=next(r for r in request.parsed_sources if r.source_id==source_id)
       parsed=_load_parsed_source(source,ref,source_id in request.recipe.force_ocr_source_ids,request.document_processing.model_dump(mode='json',by_alias=True))
       current_source=source_id;previous_binding=None
      if item['kind']=='embedding':
       start,end=binding['ranges'][0]
       text=_read_source_projection_text(parsed.reader,start,end)
       if stable_digest([text])!=binding['input_digest'] or SQLiteVecStore.embedding_operation_id(binding)!=item['operation']:raise ValueError('Paid vector input changed')
       counts['embeddings']+=1;counts['vectors']+=item['count']
      else:
       if previous_binding!=binding:
        start,end=binding['window_start'],binding['window_end']
        text=_read_source_projection_text(parsed.reader,start,end)
        ranges=_window_native_ranges(parsed.native_ranges,start,end)
        if stable_digest(text)!=item['inputDigest'] or stable_digest(ranges)!=item['rangesDigest']:raise ValueError('Paid extraction input/ranges changed')
        context=_window_grounding_context(parsed.locations,start,end)
        context_proof=None
        for batch in _extraction_context_batches(text,context,_input_token_budget(request.relays['model'])):
         grounding=stable_digest(dict(context=batch,formula=source_id in getattr(request.recipe,'formula_semantics_source_ids',()),nativeScalarRecipe='reader-scalar-structural-proof',ranges=ranges))
         if grounding==binding['grounding']:
          context_proof=stable_digest(batch);break
        if context_proof!=item['contextDigest']:raise ValueError('Paid exact context content/order changed '+source_id+':'+str(start))
        previous_binding=binding;counts['windows']+=1
       elif context_proof!=item['contextDigest']:raise ValueError('Paid shared context proof differs')
       counts[item['kind']]+=1
      hasher.update(line.encode())
    expected_counts=dict(entities=875,relations=707,embeddings=830,vectors=830,windows=875)
    if counts!=expected_counts:raise ValueError('Incomplete paid proof '+str(counts))
    return dict(originalInventorySHA256=expected,checkedRecordsDigest=hasher.hexdigest(),counts=counts,allExact=True)


def certify_span_repair(old_root, new_root):
    from semantica.semantic_publication_builder import _project_processing_digest
    files = lambda root: {p.relative_to(root).as_posix(): p for p in root.rglob('*.py')
                          if '__pycache__' not in p.parts}
    old, new = files(old_root), files(new_root)
    if old.keys() != new.keys():
        raise ValueError('Span repair runtime inventory differs')
    changed = {}
    for name in sorted(old):
        left, right = old[name].read_bytes(), new[name].read_bytes()
        if left == right:
            continue
        if name != 'semantic_extract/methods.py':
            raise ValueError('Uncertified span repair runtime change: ' + name)
        trees = []
        for side, data in [('before', left), ('after', right)]:
            tree = ast.parse(data)
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name == 'extract_entities_llm']
            if len(functions) != 1 or hashlib.sha256(ast.dump(functions[0], include_attributes=False).encode()).hexdigest() != SPAN_REPAIR_AST[side]:
                raise ValueError('Span producer differs from exact reviewed AST')
            tree.body.remove(functions[0]); trees.append(ast.dump(tree, include_attributes=False))
        if trees[0] != trees[1]:
            raise ValueError('Span repair changed another producer')
        changed[name] = {'before': hashlib.sha256(left).hexdigest(), 'after': hashlib.sha256(right).hexdigest()}
    old_processing = _project_processing_digest(old_root)
    if old_processing != 'sha256:a0eb826dc1bd23a00f40a7ef6203a33968b2bdec9465480eb920bdafb291a4db' or not changed:
        raise ValueError('Span repair requires reviewed immutable source processing')
    return {'oldProcessing': old_processing, 'newProcessing': _project_processing_digest(new_root),
            'changedFiles': changed, 'repair': 'exact-native-entity-source-span'}


class NormalizeProjectionRead(ast.NodeTransformer):
    """Keep the producer branch of _build_source compared in full."""
    assignment = ast.dump(ast.parse(
        'read = lambda start, end: _read_source_projection_text(parsed.reader, start, end)').body[0])

    def visit_Assign(self, node):
        if ast.dump(node) == self.assignment:
            return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == 'read' and len(node.args) == 2 and not node.keywords:
            start, end = node.args
            if ast.dump(end) == ast.dump(ast.BinOp(left=start, op=ast.Add(), right=ast.Constant(1))):
                return ast.Subscript(value=ast.Name(id='text', ctx=ast.Load()), slice=start, ctx=ast.Load())
            return ast.Subscript(value=ast.Name(id='text', ctx=ast.Load()),
                slice=ast.Slice(lower=start, upper=end), ctx=ast.Load())
        return node


def certify(old_root, new_root):
    """Reject runtime changes outside hydration and the exact reviewed window ASTs."""
    from semantica.semantic_publication_builder import _project_processing_digest
    files = lambda root: {p.relative_to(root).as_posix(): p for p in root.rglob('*.py')
                           if '__pycache__' not in p.parts}
    old, new = files(old_root), files(new_root)
    old_name = 'semantic_' + 'artifact_builder.py'
    new_name = 'semantic_publication_builder.py'
    if old_name in new or (old_name in old and new_name in old):
        raise ValueError('Superseded builder module retained beside its canonical owner')
    if old_name in old:
        old[new_name] = old.pop(old_name)
    if old.keys() != new.keys():
        raise ValueError('Runtime file inventory changed outside the hydration repair')
    changed = {}
    for name in sorted(old):
        left, right = old[name].read_bytes(), new[name].read_bytes()
        if left == right:
            continue
        renamed_left = left.replace(old_name[:-3].encode(), new_name[:-3].encode())
        if renamed_left == right:
            changed[name] = {'before': hashlib.sha256(left).hexdigest(), 'after': hashlib.sha256(right).hexdigest()}
            continue
        if name not in ALLOWED:
            raise ValueError('Uncertified runtime change: ' + name)

        class RemoveHydration(ast.NodeTransformer):
            def __init__(self, side):
                self.scope = []
                self.side, self.reviewed = side, set()

            def reviewed_producer(self, node, qualified):
                if qualified not in REVIEWED_PRODUCER_AST:
                    return False
                digest = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                if digest != REVIEWED_PRODUCER_AST[qualified][self.side]:
                    raise ValueError('Producer repair differs from reviewed AST: ' + qualified)
                self.reviewed.add(qualified)
                return True

            def visit_FunctionDef(self, node):
                qualified = '.'.join([*self.scope, node.name])
                if self.reviewed_producer(node, qualified):
                    return None
                if qualified in ALLOWED[name]:
                    return None
                if qualified == '_build_source':
                    node = NormalizeProjectionRead().visit(node)
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()
                return node

            def visit_ClassDef(self, node):
                qualified = '.'.join([*self.scope, node.name])
                if self.reviewed_producer(node, qualified):
                    return None
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()
                return node

        def normalized(data, side):
            transform = RemoveHydration(side)
            result = ast.dump(transform.visit(ast.parse(data)), include_attributes=False)
            expected = {key for key, values in REVIEWED_PRODUCER_AST.items() if values[side] is not None}
            if transform.reviewed != expected:
                raise ValueError('Reviewed producer repair AST inventory differs')
            return result
        if normalized(renamed_left, 'before') != normalized(right, 'after'):
            raise ValueError('Paid producer or unapproved AST changed in ' + name)
        changed[name] = {'before': hashlib.sha256(left).hexdigest(), 'after': hashlib.sha256(right).hexdigest()}
    if not changed:
        raise ValueError('No hydration repair to certify')
    return {'oldProcessing': _project_processing_digest(old_root),
            'newProcessing': _project_processing_digest(new_root), 'changedFiles': changed}


def source_recipe(request, processing):
    from semantica.semantic_publication_builder import EXTRACTION_CONTRACT_VERSION, stable_digest
    relay = request.relays['model']
    return stable_digest({'recipe': request.recipe.lineage_payload(), 'processing': processing,
        'generationBinding': relay.binding_id, 'contextWindowTokens': relay.context_window_tokens,
        'maxOutputTokens': relay.max_output_tokens, 'contract': EXTRACTION_CONTRACT_VERSION})


def source_bindings(store, project, source, recipe):
    """Cursor only this project's admitted source/recipe, at most 128 operations."""
    from semantica.triplet_store.extraction_records import BINDING, ExtractionRecords, F
    ox = store._oxigraph
    graph = ox.NamedNode('urn:semantica:project:' + hashlib.sha256(project.encode()).hexdigest())
    after = ''
    while True:
        query = f'''SELECT ?op WHERE {{ GRAPH {graph} {{
            ?op <{F}bindingSource> {ox.Literal(source)} ; <{F}bindingRecipe> {ox.Literal(recipe)} .
            FILTER(STR(?op) > {ox.Literal(after)}) }} }} ORDER BY STR(?op) LIMIT 128'''
        page = list(store.store.query(query))
        for row in page:
            operation = row['op'].value
            dummy = object.__new__(ExtractionRecords)
            dummy.owner, dummy.ox, dummy.graph = store, ox, graph
            binding = {key: dummy.one(row['op'], 'binding' + key[0].upper() + key[1:]) for key in BINDING}
            if binding['project'] != project or binding['source'] != source or binding['recipe'] != recipe:
                raise ValueError('Extraction operation escaped admitted source scope')
            if operation == store.extraction_operation_id(binding, 'entities'):
                yield binding
            after = operation
        if len(page) < 128:
            return


def validate_embedding_target(request, target, certificate=None):
    """Generation changes cannot authorize reuse of a different embedding input."""
    before = request.model_dump(mode='json', by_alias=True).get('release')
    after = target.model_dump(mode='json', by_alias=True).get('release')
    if before != after and (not certificate or before != certificate.get('sourceRelease')
                            or after != certificate.get('targetRelease')):
        raise ValueError('Generation-only adoption requires certified artifact releases and identical embedding inputs')
    def comparable(value):
        data = copy.deepcopy(value.model_dump(mode='json', by_alias=True))
        data.pop('outputDir', None)
        data.pop('release', None)
        reports = data.get('organizationReports', {})
        for field in ('recipeDigest', 'baseUrl'):
            reports.pop(field, None)
        for field in ('bindingId', 'modelId', 'contextWindowTokens', 'maxOutputTokens', 'baseUrl'):
            data['relays']['model'].pop(field, None)
        data['relays']['embedding'].pop('baseUrl', None)
        return data
    if comparable(request) != comparable(target):
        raise ValueError('Generation-only adoption requires identical immutable embedding inputs')


def certify_target_release(request, target, runtime_root, *, span_repair=False, context_repair=False, cache_repair=False):
    """Bind the one known source release to the actual installed target inventory."""
    source = request.model_dump(mode='json', by_alias=True)['release']
    expected = {
        'artifactDigest': ('sha256:18e9697019c7ba57f22f487332c60815aec62ab0e6c32c49989cbb992011b108' if cache_repair else 'sha256:c8cd9c16e9f91564b7517709d3f47e6c4921a3be7bbca6849751f35ceae860bf' if context_repair else 'sha256:a4d7ba97f885e1766a75bb2705a11000516a379a57072ec421578f020869373d'
            if span_repair else 'sha256:53739bc58a99e8b153429636d1eeff9603847b6755479d60107a38533bb7064f'),
        'schemaDigest': 'sha256:d8f3bd61820b2df90c476e2cdef2ba74d3aa07f31064575d79480a1c82db286f',
        'mediaTypes': {'document-representation': 'application/vnd.semantica.document-representation+json'},
    }
    if source != expected:
        raise ValueError('Source request release is not the reviewed immutable source artifact')
    bundle = runtime_root.parents[4]
    manifest = json.loads((bundle / 'manifest.json').read_text())
    declared = manifest['files']
    if len({item['path'] for item in declared}) != len(declared):
        raise ValueError('Duplicate target artifact inventory')
    descriptor = [manifest['protocol'], manifest['schemaDigest'], manifest.get('documentParserDigest'),
        manifest['pythonPath'], [manifest['worker']['path'], manifest['worker'].get('args', [])],
        [manifest['queryWorker']['path'], manifest['queryWorker'].get('args', [])],
        sorted([list(item) for item in manifest['mediaTypes'].items()]),
        sorted([[item['path'], item['size'], item['sha256']] for item in declared])]
    digest = 'sha256:' + hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    release = {key: manifest[key] for key in ('artifactDigest', 'schemaDigest', 'mediaTypes')}
    if digest != manifest['artifactDigest'] or release != target.model_dump(mode='json', by_alias=True)['release']:
        raise ValueError('Target request release does not match installed artifact descriptor')
    prefix = runtime_root.relative_to(bundle).as_posix() + '/'
    inventory = {item['path']: item for item in declared if item['path'].startswith(prefix) and item['path'].endswith('.py')}
    actual = {path.relative_to(bundle).as_posix(): path for path in runtime_root.rglob('*.py') if '__pycache__' not in path.parts}
    if inventory.keys() != actual.keys():
        raise ValueError('Target runtime inventory differs from its artifact manifest')
    for name, path in actual.items():
        value = path.read_bytes()
        if len(value) != inventory[name]['size'] or 'sha256:' + hashlib.sha256(value).hexdigest() != inventory[name]['sha256']:
            raise ValueError('Target runtime bytes differ from artifact manifest: ' + name)
    return {'sourceRelease': source, 'targetRelease': release}


def adopt(request, certificate, *, apply=False, embedding_target_request=None):
    from semantica.semantic_publication_builder import stable_digest, _source_windows
    from semantica.semantic_source_artifact import _load_parsed_source, _window_native_ranges
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    from semantica.source import source_processing_revision

    store_path, cache_path = Path(request.native_store_dir), Path(request.native_cache_dir) / 'accepted.sqlite'
    if not store_path.is_dir() or not cache_path.is_file():
        raise ValueError('Maintenance requires existing native owners')
    if embedding_target_request is not None:
        validate_embedding_target(request, embedding_target_request, certificate)
    old_recipe = source_recipe(request, certificate['oldProcessing'])
    new_recipe = source_recipe(embedding_target_request or request, certificate['newProcessing'])
    report = {'certificate': certificate, 'project': request.project_id, 'apply': apply,
              'requestDigest': stable_digest(request.model_dump(mode='json', by_alias=True)),
              'extractions': 0, 'embeddings': 0, 'embeddingVectors': 0,
              'missingEmbeddings': 0, 'sources': []}
    if embedding_target_request is not None:
        report['embeddingTargetRequestDigest'] = stable_digest(
            embedding_target_request.model_dump(mode='json', by_alias=True))
    old_vector_count = None
    # The dry run does not open the SQLite acceptance owner for writing.
    backend = SqliteCacheBackend(str(cache_path)) if apply else None
    cache = ExtractionCache(backend=backend, ttl=None) if apply else None
    store = OxigraphStore(str(store_path))
    acceptance = sqlite3.connect(cache_path.as_uri() + '?mode=ro', uri=True)
    key_owner = ExtractionCache()

    def verify_accepted(namespace, text, digest, **params):
        key = key_owner._generate_key(text, **params)
        row = acceptance.execute('SELECT digest FROM accepted_receipts WHERE namespace=? AND key=?',
                                 (namespace, key)).fetchone()
        if row != (digest,):
            raise ValueError('Source native result lacks its matching paid acceptance receipt')
    try:
        refs = {ref.source_id: ref for ref in request.parsed_sources}
        for source in request.sources:
            counts = dict(source=source.source_id, extractions=0, embeddings=0, missingEmbeddings=0)
            report['sources'].append(counts)
            parsed = _load_parsed_source(source, refs[source.source_id],
                source.source_id in request.recipe.force_ocr_source_ids,
                request.document_processing.model_dump(mode='json', by_alias=True))
            bindings = (() if embedding_target_request is not None else
                source_bindings(store, request.project_id, source.source_id, old_recipe))
            for binding in bindings:
                start, end = binding['window_start'], binding['window_end']
                text = parsed.text[start:end]
                ranges = _window_native_ranges(parsed.native_ranges, start, end)
                target = {**binding, 'recipe': new_recipe}
                entities = store.read_extraction(binding, 'entities', text=text, native_ranges=ranges,
                                                  extraction_spec=request.recipe.extraction_spec)
                for stage in ('entities', 'relations'):
                    receipt = store.extraction_receipt(binding, stage)
                    if receipt is None:
                        continue
                    verify_accepted(stage, text, receipt['accepted_digest'],
                        native_operation=store.extraction_operation_id(binding, stage))
                    values = entities if stage == 'entities' else store.read_extraction(
                        binding, stage, text=text, native_ranges=ranges, entities=entities,
                        extraction_spec=request.recipe.extraction_spec)
                    receipts = store.read_extraction_receipts(binding, stage)
                    if apply:
                        params = {'native_operation': store.extraction_operation_id(target, stage)}
                        existing = store.extraction_receipt(target, stage)
                        if existing is None:
                            envelope = {'values': values, 'receipts': receipts}
                            digest = cache.accept(stage, text, envelope, **params)
                            store.adopt_extraction(target, stage, values, text=text, native_ranges=ranges,
                                accepted_digest=digest, receipts=receipts,
                                extraction_spec=request.recipe.extraction_spec)
                            cache.release_accepted(stage, text, digest, **params)
                        else:
                            if cache.accepted_digest(stage, text, **params) != existing['accepted_digest']:
                                raise ValueError('Existing target acceptance differs')
                            store.read_extraction(target, stage, text=text, native_ranges=ranges,
                                entities=entities, extraction_spec=request.recipe.extraction_spec)
                    report['extractions'] += 1
                    counts['extractions'] += 1
            relay = request.relays['embedding']
            spaces = [{'binding': stable_digest({'binding': relay.binding_id, 'model': relay.model_id, 'recipe': recipe}),
                       'model': relay.model_id, 'recipe': recipe} for recipe in (old_recipe, new_recipe)]
            paths = [store_path.parent / ('embedding-' + space['binding'].removeprefix('sha256:') + '.sqlite') for space in spaces]
            old_owner = SQLiteVecStore.open_embedding_space(str(paths[0]), spaces[0])
            if old_owner is None:
                continue
            count = old_owner.count()
            if old_vector_count is not None and count != old_vector_count:
                raise ValueError('Source vector owner changed during stopped-project maintenance')
            old_vector_count = count
            new_owner = None
            try:
                # Use the same producer iterator as the current build; paid
                # identities are never invented by a maintenance-only reader.
                for start, end, text in _source_windows(parsed):
                    binding = dict(project=request.project_id, source=source.source_id,
                        material=source.material_revision, representation=refs[source.source_id].representation_revision,
                        recipe=old_recipe, parser=source_processing_revision(
                            Path(source.file_path), name=source.name, mime_type=source.mime_type,
                            force_ocr=source.source_id in request.recipe.force_ocr_source_ids,
                            document_processing=request.document_processing.model_dump(mode='json', by_alias=True)),
                        model=relay.model_id, space=spaces[0]['binding'], ranges=[[start, end]], input_digest=stable_digest([text]))
                    result = old_owner.read_embedding(binding)
                    if result is None:
                        report['missingEmbeddings'] += 1
                        counts['missingEmbeddings'] += 1
                        continue
                    verify_accepted('embedding', SQLiteVecStore.embedding_operation_id(binding), result['accepted_digest'])
                    target = {**binding, 'recipe': new_recipe, 'space': spaces[1]['binding']}
                    if apply:
                        if new_owner is None:
                            new_owner = SQLiteVecStore.open_embedding_space(str(paths[1]), spaces[1], old_owner.dimension)
                        key = SQLiteVecStore.embedding_operation_id(target)
                        existing = new_owner.read_embedding(target)
                        if existing is None:
                            pending = {'vectors': result['vectors'], 'receipt': result['receipt']}
                            digest = cache.accept('embedding', key, pending)
                            new_owner.adopt_embedding(target, pending['vectors'], pending['receipt'], accepted_digest=digest)
                            cache.release_accepted('embedding', key, digest)
                        adopted = new_owner.read_embedding(target)
                        if (adopted is None or cache.accepted_digest('embedding', key) != adopted['accepted_digest']
                                or adopted['vectors'] != result['vectors'] or adopted['receipt'] != result['receipt']):
                            raise ValueError('Target vector values, model receipt or acceptance differ from paid source')
                    report['embeddings'] += 1
                    report['embeddingVectors'] += len(result['vectors'])
                    counts['embeddings'] += 1
            finally:
                old_owner.close()
                if new_owner is not None:
                    new_owner.close()
    finally:
        acceptance.close()
        store.close()
        if backend is not None:
            backend.close()
    if old_vector_count is not None and report['embeddingVectors'] != old_vector_count:
        raise ValueError('Current producer addresses do not preserve every existing paid vector')
    return report


def main():
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, stable_digest
    import semantica
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--apply-certificate', type=Path)
    parser.add_argument('--embedding-target-request', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--span-repair', action='store_true')
    mode.add_argument('--context-repair-inventory', type=Path)
    mode.add_argument('--cache-owner-repair-inventory', type=Path)
    args = parser.parse_args()
    runtime = Path(semantica.__file__).resolve().parent
    certificate = (certify_cache_owner_repair if args.cache_owner_repair_inventory else certify_context_repair if args.context_repair_inventory else certify_span_repair if args.span_repair else certify)(args.old_root.resolve(), runtime)
    request = SemanticArtifactBuildRequest.model_validate_json(args.request.read_text())
    if args.context_repair_inventory:
        certificate['paidInputs'] = verify_context_paid_inputs(request, args.context_repair_inventory)
    if args.cache_owner_repair_inventory:
        certificate['paidInputs'] = verify_cache_paid_inputs(request, args.cache_owner_repair_inventory)
    if args.span_repair or args.context_repair_inventory or args.cache_owner_repair_inventory:
        if args.embedding_target_request:
            raise ValueError('Span repair requires full adoption of successful native results')
        target_release = json.loads((runtime.parents[4]/'manifest.json').read_text())
        target_request = request.model_copy(update={'release': request.release.model_copy(update={
            key: target_release[alias] for key, alias in [('artifact_digest', 'artifactDigest'), ('schema_digest', 'schemaDigest'), ('media_types', 'mediaTypes')]
        })})
        certificate.update(certify_target_release(request, target_request, runtime, span_repair=args.span_repair, context_repair=bool(args.context_repair_inventory), cache_repair=bool(args.cache_owner_repair_inventory)))
    target = (SemanticArtifactBuildRequest.model_validate_json(args.embedding_target_request.read_text())
              if args.embedding_target_request else None)
    if target is not None:
        certificate.update(certify_target_release(request, target, Path(semantica.__file__).resolve().parent))
        validate_embedding_target(request, target, certificate)
    target_digest = stable_digest(target.model_dump(mode='json', by_alias=True)) if target is not None else None
    if args.apply_certificate:
        prior = json.loads(args.apply_certificate.read_text())
        if prior.get('apply') is not False or prior.get('project') != request.project_id or prior.get('certificate') != certificate or prior.get('requestDigest') != stable_digest(request.model_dump(mode='json', by_alias=True)) or prior.get('embeddingTargetRequestDigest') != target_digest:
            raise ValueError('Apply requires the matching successful dry-run certificate')
    result = adopt(request, certificate, apply=args.apply_certificate is not None, embedding_target_request=target)
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
