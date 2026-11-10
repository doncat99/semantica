"""Native query uses accepted vectors in place and source scope before KNN."""
import copy

import pytest

from semantica.vector_store.sqlite_vec_store import SQLiteVecStore
from semantica.utils.exceptions import ProcessingError, ValidationError
from tests.vector_store.test_embedding_handoff import SPACE, BINDING, RECEIPT


def test_publication_preserves_boundary_joins_and_rejects_extent_damage(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.sqlite'), SPACE, 3)
    binding = {**BINDING, 'ranges': [[4, 12]]}
    adopted = owner.adopt_embedding(binding, [[1., 0., 0.]], RECEIPT, accepted_digest='paid')
    link = dict(vector_id=adopted['ids'][0], binding=binding,
        ranges=[dict(nativeRef='#/document/sections/1/text', start=0, end=6, joinBefore='\n\n')])
    try:
        owner.publish_native_ranges('project-1', 'g', [link])
        damaged = copy.deepcopy(link)
        damaged['ranges'][0]['joinBefore'] = '\n'
        with pytest.raises(ValidationError, match='extent'):
            owner.publish_native_ranges('project-1', 'next', [damaged])
        assert owner._conn.execute('SELECT generation FROM embeddings_native_publications').fetchone() == ('g',)
        link['ranges'] = [dict(nativeRef='#/document/sections/0/text', start=0, end=6, joinAfter='\n\n')]
        owner.publish_native_ranges('project-1', 'next', [link])
        damaged = copy.deepcopy(link)
        damaged['ranges'][0]['joinAfter'] = 'xx'
        with pytest.raises(ValidationError, match='invalid'):
            owner.publish_native_ranges('project-1', 'bad', [damaged])
    finally:
        owner.close()


def test_identity_migration_invalidates_old_publication_and_republishes_same_vectors(tmp_path):
    from semantica.vector_store.sqlite_vec_store import EmbeddingSpaceStaleError
    path = str(tmp_path/'vectors.sqlite')
    owner = SQLiteVecStore.open_embedding_space(path,SPACE,3)
    adopted = owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='paid')
    def links(binding):
        return [dict(vector_id=identity,binding=binding,
            ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
            for identity,(start,end) in zip(adopted['ids'],BINDING['ranges'])]
    receipt = owner.publish_native_ranges('project-1','generation-1',links(BINDING))
    prior = owner._conn.execute('SELECT * FROM embeddings_native_publications').fetchall()
    stale = SQLiteVecStore.open_embedding_space(path,SPACE)
    space = {**SPACE,'binding':'new-space','recipe':'new-recipe'}
    binding = {**BINDING,'space':space['binding'],'recipe':space['recipe']}
    owner.migrate_embedding_identity(space,[dict(previous=BINDING,current=binding)])
    assert owner.embedding_physical_operation_id(binding) == SQLiteVecStore.embedding_operation_id(BINDING)
    assert owner._conn.execute('SELECT * FROM embeddings_native_publications').fetchall() == prior
    with pytest.raises(EmbeddingSpaceStaleError):
        stale.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)
    with pytest.raises(EmbeddingSpaceStaleError):
        stale.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='paid')
    with pytest.raises(ValidationError,match='receipt differs'):
        owner.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)
    current_receipt = owner.publish_native_ranges('project-1','generation-2',links(binding))
    hits = owner.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-2',receipt=current_receipt)
    assert {hit['id'] for hit in hits} == set(adopted['ids'])
    assert owner.read_embedding(binding) == adopted
    assert owner.adopt_embedding(binding,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='paid') == adopted
    assert owner.count() == 2
    stale.close()
    owner.close()


def native_records_fixture(path, rows):
    """Accept real native operations and publish only indexed address links."""
    owner=SQLiteVecStore.open_embedding_space(str(path),SPACE,3)
    links=[]
    references={}
    for n,(vector,source,records) in enumerate(rows):
        binding={**BINDING,'source':source,'ranges':[[n,n+1]]}
        adopted=owner.adopt_embedding(binding,[vector],RECEIPT,accepted_digest='accepted:'+str(n))
        identity=adopted['ids'][0]
        links.append(dict(vector_id=identity,binding=binding,
            ranges=[dict(nativeRef='#/document/text',start=n,end=n+1)]))
        references[identity]=[dict(id=record,evidence='urn:evidence:'+record,source=source) for record in records]
    receipt=owner.publish_native_ranges('project-1','generation-1',links,
        record_references=lambda link:iter(references[link['vector_id']]))
    return owner,receipt


