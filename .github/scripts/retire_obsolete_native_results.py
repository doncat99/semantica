"""Offline retirement of explicitly named obsolete recipes; never a runtime reader.

Stop the project worker first. Dry-run builds a disk-backed deletion certificate.
Apply repeats admission against the unchanged native owners before any deletion.
Original materials and audit certificate are never cleanup targets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import unquote


def digest_rows(db):
    digest = hashlib.sha256()
    for table in ('operations', 'nodes', 'graphs', 'cache_keys', 'spaces', 'vector_audit', 'node_proofs', 'pending_audit', 'inventory', 'protected_receipts'):
        for row in db.execute('SELECT * FROM ' + table + ' ORDER BY 1,2'):
            digest.update(json.dumps([table, row], ensure_ascii=False, separators=(',', ':')).encode())
    return digest.hexdigest()


def create_plan(path):
    if path.exists():
        raise ValueError('Certificate path must be new')
    db = sqlite3.connect(path)
    path.chmod(0o600)
    db.executescript('''
      CREATE TABLE operations(id TEXT PRIMARY KEY,recipe TEXT,binding TEXT,receipt TEXT,model_receipts TEXT);
      CREATE TABLE nodes(id TEXT,graph TEXT,PRIMARY KEY(id,graph));
      CREATE TABLE graphs(id TEXT PRIMARY KEY,kind TEXT);
      CREATE TABLE cache_keys(namespace TEXT,key TEXT,digest TEXT,PRIMARY KEY(namespace,key));
      CREATE TABLE spaces(path TEXT PRIMARY KEY,identity TEXT,operations INTEGER,vectors INTEGER,receipt_digest TEXT);
      CREATE TABLE vector_audit(space TEXT,operation TEXT,receipt TEXT,accepted_digest TEXT,PRIMARY KEY(space,operation));
      CREATE TABLE pending_audit(namespace TEXT,key TEXT,binding TEXT,input_digest TEXT,digest TEXT,model_receipts TEXT,PRIMARY KEY(namespace,key));
      CREATE TABLE node_proofs(id TEXT,graph TEXT,digest TEXT,count INTEGER,PRIMARY KEY(id,graph));
      CREATE TABLE inventory(kind TEXT,id TEXT,disposition TEXT,digest TEXT,PRIMARY KEY(kind,id));
      CREATE TABLE protected_receipts(receipt_id TEXT,operation TEXT,recipe TEXT,space TEXT,source TEXT,receipt_digest TEXT,PRIMARY KEY(receipt_id,operation));
    ''')
    return db


def inventory_all(owner, plan, accepted, root, project, protected, obsolete, read_text, *, resume=False, current_space=None):
    """Classify the complete project owners before admitting any destructive write.

    Maintenance traversal is incremental; membership and certificates live on disk.
    Unknown results are blockers, never inferred obsolete from age or mismatch.
    Resume permits only disappearance of certified obsolete identities.
    """
    from semantica.triplet_store.extraction_records import ExtractionRecords, BINDING, F, operation_identity
    from semantica.triplet_store.classification_records import ClassificationRecords, BINDING as CB
    from semantica.semantic_extract.cache import ExtractionCache, NAMESPACES
    if protected & obsolete:
        raise ValueError('Protected recipe cannot be obsolete')
    ox = owner._oxigraph
    suffix = hashlib.sha256(project.encode()).hexdigest()
    facts = ox.NamedNode('urn:semantica:project:' + suffix)
    publication = 'urn:semantica:publication:' + suffix
    keys = ExtractionCache()
    def disposition(recipe):
        if recipe in protected:
            return 'protected'
        if recipe in obsolete:
            return 'obsolete'
        raise ValueError('Unknown native recipe: ' + str(recipe))
    def encoded(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    with tempfile.TemporaryDirectory(prefix='semantica-retirement-inventory-') as scratch:
        db = sqlite3.connect(Path(scratch)/'inventory.sqlite')
        try:
            db.executescript('''
              PRAGMA cache_size=-4096;
              CREATE TABLE inventory(kind,id,disposition,digest,PRIMARY KEY(kind,id));
              CREATE TABLE nodes(id TEXT PRIMARY KEY,disposition TEXT);
              CREATE TABLE graph_owners(id TEXT PRIMARY KEY,disposition TEXT);
              CREATE TABLE verified_projection(id TEXT,graph TEXT,PRIMARY KEY(id,graph));
              CREATE TABLE acceptance(namespace,key,disposition,digest,PRIMARY KEY(namespace,key));
              CREATE TABLE protected_receipts(receipt_id,operation,recipe,space,source,receipt_digest,PRIMARY KEY(receipt_id,operation));
            ''')
            def add(kind, identity, state, value):
                digest = hashlib.sha256(encoded(value).encode()).hexdigest()
                db.execute('INSERT INTO inventory VALUES(?,?,?,?)', (kind, identity, state, digest))
            def accept(namespace, key, state, digest):
                prior = db.execute('SELECT disposition,digest FROM acceptance WHERE namespace=? AND key=?', (namespace,key)).fetchone()
                if prior is not None and prior != (state,digest):
                    raise ValueError('Acceptance has conflicting native owners')
                db.execute('INSERT OR IGNORE INTO acceptance VALUES(?,?,?,?)', (namespace,key,state,digest))
            def protect_receipt(receipt, operation, recipe, space='', source=''):
                if not isinstance(receipt.get('id'),str) or not receipt['id']:
                    raise ValueError('Protected model receipt identity missing')
                digest = hashlib.sha256(encoded(receipt).encode()).hexdigest()
                row = (receipt['id'],operation,recipe,space,source,digest)
                db.execute('INSERT INTO protected_receipts VALUES(?,?,?,?,?,?)',row)
            after = ''
            while True:
                rows = list(owner.store.query(f'''SELECT ?op ?recipe WHERE {{ GRAPH {facts} {{
                    ?op <{F}bindingRecipe> ?recipe . FILTER(STR(?op) > {ox.Literal(after)})
                    }} }} ORDER BY STR(?op) LIMIT 128'''))
                for row in rows:
                    op = row['op']; after = op.value
                    state = disposition(row['recipe'].value)
                    codec = object.__new__(ExtractionRecords)
                    codec.owner, codec.ox, codec.graph = owner, ox, facts
                    classification = op.value.startswith('urn:semantica:classification:')
                    binding = {field: codec.one(op, 'binding'+field[0].upper()+field[1:]) for field in (CB if classification else BINDING)}
                    if binding['project'] != project:
                        raise ValueError('Foreign operation inside project facts')
                    if classification:
                        records = ClassificationRecords(owner, binding); stage = 'classification'
                    else:
                        stage = next((stage for stage in ('entities','relations') if operation_identity(binding,stage) == op.value), None)
                        if stage is None:
                            raise ValueError('Unclassified native operation')
                        records = ExtractionRecords(owner,binding,stage)
                    if records.operation != op or records.receipt() is None:
                        raise ValueError('Native operation identity or receipt differs')
                    receipt = records.receipt()
                    model_receipts = records.read_receipts()
                    add('operation',op.value,state,[binding,receipt,model_receipts])
                    if state=='protected':
                        for model_receipt in model_receipts:
                            protect_receipt(model_receipt,op.value,binding['recipe'],source=binding['source'])
                    for node in (op, *records.values(op,'ownedRecord')):
                        db.execute('INSERT INTO nodes VALUES(?,?)', (node.value,state))
                        add('fact-node',node.value,state,node_proof(owner,node.value,facts.value))
                    reduction = records.one(op,'classificationReduction',optional=True) if classification else None
                    if not reduction:
                        text = binding['context_digest'] if classification else read_text(binding)
                        accept(stage,keys._generate_key(text,native_operation=op.value),state,receipt['accepted_digest'])
                    if not classification:
                        for tail in (':identity-projection',':fact-projection'):
                            db.execute('INSERT INTO graph_owners VALUES(?,?)', (op.value+tail,state))
                db.commit()
                if len(rows)<128:
                    break
            # Graph ownership is exact. Stream every quad, including default/foreign graphs.
            for graph in owner.store.named_graphs():
                name = getattr(graph,'value','')
                if name in (facts.value,publication):
                    state = 'protected'
                else:
                    found = db.execute('SELECT disposition FROM graph_owners WHERE id=?',(name,)).fetchone()
                    if found is None and resume and plan.execute('SELECT 1 FROM graphs WHERE id=?',(name,)).fetchone():
                        found = ('obsolete',)
                    if found is None:
                        raise ValueError('Unclassified native graph: '+name)
                    state = found[0]
                total = count = 0
                for quad in owner.store.quads_for_pattern(None,None,None,graph):
                    subject = getattr(quad.subject,'value','')
                    if name == facts.value and db.execute('SELECT 1 FROM nodes WHERE id=?',(subject,)).fetchone() is None:
                        proof = plan.execute('SELECT digest,count FROM node_proofs WHERE id=? AND graph=?',(subject,name)).fetchone() if resume else None
                        prior = plan.execute("SELECT 1 FROM inventory WHERE kind='fact-node' AND id=? AND disposition='obsolete'",(subject,)).fetchone() if resume else None
                        if proof is None or prior is None or node_proof(owner,subject,name)!=proof:
                            raise ValueError('Unclassified project fact subject')
                        db.execute('INSERT INTO nodes VALUES(?,?)',(subject,'obsolete'))
                        add('fact-node',subject,'obsolete',proof)
                    if state=='obsolete' and resume and db.execute('SELECT 1 FROM verified_projection WHERE id=? AND graph=?',(subject,name)).fetchone() is None:
                        proof = plan.execute('SELECT digest,count FROM node_proofs WHERE id=? AND graph=?',(subject,name)).fetchone()
                        if proof is None or node_proof(owner,subject,name)!=proof:
                            raise ValueError('Obsolete projection subject changed after certification')
                        db.execute('INSERT INTO verified_projection VALUES(?,?)',(subject,name))
                    total = (total + int.from_bytes(hashlib.sha256(str(quad).encode()).digest(),'big')) % (1<<256)
                    count += 1
                # Project facts contain both classes; per-operation ownership above and
                # obsolete subject proofs protect their exact deletion closure.
                add('graph',name,state,[count,format(total,'064x')])
            if next(owner.store.quads_for_pattern(None,None,None,ox.DefaultGraph()),None) is not None:
                raise ValueError('Unclassified native graph: default')
            with os.scandir(root) as entries:
                for entry in entries:
                    if not entry.name.startswith('embedding-') or not entry.name.endswith('.sqlite'):
                        continue
                    path = Path(entry.path)
                    if path.is_symlink() or path.resolve().parent != root.resolve():
                        raise ValueError('Vector owner escapes admitted native root')
                    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
                    try:
                        row = conn.execute('SELECT identity,dimension FROM embedding_space WHERE id=1').fetchone()
                        identity = json.loads(row[0]); state = disposition(identity['recipe'])
                        if set(identity)!={'binding','model','recipe'} or type(row[1]) is not int or not 1<=row[1]<=8192:
                            raise ValueError('Vector space identity or dimension invalid')
                        if state=='protected' and identity!=current_space:
                            raise ValueError('Unclassified current-recipe vector space')
                        if path.name != 'embedding-'+identity['binding'].removeprefix('sha256:')+'.sqlite':
                            raise ValueError('Space filename and identity differ')
                        add('space',str(path),state,row)
                        for operation,count,digest,receipt,receipt_digest,acceptance in conn.execute('SELECT id,count,digest,receipt,receipt_digest,accepted_digest FROM embeddings_embedding_operations ORDER BY id'):
                            if hashlib.sha256(receipt.encode()).hexdigest()!=receipt_digest:
                                raise ValueError('Vector model receipt digest differs')
                            add('vector-operation',encoded([str(path),operation]),state,[count,digest,receipt_digest,acceptance])
                            accept('embedding',keys._generate_key(operation),state,acceptance)
                            if state=='protected':
                                protect_receipt(json.loads(receipt),operation,identity['recipe'],identity['binding'])
                    finally:
                        conn.close()
            for namespace,key,digest in plan.execute('SELECT * FROM cache_keys'):
                accept(namespace,key,'obsolete',digest)
            for namespace,key,digest in accepted.execute('SELECT namespace,key,digest FROM accepted_receipts ORDER BY namespace,key'):
                match = db.execute('SELECT disposition,digest FROM acceptance WHERE namespace=? AND key=?',(namespace,key)).fetchone()
                if namespace not in NAMESPACES or match is None or match[1]!=digest:
                    raise ValueError('Unclassified acceptance namespace/key or digest: '+encoded([namespace,key]))
                add('acceptance',encoded([namespace,key]),match[0],digest)
            for namespace,key in db.execute('SELECT namespace,key FROM acceptance'):
                if accepted.execute('SELECT 1 FROM accepted_receipts WHERE namespace=? AND key=?',(namespace,key)).fetchone() is None:
                    if not (resume and db.execute('SELECT disposition FROM acceptance WHERE namespace=? AND key=?',(namespace,key)).fetchone()==('obsolete',)):
                        raise ValueError('Native owner acceptance receipt missing')
            for namespace,key,body,digest in accepted.execute('SELECT namespace,key,CASE WHEN length(value)<=1048576 THEN value END,accepted_digest FROM cache ORDER BY namespace,key'):
                match = db.execute('SELECT disposition,digest FROM acceptance WHERE namespace=? AND key=?',(namespace,key)).fetchone()
                if namespace not in NAMESPACES or match is None or match[1]!=digest or body is None or hashlib.sha256(body).hexdigest()!=digest:
                    raise ValueError('Unclassified or corrupt cache body: '+encoded([namespace,key]))
                add('cache',encoded([namespace,key]),match[0],digest)
            db.commit()
            if resume:
                for kind,identity,state,digest in db.execute('SELECT * FROM inventory'):
                    prior = plan.execute('SELECT disposition,digest FROM inventory WHERE kind=? AND id=?',(kind,identity)).fetchone()
                    # Mixed facts graph changes only through certified obsolete subjects;
                    # apply_plan independently proves every surviving obsolete subject.
                    if kind=='graph' and identity==facts.value:
                        continue
                    if kind=='graph' and state=='obsolete' and prior is not None and prior[0]=='obsolete':
                        # A crash may leave a strict subset of certified projection
                        # subjects. Each surviving subject was verified above.
                        continue
                    if prior!=(state,digest):
                        raise ValueError('Inventory changed after certification: '+kind+':'+identity)
                for kind,identity,state,digest in plan.execute("SELECT * FROM inventory WHERE disposition='protected'"):
                    if kind=='graph' and identity==facts.value:
                        continue
                    if db.execute('SELECT disposition,digest FROM inventory WHERE kind=? AND id=?',(kind,identity)).fetchone()!=(state,digest):
                        raise ValueError('Protected inventory disappeared or changed')
            else:
                for row in db.execute('SELECT * FROM inventory'):
                    plan.execute('INSERT INTO inventory VALUES(?,?,?,?)',row)
                for row in db.execute('SELECT * FROM protected_receipts'):
                    plan.execute('INSERT INTO protected_receipts VALUES(?,?,?,?,?,?)',row)
                plan.commit()
        finally:
            db.close()


def add_cache_key(plan, accepted, namespace, key, digest):
    found = accepted.execute('SELECT digest FROM accepted_receipts WHERE namespace=? AND key=?', (namespace, key)).fetchone()
    if found != (digest,):
        raise ValueError('Obsolete acceptance key differs from native receipt')
    plan.execute('INSERT OR IGNORE INTO cache_keys VALUES(?,?,?)', (namespace, key, digest))


def pending_candidates(request, scope):
    """Reconstruct keys from the producer's canonical windows, not cache contents."""
    from semantica.semantic_publication_builder import (_source_windows, _window_grounding_context,
        _extraction_context_batches, _input_token_budget, stable_digest)
    from semantica.semantic_source_artifact import _load_parsed_source, _window_native_ranges
    from semantica.source import source_processing_revision
    from semantica.triplet_store.extraction_records import operation_identity
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    from semantica.semantic_extract.cache import ExtractionCache
    source = next(source for source in request.sources if source.source_id == scope['source'])
    ref = next(ref for ref in request.parsed_sources if ref.source_id == scope['source'])
    force = source.source_id in request.recipe.force_ocr_source_ids
    parsed = _load_parsed_source(source, ref, force, request.document_processing.model_dump(mode='json', by_alias=True))
    base = dict(project=request.project_id, source=source.source_id, material=source.material_revision,
        representation=ref.representation_revision, recipe=scope['recipe'], parser=source_processing_revision(
            Path(source.file_path), name=source.name, mime_type=source.mime_type, force_ocr=force,
            document_processing=request.document_processing.model_dump(mode='json', by_alias=True)))
    keys = ExtractionCache()
    for start, end, text in _source_windows(parsed):
        if scope.get('window') is not None and [start, end] != scope['window']:
            continue
        if scope['namespace'] == 'embedding':
            relay = request.relays['embedding']
            binding = dict(base, model=relay.model_id, space=stable_digest(dict(
                binding=relay.binding_id, model=relay.model_id, recipe=scope['recipe'])),
                ranges=[[start, end]], input_digest=stable_digest([text]))
            yield keys._generate_key(SQLiteVecStore.embedding_operation_id(binding)), binding, stable_digest(text)
        else:
            relay = request.relays['model']
            context = _window_grounding_context(parsed.locations, start, end)
            for batch in _extraction_context_batches(text, context, _input_token_budget(relay)):
                binding = dict(base, model=relay.model_id,
                    specification=request.recipe.extraction_spec.digest if request.recipe.extraction_spec else 'none',
                    window_start=start, window_end=end, grounding=stable_digest(dict(context=batch,
                        formula=source.source_id in getattr(request.recipe, 'formula_semantics_source_ids', ()),
                        nativeScalarRecipe='reader-scalar-structural-proof',
                        ranges=_window_native_ranges(parsed.native_ranges, start, end))))
                yield keys._generate_key(text, native_operation=operation_identity(binding, 'entities')), binding, stable_digest(text)


