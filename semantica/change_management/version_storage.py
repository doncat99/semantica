"""
Version Storage Module

This module provides abstract storage interfaces and concrete implementations
for persistent version management in Semantica.

Key Features:
    - Abstract VersionStorage interface
    - In-memory storage implementation
    - SQLite-based persistent storage implementation
    - Checksum computation and validation
    - Thread-safe operations

Main Classes:
    - VersionStorage: Abstract base class for storage backends
    - InMemoryVersionStorage: Dictionary-based in-memory storage
    - SQLiteVersionStorage: SQLite-based persistent storage

Example Usage:
    >>> from semantica.change_management.version_storage import SQLiteVersionStorage
    >>> storage = SQLiteVersionStorage("versions.db")
    >>> storage.save(snapshot)
    >>> versions = storage.list_all()

Author: Semantica Contributors
License: MIT
"""

import hashlib
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger


def _validate_ontology_version(version: Dict[str, Any]) -> None:
    """This storage serves ontology revisions; aggregate knowledge is retired."""
    allowed = {"label", "timestamp", "author", "description", "checksum",
               "ontology_iri", "version_info", "structure", "metadata"}
    if (not isinstance(version, dict) or set(version) - allowed
            or not {"ontology_iri", "structure"} <= version.keys()):
        raise ValidationError("Version storage accepts only ontology revisions")


class VersionStorage(ABC):
    """
    Abstract base class for version storage backends.

    This interface defines the contract that all storage implementations
    must follow for version management operations.
    """

    @abstractmethod
    def save(self, snapshot: Dict[str, Any]) -> None:
        """Save a version snapshot."""
        pass

    @abstractmethod
    def get(self, label: str) -> Optional[Dict[str, Any]]:
        """Retrieve a version snapshot by label."""
        pass

    @abstractmethod
    def list_all(self) -> List[Dict[str, Any]]:
        """List all version snapshots."""
        pass

    @abstractmethod
    def exists(self, label: str) -> bool:
        """Check if a version exists."""
        pass

    @abstractmethod
    def delete(self, label: str) -> bool:
        """Delete a version snapshot."""
        pass