def test_native_typed_ranking_frontier_duplicates_ties_scope_and_paging(tmp_path):
    path=tmp_path/'typed.sqlite'
    rows=[([1.,0.,0.],'foreign',['urn:foreign'])]*300
    rows += [([.8,.6,0.],'own',['urn:same'])]*300
    rows += [([.6,.8,0.],'own',['urn:later'])]
    # One vector's >128 typed facts page independently of its vector count.
    rows += [([1.,0.,0.],'own',[f'urn:tie:{n:04d}' for n in range(150)])]
    owner,receipt=native_records_fixture(path,rows)
    owner.close()
    owner=SQLiteVecStore.open_embedding_space(str(path),SPACE)
    args=dict(project='project-1',generation='generation-1',receipt=receipt,
        source_ids=['own'],top_k=1000,page_limit=128)
    first=owner.search_native_records([1.,0.,0.],**args)
    second=owner.search_native_records([1.,0.,0.],offset=128,**args)
    ids=[row['id'] for row in first+second]
    assert ids == [f'urn:tie:{n:04d}' for n in range(150)]+['urn:same','urn:later']
    assert len(ids)==len(set(ids))
    assert all(hit['sourceIds']==['own'] and hit['evidenceIds'] for hit in first+second)
    assert owner.search_native_records([1.,0.,0.],**{**args,'source_ids':[]})==[]
    assert owner._conn.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'knn_%'").fetchall()==[]
    columns=[row[1] for row in owner._conn.execute('PRAGMA table_info(embeddings_native_ranges_records)')]
    assert columns==['project','generation','vector_id','record_id','evidence_id','source']
    owner.close()