def plan_pending(plan, accepted, scopes, recipes, current_recipe, candidates):
    """Admit only explicit obsolete canonical keys and keep original model audit."""
    for scope in scopes:
        if (scope.get('recipe') not in recipes or scope['recipe'] == current_recipe
                or scope.get('namespace') not in ('entities', 'embedding')
                or type(scope.get('count')) is not int or not 0 < scope['count'] <= 4096):
            raise ValueError('Pending scope must name obsolete recipe, source, namespace and bounded exact count')
        found = 0
        for key, binding, input_digest in candidates(scope):
            namespace = scope['namespace']
            if binding['recipe'] != scope['recipe'] or binding['source'] != scope['source']:
                raise ValueError('Pending candidate escaped explicit scope')
            row = accepted.execute('SELECT CASE WHEN length(value)<=1048576 THEN value END,accepted_digest FROM cache WHERE namespace=? AND key=? AND accepted_digest IS NOT NULL', (namespace, key)).fetchone()
            if row is None:
                continue
            blob, digest = row
            if blob is None or hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError('Pending accepted body digest or byte budget differs')
            if plan.execute('SELECT 1 FROM cache_keys WHERE namespace=? AND key=?', (namespace, key)).fetchone():
                raise ValueError('Pending candidate duplicates an admitted native owner or scope')
            value = json.loads(blob)
            audit = value.get('receipts') if namespace == 'entities' else value.get('receipt')
            if not audit or (namespace == 'entities' and not isinstance(audit, list)):
                raise ValueError('Pending original model audit missing')
            add_cache_key(plan, accepted, namespace, key, digest)
            plan.execute('INSERT INTO pending_audit VALUES(?,?,?,?,?,?)', (namespace,key,
                json.dumps(binding,sort_keys=True), input_digest,digest,json.dumps(audit,sort_keys=True)))
            found += 1
        if found != scope['count']:
            raise ValueError('Pending exact count differs from canonical attribution')
    plan.commit()


