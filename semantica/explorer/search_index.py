"""
Explorer-local in-memory node search index.
"""

from __future__ import annotations

import bisect
import heapq
import re
import json
import sqlite3
import tempfile
from contextlib import closing, nullcontext
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from functools import cached_property
from functools import lru_cache
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


@lru_cache(maxsize=4)
def _admit_reference_file(path: Path, digest: str, identity: tuple):
    from hashlib import file_digest
    with path.open("rb") as stream:
        actual = f"sha256:{file_digest(stream, 'sha256').hexdigest()}"
    if actual != digest or _file_identity(path) != identity:
        raise ValueError("keyword artifact digest does not match or changed during admission")


class ReferenceGraphSearchIndex:
    """Read-only native index; hydrate matching canonical records, never a full graph."""

    def __init__(self, index_path: Path, index_digest: str, graph_path: Path, graph_digest: str,
                 project_id: str, snapshot_id: str):
        self.graph_path = graph_path.resolve()
        self.graph_identity = _file_identity(self.graph_path)
        index_path = index_path.resolve()
        self.index_identity = _file_identity(index_path)
        self.index_path = index_path
        self.project_id, self.snapshot_id = project_id, snapshot_id
        self.records = {}
        _admit_reference_file(index_path, index_digest, self.index_identity)
        _admit_reference_file(self.graph_path, graph_digest, self.graph_identity)
        self.db = sqlite3.connect(f"{index_path.as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            metadata = dict(self.db.execute("SELECT key,value FROM metadata"))
            if (metadata.get("format") != "semantica.keyword-references.v1"
                    or metadata.get("graph_digest") != graph_digest
                    or metadata.get("graph_size") != str(self.graph_identity[2])
                    or metadata.get("project_id") != project_id or metadata.get("snapshot_id") != snapshot_id):
                raise ValueError("keyword index does not match the requested canonical artifact; rebuild is required")
            self.graph = self.graph_path.open("rb")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.graph.close()
        self.db.close()

    def _read_record(self, field, item_id):
        key = (field, item_id)
        if key in self.records:
            return self.records[key][1]
        row = self.db.execute("SELECT ordinal,offset,length,digest FROM records WHERE field=? AND id=?", key).fetchone()
        if row is None:
            raise ValueError("keyword index has an unknown canonical record reference")
        ordinal, offset, length, digest = row
        if offset < 0 or length < 1 or offset + length > self.graph_identity[2]:
            raise ValueError("keyword index has an invalid byte reference")
        self.graph.seek(offset)
        data = self.graph.read(length)
        if sha256(data).hexdigest() != digest:
            raise ValueError("keyword canonical record digest does not match")
        item = json.loads(data)
        if item_id and (not isinstance(item, dict) or item.get("id") != item_id):
            raise ValueError("keyword canonical record identity does not match")
        self.records[key] = (ordinal, item)
        return item

    def read_catalog(self):
        header = {field: self._read_record(field, "") for field in ("protocol", "project_id", "snapshot_id", "lineage")}
        if (header["protocol"] != "semantica.semantic-artifact.v1" or header["project_id"] != self.project_id
                or header["snapshot_id"] != self.snapshot_id or not isinstance(header["lineage"], dict)):
            raise ValueError("keyword canonical header does not match the requested artifact")
        representations = [self._read_record("document_representations", row[0]) for row in self.db.execute(
            "SELECT id FROM records WHERE field='document_representations' ORDER BY ordinal")]
        return header, representations

    def prepare_matches(self, words):
        from ..context.snapshot_search import prepare_snapshot
        words = sorted({word.lower() for word in words if word})
        # Scan the vocabulary once, then use the postings primary key for matching terms.
        matched = self.db.execute("""SELECT DISTINCT r.field,r.id FROM records r JOIN postings p ON r.n=p.record
            WHERE p.term IN (SELECT n FROM terms WHERE """
            + (" OR ".join("instr(term, ?) > 0" for _ in words) or "0") + ")", words).fetchall()
        for field, item_id in matched:
            item = self._read_record(field, item_id)
            for entity_key in ("subject_id", "source_entity_id", "target_entity_id"):
                if item.get(entity_key):
                    self._read_record("entities", item[entity_key])
            evidence_ids = [item_id] if field == "evidence_spans" else item.get("evidence_ids", [])
            if not isinstance(evidence_ids, list) or any(not isinstance(ref, str) or not ref for ref in evidence_ids):
                raise ValueError("keyword canonical evidence identities are invalid")
            for evidence_id in evidence_ids:
                evidence = self._read_record("evidence_spans", evidence_id)
                self._read_record("document_representations", evidence["representation_id"])
        if _file_identity(self.graph_path) != self.graph_identity or _file_identity(self.index_path) != self.index_identity:
            raise ValueError("keyword artifacts changed during query")
        fields = ("entities", "assertions", "relations", "conflicts", "topics", "evidence_spans", "document_representations")
        sparse = SimpleNamespace(**{field: [item for _, item in sorted(
            (value for (record_field, _), value in self.records.items() if record_field == field), key=lambda value: value[0])]
            for field in fields})
        return prepare_snapshot(sparse), {item_id for _, item_id in matched}


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
    def document_matches(text: str, query: str, *, offset: int, limit: int) -> dict:
        """Literal original-text occurrences; pagination never changes recall or offsets."""
        if not query.strip() or offset < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid document keyword query")
        matches = []
        total = 0
        for match in re.finditer(re.escape(query), text, re.IGNORECASE):
            if offset <= total < offset + limit:
                matches.append((match.start(), match.end()))
            total += 1
        return {"matches": matches, "total": total,
                "nextOffset": offset + len(matches) if offset + len(matches) < total else None}

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

    @staticmethod
    def publish_reference_index(snapshot, graph_path: Path, index_path: Path) -> tuple[str, str]:
        """Replace scratch build outputs only after both canonical JSON and index are complete."""
        with tempfile.TemporaryDirectory(dir=index_path.parent) as temporary:
            root = Path(temporary)
            result = GraphSearchIndex._write_reference_index(snapshot, root / "graph.json", root / "index.sqlite")
            (root / "graph.json").replace(graph_path)
            (root / "index.sqlite").replace(index_path)
            return result

    @staticmethod
    def _write_reference_index(snapshot, graph_path: Path, index_path: Path, *, _existing=False) -> tuple[str, str]:
        """Publish canonical JSON and a disposable term/byte-reference index together.

        Only terms, record identities, byte ranges and hashes live in SQLite.
        Record bodies always come from the single canonical artifact.
        """
        from ..context.snapshot_search import prepare_snapshot
        prepared = prepare_snapshot(snapshot)
        payload = snapshot.model_dump(mode="json", by_alias=True)
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        # A fresh output is required; never replace a published index in place.
        if index_path.exists():
            raise ValueError("keyword index output already exists")
        with closing(sqlite3.connect(index_path)) as db, db, (nullcontext(None) if _existing else graph_path.open("wb")) as graph:
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE records(n INTEGER PRIMARY KEY, field TEXT NOT NULL, id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, offset INTEGER NOT NULL, length INTEGER NOT NULL, digest TEXT NOT NULL,
                    UNIQUE(field, id));
                CREATE TABLE terms(n INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE);
                CREATE TABLE postings(term INTEGER NOT NULL, record INTEGER NOT NULL,
                    PRIMARY KEY(term, record)) WITHOUT ROWID;
            """)
            digest = sha256()
            offset = 0
            def write(data):
                nonlocal offset
                if graph is not None:
                    graph.write(data)
                offset += len(data)
                digest.update(data)
            def record(field, item_id, ordinal, value):
                data = encode(value)
                db.execute("INSERT INTO records(field,id,ordinal,offset,length,digest) VALUES (?,?,?,?,?,?)",
                    (field, item_id, ordinal, offset, len(data), sha256(data).hexdigest()))
                write(data)
            write(b"{")
            fields = {"entities", "assertions", "relations", "conflicts", "topics", "evidence_spans", "document_representations"}
            for position, field in enumerate(sorted(payload)):
                if position:
                    write(b",")
                write(encode(field) + b":")
                value = payload[field]
                if field in fields:
                    write(b"[")
                    for ordinal, item in enumerate(value):
                        if ordinal:
                            write(b",")
                        record(field, item["id"], ordinal, item)
                    write(b"]")
                else:
                    record(field, "", 0, value) if field in {"lineage", "snapshot_id", "project_id", "protocol"} else write(encode(value))
            write(b"}")
            graph_digest = f"sha256:{digest.hexdigest()}"
            if _existing:
                _admit_reference_file(graph_path, graph_digest, _file_identity(graph_path))
            db.executemany("INSERT INTO metadata VALUES (?,?)", [
                ("format", "semantica.keyword-references.v1"), ("graph_digest", graph_digest),
                ("graph_size", str(offset)), ("project_id", snapshot.project_id), ("snapshot_id", snapshot.id)])
            record_ids = {(field, item_id): n for n, field, item_id in db.execute("SELECT n,field,id FROM records WHERE id != ''")}
            candidate_fields = {"entity": "entities", "assertion": "assertions", "relation": "relations",
                                "conflict": "conflicts", "topic": "topics", "evidence": "evidence_spans"}
            vocabulary = {}
            owner = GraphSearchIndex()
            for item in prepared.candidates:
                document = owner._build_document({"id": item[0], "content": item[2]})
                for term in sorted(set(document.primary_text.split()) | set(document.secondary_text.split())):
                    if term not in vocabulary:
                        vocabulary[term] = len(vocabulary) + 1
                        db.execute("INSERT INTO terms VALUES (?,?)", (vocabulary[term], term))
                    db.execute("INSERT INTO postings VALUES (?,?)", (vocabulary[term], record_ids[candidate_fields[item[1]], item[0]]))
        with index_path.open("rb") as stream:
            from hashlib import file_digest
            index_digest = f"sha256:{file_digest(stream, 'sha256').hexdigest()}"
        return graph_digest, index_digest

    @staticmethod
    def index_artifact(graph_path: Path, index_path: Path) -> tuple[str, str]:
        """Explicit offline indexing; never rewrite existing canonical content or call models."""
        from ..semantic_artifact_schema import SemanticArtifact
        graph_path = graph_path.resolve()
        if index_path.exists():
            raise ValueError("keyword index output already exists")
        snapshot = SemanticArtifact.model_validate_json(graph_path.read_bytes())
        with tempfile.TemporaryDirectory(dir=index_path.parent) as temporary:
            generated = Path(temporary) / "index.sqlite"
            result = GraphSearchIndex._write_reference_index(snapshot, graph_path, generated, _existing=True)
            generated.replace(index_path)
            return result

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
