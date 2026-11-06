"""Offline restore admission uses native receipts, never a rebuilt graph."""
import copy
import json
import shutil
import sqlite3
import subprocess
import sys

import pytest

from semantica.native_maintenance import verify_native_installation
from semantica.triplet_store.oxigraph_store import OxigraphStore
from semantica.utils.exceptions import ProcessingError
from tests.test_native_extraction_handoff import build_child


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
