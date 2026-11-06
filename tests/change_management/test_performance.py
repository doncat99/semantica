"""
Performance and Latency Tests for Enhanced Change Management Module

This module provides comprehensive performance testing for all change management
components including storage backends, version managers, and diff algorithms.
"""

import time
import tempfile
import os
import threading
import psutil
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple

import pytest
from semantica.change_management import (
    OntologyVersionManager,
    InMemoryVersionStorage,
    SQLiteVersionStorage,
    ChangeLogEntry,
    compute_checksum,
    verify_checksum
)


class PerformanceTestSuite:
    """Comprehensive performance test suite for change management module."""
    
    def __init__(self):
        """Initialize performance test suite."""
        self.results = {}
        self.process = psutil.Process()
    
    def measure_time(self, func, *args, **kwargs) -> Tuple[Any, float]:
        """Measure execution time of a function."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        return result, end_time - start_time
    
    def measure_memory(self, func, *args, **kwargs) -> Tuple[Any, float]:
        """Measure memory usage of a function."""
        initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        result = func(*args, **kwargs)
        final_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        return result, final_memory - initial_memory
    
    def generate_test_graph(self, num_entities: int, num_relationships: int) -> Dict[str, Any]:
        """Generate test knowledge graph with specified size."""
        entities = []
        for i in range(num_entities):
            entities.append({
                "id": f"entity_{i}",
                "name": f"Entity {i}",
                "type": f"Type_{i % 10}",
                "description": f"Description for entity {i}" * 5,  # Make it longer
                "properties": {
                    "category": f"Category_{i % 5}",
                    "score": i * 0.1,
                    "active": i % 2 == 0
                }
            })
        
        relationships = []
        for i in range(num_relationships):
            source_idx = i % num_entities
            target_idx = (i + 1) % num_entities
            relationships.append({
                "id": f"relationship_{i}",
                "source": f"entity_{source_idx}",
                "target": f"entity_{target_idx}",
                "type": f"relation_type_{i % 5}",
                "weight": i * 0.01,
                "properties": {
                    "strength": i % 10,
                    "confidence": 0.8 + (i % 20) * 0.01
                }
            })
        
        return {
            "entities": entities,
            "relationships": relationships
        }
    
    def generate_test_ontology(self, num_classes: int, num_properties: int) -> Dict[str, Any]:
        """Generate test ontology with specified size."""
        classes = [f"Class_{i}" for i in range(num_classes)]
        properties = [f"property_{i}" for i in range(num_properties)]
        individuals = [f"individual_{i}" for i in range(num_classes // 2)]
        axioms = [f"Class_{i} hasProperty property_{i % num_properties}" for i in range(num_classes)]
        
        return {
            "uri": "https://test.com/ontology",
            "version_info": {"version": "1.0", "date": "2024-01-30"},
            "structure": {
                "classes": classes,
                "properties": properties,
                "individuals": individuals,
                "axioms": axioms
            }
        }


class TestVersionManagerPerformance:
    """Test performance of enhanced version managers."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.perf_suite = PerformanceTestSuite()
        self.test_sizes = [50, 100, 500, 1000, 2000]


    def test_ontology_version_manager_performance(self):
        """Test OntologyVersionManager performance with ontologies."""
        print("\n=== OntologyVersionManager Performance ===")
        
        manager = OntologyVersionManager()
        results = {}
        
        ontology_sizes = [50, 100, 500, 1000]
        
        for size in ontology_sizes:
            ontology = self.perf_suite.generate_test_ontology(size, size // 2)
            
            # Test ontology snapshot creation
            _, create_time = self.perf_suite.measure_time(
                manager.create_snapshot,
                ontology,
                f"ont_v{size}",
                "test@example.com",
                f"Ontology with {size} classes"
            )
            
            results[size] = {"create_time": create_time}
            print(f"Classes {size:4d}: Create={create_time*1000:6.2f}ms")
        
        # Test structural comparison
        ont1 = self.perf_suite.generate_test_ontology(500, 250)
        ont2 = self.perf_suite.generate_test_ontology(520, 260)  # Slightly different
        
        manager.create_snapshot(ont1, "ont_comp_1", "test@example.com", "Ontology 1")
        manager.create_snapshot(ont2, "ont_comp_2", "test@example.com", "Ontology 2")
        
        _, compare_time = self.perf_suite.measure_time(
            manager.compare_versions, "ont_comp_1", "ont_comp_2"
        )
        
        print(f"Ontology comparison: {compare_time*1000:6.2f}ms")
        
        self.perf_suite.results["ontology_manager"] = results


class TestChecksumPerformance:
    """Test checksum computation and verification performance."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.perf_suite = PerformanceTestSuite()
    
    def test_checksum_performance(self):
        """Test checksum computation performance across different data sizes."""
        print("\n=== Checksum Performance ===")
        
        results = {}
        
        for size in [100, 500, 1000, 5000, 10000]:
            graph = self.perf_suite.generate_test_graph(size, size * 2)
            
            # Test checksum computation
            _, compute_time = self.perf_suite.measure_time(compute_checksum, graph)
            
            # Test checksum verification
            checksum = compute_checksum(graph)
            graph_with_checksum = graph.copy()
            graph_with_checksum["checksum"] = checksum
            
            _, verify_time = self.perf_suite.measure_time(verify_checksum, graph_with_checksum)
            
            results[size] = {
                "compute_time": compute_time,
                "verify_time": verify_time
            }
            
            print(f"Size {size:5d}: Compute={compute_time*1000:6.2f}ms, Verify={verify_time*1000:6.2f}ms")
        
        # Verify checksum performance requirements
        assert results[10000]["compute_time"] < 0.5, "Large checksum computation should be under 500ms"
        assert results[10000]["verify_time"] < 0.5, "Large checksum verification should be under 500ms"
        
        self.perf_suite.results["checksum"] = results
