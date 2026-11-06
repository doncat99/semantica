"""Native document-reader query session for complete bounded evidence units."""
from __future__ import annotations
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from time import monotonic
from .semantic_document_reader import read_source_header,DocumentReaderBudgetError,_identity
from .semantic_worker_context import check_query_cancellation

def _location_context_cte():
    return '''WITH RECURSIVE overlap AS (
            SELECT l.ordinal,l.page FROM source_location_bounds b CROSS JOIN source_locations l ON l.ordinal=b.ordinal
                WHERE b.start_min<? AND b.start_max>?),
            admitted AS (SELECT ref FROM source_locations WHERE
                ordinal IN (SELECT ordinal FROM overlap) OR page IN (SELECT page FROM overlap WHERE page IS NOT NULL)),
            initial AS (SELECT table_id,ref FROM source_locations WHERE ref IN (SELECT ref FROM admitted)),
            selected(ref) AS (SELECT ref FROM initial UNION
                SELECT ref FROM source_locations WHERE table_id IN (SELECT table_id FROM initial WHERE table_id IS NOT NULL)
                UNION SELECT d.ref FROM selected s JOIN source_locations x ON x.ordinal=
                    (SELECT MAX(ordinal) FROM source_locations WHERE ref=s.ref)
                    JOIN source_location_dependencies d ON d.ordinal=x.ordinal)
            '''


