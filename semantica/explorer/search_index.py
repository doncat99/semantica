"""
Explorer-local in-memory node search index.
"""

from __future__ import annotations

import bisect
import heapq
import re
import json
import logging
import sqlite3
import sys
import time
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_CURATED_ALIAS_KEYS = (
    "label",
    "name",
    "title",
    "pref_label",
    "preferred_label",
    "prefLabel",
    "aliases",
    "alias",
    "synonyms",
    "synonym",
    "symbol",
    "display_name",
    "displayName",
    "text",
    "content",
)


def _file_identity(path: Path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
def _original_position(start, expansions, position, end=False):
    delta = 0
    for char_index, folded_start, width in json.loads(expansions):
        if position < folded_start:
            break
        if position < folded_start + width:
            return start + char_index + int(end and position > folded_start)
        delta += width - 1
    return start + position - delta


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text)


def _tokenize(text: str) -> Tuple[str, ...]:
    if not text:
        return ()
    return tuple(dict.fromkeys(_TOKEN_RE.findall(text)))


def _collect_text_fragments(value: Any, fragments: List[str], *, limit: int = 64) -> None:
    if value is None or len(fragments) >= limit:
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_text_fragments(nested, fragments, limit=limit)
            if len(fragments) >= limit:
                return
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            _collect_text_fragments(nested, fragments, limit=limit)
            if len(fragments) >= limit:
                return
        return

    normalized = _normalize_text(value)
    if normalized:
        fragments.append(normalized)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class IndexedNodeDocument:
    node_id: str
    normalized_id: str
    node_type: str
    exact_terms: frozenset[str]
    primary_text: str
    secondary_text: str
    confidence: Optional[float]
    tags: Tuple[str, ...]

    @cached_property
    def tokens(self) -> frozenset[str]:
        return frozenset(_tokenize(self.primary_text))