def verify_pending(plan, accepted, *, resume=False):
    for namespace, key, _, _, digest, _ in plan.execute('SELECT * FROM pending_audit'):
        row = accepted.execute('SELECT CASE WHEN length(value)<=1048576 THEN value END,accepted_digest FROM cache WHERE namespace=? AND key=?', (namespace,key)).fetchone()
        if row is None and resume:
            # Both the body and receipt must be absent after an atomic cache phase.
            if accepted.execute('SELECT 1 FROM accepted_receipts WHERE namespace=? AND key=?', (namespace,key)).fetchone() is None:
                continue
        if row is None or row[0] is None or row[1] != digest or hashlib.sha256(row[0]).hexdigest() != digest:
            raise ValueError('Pending body changed after certification')


def plan_facts(owner, plan, accepted, project, recipes, read_text):
    from semantica.triplet_store.extraction_records import ExtractionRecords, BINDING, F, operation_identity
    from semantica.triplet_store.classification_records import ClassificationRecords, BINDING as CB
    from semantica.semantic_extract.cache import ExtractionCache
    ox = owner._oxigraph
    publication = ox.NamedNode('urn:semantica:publication:' + hashlib.sha256(project.encode()).hexdigest())
    for quad in owner.store.quads_for_pattern(None, None, None, publication):
        if getattr(quad.object, 'value', '') in recipes:
            raise ValueError('Current publication still names an obsolete recipe')
    graph = ox.NamedNode('urn:semantica:project:' + hashlib.sha256(project.encode()).hexdigest())
    key_owner = ExtractionCache()
    after = ''
    while True:
        values = ' '.join(str(ox.Literal(value)) for value in sorted(recipes))
        rows = list(owner.store.query(f'''SELECT ?op ?recipe WHERE {{ GRAPH {graph} {{
          ?op <{F}bindingRecipe> ?recipe . VALUES ?recipe {{ {values} }}
          FILTER(STR(?op) > {ox.Literal(after)}) }} }} ORDER BY STR(?op) LIMIT 128'''))
        for row in rows:
            op = row['op']; after = op.value
            dummy = object.__new__(ExtractionRecords); dummy.owner, dummy.ox, dummy.graph = owner, ox, graph
            classification = op.value.startswith('urn:semantica:classification:')
            fields = CB if classification else BINDING
            binding = {field: dummy.one(op, 'binding' + field[0].upper() + field[1:]) for field in fields}
            if binding['project'] != project or binding['recipe'] not in recipes:
                raise ValueError('Operation escaped admitted cleanup scope')
            if classification:
                records = ClassificationRecords(owner, binding)
                stage = 'classification'
            else:
                stage = next((stage for stage in ('entities', 'relations') if operation_identity(binding, stage) == op.value), None)
                if stage is None:
                    raise ValueError('Unknown obsolete native operation')
                records = ExtractionRecords(owner, binding, stage)
            receipt = records.receipt()
            if receipt is None:
                raise ValueError('Obsolete operation receipt missing')
            model_receipts = records.read_receipts()
            plan.execute('INSERT INTO operations VALUES(?,?,?,?,?)', (op.value, binding['recipe'], json.dumps(binding, sort_keys=True), json.dumps(receipt, sort_keys=True), json.dumps(model_receipts, sort_keys=True)))
            for node in [op, *records.values(op, 'ownedRecord')]:
                plan.execute('INSERT INTO nodes VALUES(?,?)', (node.value, graph.value))
            reduction = records.one(op, 'classificationReduction', optional=True) if classification else None
            if not reduction:
                text = binding['context_digest'] if classification else read_text(binding)
                key = key_owner._generate_key(text, native_operation=op.value)
                add_cache_key(plan, accepted, stage, key, receipt['accepted_digest'])
            if not classification:
                for suffix in (':identity-projection', ':fact-projection'):
                    derived = ox.NamedNode(op.value + suffix)
                    plan.execute('INSERT INTO graphs VALUES(?,?)', (derived.value, 'projection'))
                    # Projection subjects are bounded by the accepted operation owner.
                    count = 0
                    for quad in owner.store.quads_for_pattern(None, None, None, derived):
                        count += 1
                        if count > 131072:
                            raise ValueError('Obsolete projection exceeds maintenance operation budget')
                        if not isinstance(quad.subject, ox.NamedNode):
                            raise ValueError('Unexpected blank projection subject')
                        plan.execute('INSERT OR IGNORE INTO nodes VALUES(?,?)', (quad.subject.value, derived.value))
        plan.commit()
        if len(rows) < 128:
            break
    for identity, context in plan.execute('SELECT id,graph FROM nodes ORDER BY id,graph'):
        digest, count = node_proof(owner, identity, context)
        plan.execute('INSERT INTO node_proofs VALUES(?,?,?,?)', (identity, context, digest, count))
    plan.commit()
    assert_no_external_references(owner, plan)