def iter_source_context_units(request, *, start, end, audit=None):
    """Stream complete units from one bounded, ephemeral native address plan.

    Only numeric addresses and dependency keys enter TEMP; source bodies stay
    in the immutable artifact. The generator owns and closes the query session.
    """
    if type(start) is not int or type(end) is not int or not 0 <= start < end or end-start > 12_288:
        raise ValueError('native context range is invalid')
    read_source_header(request)
    source, index = Path(request.artifact.path), Path(request.reader_index.path)
    deadline, total_steps, statement_steps = monotonic()+30, 0, 0
    def progress():
        nonlocal total_steps, statement_steps
        check_query_cancellation()
        total_steps += 1000
        statement_steps += 1000
        if monotonic() > deadline or statement_steps > 200_000 or total_steps > 2_000_000:
            raise DocumentReaderBudgetError('native context session work budget exceeded')
        return 0
    with closing(sqlite3.connect(index.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA cache_size=-2048')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA temp.cache_size=-512')
        db.execute('PRAGMA temp.max_page_count=8192')
        db.set_progress_handler(progress, 1000)
        def execute(sql, params=()):
            nonlocal statement_steps, deadline
            statement_steps = 0
            deadline = monotonic()+30
            return db.execute(sql, params)
        def rows(cursor):
            nonlocal deadline
            while True:
                # Model waits between batches consume no reader execution time.
                deadline = monotonic()+30
                value = cursor.fetchone()
                if value is None:
                    return
                yield value
        try:
            execute('''CREATE TEMP TABLE context_addresses(
                ordinal INTEGER PRIMARY KEY,ref TEXT,table_id TEXT,is_cell INTEGER,
                row_start INTEGER,row_end INTEGER,shared INTEGER)''')
            execute(_location_context_cte()+''' INSERT INTO context_addresses
                SELECT ordinal,ref,table_id,json_extract(descriptor,'$.cell') IS NOT NULL,
                    json_extract(descriptor,'$.structure.start_row_offset_idx'),
                    MAX(json_extract(descriptor,'$.structure.start_row_offset_idx')+1,
                        COALESCE(json_extract(descriptor,'$.structure.end_row_offset_idx'),
                            json_extract(descriptor,'$.structure.start_row_offset_idx')+1)),
                    COALESCE(json_extract(descriptor,'$.structure.column_header'),0)
                        OR COALESCE(json_extract(descriptor,'$.structure.row_section'),0)
                FROM source_locations WHERE ref IN (SELECT ref FROM selected)
                AND NOT (table_id IS NOT NULL AND json_extract(descriptor,'$.cell') IS NULL)''', (end,start))
            execute('CREATE INDEX temp.context_ref ON context_addresses(ref)')
            execute('CREATE INDEX temp.context_table_shared ON context_addresses(table_id,shared,ordinal)')
            execute('CREATE INDEX temp.context_table_row ON context_addresses(table_id,row_start)')
            execute('CREATE VIRTUAL TABLE temp.context_row_bounds USING rtree_i32(ordinal,row_min,row_max)')
            execute('INSERT INTO context_row_bounds SELECT ordinal,row_start,row_end FROM context_addresses WHERE is_cell AND NOT shared')
            execute('CREATE TEMP TABLE context_notes(table_id TEXT,ref TEXT,PRIMARY KEY(table_id,ref)) WITHOUT ROWID')
            execute('''INSERT OR IGNORE INTO context_notes
                SELECT a.table_id,json_extract(j.value,'$."$ref"') FROM context_addresses a
                JOIN source_locations l ON l.ordinal=a.ordinal,
                json_each(l.descriptor,'$.structure.captions') j WHERE a.is_cell
                AND json_extract(j.value,'$."$ref"') IS NOT NULL''')
            execute('''INSERT OR IGNORE INTO context_notes
                SELECT a.table_id,json_extract(j.value,'$."$ref"') FROM context_addresses a
                JOIN source_locations l ON l.ordinal=a.ordinal,
                json_each(l.descriptor,'$.structure.footnotes') j WHERE a.is_cell
                AND json_extract(j.value,'$."$ref"') IS NOT NULL''')
            units = execute('''SELECT kind,first,table_id,row_start FROM (
                SELECT 0 AS kind,ordinal AS first,NULL AS table_id,NULL AS row_start
                    FROM context_addresses WHERE NOT is_cell OR table_id IS NULL
                UNION ALL SELECT 1,t.first,t.table_id,r.row_start
                    FROM (SELECT table_id,MIN(ordinal) AS first FROM context_addresses WHERE is_cell GROUP BY table_id) t
                    LEFT JOIN (SELECT DISTINCT table_id,row_start FROM context_addresses WHERE is_cell AND NOT shared) r
                    ON r.table_id=t.table_id)
                ORDER BY kind,first,row_start''')
            for kind, ordinal, table, row in rows(units):
                check_query_cancellation()
                if kind:
                    sql = '''SELECT l.ordinal,l.descriptor FROM source_locations l WHERE l.ordinal IN (
                        SELECT ordinal FROM context_addresses WHERE table_id=? AND shared=1
                        UNION SELECT a.ordinal FROM context_row_bounds b
                            CROSS JOIN context_addresses a ON a.ordinal=b.ordinal
                            WHERE b.row_min<=? AND b.row_max>? AND a.table_id=?
                        UNION SELECT a.ordinal FROM context_notes n JOIN context_addresses a ON a.ref=n.ref
                            WHERE n.table_id=?) ORDER BY l.ordinal'''
                    params = (table,row,row,table,table)
                    if audit is not None and 'rowQueryPlan' not in audit:
                        audit['rowQueryPlan'] = [list(item) for item in execute('EXPLAIN QUERY PLAN '+sql,params)]
                else:
                    sql = '''SELECT l.ordinal,l.descriptor FROM context_addresses a
                        JOIN source_locations l ON l.ordinal=a.ordinal
                        WHERE a.ref=(SELECT ref FROM context_addresses WHERE ordinal=?) ORDER BY l.ordinal'''
                    params = (ordinal,)
                def addresses(sql=sql, params=params):
                    for address_ordinal, encoded in rows(execute(sql,params)):
                        check_query_cancellation()
                        if len(encoded.encode()) > min(16*1024,request.selection.max_bytes):
                            raise DocumentReaderBudgetError('native location descriptor exceeds budget')
                        item=json.loads(encoded)
                        item['sourceLocationOrdinal']=address_ordinal
                        yield item
                yield addresses()
            for path, ref in ((source,request.artifact),(index,request.reader_index)):
                if ref.installation.identity != _identity(path):
                    raise ValueError('document reader installation changed during reading')
        except sqlite3.Error as exc:
            raise DocumentReaderBudgetError('native context query exceeds bounded work or temporary storage') from exc
        finally:
            db.set_progress_handler(None,0)
            if audit is not None:
                audit.update(vmSteps=total_steps,temporaryPages=db.execute('PRAGMA temp.page_count').fetchone()[0],
                    pageBytes=db.execute('PRAGMA temp.page_size').fetchone()[0],closureExecutions=1)
