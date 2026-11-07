"""Explicit offline paid-identity migration; stop every native reader first.

The operator must establish producer equivalence for the supplied old recipe.
This changes native metadata/indexes only. It never adopts or copies paid data.
Unknown physical vector operations fail closed; publications require rebuilding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import nullcontext
from itertools import batched


def source_bindings(store, project, source, recipe, *, classification=False):
    """Cursor physical extraction metadata; at most 128 operation rows per page."""
    from semantica.triplet_store.extraction_records import BINDING, ExtractionRecords, F, operation_identity
    if classification:
        from semantica.triplet_store.classification_records import BINDING
    ox = store._oxigraph
    graph = ox.NamedNode('urn:semantica:project:' + hashlib.sha256(project.encode()).hexdigest())
    prefix = 'urn:semantica:classification:' if classification else 'urn:semantica:extraction:'
    after = ''
    while True:
        query = f'''SELECT ?op WHERE {{ GRAPH {graph} {{
            ?op <{F}bindingSource> {ox.Literal(source)} ; <{F}bindingRecipe> {ox.Literal(recipe)} .
            FILTER(STRSTARTS(STR(?op), {ox.Literal(prefix)}))
            FILTER(STR(?op) > {ox.Literal(after)}) }} }} ORDER BY STR(?op) LIMIT 128'''
        page = list(store.store.query(query))
        for row in page:
            op = row['op']
            codec = object.__new__(ExtractionRecords)
            codec.owner, codec.ox, codec.graph = store, ox, graph
            binding = {key: codec.one(op, 'binding' + key[0].upper() + key[1:]) for key in BINDING}
            if binding['project'] != project or binding['source'] != source or binding['recipe'] != recipe:
                raise ValueError('Extraction operation escaped admitted source scope')
            stage = codec.one(op, 'extractionStage', optional=True)
            if classification:
                stage = 'classification'
            elif stage is None:
                stage = next((s for s in ('entities', 'relations') if operation_identity(binding, s) == op.value), None)
            if stage not in {'entities', 'relations', 'classification'}:
                raise ValueError('Unknown extraction stage')
            yield binding, stage, op.value
            after = op.value
        if len(page) < 128:
            return


def embedding_bindings(request, old_recipe, old_space, target_space, owner):
    """Reproduce paid window addresses without reading vectors or model calls."""
    from semantica.semantic_artifact_schema import stable_digest
    from semantica.semantic_publication_builder import _source_windows
    from semantica.semantic_source_artifact import _load_parsed_source
    from semantica.source import source_processing_revision
    refs = {ref.source_id: ref for ref in request.parsed_sources}
    with sqlite3.connect(Path(owner.db_path).as_uri() + '?mode=ro', uri=True) as db:
        # Indexed migrated operations include withdrawn sources and need no body hydration.
        has_index = db.execute("SELECT 1 FROM sqlite_master WHERE name='embeddings_embedding_bindings'").fetchone()
        indexed = db.execute('SELECT count(*) FROM embeddings_embedding_bindings').fetchone()[0] if has_index else 0
        total = db.execute('SELECT count(*) FROM embeddings_embedding_operations').fetchone()[0]
        if indexed:
            if indexed != total:
                raise ValueError('Embedding identity index is incomplete')
            for (raw,) in db.execute('SELECT binding_json FROM embeddings_embedding_bindings ORDER BY physical_id'):
                previous = json.loads(raw)
                yield dict(previous=previous, current={**previous, 'recipe': target_space['recipe'], 'space': target_space['binding']})
            return
        for source in request.sources:
            ref = refs[source.source_id]
            parsed = _load_parsed_source(source, ref, source.source_id in request.recipe.force_ocr_source_ids,
                request.document_processing.model_dump(mode='json', by_alias=True))
            parser = source_processing_revision(Path(source.file_path), name=source.name,
                mime_type=source.mime_type, force_ocr=source.source_id in request.recipe.force_ocr_source_ids,
                document_processing=request.document_processing.model_dump(mode='json', by_alias=True))
            for start, end, text in _source_windows(parsed):
                previous = dict(project=request.project_id, source=source.source_id,
                    material=source.material_revision, representation=ref.representation_revision,
                    recipe=old_recipe, parser=parser, model=old_space['model'], space=old_space['binding'],
                    ranges=[[start, end]], input_digest=stable_digest([text]))
                physical = owner.embedding_operation_id(previous)
                if db.execute('SELECT 1 FROM embeddings_embedding_operations WHERE id=?', (physical,)).fetchone():
                    yield dict(previous=previous, current={**previous, 'recipe': target_space['recipe'], 'space': target_space['binding']})


def migrate(request, old_recipe, *, apply=False, old_classification_recipe=None):
    from semantica.semantic_artifact_schema import stable_digest
    from semantica.semantic_publication_builder import _extraction_recipe
    from semantica.semantic_embedding_recipe import embedding_recipe
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
    from semantica.semantic_extract.cache import ExtractionCache
    if not isinstance(old_recipe, str) or not old_recipe.startswith('sha256:') or len(old_recipe) != 71:
        raise ValueError('An explicit old recipe SHA256 is required')
    current = _extraction_recipe(request)
    report = dict(project=request.project_id, requestDigest=stable_digest(request.model_dump(mode='json', by_alias=True)),
        oldRecipe=old_recipe, currentRecipe=current, apply=apply, extractions=0, embeddings=0,
        classifications=0, factsCopied=0, vectorsCopied=0, receiptsCopied=0, publications='require-rebuild')
    keys = ExtractionCache()
    cache_path = Path(request.native_cache_dir).resolve() / 'accepted.sqlite'
    with sqlite3.connect(cache_path.as_uri() + '?mode=ro', uri=True) as accepted:
        def verify(namespace, identity, digest, text=None):
            key = keys._generate_key(text, native_operation=identity) if text is not None else keys._generate_key(identity)
            if accepted.execute('SELECT digest FROM accepted_receipts WHERE namespace=? AND key=?', (namespace, key)).fetchone() != (digest,):
                raise ValueError('Native result lacks its matching paid acceptance receipt')
        store = OxigraphStore(request.native_store_dir)
        try:
            from semantica.triplet_store.extraction_records import ExtractionRecords
            from semantica.semantic_source_artifact import _load_parsed_source
            from semantica.semantic_publication_builder import _read_source_projection_text
            refs = {ref.source_id: ref for ref in request.parsed_sources}
            for source in request.sources:
                parsed = None
                for recipe in dict.fromkeys((current, old_recipe)):
                    for batch in batched(source_bindings(store, request.project_id, source.source_id, recipe), 128):
                        with store.batch_writes() if apply else nullcontext():
                            for previous, stage, physical in batch:
                                codec = ExtractionRecords(store, previous, stage)
                                # Offline migration verifies the full physical receipt,
                                # including pre-index owners, without a runtime proof cache.
                                receipt = codec._verify_receipt()
                                if receipt is None:
                                    raise ValueError('Native extraction receipt is missing')
                                if parsed is None:
                                    parsed = _load_parsed_source(source, refs[source.source_id], source.source_id in request.recipe.force_ocr_source_ids,
                                        request.document_processing.model_dump(mode='json', by_alias=True))
                                text = _read_source_projection_text(parsed.reader, previous['window_start'], previous['window_end'])
                                verify(stage, physical, receipt['accepted_digest'], text)
                                if apply:
                                    store.rebind_extraction(previous, {**previous, 'recipe': current}, stage)
                                report['extractions'] += 1
            if old_classification_recipe is not None:
                from semantica.triplet_store.classification_records import ClassificationRecords
                from semantica.semantic_publication_builder import _classification_recipe
                target_recipe = _classification_recipe(request.relays['model'])
                for source in request.sources:
                    for recipe in dict.fromkeys((target_recipe, old_classification_recipe)):
                        for batch in batched(source_bindings(store, request.project_id, source.source_id, recipe, classification=True), 128):
                            with store.batch_writes() if apply else nullcontext():
                                for previous, _, physical in batch:
                                    codec = ClassificationRecords(store, previous)
                                    receipt = codec._verify_receipt()
                                    if receipt is None:
                                        raise ValueError('Native classification receipt is missing')
                                    if not codec.one(codec.operation, 'classificationReduction', optional=True):
                                        verify('classification', physical, receipt['accepted_digest'], previous['context_digest'])
                                    if apply:
                                        store.rebind_classification(previous, {**previous, 'recipe': target_recipe})
                                    report['classifications'] += 1
        finally:
            store.close()
        relay = request.relays['embedding']
        spaces = [dict(binding=stable_digest(dict(binding=relay.binding_id, model=relay.model_id, recipe=recipe)),
            model=relay.model_id, recipe=recipe) for recipe in (old_recipe, embedding_recipe(relay))]
        root = Path(request.native_store_dir).resolve().parent
        paths = [root / ('embedding-' + space['binding'].removeprefix('sha256:') + '.sqlite') for space in spaces]
        if paths[0].exists() and paths[1].exists() and paths[0] != paths[1]:
            raise ValueError('Both old and target vector owners exist; refusing a second owner')
        path = paths[0] if paths[0].exists() else paths[1]
        if path.exists():
            # An interrupted apply may have committed metadata before the atomic path move.
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                encoded, dimension = db.execute('SELECT identity,dimension FROM embedding_space WHERE id=1').fetchone()
                actual = json.loads(encoded)
            if actual not in spaces:
                raise ValueError('Embedding owner space differs from explicit migration')
            if apply:
                owner = SQLiteVecStore.open_embedding_space(str(path), actual)
            else:
                owner = SQLiteVecStore(str(path), 'embeddings', dimension, 'cosine', read_only=True, embedding_space_identity=actual)
                owner.embedding_space_identity = actual
            try:
                def bindings():
                    count = 0
                    for item in embedding_bindings(request, old_recipe, actual, spaces[1], owner):
                        with owner._get_connection() as db:
                            logical = owner.embedding_operation_id(item['previous'])
                            # migrate_embedding_identity owns the nonreentrant lock while consuming this iterator.
                            has_index = db.execute("SELECT 1 FROM sqlite_master WHERE name='embeddings_embedding_bindings'").fetchone()
                            physical = (owner._embedding_physical_id(db, logical) if has_index else None) or logical
                            result = owner._read_embedding(db, physical, include_vectors=False)
                        if result is None:
                            raise ValueError('Embedding physical result is missing')
                        verify('embedding', physical, result['accepted_digest'])
                        count += 1
                        yield item
                    with owner._get_connection() as db:
                        total = db.execute('SELECT count(*) FROM embeddings_embedding_operations').fetchone()[0]
                    if count != total:
                        raise ValueError('Migration must cover every physical embedding operation')
                    report['embeddings'] = count
                if apply:
                    owner.migrate_embedding_identity(spaces[1], bindings())
                    # Only the main DB file is moved; force WAL contents durable there.
                    with owner._get_connection() as db:
                        checkpoint = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                    if checkpoint[0] != 0:
                        raise ValueError('Native vector owner still has active readers; refusing path move')
                else:
                    for _ in bindings():
                        pass
            finally:
                owner.close()
            if apply and path != paths[1]:
                path.rename(paths[1])
    return report


def main():
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--old-recipe', required=True)
    parser.add_argument('--old-classification-recipe')
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    request = SemanticArtifactBuildRequest.model_validate_json(args.request.read_text())
    result = migrate(request, args.old_recipe, apply=args.apply, old_classification_recipe=args.old_classification_recipe)
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