class GraphSearchIndex:
    @staticmethod
    def publish_native_positions(index_path, *, project, generation, readers):
        """Maintenance traversal over native reader pages; persist lexical features only.

        Reader requests carry the already installed immutable source identities.
        No flattened document, graph or vector carrier is admitted by this owner.
        A partial build is never returned as an installed receipt.
        """
        from hashlib import file_digest
        from ..semantic_document_reader import read_document_reader
        from ..semantic_worker_context import check_query_cancellation
        index_path = Path(index_path)
        if index_path.exists():
            raise ValueError('native position publication target already exists')
        if any(not isinstance(v, str) or not v or len(v.encode()) > 4096 for v in (project, generation)):
            raise ValueError('native position publication identity is invalid')
        recipe = sha256(b'GraphSearchIndex:native-scalar-literal-positions').hexdigest()
        try:
            with closing(sqlite3.connect(index_path)) as db, db:
                db.execute('PRAGMA cache_size=-2048')
                db.executescript('''
                    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
                    CREATE TABLE sources(source TEXT PRIMARY KEY,material TEXT,representation TEXT,digest TEXT) WITHOUT ROWID;
                    CREATE TABLE terms(id INTEGER PRIMARY KEY,term TEXT NOT NULL UNIQUE);
                    CREATE TABLE grams(gram TEXT,term INTEGER,PRIMARY KEY(gram,term)) WITHOUT ROWID;
                    CREATE TABLE positions(source TEXT,ref TEXT,ordinal INTEGER,scalar INTEGER,term INTEGER,
                        start INTEGER,end INTEGER,expansions TEXT,locator TEXT,
                        PRIMARY KEY(source,ref,ordinal)) WITHOUT ROWID;
                    CREATE INDEX positions_term ON positions(term,source,scalar,ordinal);
                ''')
                db.executemany('INSERT INTO metadata VALUES (?,?)',
                    [('project', project), ('generation', generation), ('recipe', recipe)])
                def intern(token):
                    row = db.execute('SELECT id FROM terms WHERE term=?', (token,)).fetchone()
                    if row:
                        return row[0]
                    term_id = db.execute('INSERT INTO terms(term) VALUES (?)', (token,)).lastrowid
                    # Indexed literal substring candidates for short queries too.
                    for width in (1, 2, 3):
                        db.executemany('INSERT INTO grams VALUES (?,?)',
                            ((gram, term_id) for gram in sorted({token[n:n+width] for n in range(len(token)-width+1)})))
                    return term_id
                for reader in readers:
                    check_query_cancellation()
                    source = reader.source_id
                    db.execute('INSERT INTO sources VALUES (?,?,?,?)', (source,
                        reader.material_revision, reader.representation_revision, reader.artifact.digest))
                    after, active_ref, expected_start, ordinal, pending, pending_start = -1, None, 0, 0, '', 0
                    scalar = -1
                    pending_locator = {}
                    def emit_token(token, start, locator):
                        nonlocal ordinal
                        if len(token.encode()) > 65536:
                            raise ValueError('native positional token exceeds 64 KiB')
                        expansion, folded = [], 0
                        for n, char in enumerate(token):
                            width = len(char.lower())
                            if width != 1:
                                expansion.append((n, folded, width))
                            folded += width
                        db.execute('INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?)',
                            (source, active_ref, ordinal, scalar, intern(token.lower()), start, start+len(token),
                             json.dumps(expansion), json.dumps(locator, ensure_ascii=False)))
                        ordinal += 1
                    while True:
                        selection = reader.selection.model_copy(update={'field':'chunks', 'after':after,
                            'limit':128, 'max_bytes':262144, 'page_number':None})
                        page = read_document_reader(reader.model_copy(update={'selection':selection}))
                        for item in page['items']:
                            check_query_cancellation()
                            locator, text = item['locator'], item['text']
                            ref, start = locator['nativeRef'], locator['startChar']
                            if ref != active_ref:
                                if pending:
                                    emit_token(pending, pending_start, pending_locator)
                                active_ref, expected_start, ordinal, pending = ref, 0, 0, ''
                                scalar += 1
                            if start != expected_start:
                                raise ValueError('native position reader ranges are not contiguous')
                            expected_start = locator['endChar']
                            value = pending + text
                            base = pending_start if pending else start
                            matches = list(re.finditer(r'\s+|\S+', value))
                            pending = ''
                            for n, match in enumerate(matches):
                                if n == len(matches)-1:
                                    pending, pending_start = match.group(), base+match.start()
                                    pending_locator = {**locator, 'startChar':pending_start}
                                    if len(pending.encode()) > 65536:
                                        raise ValueError('native positional token exceeds 64 KiB')
                                else:
                                    emit_token(match.group(), base+match.start(), locator)
                        if page['nextCursor'] is None:
                            break
                        after = page['nextCursor']
                    if pending:
                        emit_token(pending, pending_start, pending_locator)
            with index_path.open('rb') as stream:
                store_id = 'sha256:' + file_digest(stream, 'sha256').hexdigest()
            return {'kind':'native-scalar-positions', 'store_id':store_id, 'recipe_digest':recipe}
        except BaseException:
            index_path.unlink(missing_ok=True)
            raise

    @classmethod
    def open_native_positions(cls, index_path, *, project, generation, receipt, installation_identity):
        """Admit a trusted installation using small metadata, without rehashing it."""
        path = Path(index_path)
        if tuple(installation_identity) != _file_identity(path):
            raise ValueError('native position installation identity changed')
        if (set(receipt) != {'kind','store_id','recipe_digest'}
                or receipt['kind'] != 'native-scalar-positions'
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', receipt['store_id'])):
            raise ValueError('native position receipt identity is invalid')
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            db.execute('PRAGMA cache_size=-2048')
            metadata = dict(db.execute('SELECT key,value FROM metadata LIMIT 4'))
            if metadata != {'project':project, 'generation':generation, 'recipe':receipt['recipe_digest']}:
                raise ValueError('native position publication identity differs')
            owner = cls()
            owner._native_db, owner._native_path, owner._native_identity = db, path, tuple(installation_identity)
            db.create_function('original_position', 3, _original_position)
            return owner
        except BaseException:
            db.close()
            raise

    def close_native_positions(self):
        self._native_db.close()

    def search_native_positions(self, query, *, source_ids=None, limit=128, after=None, navigation='next'):
        """Return exact occurrence addresses, scoped before retrieval; never bodies."""
        from ..semantic_worker_context import check_query_cancellation
        if (not isinstance(query, str) or not query or len(query.encode()) > 1024
                or (source_ids is not None and (not isinstance(source_ids, (tuple,list)) or len(source_ids) > 128
                    or any(not isinstance(s, str) or not s or len(s.encode()) > 4096 for s in source_ids)))
                or type(limit) is not int or not 1 <= limit <= 128):
            raise ValueError('native keyword query scope or budget is invalid')
        if after is not None and (not isinstance(after, (tuple,list)) or len(after) != 4
                or any(type(n) is not int or n < 0 for n in after[2:])):
            raise ValueError('native keyword continuation is invalid')
        if navigation not in {'next','previous','next_source','previous_source','next_page','previous_page'}:
            raise ValueError('native keyword navigation is invalid')
        if _file_identity(self._native_path) != self._native_identity:
            raise ValueError('native position installation identity changed')
        if source_ids == []:
            return {'items':[], 'total':0, 'nextCursor':None, 'previousCursor':None, 'startOffset':0}
        deadline = time.monotonic() + 3
        def check():
            check_query_cancellation()
            if time.monotonic() > deadline:
                raise TimeoutError('native keyword query exceeded 3 second budget')
            return 0
        db = self._native_db
        try:
            db.set_progress_handler(check, 1000)
            pieces = re.findall(r'\s+|\S+', query.lower())
            anchor = max(range(len(pieces)), key=lambda n:len(pieces[n]))
            word = pieces[anchor]
            # TEMP state is per bounded query, not durable source content.
            db.execute('DROP TABLE IF EXISTS temp.native_candidates')
            db.execute('CREATE TEMP TABLE native_candidates(term INTEGER,relative INTEGER,PRIMARY KEY(term,relative)) WITHOUT ROWID')
            for term_id, term in db.execute('SELECT t.id,t.term FROM grams g JOIN terms t ON t.id=g.term WHERE g.gram=? AND instr(t.term,?)>0', (word[:3], word)):
                check()
                relative = term.find(word)
                while relative >= 0:
                    if len(pieces)==1 or (anchor==0 and relative+len(word)==len(term)) or (anchor==len(pieces)-1 and relative==0) or (0<anchor<len(pieces)-1 and term==word):
                        db.execute('INSERT INTO native_candidates VALUES (?,?)', (term_id,relative))
                    relative = term.find(word,relative+1)
            predicate = '1' if source_ids is None else 'p.source IN (' + ','.join('?' for _ in source_ids) + ')'
            params = list(source_ids or [])
            for n, piece in enumerate(pieces):
                role = 'substr(t.term,-length(?))=?' if n==0 else 'substr(t.term,1,length(?))=?' if n==len(pieces)-1 else 't.term=?'
                if len(pieces)==1:
                    break
                predicate += ' AND EXISTS(SELECT 1 FROM positions x JOIN terms t ON t.id=x.term WHERE x.source=p.source AND x.ref=p.ref AND x.ordinal=p.ordinal+? AND '+role+')'
                params.extend([n-anchor, piece, *([piece] if n in (0,len(pieces)-1) else [])])
            joins = ' FROM native_candidates c CROSS JOIN positions p INDEXED BY positions_term ON p.term=c.term WHERE '+predicate
            total = db.execute('SELECT count(*)'+joins, params).fetchone()[0]
            backward = navigation.startswith('previous')
            comparison = '<' if backward else '>'
            cursor_sql, cursor_params = '', []
            if after is not None:
                if navigation.endswith('_source'):
                    cursor_sql, cursor_params = ' AND p.source'+comparison+'?', [after[0]]
                elif navigation.endswith('_page'):
                    row = db.execute('SELECT json_extract(locator,\'$.page\') FROM positions WHERE source=? AND ref=? AND ordinal=?', after[:3]).fetchone()
                    if row is None or row[0] is None:
                        raise ValueError('native keyword position has no page navigation address')
                    cursor_sql, cursor_params = (' AND p.source=? AND json_extract(p.locator,\'$.page\')'+comparison+'?', [after[0],row[0]])
                else:
                    scalar_row = db.execute('SELECT scalar FROM positions WHERE source=? AND ref=? AND ordinal=?',after[:3]).fetchone()
                    if scalar_row is None:
                        raise ValueError('native keyword cursor is not an installed position')
                    cursor_sql, cursor_params = ' AND (p.source,p.scalar,p.ordinal,c.relative)'+comparison+'(?,?,?,?)', [after[0],scalar_row[0],*after[2:]]
            rows = db.execute('SELECT p.source,p.ref,p.ordinal,c.relative'+joins+cursor_sql+
                (' ORDER BY p.source DESC,p.scalar DESC,p.ordinal DESC,c.relative DESC' if backward else ' ORDER BY p.source,p.scalar,p.ordinal,c.relative')+
                ' LIMIT ?', [*params, *cursor_params,limit]).fetchall()
            if backward:
                rows.reverse()
            first_scalar = db.execute('SELECT scalar FROM positions WHERE source=? AND ref=? AND ordinal=?', rows[0][:3]).fetchone()[0] if rows else 0
            start_offset = db.execute('SELECT count(*)'+joins+
                ' AND (p.source,p.scalar,p.ordinal,c.relative)<(?,?,?,?)', [*params,rows[0][0],first_scalar,*rows[0][2:]]).fetchone()[0] if rows else 0
            items, byte_count = [], 0
            for source, ref, ordinal, relative in rows:
                check()
                first = db.execute('SELECT start,expansions,locator,length(t.term) FROM positions p JOIN terms t ON t.id=p.term WHERE source=? AND ref=? AND ordinal=?', (source,ref,ordinal-anchor)).fetchone()
                last = db.execute('SELECT start,expansions FROM positions WHERE source=? AND ref=? AND ordinal=?', (source,ref,ordinal-anchor+len(pieces)-1)).fetchone()
                start = _original_position(first[0],first[1],relative if len(pieces)==1 else first[3]-len(pieces[0]))
                end = _original_position(last[0],last[1],relative+len(word) if len(pieces)==1 else len(pieces[-1]),True)
                item = {'sourceId':source, 'nativeRef':ref, 'start':start, 'end':end,
                    'locator':{**json.loads(first[2]),'nativeRef':ref,'startChar':start,'endChar':end}}
                byte_count += len(json.dumps(item, ensure_ascii=False).encode())
                if byte_count > 262144:
                    raise ValueError('native keyword response exceeds byte budget')
                item['position'] = [source,ref,ordinal,relative]
                items.append(item)
            return {'items':items, 'total':total,
                'nextCursor':list(rows[-1]) if rows and start_offset+len(rows)<total else None,
                'previousCursor':list(rows[0]) if rows and start_offset>0 else None,
                'startOffset':start_offset}
        finally:
            error = sys.exc_info()[1]
            try:
                # Expired cancellation/deadline must not interrupt scratch cleanup.
                db.set_progress_handler(None,0)
                db.execute('DROP TABLE IF EXISTS temp.native_candidates')
            except sqlite3.Error:
                if error is None:
                    raise
                logging.getLogger(__name__).warning('Native keyword scratch cleanup failed', exc_info=True)

    def __init__(
        self,
        *,
        cache_size: int = 128,
        prefix_min_length: int = 2,
        prefix_max_length: int = 12,
        secondary_scan_limit: int = 12000,
    ) -> None:
        self.cache_size = cache_size
        self.prefix_min_length = prefix_min_length
        self.prefix_max_length = prefix_max_length
        self.secondary_scan_limit = secondary_scan_limit
        self._documents: Dict[str, IndexedNodeDocument] = {}
        self._exact_index: DefaultDict[str, set[str]] = defaultdict(set)
        self._token_index: DefaultDict[str, set[str]] = defaultdict(set)
        self._prefix_index: DefaultDict[str, set[str]] = defaultdict(set)
        self._ordered_node_ids: List[str] = []
        self._cache: OrderedDict[Tuple[Any, ...], List[Tuple[str, float]]] = OrderedDict()
        self._substring_index: Optional[Dict[str, set[str]]] = None
        self._ranked_ready = False

    def rebuild(self, nodes: Iterable[Dict[str, Any]]) -> None:
        self._documents.clear()
        self._exact_index.clear()
        self._token_index.clear()
        self._prefix_index.clear()
        self._ordered_node_ids = []
        self._ranked_ready = False
        self.clear_cache()

        for node in nodes:
            node_id = str(node.get("id", "")).strip()
            if node_id:
                self._documents[node_id] = self._build_document(node)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._substring_index = None

    def substring_candidates(self, words: Iterable[str]) -> set[str]:
        """Complete OR-substring candidates, without Explorer's ranked scan limits.

        Whitespace tokens retain Unicode and punctuation. A query word cannot
        cross whitespace, so searching the vocabulary preserves substring recall
        without rescanning every document. Callers retain their own native scorer.
        """
        if self._substring_index is None:
            postings: DefaultDict[str, set[str]] = defaultdict(set)
            for node_id, document in self._documents.items():
                for token in set(document.primary_text.split()) | set(document.secondary_text.split()):
                    postings[token].add(node_id)
            self._substring_index = dict(postings)
        terms = {word.lower() for word in words if word}
        matches: set[str] = set()
        for token, node_ids in self._substring_index.items():
            if any(word in token for word in terms):
                matches.update(node_ids)
        return matches

    def remove(self, node_id: str, *, clear_cache: bool = True) -> None:
        self._substring_index = None
        existing = self._documents.pop(node_id, None)
        if existing is None or not self._ranked_ready:
            if clear_cache:
                self.clear_cache()
            return

        for term in existing.exact_terms:
            bucket = self._exact_index.get(term)
            if bucket is None:
                continue
            bucket.discard(node_id)
            if not bucket:
                self._exact_index.pop(term, None)

        for token in existing.tokens:
            bucket = self._token_index.get(token)
            if bucket is None:
                continue
            bucket.discard(node_id)
            if not bucket:
                self._token_index.pop(token, None)

            for length in range(self.prefix_min_length, min(len(token), self.prefix_max_length) + 1):
                prefix = token[:length]
                prefix_bucket = self._prefix_index.get(prefix)
                if prefix_bucket is None:
                    continue
                prefix_bucket.discard(node_id)
                if not prefix_bucket:
                    self._prefix_index.pop(prefix, None)

        pos = bisect.bisect_left(self._ordered_node_ids, node_id)
        if pos < len(self._ordered_node_ids) and self._ordered_node_ids[pos] == node_id:
            self._ordered_node_ids.pop(pos)

        if clear_cache:
            self.clear_cache()

    def upsert(self, node: Dict[str, Any], *, clear_cache: bool = True) -> None:
        self._substring_index = None
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            return

        self.remove(node_id, clear_cache=False)
        document = self._build_document(node)
        self._documents[node_id] = document

        if self._ranked_ready:
            self._index_ranked_document(document)
            bisect.insort(self._ordered_node_ids, node_id)

        if clear_cache:
            self.clear_cache()

    def _index_ranked_document(self, document: IndexedNodeDocument) -> None:
        node_id = document.node_id
        for term in document.exact_terms:
            self._exact_index[term].add(node_id)

        for token in document.tokens:
            self._token_index[token].add(node_id)
            for length in range(self.prefix_min_length, min(len(token), self.prefix_max_length) + 1):
                self._prefix_index[token[:length]].add(node_id)

    def _prepare_ranked_index(self) -> None:
        if not self._ranked_ready:
            for document in self._documents.values():
                self._index_ranked_document(document)
            self._ordered_node_ids = sorted(self._documents)
            self._ranked_ready = True

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Tuple[str, float]], Dict[str, Any]]:
        normalized_query = _normalize_text(query)
        filters = filters or {}
        diagnostics: Dict[str, Any] = {
            "cache_hit": False,
            "path": "empty",
            "candidates": 0,
        }
        if not normalized_query:
            return [], diagnostics

        cache_key = self._cache_key(normalized_query, limit, filters)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            diagnostics.update({"cache_hit": True, "path": "cache", "candidates": len(cached)})
            return list(cached), diagnostics

        self._prepare_ranked_index()
        query_tokens = _tokenize(normalized_query)
        exact_ids = set(self._exact_index.get(normalized_query, set()))
        token_sets: List[set[str]] = []
        prefix_sets: List[set[str]] = []
        for token in query_tokens:
            exact_token_ids = set(self._token_index.get(token, set()))
            prefix_ids = set(self._prefix_index.get(token, set())) if len(token) >= self.prefix_min_length else set()
            if exact_token_ids:
                token_sets.append(exact_token_ids)
            if prefix_ids:
                prefix_sets.append(prefix_ids)

        candidate_ids: set[str] = set(exact_ids)
        if token_sets:
            intersected = set.intersection(*token_sets)
            candidate_ids.update(intersected if intersected else set().union(*token_sets))
        if prefix_sets:
            candidate_ids.update(set().union(*prefix_sets))

        diagnostics["path"] = "index"

        if not candidate_ids:
            diagnostics["path"] = "secondary_scan"
            candidate_ids = self._secondary_scan(normalized_query, limit)

        diagnostics["candidates"] = len(candidate_ids)

        scored: List[Tuple[float, int, int, str]] = []
        for node_id in candidate_ids:
            document = self._documents.get(node_id)
            if document is None or not self._passes_filters(document, filters):
                continue
            score = self._score_document(document, normalized_query, query_tokens)
            if score <= 0:
                continue
            token_hits = sum(1 for token in query_tokens if token in document.tokens)
            exactness = 1 if normalized_query == document.normalized_id or normalized_query in document.exact_terms else 0
            scored.append((score, exactness, token_hits, node_id))

        top_matches = heapq.nlargest(limit, scored, key=lambda item: (item[0], item[1], item[2], item[3]))
        results = [(node_id, round(score, 4)) for score, _, _, node_id in top_matches]
        self._store_cache(cache_key, results)
        return results, diagnostics

    def _secondary_scan(self, normalized_query: str, limit: int) -> set[str]:
        matches: set[str] = set()
        max_hits = max(limit * 20, 200)
        scanned = 0
        for node_id in self._ordered_node_ids:
            if scanned >= self.secondary_scan_limit or len(matches) >= max_hits:
                break
            scanned += 1
            document = self._documents.get(node_id)
            if document is None:
                continue
            if normalized_query in document.primary_text or normalized_query in document.secondary_text:
                matches.add(node_id)
        return matches

    def _score_document(
        self,
        document: IndexedNodeDocument,
        normalized_query: str,
        query_tokens: Tuple[str, ...],
    ) -> float:
        score = 0.0
        if normalized_query == document.normalized_id:
            score = max(score, 140.0)
        elif normalized_query in document.exact_terms:
            score = max(score, 120.0)

        if normalized_query and normalized_query in document.primary_text:
            score = max(score, 78.0 + min(len(normalized_query), 24) / 10.0)
        elif normalized_query and normalized_query in document.secondary_text:
            score = max(score, 26.0 + min(len(normalized_query), 24) / 20.0)

        token_hits = 0
        prefix_hits = 0
        for token in query_tokens:
            if token in document.tokens:
                token_hits += 1
            elif len(token) >= self.prefix_min_length and any(candidate.startswith(token) for candidate in document.tokens):
                prefix_hits += 1

        score += token_hits * 18.0
        score += prefix_hits * 10.0

        if len(query_tokens) > 1 and token_hits:
            score += token_hits * 4.0

        return score

    def _passes_filters(self, document: IndexedNodeDocument, filters: Dict[str, Any]) -> bool:
        filter_type = filters.get("type") or filters.get("node_type")
        if filter_type and document.node_type != str(filter_type):
            return False

        min_confidence = _coerce_float(filters.get("min_confidence"))
        if min_confidence is not None:
            if document.confidence is None or document.confidence < min_confidence:
                return False

        tags_filter = filters.get("tags")
        if tags_filter:
            if isinstance(tags_filter, str):
                required_tags = {_normalize_text(tags_filter)}
            else:
                required_tags = {
                    normalized
                    for normalized in (_normalize_text(tag) for tag in tags_filter)
                    if normalized
                }
            if required_tags and not required_tags.issubset(set(document.tags)):
                return False

        return True

    def _cache_key(
        self,
        normalized_query: str,
        limit: int,
        filters: Dict[str, Any],
    ) -> Tuple[Any, ...]:
        serialized_filters: List[Tuple[str, Any]] = []
        for key in sorted(filters.keys()):
            value = filters[key]
            if isinstance(value, (list, tuple, set)):
                serialized_filters.append((key, tuple(sorted(str(item) for item in value))))
            else:
                serialized_filters.append((key, str(value)))
        return normalized_query, limit, tuple(serialized_filters)

    def _store_cache(self, cache_key: Tuple[Any, ...], results: List[Tuple[str, float]]) -> None:
        self._cache[cache_key] = list(results)
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _build_document(self, node: Dict[str, Any]) -> IndexedNodeDocument:
        node_id = str(node.get("id", "")).strip()
        node_type = str(node.get("type", "entity"))
        properties = dict(node.get("properties", {}) or {})

        primary_terms: List[str] = []
        for candidate in (node_id, node.get("content", "")):
            normalized = _normalize_text(candidate)
            if normalized:
                primary_terms.append(normalized)

        for alias_key in _CURATED_ALIAS_KEYS:
            _collect_text_fragments(properties.get(alias_key), primary_terms, limit=32)

        deduped_primary_terms = tuple(dict.fromkeys(term for term in primary_terms if term))
        primary_text = " ".join(deduped_primary_terms)

        secondary_fragments: List[str] = []
        for key, value in properties.items():
            if key in _CURATED_ALIAS_KEYS or key in {"content", "valid_from", "valid_until"}:
                continue
            _collect_text_fragments(value, secondary_fragments, limit=48)
            if len(secondary_fragments) >= 48:
                break

        secondary_text = " ".join(dict.fromkeys(fragment for fragment in secondary_fragments if fragment))
        confidence = _coerce_float(properties.get("confidence"))

        raw_tags = properties.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        tags = tuple(
            dict.fromkeys(
                normalized for normalized in (_normalize_text(tag) for tag in raw_tags) if normalized
            )
        )

        return IndexedNodeDocument(
            node_id=node_id,
            normalized_id=_normalize_text(node_id),
            node_type=node_type,
            exact_terms=frozenset(deduped_primary_terms),
            primary_text=primary_text,
            secondary_text=secondary_text,
            confidence=confidence,
            tags=tags,
        )