def node_proof(owner, identity, graph):
    ox = owner._oxigraph
    values = []
    byte_count = 0
    for quad in owner.store.quads_for_pattern(ox.NamedNode(identity), None, None, ox.NamedNode(graph)):
        value = str(quad).encode()
        byte_count += len(value)
        if len(values) >= 32768 or byte_count > 2*1024*1024:
            raise ValueError('Cleanup subject proof exceeds native operation budget')
        values.append(value)
    return hashlib.sha256(b'\n'.join(sorted(values))).hexdigest(), len(values)


def assert_no_external_references(owner, plan):
    """Incoming references, including encoded native identities, must stay in closure."""
    ox = owner._oxigraph
    for identity, graph in plan.execute('SELECT id,graph FROM nodes ORDER BY id,graph'):
        for quad in owner.store.quads_for_pattern(None, None, ox.NamedNode(identity), None):
            if not plan.execute('SELECT 1 FROM nodes WHERE id=? AND graph=?', (quad.subject.value, getattr(quad.graph_name, 'value', ''))).fetchone():
                raise ValueError('Current publication or another owner references obsolete node: ' + identity)
    # Literal or percent-encoded native identities cannot bypass direct IRI admission.
    # Maintenance legitimately traverses all graphs, retaining only one quad.
    for quad in owner.store:
        if plan.execute('SELECT 1 FROM nodes WHERE id=? AND graph=?', (quad.subject.value, getattr(quad.graph_name, 'value', ''))).fetchone():
            continue
        value = unquote(getattr(quad.object, 'value', ''))
        for token in re.findall(r'urn:semantica:[A-Za-z0-9:_./#%+-]+', value):
            if plan.execute('SELECT 1 FROM nodes WHERE id=? LIMIT 1', (token,)).fetchone():
                raise ValueError('Encoded external reference to obsolete node')


