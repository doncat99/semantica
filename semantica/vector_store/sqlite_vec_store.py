"""
SQLite Vector Store Module using sqlite-vec

This module provides SQLite integration using the sqlite-vec extension for vector storage and
similarity search in the Semantica framework, supporting L2 and Cosine distance metrics,
dynamic JSON metadata filtering, and disk-backed persistence.

Key Features:
    - Distance metrics (Cosine, L2/Euclidean)
    - Fully persistent or in-memory SQLite storage
    - Dynamic metadata filtering using SQLite's JSON extract functions
    - Thread-safe operations via a shared connection lock, with optional WAL mode
      (pass use_wal=True) for concurrent readers
    - Strict validation of vector dimensions and table names
    - Parity with PgVectorStore interface for seamless drop-in usage

Main Classes:
    - SQLiteVecStore: Main SQLite vector store using sqlite-vec virtual tables

Example Usage:
    >>> from semantica.vector_store import SQLiteVecStore
    >>> store = SQLiteVecStore(
    ...     db_path="vectors.db",
    ...     table_name="vectors",
    ...     dimension=768,
    ...     distance_metric="cosine"
    ... )
    >>> store.add(vectors, metadata, ids)
    >>> results = store.search(query_vector, top_k=10)
    >>> store.close()

Author: Semantica Contributors
License: MIT
"""

import importlib.util
import json
import os
import hashlib
import re
import sqlite3
import sys
import threading
import time
import uuid
from bisect import insort
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union
from urllib.request import pathname2url

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger

# Optional sqlite-vec import
# (Loaded lazily inside SQLiteVecStore.__init__ to prevent eager loading)
sqlite_vec = None

# Per-query disk scratch ceiling, independent of eligible vector count.
_NATIVE_QUERY_TEMP_BYTES = 32 * 1024 * 1024

# Availability check only (via find_spec, not an actual import) so callers and
# tests can detect whether sqlite-vec is installed without paying the load cost.
SQLITE_VEC_AVAILABLE = importlib.util.find_spec("sqlite_vec") is not None


