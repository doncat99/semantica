"""Offline restore admission uses native receipts, never a rebuilt graph."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from semantica.native_maintenance import verify_native_installation
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError
from tests.test_native_extraction_handoff import build_child


@pytest.mark.parametrize('target_exists', [False, True])
def test_source_projection_semantic_rebind_is_offline_exact_and_idempotent(tmp_path, target_exists):
    from semantica.triplet_store.extraction_records import ExtractionRecords, F
    from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest, stable_digest
    from semantica.semantic_extraction_recipe import extraction_recipe
    from tests.test_semantic_artifact import _request
    result = build_child(tmp_path, stop_before_publication=False)
    request = SemanticArtifactBuildRequest.model_validate(_request(tmp_path/'source.txt', tmp_path/'published', recipe='model')['params'])
    source = request.sources[0]
    recipe = extraction_recipe(request)
    revision = request.parsed_sources[0].representation_revision
    identity = ExtractionRecords.source_projection_identity(project=request.project_id, source=source.source_id,
        material=source.material_revision, mime_type=source.mime_type, representation=revision,
        mode='model', force_ocr=False, extraction=recipe, formula_semantics=False)
    owner = OxigraphStore(result['semantic_store']['path'])
    try:
        addresses = list(ExtractionRecords.source_projection(owner, request.project_id, identity))
        previous = dict(source=source.model_dump(mode='json',by_alias=True), representation=revision,
            mode='model', force_ocr=False, operations=sorted(set(addresses[0]['operations'])))
        old_key = stable_digest(previous)
        ExtractionRecords.source_projection(owner, request.project_id, old_key, iter(addresses))
        before = sorted(str(q) for q in owner.store if q.graph_name.value.startswith('urn:semantica:project:'))
        def migrate(**options):
            return ExtractionRecords.rebind_source_projection(owner, request.project_id, previous,
                extraction=recipe, formula_semantics=False, **options)
        assert migrate()['executed'] is False
        assert list(ExtractionRecords.source_projection(owner,request.project_id,old_key)) == addresses
        # Same count and a valid address schema do not prove target equality.
        ox=owner._oxigraph
        import hashlib
        address = 'urn:semantica:source-projection:' + hashlib.sha256(
            json.dumps([request.project_id,identity],separators=(',',':')).encode()).hexdigest()
        graph = ox.NamedNode(address+':addresses')
        address_quad=next(q for q in owner.store.quads_for_pattern(None,ox.NamedNode(F+'address'),None,graph)
            if ':1' == q.subject.value[len(address):])
        changed=json.loads(address_quad.object.value)
        changed['quote_digest']='sha256:'+'0'*64
        replacement=ox.Quad(address_quad.subject,address_quad.predicate,
            ox.Literal(json.dumps(changed,ensure_ascii=False,separators=(',',':'))),graph)
        owner.store.remove(address_quad)
        owner.store.add(replacement)
        with pytest.raises(ProcessingError,match='target differs'):
            migrate(execute=True)
        assert list(ExtractionRecords.source_projection(owner,request.project_id,old_key)) == addresses
        owner.store.remove(replacement)
        owner.store.add(address_quad)
        quad=next(q for q in owner.store if q.predicate==ox.NamedNode(F+'address') and
            q.graph_name.value.startswith('urn:semantica:source-projection:') and
            q.object.value==json.dumps(addresses[0],ensure_ascii=False,separators=(',',':')))
        owner.store.remove(quad)
        with pytest.raises(ProcessingError,match='missing'):
            migrate(execute=True)
        owner.store.add(quad)
        if not target_exists:
            owner.store.clear_graph(ox.NamedNode(address+':addresses'))
        assert migrate(execute=True)['inputKey'] == identity
        assert migrate(execute=True)['inputKey'] == identity
        assert ExtractionRecords.source_projection(owner,request.project_id,old_key) is None
        assert list(ExtractionRecords.source_projection(owner,request.project_id,identity)) == addresses
        assert sorted(str(q) for q in owner.store if q.graph_name.value.startswith('urn:semantica:project:')) == before
    finally:
        owner.close()


@pytest.fixture
def ready(tmp_path):
    result = build_child(tmp_path, stop_before_publication=False)
    indexes = result['native_indexes']
    semantic = indexes['semantic']
    return dict(semanticStorePath=result['semantic_store']['path'],
        project=result['publication']['project'], generation=result['publication']['generation'],
        publicationReference=result['publication'],
        keyword={key:indexes['keyword'][key] for key in ('path','receipt')},
        semantic=dict(path=semantic['path'], receipt=semantic['receipt'], dimensions=semantic['space']['dimensions'],
            space=dict(binding=semantic['space']['space_id'], model=semantic['space']['modelId'], recipe=semantic['space']['recipe'])))


def test_ready_restart_relocation_cli_and_corrupt_keyword_rejection(ready, tmp_path):
    original = verify_native_installation(ready)
    assert original['counts']['sources'] == 1
    assert original['counts']['operations'] == 4
    assert original['counts']['canonicalRecords'] == 2
    assert original['counts']['vectors'] > 0
    assert original['counts']['associations'] > 0
    assert all(isinstance(value,str) and value.isdecimal() for value in original['keywordInstallation'])
    restored = copy.deepcopy(ready)
    for key in ('keyword','semantic'):
        destination = tmp_path/('restored-'+key+'.sqlite')
        shutil.copy2(restored[key]['path'], destination)
        restored[key]['path'] = str(destination)
    request = tmp_path/'verify.json'
    request.write_text(json.dumps(restored))
    result = subprocess.run([sys.executable,'-m','semantica.native_maintenance','--request-file',str(request)],
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr
    verified = json.loads(result.stdout)
    assert verified['keywordInstallation'] != original['keywordInstallation']
    assert verified['counts'] == original['counts']
    with sqlite3.connect(restored['keyword']['path']) as db:
        db.execute("UPDATE metadata SET value='wrong' WHERE key='project'")
    with pytest.raises(ProcessingError,match='digest'):
        verify_native_installation(restored)


def test_rebuild_keyword_index_uses_saved_reader_and_recovers_native_receipt(tmp_path, monkeypatch):
    import semantica.native_maintenance as maintenance

    project, source, generation = 'project-1', 'source-1', 'a' * 64
    old_keyword = dict(kind='native-scalar-positions', store_id='sha256:' + '1' * 64,
        recipe_digest='sha256:' + '2' * 64)
    semantic = dict(kind='native-sqlite-vec', store_id='sha256:' + '3' * 64,
        recipe_digest='sha256:' + '4' * 64, space_id='sha256:' + '5' * 64)
    reference = dict(project=project, generation=generation, state='ready', source_count=1,
        canonical_count=0, indexes=dict(keyword=old_keyword, semantic=semantic))
    state = {'publication': copy.deepcopy(reference), 'addresses': None}

    class NativeStore:
        def __init__(self, _path): pass
        def close(self): pass

    class Publication:
        def __init__(self, _owner, _project): pass
        def status(self): return copy.deepcopy(state['publication'])
        def source_binding(self, _generation, source_id):
            assert source_id == source
            return dict(source=source, material='sha256:' + '6' * 64, representation='sha256:' + '7' * 64)
        def replace_keyword_index(self, _generation, receipt, address):
            state['publication']['indexes']['keyword'] = receipt
            state['addresses'] = address
            return copy.deepcopy(state['publication'])

    class SearchIndex:
        @staticmethod
        def native_positions_recipe_digest(): return 'sha256:' + '8' * 64
        @staticmethod
        def publish_native_positions(path, *, project, generation, readers):
            assert project == project_id and generation == expected_generation
            assert [item.source_id for item in readers] == [source]
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE sources(source TEXT,material TEXT,representation TEXT,digest TEXT)')
                db.execute('INSERT INTO sources VALUES (?,?,?,?)',
                    (source, 'sha256:' + '6' * 64, 'sha256:' + '7' * 64, 'sha256:' + '9' * 64))
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            return dict(kind='native-scalar-positions', store_id='sha256:' + digest,
                recipe_digest=SearchIndex.native_positions_recipe_digest())
        @staticmethod
        def open_native_positions(path, **_kwargs):
            db = sqlite3.connect(path)
            return SimpleNamespace(_native_db=db, close_native_positions=db.close)

    project_id, expected_generation = project, generation
    monkeypatch.setattr(maintenance, 'OxigraphStore', NativeStore, raising=False)
    monkeypatch.setattr('semantica.triplet_store.oxigraph_store.OxigraphStore', NativeStore)
    monkeypatch.setattr('semantica.triplet_store.publication_records.PublicationRecords', Publication)
    monkeypatch.setattr('semantica.explorer.search_index.GraphSearchIndex', SearchIndex)
    monkeypatch.setattr('semantica.explorer.search_index._file_identity',
        lambda path: (Path(path).stat().st_dev, Path(path).stat().st_ino, Path(path).stat().st_size,
            Path(path).stat().st_mtime_ns, Path(path).stat().st_ctime_ns))

    class Reader:
        source_id = source
        material_revision = 'sha256:' + '6' * 64
        representation_revision = 'sha256:' + '7' * 64

    class ReaderRequest:
        @classmethod
        def model_validate(cls, _value): return Reader()

    monkeypatch.setattr('semantica.semantic_query_schema.DocumentReaderRequest', ReaderRequest)
    store_path = tmp_path/'native'/'store'
    store_path.mkdir(parents=True)
    target = store_path.parent / f"keyword-{generation}-{'8' * 16}.sqlite"
    request = dict(semanticStorePath=str(store_path), publicationReference=reference,
        readers=[{}], targetPath=str(target), deadlineSeconds=10)

    first = maintenance.rebuild_keyword_index(request)
    assert first['state'] == 'rebuilt'
    assert first['generation'] == generation
    assert first['publicationReference']['indexes']['semantic'] == semantic
    assert state['addresses']['receipt'] == first['keyword']['receipt']

    request['publicationReference'] = first['publicationReference']
    second = maintenance.rebuild_keyword_index(request)
    assert second == first


def test_native_facts_corruption_is_rejected_by_owner_receipt(ready):
    store = OxigraphStore(ready['semanticStorePath'])
    quad = next(store.store.quads_for_pattern(None,store._oxigraph.NamedNode('urn:semantica:field:name'),None,None))
    store.store.remove(quad)
    store.close()
    with pytest.raises(ProcessingError,match='corrupt'):
        verify_native_installation(ready)


def test_live_store_pending_withdrawn_reference_and_cancellation(tmp_path):
    owner = OxigraphStore(tmp_path/'facts')
    status = owner.begin_publication('p',expected_generation=None,source_count=2,canonical_count=1)
    request = dict(semanticStorePath=str(tmp_path/'facts'),publicationReference=status)
    with pytest.raises(ProcessingError,match='initialize'):
        verify_native_installation(request)
    owner.close()
    assert verify_native_installation(request)['keywordInstallation'] is None
    with pytest.raises(ProcessingError,match='cancelled'):
        verify_native_installation(request,cancelled=lambda:True)
    mismatch=copy.deepcopy(request)
    mismatch['publicationReference']['canonical_count']=9
    with pytest.raises(ProcessingError,match='reference differs'):
        verify_native_installation(mismatch)


def test_withdrawn_publication_keeps_facts_but_does_not_admit_indexes(ready):
    owner=OxigraphStore(ready['semanticStorePath'])
    withdrawn=owner.withdraw_publication(ready['project'],expected_generation=ready['generation'])
    owner.close()
    request=dict(semanticStorePath=ready['semanticStorePath'],publicationReference=withdrawn)
    assert verify_native_installation(request)['state']=='verified'


def test_corrupt_embedding_receipt_rejected(ready):
    with sqlite3.connect(ready['semantic']['path']) as db:
        db.execute("UPDATE embeddings_embedding_operations SET receipt_digest='wrong'")
    with pytest.raises(ProcessingError,match='receipt corrupt'):
        verify_native_installation(ready)


def test_deleted_native_association_rejected_by_reproducible_digest(ready):
    with sqlite3.connect(ready['semantic']['path']) as db:
        identity = db.execute('SELECT vector_id,record_id,evidence_id FROM embeddings_native_ranges_records LIMIT 1').fetchone()
        assert identity is not None
        db.execute('DELETE FROM embeddings_native_ranges_records WHERE vector_id=? AND record_id=? AND evidence_id=?',identity)
    with pytest.raises(ProcessingError,match='reference digest differs'):
        verify_native_installation(ready)
