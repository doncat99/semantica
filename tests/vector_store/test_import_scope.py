"""Selecting a native backend must not initialize unrelated pipelines."""
import subprocess
import sys


def test_sqlite_backend_import_is_scoped():
    subprocess.run([sys.executable, '-c', '''
import sys
from semantica.vector_store import SQLiteVecStore
assert SQLiteVecStore.__module__ == 'semantica.vector_store.sqlite_vec_store'
unrelated = [name for name in sys.modules if name.startswith((
    'semantica.vector_store.decision_', 'semantica.vector_store.hybrid_',
    'semantica.vector_store.faiss_', 'semantica.vector_store.weaviate_',
    'semantica.vector_store.qdrant_', 'semantica.vector_store.milvus_',
    'semantica.vector_store.pinecone_', 'semantica.vector_store.pgvector_'))]
assert not unrelated, unrelated
'''], check=True)


def test_hybrid_function_remains_callable_after_class_import():
    subprocess.run([sys.executable, '-c', '''
from semantica.vector_store import HybridSearch, hybrid_search
assert callable(HybridSearch)
assert callable(hybrid_search), hybrid_search
'''], check=True)
