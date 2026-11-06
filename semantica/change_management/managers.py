"""
Enhanced Version Managers Module

This module provides enhanced version management capabilities for ontologies, with comprehensive change tracking, persistent storage, and audit trails.

Key Features:
    - Enhanced VersionManager for ontologies
    - Structural comparison for ontology elements
    - Integration with storage backends and metadata

Main Classes:
    - EnhancedVersionManager: Advanced ontology version management

Author: Semantica Contributors
License: MIT
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from .change_log import ChangeLogEntry
from .version_storage import (
    InMemoryVersionStorage,
    SQLiteVersionStorage,
    compute_checksum,
    verify_checksum,
)
from ..utils.exceptions import ValidationError
from ..utils.logging import get_logger


class BaseVersionManager(ABC):
    """
    Abstract base class for enhanced version managers.

    Provides common functionality for version management across different data types.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize base version manager.

        Args:
            storage_path: Path to SQLite database for persistent storage.
                         If None, uses in-memory storage.
        """
        self.logger = get_logger(self.__class__.__name__.lower())

        # Initialize storage backend
        if storage_path:
            self.storage = SQLiteVersionStorage(storage_path)
            self.logger.info(f"Initialized with SQLite storage: {storage_path}")
        else:
            self.storage = InMemoryVersionStorage()
            self.logger.info("Initialized with in-memory storage")

    @abstractmethod
    def create_snapshot(
        self, data: Any, version_label: str, author: str, description: str, **options
    ) -> Dict[str, Any]:
        """Create a versioned snapshot of the data."""
        pass

    @abstractmethod
    def compare_versions(
        self, version1: Any, version2: Any, **options
    ) -> Dict[str, Any]:
        """Compare two versions and return detailed differences."""
        pass

    def list_versions(self) -> List[Dict[str, Any]]:
        """List all version snapshots."""
        return self.storage.list_all()

    def get_version(self, label: str) -> Optional[Dict[str, Any]]:
        """Retrieve specific version by label."""
        return self.storage.get(label)

    def verify_checksum(self, snapshot: Dict[str, Any]) -> bool:
        """Verify the integrity of a snapshot using its checksum."""
        return verify_checksum(snapshot)


class OntologyVersionManager(BaseVersionManager):
    """
    Version management for ontologies with structural comparison.

    Provides comprehensive version management for ontologies including
    detailed structural analysis and change tracking.

    Features:
        - Structural comparison of ontology elements
        - Detailed diff for classes, properties, individuals, axioms
        - Persistent storage with metadata
        - Change tracking and audit trails
    """

    def __init__(self, storage_path: Optional[str] = None, **config):
        """
        Initialize enhanced version manager.

        Args:
            storage_path: Path to SQLite database file for persistent storage.
                         If None, uses in-memory storage
            **config: Additional configuration options
        """
        super().__init__(storage_path)
        self.config = config
        self.versions = {}  # In-memory version tracking for compatibility

    def create_snapshot(
        self,
        ontology_data: Dict[str, Any],
        version_label: str,
        author: str,
        description: str,
        **options,
    ) -> Dict[str, Any]:
        """
        Create ontology version snapshot.

        Args:
            ontology_data: Ontology data dictionary
            version_label: Version string (e.g., "v1.0")
            author: Email address of the change author
            description: Change description
            **options: Additional options including metadata

        Returns:
            dict: Ontology version snapshot
        """
        change_entry = ChangeLogEntry(
            timestamp=datetime.now().isoformat(), author=author, description=description
        )

        snapshot = {
            "label": version_label,
            "timestamp": change_entry.timestamp,
            "author": change_entry.author,
            "description": change_entry.description,
            "ontology_iri": ontology_data.get("uri", ""),
            "version_info": ontology_data.get("version_info", {}),
            "structure": ontology_data.get("structure", {}),
            "metadata": options.get("metadata", {}),
        }

        snapshot["checksum"] = compute_checksum(snapshot)
        self.storage.save(snapshot)
        self.versions[version_label] = snapshot
        self.logger.info(f"Created ontology snapshot '{version_label}' by {author}")
        return snapshot

    def compare_versions(
        self, version1: str, version2: str, **options
    ) -> Dict[str, Any]:
        """
        Compare two ontology versions with detailed structural analysis.

        Args:
            version1: First version label
            version2: Second version label
            **options: Additional comparison options

        Returns:
            Detailed comparison results including structural differences
        """
        # Get versions from storage
        v1_snapshot = self.storage.get(version1)
        v2_snapshot = self.storage.get(version2)

        if not v1_snapshot:
            raise ValidationError(f"Version not found: {version1}")
        if not v2_snapshot:
            raise ValidationError(f"Version not found: {version2}")

        # Basic metadata comparison
        metadata_changes = {}
        if v1_snapshot.get("ontology_iri") != v2_snapshot.get("ontology_iri"):
            metadata_changes["ontology_iri"] = {
                "from": v1_snapshot.get("ontology_iri"),
                "to": v2_snapshot.get("ontology_iri"),
            }
        if v1_snapshot.get("version_info") != v2_snapshot.get("version_info"):
            metadata_changes["version_info"] = {
                "from": v1_snapshot.get("version_info"),
                "to": v2_snapshot.get("version_info"),
            }

        # Structural comparison
        structural_diff = self._compare_ontology_structures(v1_snapshot, v2_snapshot)

        return {
            "version1": version1,
            "version2": version2,
            "metadata_changes": metadata_changes,
            **structural_diff,
        }

    def _compare_ontology_structures(
        self, v1_snapshot: Dict[str, Any], v2_snapshot: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare structural elements between two ontology versions.

        Args:
            v1_snapshot: First ontology version snapshot
            v2_snapshot: Second ontology version snapshot

        Returns:
            Dictionary with structural differences
        """
        # Extract structural information
        v1_structure = v1_snapshot.get("structure", {})
        v2_structure = v2_snapshot.get("structure", {})

        # Compare classes
        v1_classes = set(v1_structure.get("classes", []))
        v2_classes = set(v2_structure.get("classes", []))

        classes_added = list(v2_classes - v1_classes)
        classes_removed = list(v1_classes - v2_classes)

        # Compare properties
        v1_properties = set(v1_structure.get("properties", []))
        v2_properties = set(v2_structure.get("properties", []))

        properties_added = list(v2_properties - v1_properties)
        properties_removed = list(v1_properties - v2_properties)

        # Compare individuals
        v1_individuals = set(v1_structure.get("individuals", []))
        v2_individuals = set(v2_structure.get("individuals", []))

        individuals_added = list(v2_individuals - v1_individuals)
        individuals_removed = list(v1_individuals - v2_individuals)

        # Compare axioms/rules
        v1_axioms = set(v1_structure.get("axioms", []))
        v2_axioms = set(v2_structure.get("axioms", []))

        axioms_added = list(v2_axioms - v1_axioms)
        axioms_removed = list(v1_axioms - v2_axioms)

        return {
            "classes_added": classes_added,
            "classes_removed": classes_removed,
            "properties_added": properties_added,
            "properties_removed": properties_removed,
            "individuals_added": individuals_added,
            "individuals_removed": individuals_removed,
            "axioms_added": axioms_added,
            "axioms_removed": axioms_removed,
            "summary": {
                "classes_added": len(classes_added),
                "classes_removed": len(classes_removed),
                "properties_added": len(properties_added),
                "properties_removed": len(properties_removed),
                "individuals_added": len(individuals_added),
                "individuals_removed": len(individuals_removed),
                "axioms_added": len(axioms_added),
                "axioms_removed": len(axioms_removed),
            },
        }
