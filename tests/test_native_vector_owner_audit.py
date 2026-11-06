"""Native accepted-vector query survives an actual process boundary."""
import os
from pathlib import Path
import subprocess
import sys


def test_native_reference_scope_and_vectors_survive_process_restart(tmp_path):
    root=Path(__file__).resolve().parents[1]
    common='''
import sys
from pathlib import Path
from tests.vector_store.test_native_range_publication import native_records_fixture
from tests.vector_store.test_embedding_handoff import SPACE
from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
path=Path(sys.argv[1])/'vectors.sqlite'
'''
    steps=['''
owner,receipt=native_records_fixture(path,
    [([1.,0.,0.],'foreign',['urn:foreign'])]*300+
    [([.8,.6,0.],'own',['urn:own:1']),([.6,.8,0.],'own',['urn:own:2'])])
owner.close()
''','''
owner=SQLiteVecStore.open_embedding_space(str(path),SPACE)
generation,digest,recipe=owner._conn.execute(
    'SELECT generation,digest,recipe FROM embeddings_native_publications WHERE project=?',('project-1',)).fetchone()
receipt=dict(kind='native-sqlite-vec',store_id=digest,recipe_digest=recipe,space_id=SPACE['binding'])
traced=[]
owner._conn.set_trace_callback(traced.append)
args=dict(project='project-1',generation=generation,receipt=receipt,top_k=2)
hits=owner.search_native_records([1.,0.,0.],source_ids=['own'],**args)
assert [hit['id'] for hit in hits]==['urn:own:1','urn:own:2']
assert owner.search_native_records([1.,0.,0.],source_ids=[],**args)==[]
assert owner.search_native_records([1.,0.,0.],source_ids=['missing'],**args)==[]
assert owner.count()==302
assert any('embedding MATCH' in sql and 'knn_scope' in sql for sql in traced)
assert not any('SELECT id, embedding, metadata' in sql for sql in traced)
assert owner._conn.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'knn_%'").fetchall()==[]
owner.close()
''']
    for step in steps:
        result=subprocess.run([sys.executable,'-c',common+step,str(tmp_path)],cwd=root,
            env={**os.environ,'PYTHONPATH':str(root)},text=True,capture_output=True,timeout=30)
        assert result.returncode==0,result.stdout+result.stderr
