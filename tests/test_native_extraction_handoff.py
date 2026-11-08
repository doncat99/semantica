"""Crash acceptance for the production grounded extractor and native owners."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


TEXT = 'Acme uses Engine.'


def child(root, fault='none', fault_stage='entities', source='source-1', recipe='recipe-1'):
    from semantica.semantic_extract.cache import ExtractionCache, SqliteCacheBackend
    from semantica.semantic_extract.grounded_window import extract_grounded_window
    from semantica.semantic_extract.providers import BaseProvider
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    from semantica.utils.exceptions import ProcessingError

    root = Path(root)
    binding = dict(project='project-1', source=source, material='material-1',
        representation='representation-1', recipe=recipe, model='model-1',
        specification='specification-1', parser='parser-1', grounding='sha256:' + '3' * 64,
        window_start=0, window_end=len(TEXT))
    cache = ExtractionCache(backend=SqliteCacheBackend(str(root/'accepted.sqlite')))
    store = OxigraphStore(root/'facts')

    class Provider(BaseProvider):
        def __init__(self):
            super().__init__(model='model-1')
            self.receipts, self.rejections = [], []

        def generate(self, prompt, **kwargs):
            stage = kwargs['extraction_stage']
            with (root/'calls.jsonl').open('a') as stream:
                stream.write(json.dumps([source, recipe, stage])+'\n')
                stream.flush()
                os.fsync(stream.fileno())
            self.receipts.append(dict(id=f'receipt:{source}:{recipe}:{stage}', provider='fixture',
                model='model-1', operation='structured_extraction', metadata={'extraction_stage':stage},
                input_digest='sha256:'+'1'*64, output_digest='sha256:'+'2'*64))
            if stage == 'entities':
                if recipe == 'empty':
                    return json.dumps({'entities': []})
                return json.dumps({'entities': [dict(text=name, label='ORG', occurrence=0,
                    confidence=.9, attributes={}) for name in ('Acme', 'Engine')]})
            return json.dumps({'relations': [dict(subject_id='mention:0',
                predicate='uses', object_id='mention:1', evidence=TEXT, supporting_refs=[],
                evidence_occurrence=0, confidence=.9, qualifiers={'polarity':'positive'})]})

    original_accept = cache.accept
    def accept(namespace, *args, **kwargs):
        value = original_accept(namespace, *args, **kwargs)
        if fault == 'after-accept' and namespace == fault_stage:
            os._exit(73)
        return value
    cache.accept = accept
    original_adopt = store.adopt_extraction
    def adopt(bound, stage, *args, **kwargs):
        value = original_adopt(bound, stage, *args, **kwargs)
        if fault == 'after-adopt' and stage == fault_stage:
            os._exit(73)
        return value
    store.adopt_extraction = adopt
    original_flush = store.flush
    def flush():
        if fault == 'flush':
            raise ProcessingError('injected native flush failure')
        return original_flush()
    store.flush = flush
    original_release = cache.release_accepted
    def release(namespace, *args, **kwargs):
        if fault == 'release' and namespace == fault_stage:
            raise ProcessingError('injected accepted release failure')
        return original_release(namespace, *args, **kwargs)
    cache.release_accepted = release
    entities, relations, provider = extract_grounded_window(TEXT, model='model-1',
        provider_instance=Provider(), retries=0, native_store=store,
        accepted_cache=cache, extraction_binding=binding,
        native_ranges=[dict(nativeRef='#/document/text', start=0, end=len(TEXT), windowStart=0, windowEnd=len(TEXT))])
    if recipe == 'empty':
        assert entities == relations == []
    else:
        assert [item.text for item in entities] == ['Acme', 'Engine']
        assert len(relations) == 1 and relations[0].predicate == 'uses'
        assert relations[0].context == TEXT
    assert store.extraction_receipt(binding, 'entities') is not None
    if recipe != 'empty':
        assert store.extraction_receipt(binding, 'relations') is not None
    with sqlite3.connect(root/'accepted.sqlite') as db:
        assert db.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 0
    print('completed', flush=True)


def run_child(root, fault='none', stage='entities', source='source-1', recipe='recipe-1'):
    return subprocess.run([sys.executable, '-c',
        "import runpy,sys; runpy.run_path(sys.argv[1])['child'](*sys.argv[2:])",
        str(Path(__file__).resolve()), str(root), fault, stage, source, recipe],
        capture_output=True, text=True, timeout=30)


def calls(root):
    path = root/'calls.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def damage_native(root, mutation):
    from semantica.triplet_store.oxigraph_store import OxigraphStore
    store = OxigraphStore(Path(root)/'facts')
    ox = store._oxigraph
    predicate = ox.NamedNode('urn:semantica:field:name' if mutation == 'fact'
                            else 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
    expected = None if mutation == 'fact' else ox.NamedNode('urn:semantica:field:ExtractionOperation')
    quad = next(store.store.quads_for_pattern(None, predicate, expected, None))
    store.store.remove(quad)
    store.flush()


@pytest.mark.parametrize('stage', ['entities', 'relations'])
@pytest.mark.parametrize('fault', ['after-accept', 'after-adopt'])
def test_production_restart_never_repays_an_accepted_stage(tmp_path, stage, fault):
    first = run_child(tmp_path, fault, stage)
    assert first.returncode == 73, first.stderr
    resumed = run_child(tmp_path)
    assert resumed.returncode == 0, resumed.stderr
    assert calls(tmp_path) == [['source-1', 'recipe-1', 'entities'],
                               ['source-1', 'recipe-1', 'relations']]
    again = run_child(tmp_path)
    assert again.returncode == 0, again.stderr
    assert len(calls(tmp_path)) == 2


@pytest.mark.parametrize('fault', ['flush', 'release'])
def test_production_durability_failure_preserves_pending_paid_work(tmp_path, fault):
    failed = run_child(tmp_path, fault)
    assert failed.returncode != 0
    assert 'injected' in failed.stderr
    with sqlite3.connect(tmp_path/'accepted.sqlite') as db:
        assert db.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 1
    resumed = run_child(tmp_path)
    assert resumed.returncode == 0, resumed.stderr
    assert calls(tmp_path) == [['source-1', 'recipe-1', 'entities'],
                               ['source-1', 'recipe-1', 'relations']]


def test_replaying_released_native_work_does_not_flush(tmp_path):
    completed = run_child(tmp_path)
    assert completed.returncode == 0, completed.stderr
    replayed = run_child(tmp_path, 'flush')
    assert replayed.returncode == 0, replayed.stderr
    assert len(calls(tmp_path)) == 2


@pytest.mark.parametrize('mutation', ['missing', 'corrupt'])
def test_production_lost_paid_work_fails_closed_without_new_model_call(tmp_path, mutation):
    first = run_child(tmp_path, 'after-accept')
    assert first.returncode == 73, first.stderr
    with sqlite3.connect(tmp_path/'accepted.sqlite') as db:
        if mutation == 'missing':
            db.execute('DELETE FROM cache WHERE accepted_digest IS NOT NULL')
        else:
            db.execute('UPDATE cache SET value=? WHERE accepted_digest IS NOT NULL', (b'corrupt',))
    resumed = run_child(tmp_path)
    assert resumed.returncode != 0
    assert len(calls(tmp_path)) == 1
    assert ('missing' if mutation == 'missing' else 'digest') in resumed.stderr.lower()


@pytest.mark.parametrize('source,recipe', [('source-2','recipe-1'), ('source-1','recipe-2')])
def test_production_identical_text_does_not_cross_source_or_recipe(tmp_path, source, recipe):
    for bound_source, bound_recipe in [('source-1','recipe-1'), (source,recipe)]:
        result = run_child(tmp_path, source=bound_source, recipe=bound_recipe)
        assert result.returncode == 0, result.stderr
    assert calls(tmp_path) == [['source-1','recipe-1','entities'], ['source-1','recipe-1','relations'],
                               [source,recipe,'entities'], [source,recipe,'relations']]


def test_production_empty_extraction_is_a_completed_paid_result(tmp_path):
    for _ in range(2):
        result = run_child(tmp_path, recipe='empty')
        assert result.returncode == 0, result.stderr
    assert calls(tmp_path) == [['source-1','empty','entities']]


@pytest.mark.parametrize('mutation', ['fact', 'operation'])
def test_production_damaged_adopted_result_never_rebuys_paid_work(tmp_path, mutation):
    completed = run_child(tmp_path)
    assert completed.returncode == 0, completed.stderr
    damaged = subprocess.run([sys.executable, '-c',
        "import runpy,sys; runpy.run_path(sys.argv[1])['damage_native'](*sys.argv[2:])",
        str(Path(__file__).resolve()), str(tmp_path), mutation],
        capture_output=True, text=True, timeout=30)
    assert damaged.returncode == 0, damaged.stderr
    resumed = run_child(tmp_path)
    assert resumed.returncode != 0
    assert len(calls(tmp_path)) == 2
    assert 'missing' in resumed.stderr.lower()


def build_child(root, stop_before_publication=True):
    """Actual build stages; only the remote transport is a no-network fixture."""
    import urllib.request
    from semantica.semantic_publication_builder import build_semantic_artifacts
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, stable_digest
    from tests.test_semantic_artifact import _request, _classification_profile, _native_report, _typed_prompt_context

    root = Path(root)
    source = root/'source.txt'
    if not source.exists():
        source.write_text('Ada Lovelace designed the Analytical Engine.')
    os.environ['OPENAI_API_KEY'] = 'fixture-only'
    request = _request(source, root/'published', recipe='model')['params']
    request['relays']['embedding']['bindingId'] = 'binding:fixture-embedding'
    request['recipe']['classificationProfile'] = _classification_profile()
    product = root/'host-product.json'

    class Response:
        status = 200
        def __init__(self, value):
            self.value = json.dumps(value).encode()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size=-1): return self.value[:size]

    def transport(req, timeout):
        payload = json.loads(req.data)
        if '/products/semantic-organization/' in req.full_url:
            operation = stable_digest([payload[key] for key in
                ('projectId', 'inputRevision', 'recipeDigest', 'modelId', 'targetId', 'inputDigest')])
            if req.full_url.endswith('/adopt'):
                # This file stands for the final host business product, never a fork cache.
                with product.open('w') as stream:
                    json.dump(dict(report=payload['report'], receipts=payload['receipts'],
                        operationId=operation, digest=stable_digest(payload)), stream)
                    stream.flush()
                    os.fsync(stream.fileno())
            return Response(json.loads(product.read_text()) if product.exists() else {'report': None})
        if req.full_url.endswith('/embeddings'):
            stage = 'embedding'
            result = {'model': payload['model'], 'data': [dict(index=i, embedding=[.25,.5,.75])
                for i, _ in enumerate(payload['input'])]}
        else:
            prompt = payload['messages'][0]['content']
            if 'Explain the supplied knowledge' in prompt:
                stage, content = 'organization', _native_report(payload)
            elif 'Classify this source' in prompt:
                stage = 'classification'
                ref = _typed_prompt_context(payload)['evidence'][0]['id']
                content = {'assignments': [dict(dimension_id='purpose', item_id='history',
                    confidence=.95, citations=[dict(evidence_id=ref)])]}
            elif 'Extract source-grounded relations' in prompt:
                stage = 'relations'
                content = {'relations': [dict(subject_id='mention:0', predicate='designed',
                    object_id='mention:1', evidence=source.read_text(), evidence_occurrence=0,
                    confidence=.9, qualifiers={'polarity':'positive'}, supporting_refs=[])]}
            else:
                stage = 'entities'
                content = {'entities': [dict(text=name, label=label, occurrence=0, attributes={}, confidence=.9)
                    for name,label in [('Ada Lovelace','PERSON'), ('Analytical Engine','CONCEPT')]]}
            result = {'model': payload['model'], 'choices': [{'finish_reason':'stop',
                'message': {'content':json.dumps(content)}}]}
        with (root/'build-calls.jsonl').open('a') as stream:
            stream.write(json.dumps(stage)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return Response(result)
    urllib.request.urlopen = transport
    stages = []
    def progress(event):
        stages.append(event['stage'])
        if event['stage'] == 'artifact_writing' and stop_before_publication:
            (root/'stages.json').write_text(json.dumps(stages))
            os._exit(74)
    result = build_semantic_artifacts(SemanticArtifactBuildRequest.model_validate(request), progress=progress)
    if stop_before_publication:
        raise AssertionError('publication fault was not reached')
    return result


def test_actual_build_restarts_without_rebuy_or_checkpoint_before_publication(tmp_path):
    command = [sys.executable, '-c',
        "import runpy,sys; runpy.run_path(sys.argv[1])['build_child'](sys.argv[2])",
        str(Path(__file__).resolve()), str(tmp_path)]
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        assert result.returncode == 74, result.stderr
    paid = [json.loads(line) for line in (tmp_path/'build-calls.jsonl').read_text().splitlines()]
    assert sorted(paid) == sorted(['entities','relations','embedding','classification','organization'])
    stages = json.loads((tmp_path/'stages.json').read_text())
    assert {'document_parsing','extracting','source_projection','source_classification',
        'entity_resolution','fact_reconciliation','semantic_organization','artifact_writing'} <= set(stages)
    assert (tmp_path/'host-product.json').is_file()
    assert not list(tmp_path.rglob('*checkpoint*'))
    assert not list((tmp_path/'published').glob('*.json'))
    with sqlite3.connect(tmp_path/'native-cache'/'accepted.sqlite') as db:
        assert db.execute('SELECT count(*) FROM cache WHERE accepted_digest IS NOT NULL').fetchone()[0] == 0