class SQLiteVecStore:
    """
    SQLite vector store using the sqlite-vec extension for similarity search.

    - Vector storage with vec0 virtual table
    - Similarity search with L2 and Cosine metrics
    - Thread-safe query and insertion execution
    - Dynamic metadata extraction and filtering
    """

    SUPPORTED_METRICS = {"cosine", "l2"}
    _embedding_space_lock = threading.Lock()

    def __init__(
        self,
        db_path: str,
        table_name: str,
        dimension: int,
        distance_metric: str = "cosine",
        read_only: bool = False,
        **kwargs,
    ):
        """
        Initialize SQLiteVecStore.

        Args:
            db_path: Path to SQLite database file, or ':memory:'
            table_name: Name of the virtual table to store vectors
            dimension: Vector dimension
            distance_metric: Distance metric (cosine, l2)
            read_only: Open database in read-only mode (requires existing database)
            **kwargs: Additional option parameters
                use_wal: If True, enable WAL journal mode and NORMAL synchronous
                    durability for improved write concurrency (default: False)

        Raises:
            ValidationError: If parameters are invalid
            ProcessingError: If sqlite-vec or connection load extension fails
        """
        self.logger = get_logger("sqlite_vec_store")

        # Validate dependencies and lazy load
        global sqlite_vec
        if sqlite_vec is None:
            try:
                import sqlite_vec
            except (ImportError, OSError):
                raise ProcessingError(
                    "sqlite-vec Python package is not available. "
                    "Install with: pip install sqlite-vec"
                )

        # Validate parameters
        if distance_metric.lower() not in self.SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported distance metric: {distance_metric}. "
                f"Supported: {', '.join(self.SUPPORTED_METRICS)}"
            )

        if not self._is_safe_identifier(table_name):
            raise ValidationError(
                f"Invalid table name: {table_name!r}. "
                "Table names must start with a letter or underscore and contain "
                "only alphanumeric characters and underscores."
            )

        if not isinstance(dimension, int) or dimension <= 0:
            raise ValidationError(
                f"Dimension must be a positive integer, got: {dimension}"
            )

        self.db_path = db_path
        self.table_name = table_name
        self.dimension = dimension
        self.distance_metric = distance_metric.lower()
        self.read_only = read_only
        self.config = kwargs
        self.use_wal = kwargs.get("use_wal", False)

        # Lock to ensure thread safety when sharing a single SQLite connection
        self._lock = threading.Lock()
        self._conn = None

        # Connect to database
        self._init_connection()

        # Ensure table exists (if not read-only)
        if not self.read_only:
            self._ensure_table_exists()

        self.logger.info(
            f"Initialized SQLiteVecStore: db_path={db_path}, table={table_name}, "
            f"dimension={dimension}, metric={distance_metric}, read_only={read_only}"
        )

    def _init_connection(self):
        """Initialize database connection and load sqlite-vec extension."""
        try:
            if self.read_only:
                if self.db_path == ":memory:":
                    self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                else:
                    if not os.path.exists(self.db_path):
                        raise ProcessingError(
                            f"Database file does not exist for read-only mode: {self.db_path}"
                        )
                    abs_path = os.path.abspath(self.db_path)
                    url_path = pathname2url(abs_path)
                    self._conn = sqlite3.connect(
                        f"file:{url_path}?mode=ro", uri=True, check_same_thread=False
                    )
            else:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)

            # Enable and load extension
            try:
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
            except AttributeError as ae:
                raise ProcessingError(
                    "SQLite load extension attribute is not available in this Python build. "
                    "Make sure you are using a Python build compiled with loadable extension support."
                ) from ae
            except Exception as e:
                raise ProcessingError(
                    f"Failed to load sqlite-vec extension: {e}"
                ) from e

            # Set WAL journal mode + NORMAL synchronous for performance and
            # concurrent readers, if configured via use_wal=True
            if self.use_wal and not self.read_only and self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            # Accepted paid results are released only after their canonical
            # vectors survive a durable commit, including reopened connections.
            if not self.read_only and self.config.get('embedding_space_identity') is not None:
                self._conn.execute('PRAGMA synchronous=FULL')

        except (ValidationError, ProcessingError):
            if self._conn:
                self._conn.close()
            raise
        except Exception as e:
            if self._conn:
                self._conn.close()
            raise ProcessingError(f"Failed to establish SQLite connection: {e}") from e

    @contextmanager
    def _get_connection(self):
        """Get the active connection."""
        if not self._conn:
            raise ProcessingError("Database connection is closed.")
        try:
            yield self._conn
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError("Database operation failed") from e

    def _is_safe_identifier(self, key: str) -> bool:
        """
        Validate that a string is safe to use as a SQL identifier.

        Only allows alphanumeric characters and underscores.
        """
        if not isinstance(key, str):
            return False
        if not key:
            return False
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key))

    def _ensure_table_exists(self):
        """Ensure the vector table exists."""
        # Define vec0 virtual table
        create_table_sql = f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING vec0(
                id TEXT PRIMARY KEY,
                embedding float[{self.dimension}] distance_metric={self.distance_metric},
                +metadata TEXT
            )
        """
        with self._lock, self._get_connection() as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute(create_table_sql)
                conn.execute(f'''CREATE TABLE IF NOT EXISTS {self.table_name}_embedding_operations (
                    id TEXT PRIMARY KEY, count INTEGER NOT NULL, digest TEXT NOT NULL,
                    receipt TEXT NOT NULL, receipt_digest TEXT NOT NULL,
                    accepted_digest TEXT NOT NULL) WITHOUT ROWID''')
                if self.config.get('embedding_space_identity') is not None:
                    conn.execute('CREATE TABLE IF NOT EXISTS embedding_space(id INTEGER PRIMARY KEY CHECK(id=1),identity TEXT NOT NULL,dimension INTEGER NOT NULL)')
                    conn.execute('INSERT OR IGNORE INTO embedding_space VALUES(1,?,?)',
                        (json.dumps(self.config['embedding_space_identity'], sort_keys=True, separators=(',', ':')), self.dimension))
                conn.commit()
                self.logger.debug(f"Virtual table {self.table_name} ensured")
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to create vec0 virtual table") from e

    @classmethod
    def open_embedding_space(cls, db_path, space, dimension=None):
        # Multiple bounded build workers can encounter a new space together.
        # Hold only schema admission, never model execution or vector queries.
        with cls._embedding_space_lock:
            return cls._open_embedding_space(db_path, space, dimension)

    @classmethod
    def _open_embedding_space(cls, db_path, space, dimension=None):
        """Open a bound native space without a model call to rediscover dimension.

        A new space has no carrier until the first accepted model response gives
        its dimension. Existing malformed/incompatible metadata fails closed.
        """
        if (not isinstance(space, dict) or set(space) != {'binding', 'model', 'recipe'}
                or any(not isinstance(v, str) or not v or len(v.encode()) > 4096 for v in space.values())):
            raise ValidationError('Embedding space requires exact binding/model/recipe identities')
        encoded = json.dumps(space, sort_keys=True, separators=(',', ':'))
        exists = os.path.exists(db_path)
        if exists:
            with sqlite3.connect(f'file:{pathname2url(os.path.abspath(db_path))}?mode=ro', uri=True) as conn:
                row = conn.execute('SELECT identity,dimension FROM embedding_space WHERE id=1').fetchone()
            if row is None or len(row[0]) > 16384 or row[0] != encoded or (dimension is not None and row[1] != dimension):
                raise ProcessingError('Embedding space identity or dimension differs')
            dimension = row[1]
        elif dimension is None:
            return None
        if type(dimension) is not int or not 1 <= dimension <= 8192:
            raise ValidationError('Embedding dimension exceeds native space budget')
        owner = cls(str(db_path), 'embeddings', dimension, 'cosine', embedding_space_identity=space)
        owner.embedding_space_identity = space
        return owner

    @staticmethod
    def embedding_operation_id(binding):
        fields = {'project', 'source', 'material', 'representation', 'recipe', 'model', 'space', 'parser', 'ranges', 'input_digest'}
        if not isinstance(binding, dict) or set(binding) != fields:
            raise ValidationError('Embedding operation requires the complete named input tuple')
        if any(not isinstance(binding[k], str) or not binding[k] or len(binding[k].encode()) > 4096 for k in fields - {'ranges'}):
            raise ValidationError('Invalid embedding input identity')
        ranges = binding['ranges']
        if (not isinstance(ranges, list) or not 1 <= len(ranges) <= 256
                or any(not isinstance(r, list) or len(r) != 2 or any(type(n) is not int or n < 0 for n in r) or r[1] <= r[0] for r in ranges)):
            raise ValidationError('Embedding source ranges exceed the bounded batch contract')
        return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def _read_embedding(self, conn, identity, *, include_vectors=True):
        row = conn.execute(f'SELECT count,digest,receipt,receipt_digest,accepted_digest FROM {self.table_name}_embedding_operations WHERE id=?', (identity,)).fetchone()
        if row is None:
            return None
        count, digest, receipt, receipt_digest, accepted_digest = row
        if not 1 <= count <= 256 or count * self.dimension * 4 > 8 * 1024 * 1024 or len(receipt.encode()) > 65536:
            raise ProcessingError('Stored embedding operation exceeds resource budget')
        vectors, hasher = [], hashlib.sha256()
        for index in range(count):
            record = conn.execute(f'SELECT embedding FROM {self.table_name} WHERE id=?', (identity + ':' + str(index),)).fetchone()
            if record is None or len(record[0]) != self.dimension * 4:
                raise ProcessingError('Adopted embedding vector is missing or invalid')
            hasher.update(record[0])
            vector = np.frombuffer(record[0], dtype=np.float32)
            if not np.all(np.isfinite(vector)):
                raise ProcessingError('Adopted embedding vector is corrupt')
            if include_vectors:
                vectors.append(vector.tolist())
        if hasher.hexdigest() != digest or hashlib.sha256(receipt.encode()).hexdigest() != receipt_digest:
            raise ProcessingError('Adopted embedding operation digest differs')
        result = dict(ids=[identity + ':' + str(i) for i in range(count)],
                      receipt=json.loads(receipt), accepted_digest=accepted_digest)
        if include_vectors:
            result['vectors'] = vectors
        return result

    def read_embedding(self, binding, *, include_vectors=True):
        """Read only one indexed, bounded paid operation; never scan the matrix."""
        identity = self.embedding_operation_id(binding)
        space = getattr(self, 'embedding_space_identity', None)
        if space is None or any(binding[k] != space[k] for k in ('model', 'recipe')) or binding['space'] != space['binding']:
            raise ValidationError('Embedding operation differs from its native space')
        with self._lock, self._get_connection() as conn:
            return self._read_embedding(conn, identity, include_vectors=include_vectors)

    @staticmethod
    def pack_embedding_vectors(vectors, dimension, count):
        """Validate and encode the sole native float32 representation."""
        if (type(dimension) is not int or not 1 <= dimension <= 8192
                or not isinstance(vectors, list) or len(vectors) != count
                or not 1 <= count <= 256 or count * dimension * 4 > 8 * 1024 * 1024):
            raise ValidationError('Embedding adoption exceeds vector byte or dimension budget')
        packed = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != dimension or any(type(v) not in (int, float) for v in vector):
                raise ValidationError('Embedding vector shape or scalar type differs')
            with np.errstate(over='ignore', invalid='ignore'):
                array = np.asarray(vector, dtype=np.float32)
            if array.shape != (dimension,) or not np.all(np.isfinite(array)) or not np.any(array):
                raise ValidationError('Embedding vector is invalid for its native space')
            packed.append(array.tobytes())
        return packed

    def adopt_embedding(self, binding, vectors, receipt, *, accepted_digest, include_vectors=True):
        """Atomically adopt vectors and their small receipt into their sole owner."""
        if self.read_only or self.db_path == ':memory:':
            raise ProcessingError('Paid embeddings require a persistent writable native store')
        identity = self.embedding_operation_id(binding)
        self.read_embedding(binding)  # Validates native space admission.
        if hasattr(receipt, 'model_dump'):
            receipt = receipt.model_dump(mode='json')
        fields = {'id', 'operation', 'provider', 'model', 'input_digest', 'output_digest', 'created_at', 'parameters', 'metadata'}
        if (not isinstance(receipt, dict) or set(receipt) - fields
                or receipt.get('operation') != 'embedding' or receipt.get('model') != binding['model']
                or any(not isinstance(receipt.get(k), str) or not receipt[k] for k in ('id', 'provider', 'input_digest', 'output_digest'))
                or not isinstance(receipt.get('metadata', {}), dict) or set(receipt.get('metadata', {})) - {'usage'}
                or not isinstance(receipt.get('parameters', {}), dict) or set(receipt.get('parameters', {})) - {'dimensions', 'encoding_format'}
                or not isinstance(receipt.get('metadata', {}).get('usage', {}), dict)
                or set(receipt.get('metadata', {}).get('usage', {})) - {'prompt_tokens', 'completion_tokens', 'total_tokens', 'input_tokens'}
                or not isinstance(accepted_digest, str) or not accepted_digest):
            raise ValidationError('Embedding adoption requires a typed matching receipt')
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        usage = receipt.get('metadata', {}).get('usage', {})
        if any(type(value) is not int or value < 0 for value in usage.values()):
            raise ValidationError('Embedding usage must contain nonnegative token counts')
        if usage.get('completion_tokens', 0) != 0:
            raise ValidationError('Embedding usage cannot include generated tokens')
        input_count = usage.get('prompt_tokens', usage.get('input_tokens'))
        if (input_count is not None and 'total_tokens' in usage
                and usage['total_tokens'] != input_count):
            raise ValidationError('Embedding usage total differs from input tokens')
        if len(encoded.encode()) > 65536 or not isinstance(vectors, list) or len(vectors) != len(binding['ranges']):
            raise ValidationError('Embedding adoption exceeds receipt or batch budget')
        packed = self.pack_embedding_vectors(vectors, self.dimension, len(binding['ranges']))
        digest = hashlib.sha256(b''.join(packed)).hexdigest()
        with self._lock, self._get_connection() as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')
                existing = self._read_embedding(conn, identity, include_vectors=include_vectors)
                if existing is not None:
                    prior = conn.execute(f'SELECT digest,receipt_digest FROM {self.table_name}_embedding_operations WHERE id=?', (identity,)).fetchone()
                    if existing['accepted_digest'] != accepted_digest or prior != (digest, hashlib.sha256(encoded.encode()).hexdigest()):
                        raise ProcessingError('Embedding acceptance digest differs from adopted operation')
                    conn.commit()
                    return existing
                conn.executemany(f'INSERT INTO {self.table_name}(id,embedding,metadata) VALUES(?,?,?)',
                    ((identity + ':' + str(i), value, '{}') for i, value in enumerate(packed)))
                conn.execute(f'INSERT INTO {self.table_name}_embedding_operations VALUES(?,?,?,?,?,?)',
                    (identity, len(packed), digest, encoded, hashlib.sha256(encoded.encode()).hexdigest(), accepted_digest))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.read_embedding(binding, include_vectors=include_vectors)

    def add(
        self,
        vectors: Union[List[np.ndarray], np.ndarray],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Add vectors to the store.

        Args:
            vectors: List of vectors or numpy array
            metadata: List of metadata dictionaries (one per vector)
            ids: Optional list of IDs (auto-generated if not provided)

        Returns:
            List of vector IDs

        Raises:
            ValidationError: If input dimensions or lengths don't match
            ProcessingError: If read-only mode is active or database operation fails
        """
        if self.read_only:
            raise ProcessingError("Cannot add vectors in read-only mode")

        # Convert to list if numpy array
        if isinstance(vectors, np.ndarray):
            vectors = [vectors[i] for i in range(len(vectors))]

        num_vectors = len(vectors)

        # Validate dimensions
        for i, vec in enumerate(vectors):
            if len(vec) != self.dimension:
                raise ValidationError(
                    f"Vector at index {i} has dimension {len(vec)}, "
                    f"expected {self.dimension}"
                )

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(num_vectors)]
        elif len(ids) != num_vectors:
            raise ValidationError(
                f"IDs length ({len(ids)}) must match vectors length ({num_vectors})"
            )

        # Prepare metadata
        if metadata is None:
            metadata = [{} for _ in range(num_vectors)]
        elif len(metadata) != num_vectors:
            raise ValidationError(
                f"Metadata length ({len(metadata)}) must match vectors length ({num_vectors})"
            )

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                # Run deletes first to emulate INSERT OR REPLACE / UPSERT behavior
                # Use batched deletes to avoid a massive performance bottleneck
                if ids:
                    batch_size = 1000
                    for i in range(0, len(ids), batch_size):
                        batch_ids = ids[i : i + batch_size]
                        placeholders = ",".join(["?"] * len(batch_ids))
                        cur.execute(
                            f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                            batch_ids,
                        )

                # Build data tuples for insert
                data_tuples = [
                    (
                        vec_id,
                        sqlite_vec.serialize_float32(vec),
                        json.dumps(meta),
                    )
                    for vec_id, vec, meta in zip(ids, vectors, metadata)
                ]

                # Bulk insert
                cur.executemany(
                    f"INSERT INTO {self.table_name} (id, embedding, metadata) VALUES (?, ?, ?)",
                    data_tuples,
                )
                conn.commit()
                cur.close()
                self.logger.info(f"Added {num_vectors} vectors")
                return ids
            except (ValidationError, ProcessingError):
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to add vectors to database") from e

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filter: Optional metadata filter (dict of key-value pairs)

        Returns:
            List of results with id, score (similarity), and metadata

        Raises:
            ValidationError: If query vector dimension doesn't match
            ProcessingError: If database operation fails
        """
        if len(query_vector) != self.dimension:
            raise ValidationError(
                f"Query vector has dimension {len(query_vector)}, expected {self.dimension}"
            )

        # Serialize query vector
        query_serialized = sqlite_vec.serialize_float32(query_vector)

        # Build query
        filter_conditions = []
        filter_params = []
        if filter:
            for key, value in filter.items():
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must start with a letter or underscore and contain "
                        "only alphanumeric characters and underscores."
                    )
                filter_conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                if isinstance(value, bool):
                    filter_params.append(1 if value else 0)
                else:
                    filter_params.append(value)

        where_clause = ""
        if filter_conditions:
            where_clause = " AND " + " AND ".join(filter_conditions)

        search_sql = f"""
            SELECT id, distance, metadata
            FROM {self.table_name}
            WHERE embedding MATCH ? AND k = ?{where_clause}
        """
        params = [query_serialized, top_k] + filter_params

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(search_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, distance, meta_json = row
                    # Convert distance to similarity score
                    similarity = 1.0 / (1.0 + float(distance))

                    results.append(
                        {
                            "id": vec_id,
                            "score": similarity,
                            "metadata": json.loads(meta_json) if meta_json else {},
                            "vector": None,
                            "distance": None,
                        }
                    )

                return results
            except (ValidationError, ProcessingError):
                raise
            except Exception as e:
                raise ProcessingError("Failed to search vectors") from e

    def native_publication_digest(self, conn, project, generation, *, check):
        """Reproducible bounded integrity traversal for publish and offline verify."""
        digest, count = hashlib.sha256(), 0
        table = self.table_name + '_native_ranges'
        for kind, columns, order in (
            ('range', 'project,generation,vector_id,source,material,representation,ranges', 'vector_id'),
            ('record', 'project,generation,vector_id,record_id,evidence_id,source', 'vector_id,record_id,evidence_id'),
        ):
            selected = table if kind == 'range' else table+'_records'
            for row in conn.execute(f'SELECT {columns} FROM {selected} WHERE project=? AND generation=? ORDER BY {order}', (project,generation)):
                check()
                encoded = json.dumps([kind,*row],separators=(',',':'),ensure_ascii=False).encode()
                if len(encoded) > 262144:
                    raise ProcessingError('Native publication digest row exceeds byte budget')
                digest.update(encoded)
                digest.update(b'\n')
                count += kind == 'range'
        return 'sha256:'+digest.hexdigest(), count

    def publish_native_ranges(self, project, generation, links, *, record_references=None):
        """Associate accepted vectors with current native scalar addresses, no copies.

        Called only by publication maintenance. Every link proves its original
        paid operation binding; query reads never inspect its vector body.
        """
        if self.read_only or not project or not generation:
            raise ValidationError('Native vector publication requires a writable project generation')
        from ..semantic_worker_context import check_query_cancellation
        recipe = hashlib.sha256(b'SQLiteVecStore:native-scalar-range-links:canonical-key-digest').hexdigest()
        count = 0
        table = self.table_name + '_native_ranges'
        metadata = self.table_name + '_native_publications'
        with self._lock, self._get_connection() as conn:
            conn.executescript(f'''CREATE TABLE IF NOT EXISTS {table}(
                project TEXT,generation TEXT,vector_id TEXT,source TEXT,material TEXT,
                representation TEXT,ranges TEXT,PRIMARY KEY(project,vector_id)) WITHOUT ROWID;
                CREATE INDEX IF NOT EXISTS {table}_scope ON {table}(project,generation,source,vector_id);
                CREATE TABLE IF NOT EXISTS {metadata}(project TEXT PRIMARY KEY,generation TEXT,
                    count INTEGER,digest TEXT,recipe TEXT) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS {table}_records(
                    project TEXT,generation TEXT,vector_id TEXT,record_id TEXT,evidence_id TEXT,source TEXT,
                    PRIMARY KEY(project,vector_id,record_id,evidence_id)) WITHOUT ROWID;
                CREATE INDEX IF NOT EXISTS {table}_records_record ON {table}_records(project,generation,record_id);
                CREATE INDEX IF NOT EXISTS {table}_records_evidence ON {table}_records(project,generation,record_id,evidence_id,source);
                CREATE INDEX IF NOT EXISTS {table}_records_scope ON {table}_records(project,generation,source,vector_id);''')
            try:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute(f'DELETE FROM {table} WHERE project=?', (project,))
                conn.execute(f'DELETE FROM {table}_records WHERE project=?', (project,))
                for link in links:
                    check_query_cancellation()
                    if not isinstance(link, dict) or set(link) != {'vector_id','binding','ranges'}:
                        raise ValidationError('Native vector link requires exact reference fields')
                    binding, ranges = link['binding'], link['ranges']
                    operation = self.embedding_operation_id(binding)
                    if binding['project'] != project:
                        raise ValidationError('Native vector link belongs to another project')
                    space = self.embedding_space_identity
                    if binding['space'] != space['binding'] or any(binding[k] != space[k] for k in ('model','recipe')):
                        raise ValidationError('Native vector link differs from its embedding space')
                    adopted = self._read_embedding(conn, operation)
                    if adopted is None or link['vector_id'] not in adopted['ids']:
                        raise ProcessingError('Native vector link has no accepted native vector')
                    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 128:
                        raise ValidationError('Native vector address fanout exceeds budget')
                    previous = 0
                    for item in ranges:
                        if (not isinstance(item, dict) or set(item)-{'nativeRef','start','end','joinBefore'}
                                or not {'nativeRef','start','end'} <= set(item)
                                or not isinstance(item['nativeRef'],str) or not item['nativeRef'].startswith('#/document/')
                                or len(item['nativeRef'].encode()) > 4096
                                or any(type(item[k]) is not int for k in ('start','end'))
                                or not 0 <= item['start'] < item['end'] or item['end']-item['start'] > 65536
                                or not isinstance(item.get('joinBefore',''), str)
                                or len(item.get('joinBefore','').encode()) > 8
                                or item.get('joinBefore','').strip()):
                            raise ValidationError('Native vector scalar address is invalid')
                        previous += item['end']-item['start']+len(item.get('joinBefore',''))
                    vector_index = adopted['ids'].index(link['vector_id'])
                    if previous != binding['ranges'][vector_index][1]-binding['ranges'][vector_index][0]:
                        raise ValidationError('Native vector scalar addresses differ from accepted input extent')
                    encoded = json.dumps(ranges, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
                    if len(encoded.encode()) > 65536:
                        raise ValidationError('Native vector scalar addresses exceed byte budget')
                    values = (project,generation,link['vector_id'],binding['source'],binding['material'],binding['representation'],encoded)
                    conn.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?)', values)
                    if record_references is not None:
                        for reference in record_references(link):
                            check_query_cancellation()
                            if (not isinstance(reference,dict) or set(reference) != {'id','evidence','source'}
                                    or reference['source'] != binding['source']
                                    or any(not isinstance(reference[key],str) or not reference[key]
                                           or len(reference[key].encode())>8192 for key in ('id','evidence'))):
                                raise ValidationError('Invalid native record association')
                            association = (project,generation,link['vector_id'],reference['id'],reference['evidence'],reference['source'])
                            conn.execute(f'INSERT OR IGNORE INTO {table}_records VALUES (?,?,?,?,?,?)',association)
                    count += 1
                store_id, verified_count = self.native_publication_digest(conn,project,generation,check=check_query_cancellation)
                if verified_count != count:
                    raise ProcessingError('Native vector publication inserted count differs')
                conn.execute(f'INSERT OR REPLACE INTO {metadata} VALUES (?,?,?,?,?)', (project,generation,count,store_id,recipe))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return {'kind':'native-sqlite-vec', 'store_id':store_id, 'recipe_digest':recipe,
            'space_id':self.embedding_space_identity['binding']}

    def search_native_ranges(self, query_vector, *, project, generation, receipt, top_k=128, source_ids=None,
                             page_limit=128, offset=0):
        """Current-scope native KNN over accepted rows; return only scalar addresses."""
        from ..semantic_worker_context import check_query_cancellation
        if (type(top_k) is not int or not 1 <= top_k <= 1000
                or type(page_limit) is not int or not 1 <= page_limit <= 128
                or type(offset) is not int or not 0 <= offset < top_k
                or set(receipt) != {'kind','store_id','recipe_digest','space_id'}
                or receipt['kind'] != 'native-sqlite-vec'
                or receipt['space_id'] != self.embedding_space_identity['binding']
                or (source_ids is not None and (not isinstance(source_ids,list) or len(source_ids)>128
                    or any(not isinstance(s,str) or not s or len(s.encode())>4096 for s in source_ids)))):
            raise ValidationError('Native vector query scope or receipt differs')
        vector = np.asarray(query_vector, dtype=np.float32)
        if (self.distance_metric != 'cosine' or vector.shape != (self.dimension,)
                or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector)):
            raise ValidationError('Native vector query requires a finite matching cosine vector')
        table, metadata = self.table_name+'_native_ranges', self.table_name+'_native_publications'
        with self._lock, self._get_connection() as conn:
            row = conn.execute(f'SELECT generation,digest,recipe FROM {metadata} WHERE project=?', (project,)).fetchone()
            if row != (generation,receipt['store_id'],receipt['recipe_digest']):
                raise ProcessingError('Native vector publication is missing or stale')
            if source_ids == []:
                return []
            deadline = time.monotonic()+3
            def check():
                check_query_cancellation()
                return int(time.monotonic()>deadline)
            conn.set_progress_handler(check,1000)
            try:
                scope = '' if source_ids is None else ' AND source IN ('+','.join('?' for _ in source_ids)+')'
                rows = conn.execute(f'''WITH matches AS MATERIALIZED (
                    SELECT id,distance FROM {self.table_name} WHERE embedding MATCH ? AND k=? AND id IN (
                        SELECT vector_id FROM {table} WHERE project=? AND generation=?{scope}))
                    SELECT r.vector_id,v.distance,r.source,r.material,r.representation,r.ranges
                    FROM matches v JOIN {table} r ON r.vector_id=v.id AND r.project=? AND r.generation=?
                    ORDER BY v.distance,r.vector_id LIMIT ? OFFSET ?''', [sqlite_vec.serialize_float32(vector),top_k,
                    project,generation,*(source_ids or []),project,generation,min(page_limit,top_k-offset),offset]).fetchall()
                check_query_cancellation()
                result = [dict(id=identity,score=1.-float(distance),sourceId=source,materialRevision=material,
                    representationRevision=representation,ranges=json.loads(ranges))
                    for identity,distance,source,material,representation,ranges in rows]
                if len(json.dumps(result,ensure_ascii=False).encode())>262144:
                    raise ProcessingError('Native vector query response exceeds byte budget')
                return result
            finally:
                conn.set_progress_handler(None,0)

    def search_native_records(self, query_vector, *, project, generation, receipt,
                              top_k=128, source_ids=None, page_limit=128, offset=0):
        """Exact grouped cosine KNN with scope admission before ranking.

        Repeated vectors for one group must not consume the result budget. Disk
        scratch tracks visited vector IDs; only top_k groups are retained in Python.
        Continue through tied frontiers so native record ID ties remain stable.
        The candidate budget is never confused with the typed result budget.
        """
        from ..semantic_worker_context import check_query_cancellation, query_cancellation
        check_query_cancellation()
        cancellation = query_cancellation.get()
        if (self.distance_metric != 'cosine' or type(top_k) is not int or not 1 <= top_k <= 1000
                or type(page_limit) is not int or not 1 <= page_limit <= 128
                or type(offset) is not int or not 0 <= offset < top_k
                or (source_ids is not None and (not isinstance(source_ids,list) or len(source_ids)>128
                    or any(not isinstance(source,str) or not source or len(source.encode())>4096 for source in source_ids)))):
            raise ValidationError('group search requires cosine and a bounded result limit')
        vector = np.asarray(query_vector, dtype=np.float32)
        if vector.shape != (self.dimension,) or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector):
            raise ValidationError('group query vector is invalid')
        if source_ids == []:
            return []
        serialized = sqlite_vec.serialize_float32(vector)
        links = self.table_name+'_native_ranges_records'
        with self._lock, self._get_connection() as conn:
            row = conn.execute(f'SELECT generation,digest,recipe FROM {self.table_name}_native_publications WHERE project=?',(project,)).fetchone()
            if (set(receipt) != {'kind','store_id','recipe_digest','space_id'}
                    or receipt['kind'] != 'native-sqlite-vec'
                    or receipt['space_id'] != self.embedding_space_identity['binding']
                    or row != (generation,receipt['store_id'],receipt['recipe_digest'])):
                raise ProcessingError('Native record index publication is missing or stale')
            conn.execute('PRAGMA temp_store=FILE')
            conn.execute('PRAGMA cache_size=-8192')
            deadline = time.monotonic() + 3
            best = {}
            ordered = []
            try:
                conn.set_progress_handler(lambda: int(time.monotonic() > deadline
                    or (cancellation is not None and cancellation.is_set())), 10000)
                conn.execute('PRAGMA temp.cache_size=-512')
                page_size = conn.execute('PRAGMA temp.page_size').fetchone()[0]
                max_pages = _NATIVE_QUERY_TEMP_BYTES // page_size
                if max_pages < 1:
                    raise ProcessingError('Native record query scratch exceeds byte budget')
                actual_pages = conn.execute(f'PRAGMA temp.max_page_count={max_pages}').fetchone()[0]
                if actual_pages * page_size > _NATIVE_QUERY_TEMP_BYTES:
                    raise ProcessingError('Native record query scratch exceeds byte budget')
                conn.executescript('''DROP TABLE IF EXISTS temp.knn_seen; DROP TABLE IF EXISTS temp.knn_scope;
                    DROP TABLE IF EXISTS temp.knn_batch;
                    CREATE TEMP TABLE knn_seen(id TEXT PRIMARY KEY) WITHOUT ROWID;
                    CREATE TEMP TABLE knn_batch(id TEXT PRIMARY KEY,distance REAL) WITHOUT ROWID;
                    CREATE INDEX temp.knn_batch_distance ON knn_batch(distance,id);
                    CREATE TEMP TABLE knn_scope(id TEXT PRIMARY KEY) WITHOUT ROWID;''')
                if source_ids is not None:
                    conn.executemany('INSERT INTO knn_scope VALUES (?)', ((source,) for source in source_ids))
                while True:
                    check_query_cancellation()
                    if time.monotonic() > deadline:
                        raise ProcessingError('group query exceeded its execution budget')
                    rows = conn.execute(f'''SELECT id,distance FROM {self.table_name}
                        WHERE embedding MATCH ? AND k=256 AND id IN (
                            SELECT DISTINCT g.vector_id FROM {links} g
                            WHERE g.project=? AND g.generation=?
                            AND g.vector_id NOT IN (SELECT id FROM knn_seen)
                            AND (? OR g.source IN (SELECT id FROM knn_scope)))
                        ORDER BY distance''',
                        (serialized, project,generation, source_ids is None)).fetchall()
                    rows.sort(key=lambda row:(row[1],row[0]))
                    if not rows:
                        break
                    conn.execute('DELETE FROM knn_batch')
                    conn.executemany('INSERT INTO knn_batch VALUES (?,?)', rows)
                    # Aggregate the bounded batch's indexed links once; a
                    # correlated distance lookup rescans the batch per group.
                    for group_id, position, distance in conn.execute(f'''WITH batch_groups AS MATERIALIZED (
                            SELECT g.record_id AS group_id, 0 AS position, MIN(b.distance) AS distance
                            FROM knn_batch b CROSS JOIN {links} g
                            WHERE g.vector_id=b.id AND g.project=? AND g.generation=?
                            AND (? OR g.source IN (SELECT id FROM knn_scope)) GROUP BY g.record_id)
                            SELECT group_id,position,distance FROM batch_groups
                            ORDER BY distance,group_id LIMIT ?''',
                            (project,generation,source_ids is None, top_k)):
                        entry = (float(distance), position, group_id)
                        previous = best.get(group_id)
                        if previous is not None and entry >= previous:
                            continue
                        if previous is None and len(ordered) == top_k and entry >= ordered[-1]:
                            continue
                        if previous is not None:
                            ordered.remove(previous)
                        insort(ordered, entry)
                        best[group_id] = entry
                        if len(ordered) > top_k:
                            del best[ordered.pop()[2]]
                    conn.executemany('INSERT INTO knn_seen VALUES (?)', ((row[0],) for row in rows))
                    if len(rows) < 256 or (len(ordered) == top_k and ordered[-1][0] < rows[-1][1]):
                        break
                result=[]
                for distance,_,identity in ordered[offset:offset+page_limit]:
                    evidence=self._native_evidence_page(conn,project,generation,identity,source_ids,limit=128)
                    refs=[(item['id'],item['source']) for item in evidence['items']]
                    result.append(dict(id=identity,score=1.-distance,
                        evidenceIds=sorted({e for e,_ in refs}),sourceIds=sorted({s for _,s in refs}),
                        evidenceNextCursor=evidence['nextCursor']))
                if len(json.dumps(result,ensure_ascii=False).encode())>262144:
                    raise ProcessingError('Native record query response exceeds byte budget')
                check_query_cancellation()
                if time.monotonic() > deadline:
                    raise ProcessingError('group query exceeded its execution budget')
                return result
            except sqlite3.Error as error:
                check_query_cancellation()
                if time.monotonic() > deadline:
                    raise ProcessingError('group query exceeded its execution budget') from error
                if (getattr(error, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL
                        or str(error) == 'database or disk is full'):
                    raise ProcessingError('Native record query scratch exceeds byte budget') from error
                raise ProcessingError('Native record query database operation failed') from error
            finally:
                error = sys.exc_info()[1]
                try:
                    conn.set_progress_handler(None, 0)
                    conn.executescript('DROP TABLE IF EXISTS temp.knn_seen; DROP TABLE IF EXISTS temp.knn_scope; DROP TABLE IF EXISTS temp.knn_batch;')
                except sqlite3.Error:
                    if error is None:
                        raise
                    self.logger.warning('Native record scratch cleanup failed', exc_info=True)

    def _native_evidence_page(self,conn,project,generation,identity,source_ids,*,after=None,limit=128):
        from ..semantic_worker_context import check_query_cancellation
        if (type(limit) is not int or not 1<=limit<=128 or not isinstance(identity,str)
                or not identity or len(identity.encode())>8192
                or (after is not None and (not isinstance(after,(tuple,list)) or len(after)!=2
                    or any(not isinstance(value,str) or not value or len(value.encode())>8192 for value in after)))):
            raise ValidationError('Invalid native evidence selection')
        scope='' if source_ids is None else ' AND source IN ('+','.join('?' for _ in source_ids)+')'
        cursor='' if after is None else ' AND (evidence_id,source)>(?,?)'
        result=[]
        size=0
        rows=conn.execute(f'''SELECT DISTINCT evidence_id,source FROM {self.table_name}_native_ranges_records
            WHERE project=? AND generation=? AND record_id=?{scope}{cursor}
            ORDER BY evidence_id,source LIMIT ?''',[project,generation,identity,*(source_ids or []),*(after or []),limit+1])
        for evidence,source in rows:
            check_query_cancellation()
            item=dict(id=evidence,source=source)
            size+=len(json.dumps(item).encode())
            if len(result)==limit or size>262144:
                if not result:
                    raise ProcessingError('Native evidence exceeds byte budget')
                return dict(items=result,nextCursor=[result[-1]['id'],result[-1]['source']])
            result.append(item)
        return dict(items=result,nextCursor=None)

    def read_native_evidence(self, *,project,generation,receipt,identity,source_ids=None,after=None,limit=128):
        """Page reference-only evidence links for one current native result."""
        if source_ids is not None and (not isinstance(source_ids,list) or len(source_ids)>128
                or any(not isinstance(s,str) or not s or len(s.encode())>4096 for s in source_ids)):
            raise ValidationError('Invalid native evidence source scope')
        if set(receipt)!={'kind','store_id','recipe_digest','space_id'}:
            raise ValidationError('Invalid native evidence receipt')
        with self._lock,self._get_connection() as conn:
            row=conn.execute(f'SELECT generation,digest,recipe FROM {self.table_name}_native_publications WHERE project=?',(project,)).fetchone()
            if (receipt['kind']!='native-sqlite-vec' or receipt['space_id']!=self.embedding_space_identity['binding']
                    or row!=(generation,receipt['store_id'],receipt['recipe_digest'])):
                raise ProcessingError('Native evidence publication missing or stale')
            from ..semantic_worker_context import check_query_cancellation
            deadline=time.monotonic()+10
            def progress():
                check_query_cancellation()
                return int(time.monotonic()>deadline)
            conn.set_progress_handler(progress,1000)
            try:
                return self._native_evidence_page(conn,project,generation,identity,source_ids,after=after,limit=limit)
            finally:
                conn.set_progress_handler(None,0)

    def delete(self, ids: List[str]) -> bool:
        """
        Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete

        Returns:
            True if successful

        Raises:
            ProcessingError: If read-only mode is active or database operation fails
        """
        if not ids:
            return True

        if self.read_only:
            raise ProcessingError("Cannot delete vectors in read-only mode")

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                batch_size = 1000
                for i in range(0, len(ids), batch_size):
                    batch_ids = ids[i : i + batch_size]
                    placeholders = ",".join(["?"] * len(batch_ids))
                    cur.execute(
                        f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                        batch_ids,
                    )
                conn.commit()
                cur.close()
                self.logger.info(f"Deleted vectors: {len(ids)}")
                return True
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to delete vectors") from e

    def update(
        self,
        ids: List[str],
        vectors: Optional[Union[List[np.ndarray], np.ndarray]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Update existing vectors.

        Args:
            ids: List of vector IDs to update
            vectors: Optional new vectors
            metadata: Optional new metadata

        Returns:
            IDs the UPDATE matched, in request order and without
            duplicates. Missing IDs are omitted. An empty request
            returns an empty list.

        Raises:
            ValidationError: If input dimensions or lengths don't match
            ProcessingError: If read-only mode is active or database operation fails
        """
        if not ids:
            return []

        if self.read_only:
            raise ProcessingError("Cannot update vectors in read-only mode")

        if vectors is None and metadata is None:
            raise ValidationError(
                "Either vectors or metadata must be provided for update"
            )

        if vectors is not None:
            if isinstance(vectors, np.ndarray):
                vectors = [vectors[i] for i in range(len(vectors))]
            if len(vectors) != len(ids):
                raise ValidationError("Vectors length must match IDs length")
            for i, vec in enumerate(vectors):
                if len(vec) != self.dimension:
                    raise ValidationError(
                        f"Vector at index {i} has dimension {len(vec)}, expected {self.dimension}"
                    )

        if metadata is not None and len(metadata) != len(ids):
            raise ValidationError("Metadata length must match IDs length")

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()

                # Same columns are updated for every row. Execute one
                # statement per id: vec0 virtual tables reject UPDATE
                # RETURNING, and executemany reports only a combined count.
                if vectors is not None and metadata is not None:
                    update_sql = f"UPDATE {self.table_name} SET embedding = ?, metadata = ? WHERE id = ?"
                    data_tuples = [
                        (sqlite_vec.serialize_float32(vectors[i]), json.dumps(metadata[i]), vec_id)
                        for i, vec_id in enumerate(ids)
                    ]
                elif vectors is not None:
                    update_sql = f"UPDATE {self.table_name} SET embedding = ? WHERE id = ?"
                    data_tuples = [
                        (sqlite_vec.serialize_float32(vectors[i]), vec_id)
                        for i, vec_id in enumerate(ids)
                    ]
                else:
                    update_sql = f"UPDATE {self.table_name} SET metadata = ? WHERE id = ?"
                    data_tuples = [
                        (json.dumps(metadata[i]), vec_id) for i, vec_id in enumerate(ids)
                    ]

                confirmed_ids: List[str] = []
                seen = set()
                for params in data_tuples:
                    cur.execute(update_sql, params)
                    vec_id = params[-1]
                    if cur.rowcount > 0 and vec_id not in seen:
                        seen.add(vec_id)
                        confirmed_ids.append(vec_id)
                conn.commit()
                cur.close()
                self.logger.info(f"Updated {len(confirmed_ids)} of {len(ids)} vectors")
                return confirmed_ids
            except ValidationError:
                conn.rollback()
                raise
            except Exception as e:
                conn.rollback()
                raise ProcessingError("Failed to update vectors") from e

    def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get vectors by ID.

        Args:
            ids: List of vector IDs

        Returns:
            List of dictionaries with id, vector, and metadata

        Raises:
            ProcessingError: If database operation fails
        """
        if not ids:
            return []

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                results = []
                batch_size = 1000
                for i in range(0, len(ids), batch_size):
                    batch_ids = ids[i : i + batch_size]
                    placeholders = ",".join(["?"] * len(batch_ids))
                    cur.execute(
                        f"SELECT id, embedding, metadata FROM {self.table_name} "
                        f"WHERE id IN ({placeholders})",
                        batch_ids,
                    )
                    for row in cur.fetchall():
                        vid, embedding_blob, metadata_json = row
                        vec = (
                            np.frombuffer(embedding_blob, dtype=np.float32).copy()
                            if embedding_blob
                            else None
                        )
                        meta = json.loads(metadata_json) if metadata_json else {}
                        results.append(
                            {
                                "id": vid,
                                "vector": vec,
                                "metadata": meta,
                            }
                        )
                cur.close()
                return results
            except Exception as e:
                raise ProcessingError("Failed to get vectors") from e

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        try:
            results = self.get([vector_id])
            if results and len(results) > 0:
                return results[0].get("vector")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get vector {vector_id}: {e}")
            return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        try:
            results = self.get([vector_id])
            if results and len(results) > 0:
                return results[0].get("metadata")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {vector_id}: {e}")
            return None

    def scan_vectors(self, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Page through stored vectors ordered by id.

        Args:
            offset: Number of rows to skip
            limit: Maximum number of rows to return

        Returns:
            List of result dicts with 'id', 'metadata', and 'vector'
        """
        if limit <= 0:
            return []

        query_sql = f"""
            SELECT id, embedding, metadata
            FROM {self.table_name}
            ORDER BY id
            LIMIT ? OFFSET ?
        """

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(query_sql, (limit, offset))
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, embedding_blob, meta_json = row
                    vec = None
                    if embedding_blob:
                        vec = np.frombuffer(embedding_blob, dtype=np.float32).copy()
                    results.append({
                        "id": vec_id,
                        "metadata": json.loads(meta_json) if meta_json else {},
                        "vector": vec,
                    })
                return results
            except Exception as e:
                raise ProcessingError(f"Failed to scan vectors: {str(e)}") from e

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter stored vectors by metadata using SQLite JSON functions.

        Args:
            filters: Dictionary of metadata filter conditions
            limit: Maximum number of results

        Returns:
            List of results containing id, metadata, and vector
        """
        filter_conditions = []
        filter_params = []

        if filters:
            for key, value in filters.items():
                if not self._is_safe_identifier(key):
                    raise ValidationError(
                        f"Invalid filter key: {key!r}. "
                        "Keys must start with a letter or underscore and contain "
                        "only alphanumeric characters and underscores."
                    )
                if isinstance(value, dict):
                    if "min" in value and value["min"] is not None:
                        filter_conditions.append(f"CAST(json_extract(metadata, '$.{key}') AS NUMERIC) >= ?")
                        filter_params.append(value["min"])
                    if "max" in value and value["max"] is not None:
                        filter_conditions.append(f"CAST(json_extract(metadata, '$.{key}') AS NUMERIC) <= ?")
                        filter_params.append(value["max"])
                elif isinstance(value, list):
                    # If the metadata value at this key is itself a JSON array, match on
                    # intersection (mirrors the in-memory backend's set-intersection
                    # semantics); otherwise fall back to plain scalar membership. Both
                    # cases are handled uniformly via json_each: a non-array value is
                    # wrapped in a one-element array first so json_each always sees a
                    # valid JSON array to iterate.
                    placeholders = ", ".join(["?"] * len(value))
                    filter_conditions.append(
                        f"EXISTS (SELECT 1 FROM json_each("
                        f"  CASE WHEN json_type(metadata, '$.{key}') = 'array'"
                        f"       THEN json_extract(metadata, '$.{key}')"
                        f"       ELSE json_array(json_extract(metadata, '$.{key}'))"
                        f"  END"
                        f") je WHERE je.value IN ({placeholders}))"
                    )
                    filter_params.extend([str(v) if not isinstance(v, (int, float, bool)) else v for v in value])
                else:
                    filter_conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                    if isinstance(value, bool):
                        filter_params.append(1 if value else 0)
                    else:
                        filter_params.append(value)

        where_clause = ""
        if filter_conditions:
            where_clause = " WHERE " + " AND ".join(filter_conditions)

        query_sql = f"""
            SELECT id, embedding, metadata
            FROM {self.table_name}
            {where_clause}
            LIMIT ?
        """
        params = filter_params + [limit]

        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    vec_id, embedding_blob, meta_json = row
                    vec = None
                    if embedding_blob:
                        vec = np.frombuffer(embedding_blob, dtype=np.float32).copy()

                    results.append({
                        "id": vec_id,
                        "metadata": json.loads(meta_json) if meta_json else {},
                        "vector": vec
                    })
                return results
            except Exception as e:
                raise ProcessingError(f"Failed to filter by metadata: {str(e)}") from e

    def create_index(
        self,
        index_type: str = "hnsw",
        params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create an index on the vector column.
        For SQLiteVecStore, vec0 virtual tables automatically index vectors,
        so this is a no-op that always returns True for interface parity.
        """
        self.logger.debug("create_index is a no-op for SQLiteVecStore")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        Get store statistics.

        Returns:
            Dictionary with vector_count, dimension, and distance_metric
        """
        with self._lock, self._get_connection() as conn:
            try:
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                count = cur.fetchone()[0]
                cur.close()
                return {
                    "vector_count": count,
                    "dimension": self.dimension,
                    "distance_metric": self.distance_metric,
                }
            except Exception as e:
                raise ProcessingError("Failed to get store statistics") from e

    def count(self) -> int:
        """Return the exact number of vectors stored in this SQLite table.

        Executes ``SELECT COUNT(*) FROM <table>`` under the store's lock to
        guarantee a consistent, transaction-aware result.
        """
        stats = self.get_stats()
        return int(stats["vector_count"])

    def close(self):
        """Close the database connection."""
        if hasattr(self, "_lock") and self._lock:
            with self._lock:
                if hasattr(self, "_conn") and self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
        else:
            if hasattr(self, "_conn") and self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()