def test_native_vector_publication_restart_scope_and_no_vector_copy(tmp_path):
    path = str(tmp_path/'vectors.sqlite')
    owner = SQLiteVecStore.open_embedding_space(path,SPACE,3)
    adopted = owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='accepted')
    links = [dict(vector_id=identity,binding=BINDING,
        ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
        for identity,(start,end) in zip(adopted['ids'],BINDING['ranges'])]
    receipt = owner.publish_native_ranges('project-1','generation-1',links)
    assert owner.count() == 2
    owner.close()
    owner = SQLiteVecStore.open_embedding_space(path,SPACE)
    result = owner.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)
    assert len(result)==2 and result[0]['id']==adopted['ids'][0]
    assert result[0]['ranges']==links[0]['ranges']
    assert owner.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt,source_ids=['other'])==[]
    assert owner.count()==2
    with pytest.raises(ProcessingError,match='stale'):
        owner.search_native_ranges([1.,0.,0.],project='project-1',generation='wrong',receipt=receipt)
    bad = copy.deepcopy(links)
    bad[0]['ranges'][0]['end'] += 1
    with pytest.raises(ValidationError,match='extent'):
        owner.publish_native_ranges('project-1','generation-2',bad)
    # Failed replacement leaves both ready metadata and original links intact.
    assert len(owner.search_native_ranges([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt))==2
    owner.close()


def test_publication_checks_each_contiguous_paid_batch_once_without_float_expansion(tmp_path,monkeypatch):
    owner=SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.sqlite'),SPACE,3)
    try:
        adopted=owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='accepted')
        links=[dict(vector_id=identity,binding=BINDING,
            ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
            for identity,(start,end) in zip(adopted['ids'],BINDING['ranges'])]
        original=owner._read_embedding
        reads=[]
        def checked(conn,identity,*,include_vectors=True):
            assert include_vectors is False, 'publication expanded unused vector bodies'
            reads.append(identity)
            return original(conn,identity,include_vectors=include_vectors)
        monkeypatch.setattr(owner,'_read_embedding',checked)
        owner.publish_native_ranges('project-1','generation-1',links)
        assert len(reads)==1
        owner._conn.execute('UPDATE embeddings SET embedding=? WHERE id=?',
            (b'\0'*12,adopted['ids'][1]))
        with pytest.raises(ProcessingError,match='digest differs'):
            owner.publish_native_ranges('project-1','generation-2',links)
    finally:
        owner.close()


def test_native_vector_scope_participates_in_knn_not_postfilter(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'vectors.sqlite'),SPACE,3)
    a = owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='a')
    other = {**BINDING,'source':'source-2'}
    b = owner.adopt_embedding(other,[[0.,0.,1.],[0.,0.,1.]],RECEIPT,accepted_digest='b')
    links = [dict(vector_id=identity,binding=binding,
        ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
        for binding,adopted in [(BINDING,a),(other,b)]
        for identity,(start,end) in zip(adopted['ids'],binding['ranges'])]
    receipt = owner.publish_native_ranges('project-1','g',links)
    result = owner.search_native_ranges([1.,0.,0.],project='project-1',generation='g',receipt=receipt,top_k=1,source_ids=['source-2'])
    assert len(result)==1 and result[0]['sourceId']=='source-2'
    owner.close()


def test_native_publication_digest_is_independent_of_producer_order(tmp_path):
    owner = SQLiteVecStore.open_embedding_space(str(tmp_path/'ordered.sqlite'),SPACE,3)
    adopted = owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='accepted')
    links = [dict(vector_id=identity,binding=BINDING,
        ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
        for identity,(start,end) in zip(adopted['ids'],BINDING['ranges'])]
    references = [dict(id='urn:record:'+str(n),evidence='urn:evidence:'+str(n),source=BINDING['source'])
        for n in range(3)]
    receipt = owner.publish_native_ranges('project-1','generation-1',links,
        record_references=lambda _:iter(references))
    reversed_receipt = owner.publish_native_ranges('project-1','generation-1',reversed(links),
        record_references=lambda _:reversed(references))
    assert receipt == reversed_receipt
    digest,count = owner.native_publication_digest(owner._conn,'project-1','generation-1',check=lambda:None)
    assert digest == receipt['store_id'] and count == len(links)
    owner.close()


def test_native_record_evidence_pages_all_references_without_sampling(tmp_path):
    owner=SQLiteVecStore.open_embedding_space(str(tmp_path/'evidence.sqlite'),SPACE,3)
    adopted=owner.adopt_embedding(BINDING,[[1.,0.,0.],[0.,1.,0.]],RECEIPT,accepted_digest='accepted')
    links=[dict(vector_id=identity,binding=BINDING,
        ranges=[dict(nativeRef='#/document/text',start=start,end=end)])
        for identity,(start,end) in zip(adopted['ids'],BINDING['ranges'])]
    receipt=owner.publish_native_ranges('project-1','generation-1',links,
        record_references=lambda link:(dict(id='urn:record',evidence=f'urn:evidence:{n:04d}',source='source-1')
            for n in range(257)))
    hit=owner.search_native_records([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)[0]
    assert len(hit['evidenceIds'])==128 and hit['evidenceNextCursor']
    identities=list(hit['evidenceIds'])
    cursor=hit['evidenceNextCursor']
    while cursor:
        page=owner.read_native_evidence(project='project-1',generation='generation-1',receipt=receipt,
            identity='urn:record',source_ids=['source-1'],after=cursor)
        assert len(page['items'])<=128
        identities.extend(item['id'] for item in page['items'])
        cursor=page['nextCursor']
    assert identities==[f'urn:evidence:{n:04d}' for n in range(257)]
    assert owner.read_native_evidence(project='project-1',generation='generation-1',receipt=receipt,
        identity='urn:record',source_ids=[])==dict(items=[],nextCursor=None)
    with pytest.raises(ProcessingError,match='stale'):
        owner.read_native_evidence(project='project-1',generation='wrong',receipt=receipt,identity='urn:record')
    owner.close()


def test_native_record_query_cancellation_cleans_scratch_and_next_request_runs(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from threading import Event
    from semantica.semantic_worker_context import query_cancellation
    owner,receipt=native_records_fixture(tmp_path/'cancel.sqlite',
        [([1.,0.,0.],'own',[f'urn:{n:04d}']) for n in range(512)])
    connection=owner._conn
    event=Event()
    class CancelingConnection:
        def __getattr__(self,name):
            return getattr(connection,name)
        def set_progress_handler(self,callback,interval):
            def cancel():
                event.set()
                return callback()
            connection.set_progress_handler(cancel if callback else None,min(interval,10))
    @contextmanager
    def canceling_connection():
        yield CancelingConnection()
    token=query_cancellation.set(event)
    args=dict(project='project-1',generation='generation-1',receipt=receipt,top_k=1,source_ids=['own'])
    try:
        with monkeypatch.context() as patch:
            patch.setattr(owner,'_get_connection',canceling_connection)
            with pytest.raises(ProcessingError,match='canceled'):
                owner.search_native_records([1.,0.,0.],**args)
        assert connection.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'knn_%'").fetchall()==[]
        assert connection.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000) SELECT sum(x) FROM n').fetchone()[0]==50005000
        event.clear()
        assert owner.search_native_records([1.,0.,0.],**args)[0]['id']=='urn:0000'
    finally:
        query_cancellation.reset(token)
        owner.close()


def test_native_record_query_scratch_budget_is_enforced_and_reusable(tmp_path,monkeypatch):
    import semantica.vector_store.sqlite_vec_store as module
    owner,receipt=native_records_fixture(tmp_path/'scratch.sqlite',
        [([1.,0.,0.],'own',[f'urn:{n:04d}']) for n in range(300)])
    args=dict(project='project-1',generation='generation-1',receipt=receipt,top_k=1)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(module,'_NATIVE_QUERY_TEMP_BYTES',8192,raising=False)
            with pytest.raises(ProcessingError,match='scratch.*budget'):
                owner.search_native_records([1.,0.,0.],**args)
        assert owner._conn.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'knn_%'").fetchall()==[]
        assert owner.search_native_records([1.,0.,0.],**args)[0]['id']=='urn:0000'
        db=owner._conn
        page_size=db.execute('PRAGMA temp.page_size').fetchone()[0]
        assert db.execute('PRAGMA temp.max_page_count').fetchone()[0]*page_size<=32*1024*1024
        assert db.execute('PRAGMA temp.cache_size').fetchone()[0]==-512
        assert db.execute('PRAGMA cache_size').fetchone()[0]==-8192
    finally:
        owner.close()


def test_native_record_query_enforces_three_seconds_after_native_knn(tmp_path,monkeypatch):
    from contextlib import contextmanager
    import semantica.vector_store.sqlite_vec_store as module
    owner,receipt=native_records_fixture(tmp_path/'deadline.sqlite',[([1.,0.,0.],'own',['urn:one'])])
    connection=owner._conn
    now=[0.]
    class SlowNativeConnection:
        def __getattr__(self,name):
            return getattr(connection,name)
        def execute(self,sql,*args):
            cursor=connection.execute(sql,*args)
            if 'embedding MATCH' in sql:
                now[0]=3.01
            return cursor
    @contextmanager
    def slow_connection():
        yield SlowNativeConnection()
    args=dict(project='project-1',generation='generation-1',receipt=receipt,top_k=1)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(module.time,'monotonic',lambda:now[0])
            patch.setattr(owner,'_get_connection',slow_connection)
            with pytest.raises(ProcessingError,match='execution budget'):
                owner.search_native_records([1.,0.,0.],**args)
        assert connection.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'knn_%'").fetchall()==[]
        assert owner.search_native_records([1.,0.,0.],**args)[0]['id']=='urn:one'
    finally:
        owner.close()


def test_native_record_cleanup_preserves_primary_error(tmp_path,monkeypatch,caplog):
    import sqlite3
    from contextlib import contextmanager
    owner,receipt=native_records_fixture(tmp_path/'cleanup.sqlite',[([1.,0.,0.],'own',['urn:one'])])
    connection=owner._conn
    original=ProcessingError('original query failure')
    class BrokenCleanupConnection:
        def __getattr__(self,name):
            return getattr(connection,name)
        def executescript(self,sql):
            if 'CREATE TEMP TABLE' in sql:
                raise original
            raise sqlite3.OperationalError('cleanup failure')
    @contextmanager
    def broken_connection():
        yield BrokenCleanupConnection()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(owner,'_get_connection',broken_connection)
            with pytest.raises(ProcessingError) as raised:
                owner.search_native_records([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)
        assert raised.value is original
        assert 'Native record scratch cleanup failed' in caplog.text
        assert owner.search_native_records([1.,0.,0.],project='project-1',generation='generation-1',receipt=receipt)[0]['id']=='urn:one'
    finally:
        owner.close()