class InMemoryVersionStorage(VersionStorage):
    """
    In-memory version storage implementation.

    This implementation stores all version data in memory using a dictionary.
    Data is lost when the process ends.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.logger = get_logger("in_memory_storage")

    def save(self, snapshot: Dict[str, Any]) -> None:
        """Save snapshot to memory."""
        _validate_ontology_version(snapshot)
        label = snapshot.get("label")
        if not label:
            raise ValidationError("Snapshot must have a 'label' field")

        with self._lock:
            if label in self._storage:
                raise ValidationError(f"Version '{label}' already exists")

            # Deep copy to prevent external modifications
            self._storage[label] = json.loads(json.dumps(snapshot))
            self.logger.debug(f"Saved version '{label}' to memory")

    def get(self, label: str) -> Optional[Dict[str, Any]]:
        """Retrieve snapshot from memory."""
        with self._lock:
            snapshot = self._storage.get(label)
            if snapshot:
                _validate_ontology_version(snapshot)
                # Return deep copy to prevent external modifications
                return json.loads(json.dumps(snapshot))
            return None

    def list_all(self) -> List[Dict[str, Any]]:
        """List all snapshots in memory."""
        with self._lock:
            # Return metadata only (without full graph data)
            metadata_list = []
            for label, snapshot in self._storage.items():
                _validate_ontology_version(snapshot)
                metadata = {
                    "label": snapshot.get("label"),
                    "timestamp": snapshot.get("timestamp"),
                    "author": snapshot.get("author"),
                    "description": snapshot.get("description"),
                    "checksum": snapshot.get("checksum"),
                    }
                metadata_list.append(metadata)
            return metadata_list

    def exists(self, label: str) -> bool:
        """Check if version exists in memory."""
        with self._lock:
            return label in self._storage

    def delete(self, label: str) -> bool:
        """Delete version from memory."""
        with self._lock:
            if label in self._storage:
                del self._storage[label]
                self.logger.debug(f"Deleted version '{label}' from memory")
                return True
            return False


class SQLiteVersionStorage(VersionStorage):
    """
    SQLite-based persistent version storage implementation.

    This implementation stores version data in a SQLite database file,
    providing persistence across process restarts.
    """

    def __init__(self, storage_path: str):
        """
        Initialize SQLite storage.

        Args:
            storage_path: Path to SQLite database file
        """
        self.storage_path = Path(storage_path)
        self._lock = threading.RLock()
        self.logger = get_logger("sqlite_storage")

        # Create directory if it doesn't exist
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS versions (
                        label TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        author TEXT NOT NULL,
                        description TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        snapshot_data TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)

                conn.commit()
                self.logger.debug(f"Initialized SQLite database at {self.storage_path}")
            finally:
                conn.close()

    def save(self, snapshot: Dict[str, Any]) -> None:
        """Save snapshot to SQLite database."""
        _validate_ontology_version(snapshot)
        label = snapshot.get("label")
        if not label:
            raise ValidationError("Snapshot must have a 'label' field")

        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()

                # Check if version already exists
                cursor.execute("SELECT label FROM versions WHERE label = ?", (label,))
                if cursor.fetchone():
                    raise ValidationError(f"Version '{label}' already exists")

                # Insert new version
                cursor.execute(
                    """
                    INSERT INTO versions
                    (label, timestamp, author, description, checksum, snapshot_data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        label,
                        snapshot.get("timestamp", ""),
                        snapshot.get("author", ""),
                        snapshot.get("description", ""),
                        snapshot.get("checksum", ""),
                        json.dumps(snapshot),
                        datetime.now().isoformat(),
                    ),
                )

                conn.commit()
                self.logger.debug(f"Saved version '{label}' to SQLite database")

            except sqlite3.Error as e:
                raise ProcessingError(f"Failed to save version to database: {e}")
            finally:
                conn.close()

    def get(self, label: str) -> Optional[Dict[str, Any]]:
        """Retrieve snapshot from SQLite database."""
        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT snapshot_data FROM versions WHERE label = ?
                """,
                    (label,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                snapshot = json.loads(row[0])
                _validate_ontology_version(snapshot)
                return snapshot

            except sqlite3.Error as e:
                raise ProcessingError(f"Failed to retrieve version from database: {e}")
            finally:
                conn.close()

    def list_all(self) -> List[Dict[str, Any]]:
        """List all snapshots in SQLite database."""
        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT snapshot_data FROM versions ORDER BY timestamp DESC
                """)

                metadata_list = []
                for row in cursor.fetchall():
                    snapshot = json.loads(row[0])
                    _validate_ontology_version(snapshot)

                    metadata = {
                        "label": snapshot.get("label"),
                        "timestamp": snapshot.get("timestamp"),
                        "author": snapshot.get("author"),
                        "description": snapshot.get("description"),
                        "checksum": snapshot.get("checksum"),
                    }
                    metadata_list.append(metadata)

                return metadata_list

            except sqlite3.Error as e:
                raise ProcessingError(f"Failed to list versions from database: {e}")
            finally:
                conn.close()

    def exists(self, label: str) -> bool:
        """Check if version exists in SQLite database."""
        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM versions WHERE label = ?", (label,))
                return cursor.fetchone() is not None
            except sqlite3.Error as e:
                raise ProcessingError(f"Failed to check version existence: {e}")
            finally:
                conn.close()

    def delete(self, label: str) -> bool:
        """Delete version from SQLite database."""
        with self._lock:
            conn = sqlite3.connect(str(self.storage_path))
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM versions WHERE label = ?", (label,))
                deleted = cursor.rowcount > 0
                conn.commit()

                if deleted:
                    self.logger.debug(f"Deleted version '{label}' from SQLite database")

                return deleted

            except sqlite3.Error as e:
                raise ProcessingError(f"Failed to delete version from database: {e}")
            finally:
                conn.close()


def compute_checksum(data: Dict[str, Any]) -> str:
    """
    Compute SHA-256 checksum for version data.

    Args:
        data: Dictionary containing version data

    Returns:
        SHA-256 checksum as hexadecimal string
    """
    # Create a deterministic JSON representation
    json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def verify_checksum(snapshot: Dict[str, Any]) -> bool:
    """
    Verify the integrity of a snapshot using its checksum.

    Args:
        snapshot: Snapshot dictionary with checksum field

    Returns:
        True if checksum is valid, False otherwise
    """
    stored_checksum = snapshot.get("checksum")
    if not stored_checksum:
        return False

    # Create copy without checksum for verification
    data_copy = snapshot.copy()
    data_copy.pop("checksum", None)

    computed_checksum = compute_checksum(data_copy)
    return stored_checksum == computed_checksum