def plan_spaces(root, plan, accepted, recipes, current_recipe):
    from semantica.semantic_extract.cache import ExtractionCache
    key_owner = ExtractionCache()
    for path in sorted(root.glob('embedding-*.sqlite')):
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise ValueError('Vector owner escapes admitted native root')
        conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            encoded, dimension = conn.execute('SELECT identity,dimension FROM embedding_space WHERE id=1').fetchone()
            identity = json.loads(encoded)
            if identity['recipe'] not in recipes:
                continue
            if identity['recipe'] == current_recipe:
                raise ValueError('Current vector space cannot be retired')
            if path.name != 'embedding-' + identity['binding'].removeprefix('sha256:') + '.sqlite':
                raise ValueError('Space filename and identity differ')
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='embeddings_native_publications'").fetchone() and conn.execute('SELECT 1 FROM embeddings_native_publications LIMIT 1').fetchone():
                raise ValueError('Obsolete vector space still has publication receipts')
            digest = hashlib.sha256(); operations = vectors = 0
            for row in conn.execute('SELECT id,count,digest,receipt,receipt_digest,accepted_digest FROM embeddings_embedding_operations ORDER BY id'):
                operation, count, vector_digest, receipt, receipt_digest, acceptance = row
                if hashlib.sha256(receipt.encode()).hexdigest() != receipt_digest:
                    raise ValueError('Obsolete model receipt digest differs')
                digest.update(json.dumps(row, separators=(',', ':')).encode())
                plan.execute('INSERT INTO vector_audit VALUES(?,?,?,?)', (str(path), operation, receipt, acceptance))
                add_cache_key(plan, accepted, 'embedding', key_owner._generate_key(operation), acceptance)
                operations += 1; vectors += count
            if conn.execute('SELECT count(*) FROM embeddings_rowids').fetchone()[0] != vectors:
                raise ValueError('Obsolete vector row count differs')
            plan.execute('INSERT INTO spaces VALUES(?,?,?,?,?)', (str(path), encoded, operations, vectors, digest.hexdigest()))
        finally:
            conn.close()
    plan.commit()


def assert_publication_spaces(owner, plan, project):
    ox = owner._oxigraph
    graph = ox.NamedNode('urn:semantica:publication:' + hashlib.sha256(project.encode()).hexdigest())
    spaces = set()
    recipes = {recipe for recipe, in plan.execute('SELECT DISTINCT recipe FROM operations')}
    for identity, in plan.execute('SELECT identity FROM spaces'):
        identity = json.loads(identity)
        spaces.add(identity['binding']); recipes.add(identity['recipe'])
    for quad in owner.store.quads_for_pattern(None, None, None, graph):
        if any(identity in unquote(getattr(quad.object, 'value', '')) for identity in spaces | recipes):
            raise ValueError('Current publication still references retired recipe or vector space')


def apply_plan(owner, plan, accepted_path, *, resume=False):
    ox = owner._oxigraph
    assert_no_external_references(owner, plan)
    for identity, graph, digest, count in plan.execute('SELECT * FROM node_proofs'):
        actual = node_proof(owner, identity, graph)
        if actual != (digest, count) and not (resume and actual[1] == 0):
            raise ValueError('Cleanup subject changed after certification')
    # Recheck every remaining owner before RDF writes, including crash resumes.
    conn = sqlite3.connect(accepted_path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        verify_pending(plan, conn, resume=resume)
        for namespace, key, digest in plan.execute('SELECT * FROM cache_keys'):
            actual = conn.execute('SELECT digest FROM accepted_receipts WHERE namespace=? AND key=?', (namespace, key)).fetchone()
            if actual != (digest,) and not (resume and actual is None):
                raise ValueError('Acceptance changed after admission')
    finally:
        conn.close()
    for filename, identity, operations, vectors, expected_digest in plan.execute('SELECT * FROM spaces'):
        path = Path(filename)
        if resume and not path.exists():
            continue
        if path.is_symlink():
            raise ValueError('Retired vector owner changed after certification')
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            actual_identity = conn.execute('SELECT identity FROM embedding_space WHERE id=1').fetchone()
            digest = hashlib.sha256(); operation_count = vector_count = 0
            for row in conn.execute('SELECT id,count,digest,receipt,receipt_digest,accepted_digest FROM embeddings_embedding_operations ORDER BY id'):
                digest.update(json.dumps(row, separators=(',', ':')).encode())
                operation_count += 1; vector_count += row[1]
            published = conn.execute("SELECT 1 FROM sqlite_master WHERE name='embeddings_native_publications'").fetchone() and conn.execute('SELECT 1 FROM embeddings_native_publications LIMIT 1').fetchone()
            if (actual_identity != (identity,) or operation_count != operations or vector_count != vectors
                    or digest.hexdigest() != expected_digest or published
                    or conn.execute('SELECT count(*) FROM embeddings_rowids').fetchone()[0] != vectors):
                raise ValueError('Retired vector owner changed after certification')
        finally:
            conn.close()
    # Admission completed for the whole closure before the first destructive write.
    for identity, graph in plan.execute('SELECT id,graph FROM nodes ORDER BY graph,id'):
        owner.store.update(f'DELETE WHERE {{ GRAPH {ox.NamedNode(graph)} {{ {ox.NamedNode(identity)} ?p ?o }} }}')
    for graph, _ in plan.execute('SELECT * FROM graphs'):
        owner.store.remove_graph(ox.NamedNode(graph))
    owner.flush(); owner.store.optimize(); owner.flush()
    conn = sqlite3.connect(accepted_path)
    try:
        with conn:
            for namespace, key, digest in plan.execute('SELECT * FROM cache_keys'):
                conn.execute('DELETE FROM cache WHERE namespace=? AND key=?', (namespace, key))
                changed = conn.execute('DELETE FROM accepted_receipts WHERE namespace=? AND key=? AND digest=?', (namespace, key, digest)).rowcount
                if changed != 1 and not (resume and conn.execute('SELECT 1 FROM accepted_receipts WHERE namespace=? AND key=?', (namespace, key)).fetchone() is None):
                    raise ValueError('Acceptance changed after admission')
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.execute('VACUUM')
    finally:
        conn.close()
    for path, *_ in plan.execute('SELECT * FROM spaces'):
        for suffix in ('', '-wal', '-shm'):
            Path(path + suffix).unlink(missing_ok=True)
    for identity, graph in plan.execute('SELECT id,graph FROM nodes'):
        if next(owner.store.quads_for_pattern(ox.NamedNode(identity), None, None, ox.NamedNode(graph)), None):
            raise ValueError('Obsolete facts survived deletion')


def main():
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, stable_digest
    from semantica.semantic_publication_builder import _project_processing_digest, _read_source_projection_text
    from semantica.semantic_source_artifact import _load_parsed_source
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--obsolete-recipe', required=True, action='append')
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--apply-certificate', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--pending-scopes', type=Path, help='Explicit canonical obsolete pending scopes and exact counts')
    parser.add_argument('--app-db', required=True, type=Path)
    parser.add_argument('--actor-id', required=True)
    args = parser.parse_args()
    import semantica
    request = SemanticArtifactBuildRequest.model_validate_json(args.request.read_text())
    helper = __import__('runpy').run_path(str(Path(__file__).with_name('rebind_paid_native_results.py')))
    current = helper['source_recipe'](request, _project_processing_digest(Path(semantica.__file__).parent))
    processing = _project_processing_digest(Path(semantica.__file__).parent)
    protected = {current, stable_digest(dict(recipe=request.recipe.lineage_payload(),
        processing=processing, binding=request.relays['model'].binding_id))}
    relay = request.relays['embedding']
    current_space = dict(binding=stable_digest(dict(binding=relay.binding_id,model=relay.model_id,recipe=current)),
        model=relay.model_id,recipe=current)
    recipes = set(args.obsolete_recipe)
    if protected & recipes or not recipes or any(not value.startswith('sha256:') or len(value) != 71 for value in recipes):
        raise ValueError('Explicit obsolete recipes must exclude current recipe')
    root = Path(request.native_store_dir).resolve().parent
    cache_path = Path(request.native_cache_dir).resolve()/'accepted.sqlite'
    if root != cache_path.parent.parent or not root.is_dir() or not cache_path.is_file():
        raise ValueError('Existing project native owners must share one root')
    for output in (args.plan, args.report):
        if output.resolve().is_relative_to(root) or output.resolve() in (args.request.resolve(), args.app_db.resolve()):
            raise ValueError('Maintenance evidence must stay outside native owners and inputs')
    def require_idle():
        db = sqlite3.connect(args.app_db.resolve().as_uri()+'?mode=ro', uri=True)
        try:
            active = db.execute("SELECT r.id FROM execution_runs r JOIN knowledge_jobs j ON j.execution_run_id=r.id WHERE j.actor_id=? AND j.resource_id=? AND r.status NOT IN ('succeeded','failed','canceled','interrupted') LIMIT 1", (args.actor_id, request.project_id)).fetchone()
            if active:
                raise ValueError('Project worker is still active')
        finally:
            db.close()
    require_idle()
    if args.resume and not args.apply_certificate:
        raise ValueError('Resume requires original dry-run certificate and retained plan')
    plan = sqlite3.connect(args.plan.resolve().as_uri()+'?mode=ro', uri=True) if args.resume else create_plan(args.plan)
    owner = OxigraphStore(request.native_store_dir)
    accepted = sqlite3.connect(cache_path.as_uri() + '?mode=ro', uri=True)
    parsed_cache = [None, None]
    def read_text(binding):
        source = next(source for source in request.sources if source.source_id == binding['source'])
        ref = next(ref for ref in request.parsed_sources if ref.source_id == source.source_id)
        if binding['material'] != source.material_revision or binding['representation'] != ref.representation_revision:
            raise ValueError('Old operation does not match retained material/representation')
        if parsed_cache[0] != source.source_id:
            parsed_cache[:] = [source.source_id, _load_parsed_source(source, ref, source.source_id in request.recipe.force_ocr_source_ids, request.document_processing.model_dump(mode='json', by_alias=True))]
        return _read_source_projection_text(parsed_cache[1].reader, binding['window_start'], binding['window_end'])
    try:
        if not args.resume:
            plan_facts(owner, plan, accepted, request.project_id, recipes, read_text)
            plan_spaces(root, plan, accepted, recipes, current)
            if args.pending_scopes:
                scopes = json.loads(args.pending_scopes.read_text())
                if not isinstance(scopes, list) or len(scopes) > 128:
                    raise ValueError('Pending scopes exceed maintenance budget')
                plan_pending(plan, accepted, scopes, recipes, current, lambda scope: pending_candidates(request, scope))
        inventory_all(owner, plan, accepted, root, request.project_id, protected, recipes, read_text, resume=args.resume, current_space=current_space)
        assert_publication_spaces(owner, plan, request.project_id)
        report = dict(project=request.project_id, artifactDigest=request.release.artifact_digest,
            inputRevision=request.input_revision,currentEmbeddingSpace=current_space,
            requestDigest=stable_digest(request.model_dump(mode='json', by_alias=True)), currentRecipe=current, protectedRecipes=sorted(protected), obsoleteRecipes=sorted(recipes), planDigest=digest_rows(plan), counts={table: plan.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('operations','nodes','graphs','cache_keys','spaces','pending_audit','inventory','protected_receipts')}, apply=False)
        if args.apply_certificate:
            prior = json.loads(args.apply_certificate.read_text())
            if prior != report:
                raise ValueError('Apply requires identical successful dry-run certificate')
            require_idle()
            accepted.close()
            apply_plan(owner, plan, cache_path, resume=args.resume)
            report['apply'] = True
        args.report.write_text(json.dumps(report, indent=2))
        args.report.chmod(0o600)
        print(json.dumps(report))
    finally:
        accepted.close(); owner.close(); plan.close()


if __name__ == '__main__':
    main()
