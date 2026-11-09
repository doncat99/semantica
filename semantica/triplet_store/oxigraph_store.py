"""Embedded RDF storage backed by Oxigraph.

This backend provides an in-process SPARQL 1.1 store for development, tests,
and workloads that do not need a separately managed graph database server.
It can run entirely in memory or persist its data to a local directory.
"""

import importlib
import json
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from ..semantic_extract.triplet_extractor import Triplet
from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from . import sparql_escaping


class _LockedNativeStore:
    """Serialize raw native writes with short completion reads and publication edits."""
    _MUTATORS = frozenset({'add', 'add_graph', 'bulk_extend', 'bulk_load', 'clear',
        'clear_graph', 'extend', 'load', 'remove', 'remove_graph', 'update'})

    def __init__(self, native, owner):
        self._native, self._owner = native, owner

    def __getattr__(self, name):
        method = getattr(self._native, name)
        if name not in self._MUTATORS:
            return method
        def mutate(*args, **kwargs):
            with self._owner._publication_lock:
                return method(*args, **kwargs)
        return mutate

    def __iter__(self):
        return iter(self._native)

    def __len__(self):
        return len(self._native)

    def __contains__(self, value):
        return value in self._native


class OxigraphStore:
    """Embedded, optionally persistent RDF store powered by PyOxigraph."""

    supports_named_graphs = True
    _XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"

    def close(self):
        """Flush and release the native handle before a process handoff."""
        if hasattr(self, "store"):
            try:
                self.flush()
            finally:
                del self.store

    def publication_status(self, project):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).status()

    def publication_attribute_reference(self, project, generation, entity, name):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).attribute_reference(generation, entity, name)

    def begin_publication(self, project, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).begin(**options)

    def identity_stage_status(self, project, generation, input_key):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).identity_stage_status(generation, input_key)

    def reset_identity_stage(self, project, generation):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).reset_identity_stage(generation)

    def seal_identity_stage(self, project, generation, input_key):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).seal_identity_stage(generation, input_key)

    def stage_publication_sources(self, project, generation, sources):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).stage_sources(generation, sources)

    def stage_publication_canonical(self, project, generation, records):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).stage_canonical(generation, records)

    def seal_publication_canonical_count(self, project, generation, count):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).seal_canonical_count(generation, count)


    def read_publication_fact_members(self, project, generation, identity, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).fact_members(generation, identity, **options)

    def activate_publication(self, project, generation, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).activate(generation, **options)

    def stage_publication_communities(self, project, generation, records):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).stage_communities(generation, records)

    def stage_publication_topics(self, project, generation, records):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).stage_topics(generation, records)

    def read_native_source_scene(self, project, generation, selection):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).source_scene(generation, selection)

    def read_native_classification_dimension(self, project, generation, source, dimension_id=None, **page):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).classification_dimension(generation, source, dimension_id, **page)

    def read_native_section_records(self, project, generation, selection):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).section_records(generation, selection)

    def withdraw_publication(self, project, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).withdraw(**options)

    def read_native_records(self, project, generation, record_ids, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).read(generation, record_ids, **options)

    def read_record_binding(self, project, generation, identity):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).record_binding(generation, identity)

    def read_source_binding(self, project, generation, source):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).source_binding(generation, source)

    def read_grounded_candidates(self, project, generation, positions, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).grounded_candidates(generation, positions, **options)

    def read_grounded_reference_page(self, project, generation, position, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).grounded_reference_page(generation, position, **options)

    def read_publication_scene(self, project, generation, selection):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).scene(generation, selection)

    def read_publication_records(self, project, generation, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).page(generation, **options)

    def read_build_records(self, project, generation, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).build_page(generation, **options)

    def read_build_nodes(self, project, generation, record_ids, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).build_read(generation, record_ids, **options)

    def read_canonical_membership(self, project, generation, **options):
        from .publication_records import PublicationRecords
        return PublicationRecords(self, project).page(generation, canonical=True, **options)

    def extraction_operation_id(self, binding, stage):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).operation.value

    def rebind_extraction(self, previous_binding, current_binding, stage):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords.rebind(self, previous_binding, current_binding, stage)

    def extraction_receipt(self, binding, stage):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).receipt()

    def audit_extraction(self, binding, stage):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).audit()

    def adopt_extraction(self, binding, stage, values, **options):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).adopt(values, **options)

    def read_extraction(self, binding, stage, **options):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).read(**options)

    def read_extraction_records(self, binding, stage, **options):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).page(**options)

    def read_extraction_nodes(self, binding, stage, record_ids, **options):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).read_nodes(record_ids, **options)

    def read_extraction_receipts(self, binding, stage):
        from .extraction_records import ExtractionRecords
        return ExtractionRecords(self, binding, stage).read_receipts()

    def classification_operation_id(self, binding):
        from .classification_records import ClassificationRecords
        return ClassificationRecords(self, binding).operation.value

    def rebind_classification(self, previous_binding, current_binding):
        from .classification_records import ClassificationRecords
        return ClassificationRecords.rebind(self, previous_binding, current_binding)

    def classification_receipt(self, binding):
        from .classification_records import ClassificationRecords
        return ClassificationRecords(self, binding).receipt()

    def adopt_classification(self, binding, value, **options):
        from .classification_records import ClassificationRecords
        return ClassificationRecords(self, binding).adopt(value, **options)

    def read_classification(self, binding, **options):
        from .classification_records import ClassificationRecords
        return ClassificationRecords(self, binding).read(**options)

    def read_classification_receipts(self, binding):
        from .classification_records import ClassificationRecords
        return ClassificationRecords(self, binding).read_receipts()

    def __init__(
        self,
        path: Optional[Union[str, os.PathLike]] = None,
        **config,
    ):
        """Initialize an in-memory or on-disk Oxigraph store.

        Args:
            path: Directory used for persistent storage. If omitted, the store
                is kept in memory.
            **config: Backend configuration. ``path`` may also be supplied in
                this mapping.

        Raises:
            ImportError: If the optional ``pyoxigraph`` package is missing.
            ProcessingError: If the store cannot be opened.
        """
        self.logger = get_logger("oxigraph_store")
        self._publication_lock = threading.RLock()
        self._defer_flush = False
        # Accept storage_path as an alias for path (matches the convention used
        # by other Semantica stores). Pop it so it isn't left in self.config.
        if path is None and "storage_path" in config:
            path = config.pop("storage_path")
        self.config = config
        self.path = path if path is not None else config.get("path")

        try:
            self._oxigraph = importlib.import_module("pyoxigraph")
        except (ImportError, OSError) as exc:
            raise ImportError(
                "PyOxigraph is required for the 'oxigraph' backend. "
                'Install it with: pip install "semantica[tripletstore-oxigraph]"'
            ) from exc

        store_path = None
        if self.path is not None:
            path_obj = Path(self.path).expanduser()
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ProcessingError(
                    f"Failed to create Oxigraph store directory {path_obj}: {exc}"
                ) from exc
            store_path = str(path_obj)
            self.path = store_path

        try:
            self.store = _LockedNativeStore(self._oxigraph.Store(store_path), self)
        except Exception as exc:
            location = store_path or "memory"
            raise ProcessingError(
                f"Failed to initialize Oxigraph store at {location}: {exc}"
            ) from exc

    def _update_derived_graph(self, graph, *, insert='', delete='', where=''):
        """Owner-only graph-scoped writes cannot invalidate accepted RDF facts.

        Templates come from the extraction/publication codecs. The mutation
        target is constructed here, never inferred from arbitrary SPARQL text.
        Public raw Store.update remains conservatively invalidating.
        """
        value = graph.value
        if not (re.fullmatch(r'urn:semantica:publication:[0-9a-f]{64}', value)
                or re.fullmatch(r'urn:semantica:extraction:[0-9a-f]{64}:(?:identity|fact)-projection', value)):
            raise ProcessingError('Derived mutation cannot target accepted extraction facts')
        statement = ''
        if delete:
            statement += f'DELETE {{ GRAPH {graph} {{ {delete} }} }} '
        if insert:
            statement += f'INSERT {{ GRAPH {graph} {{ {insert} }} }} '
        statement += f'WHERE {{ {where} }}'
        with self._publication_lock:
            self.store._native.update(statement)

    def add_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Add one triplet to the default graph or ``options['graph']``.

        The write is committed to the store's in-memory state immediately.
        pyoxigraph's background threads will persist it to disk shortly
        afterward; call :meth:`flush` explicitly if you need a synchronous
        durability guarantee before reopening or crashing.
        """
        try:
            graph_name = self._graph_name(options.get("graph"))
            self.store.extend([self._to_quad(triplet, graph_name)])
            return {
                "success": True,
                "triplets_loaded": 1,
                "graph": options.get("graph"),
            }
        except Exception as exc:
            self.logger.error(f"Oxigraph load failed: {exc}")
            raise ProcessingError(f"Oxigraph load failed: {exc}") from exc

    def add_triplets(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """Add triplets in one native Oxigraph batch.

        The batch is written transactionally and then explicitly flushed to
        disk before returning.  This makes the full batch durable without
        requiring a separate :meth:`flush` call.  In-memory stores skip the
        flush (there is nothing to sync).

        For high-volume imports the :class:`~.bulk_loader.BulkLoader` splits
        work into chunks and calls this method once per chunk, so each chunk
        lands as one atomic, durable unit.
        """
        try:
            graph_name = self._graph_name(options.get("graph"))
            quads = [self._to_quad(triplet, graph_name) for triplet in triplets]
            self.store.extend(quads)
        except Exception as exc:
            self.logger.error(f"Oxigraph load failed: {exc}")
            raise ProcessingError(f"Oxigraph load failed: {exc}") from exc

        # Flush is kept outside the write try/except so that a flush I/O error
        # does not produce a misleading "load failed" message when extend()
        # already committed the batch successfully.
        if self.path is not None:
            try:
                self.flush()
            except OSError as exc:
                self.logger.warning(
                    f"Oxigraph flush failed after successful write: {exc}"
                )
                raise ProcessingError(
                    f"Oxigraph flush failed after successful write: {exc}"
                ) from exc

        return {
            "success": True,
            "triplets_loaded": len(triplets),
            "graph": options.get("graph"),
        }

    def bulk_load(self, triplets: List[Triplet], **options) -> Dict[str, Any]:
        """Load a batch of triplets using Oxigraph's native bulk operation."""
        return self.add_triplets(triplets, **options)

    def get_triplets(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        **options,
    ) -> List[Triplet]:
        """Return triplets matching a pattern in one graph.

        The default graph is queried unless ``graph`` is provided, matching
        the behavior of the other graph-aware triplet-store backends.
        """
        try:
            ox = self._oxigraph
            subject_term = ox.NamedNode(subject) if subject is not None else None
            predicate_term = ox.NamedNode(predicate) if predicate is not None else None
            object_term = (
                self._object_from_value(object) if object is not None else None
            )
            graph_name = self._graph_name(options.get("graph"))
            quads = self.store.quads_for_pattern(
                subject_term, predicate_term, object_term, graph_name
            )
            return [self._quad_to_triplet(quad) for quad in quads]
        except Exception as exc:
            self.logger.error(f"Failed to get Oxigraph triplets: {exc}")
            raise ProcessingError(f"Failed to get Oxigraph triplets: {exc}") from exc

    def delete_triplet(self, triplet: Triplet, **options) -> Dict[str, Any]:
        """Delete one triplet from the default graph or ``options['graph']``."""
        try:
            graph_name = self._graph_name(options.get("graph"))
            self.store.remove(self._to_quad(triplet, graph_name))
            return {"success": True}
        except Exception as exc:
            self.logger.error(f"Failed to delete Oxigraph triplet: {exc}")
            raise ProcessingError(f"Failed to delete Oxigraph triplet: {exc}") from exc

    def execute_sparql(self, query: str, **options) -> Dict[str, Any]:
        """Execute a query, optionally bounding retained serialized result records.

        ``max_rows`` and ``max_bytes`` reject overflow rather than truncate it.
        They bound Python result materialization, not the native query planner;
        callers must still use scoped indexed patterns and bounded query plans.
        ``substitutions`` accepts native RDF variable/term bindings.
        """
        result_format = options.get("result_format")
        if result_format not in (None, "bindings", "construct"):
            raise ValidationError(f"Invalid result_format: {result_format!r}")

        max_rows = options.get("max_rows")
        max_bytes = options.get("max_bytes")
        for name, value in (("max_rows", max_rows), ("max_bytes", max_bytes)):
            if value is not None and (type(value) is not int or value < 1):
                raise ValidationError(f"{name} must be a positive integer")
        retained_bytes = 0

        def append_result(values, value):
            nonlocal retained_bytes
            if max_rows is not None and len(values) >= max_rows:
                raise ProcessingError("Oxigraph query row budget exceeded")
            if max_bytes is not None:
                retained_bytes += len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                if retained_bytes > max_bytes:
                    raise ProcessingError("Oxigraph query byte budget exceeded")
            values.append(value)

        try:
            result = self.store.query(query, substitutions=options.get("substitutions"))

            if isinstance(result, self._oxigraph.QuerySolutions):
                if result_format == "construct":
                    raise ValidationError(
                        "result_format='construct' requires a CONSTRUCT or "
                        "DESCRIBE query"
                    )
                variables = [variable.value for variable in result.variables]
                bindings = []
                for solution in result:
                    binding = {}
                    for variable in variables:
                        term = solution[variable]
                        if term is not None:
                            binding[variable] = self._term_to_binding(term)
                    append_result(bindings, binding)
                return {
                    "success": True,
                    "bindings": bindings,
                    "variables": variables,
                    "metadata": {"query": query},
                }

            if isinstance(result, self._oxigraph.QueryBoolean):
                if result_format == "construct":
                    raise ValidationError(
                        "result_format='construct' requires a CONSTRUCT or "
                        "DESCRIBE query"
                    )
                append_result([], bool(result))
                return {
                    "success": True,
                    "bindings": [],
                    "variables": [],
                    "metadata": {"query": query, "boolean": bool(result)},
                }

            if isinstance(result, self._oxigraph.QueryTriples):
                if result_format == "bindings":
                    raise ValidationError(
                        "result_format='bindings' cannot be used with a "
                        "CONSTRUCT or DESCRIBE query"
                    )
                triples = []
                for triple in result:
                    metadata = self._literal_metadata(triple.object)
                    append_result(triples,
                        (
                            self._term_value(triple.subject),
                            self._term_value(triple.predicate),
                            self._term_value(triple.object),
                            metadata,
                        )
                    )
                return {
                    "success": True,
                    "bindings": [],
                    "variables": [],
                    "triples": triples,
                    "metadata": {
                        "query": query,
                        "result_format": "construct",
                    },
                }

            raise ProcessingError(
                f"Unsupported Oxigraph query result: {type(result).__name__}"
            )
        except (ValidationError, ProcessingError):
            raise
        except Exception as exc:
            self.logger.error(f"Oxigraph SPARQL query failed: {exc}")
            raise ProcessingError(f"Oxigraph SPARQL query failed: {exc}") from exc

    def execute_update(self, update: str) -> Dict[str, Any]:
        """Commit one native atomic update; persistent stores flush before return.

        Update templates are trusted application code. Dynamic RDF values must
        use native term serialization; the engine has no update substitutions.
        """
        try:
            self.store.update(update)
        except Exception as exc:
            raise ProcessingError(f"Oxigraph update failed: {exc}") from exc
        if self.path is not None:
            try:
                self.flush()
            except OSError as exc:
                raise ProcessingError("Oxigraph update committed but durability flush failed") from exc
        return {"success": True}

    @contextmanager
    def batch_writes(self):
        """Flush once at a caller-bounded maintenance boundary, including on error.

        This is not a rollback transaction. Release accepted recovery envelopes
        only after this context exits successfully. Other writers are excluded.
        """
        with self._publication_lock:
            if self._defer_flush:
                raise ProcessingError("Nested native write batches are not supported")
            self._defer_flush = True
            try:
                yield
            finally:
                self._defer_flush = False
                self.flush()

    def flush(self) -> None:
        """Flush pending writes, or defer to the enclosing maintenance boundary."""
        with self._publication_lock:
            if not self._defer_flush:
                self.store.flush()

    def _to_quad(self, triplet: Triplet, graph_name: Any) -> Any:
        ox = self._oxigraph
        return ox.Quad(
            ox.NamedNode(triplet.subject),
            ox.NamedNode(triplet.predicate),
            self._object_from_triplet(triplet),
            graph_name,
        )

    def _object_from_triplet(self, triplet: Triplet) -> Any:
        metadata = triplet.metadata or {}
        language = metadata.get("lang") or metadata.get("language")
        datatype = metadata.get("datatype") or metadata.get("literal_datatype")
        if language:
            return self._oxigraph.Literal(str(triplet.object), language=str(language))
        if datatype:
            datatype_iri = self._unwrap_iri(
                sparql_escaping.resolve_datatype_iri(str(datatype))
            )
            return self._oxigraph.Literal(
                str(triplet.object),
                datatype=self._oxigraph.NamedNode(datatype_iri),
            )
        if self._is_uri_value(triplet.object):
            return self._oxigraph.NamedNode(self._unwrap_iri(triplet.object))
        return self._oxigraph.Literal(str(triplet.object))

    def _object_from_value(self, value: str) -> Any:
        if self._is_uri_value(value):
            return self._oxigraph.NamedNode(self._unwrap_iri(value))
        return self._oxigraph.Literal(str(value))

    def _graph_name(self, graph: Optional[str]) -> Any:
        if graph is None:
            return self._oxigraph.DefaultGraph()
        return self._oxigraph.NamedNode(str(graph))

    def _quad_to_triplet(self, quad: Any) -> Triplet:
        metadata = {"source": "oxigraph"}
        metadata.update(self._literal_metadata(quad.object))
        return Triplet(
            subject=self._term_value(quad.subject),
            predicate=self._term_value(quad.predicate),
            object=self._term_value(quad.object),
            metadata=metadata,
        )

    def _term_to_binding(self, term: Any) -> Dict[str, str]:
        if isinstance(term, self._oxigraph.NamedNode):
            return {"type": "uri", "value": term.value}
        if isinstance(term, self._oxigraph.BlankNode):
            return {"type": "bnode", "value": term.value}
        if isinstance(term, self._oxigraph.Literal):
            binding = {"type": "literal", "value": term.value}
            if term.language is not None:
                binding["xml:lang"] = term.language
            elif term.datatype.value != self._XSD_STRING:
                binding["datatype"] = term.datatype.value
            return binding
        return {"type": "literal", "value": str(term)}

    def _literal_metadata(self, term: Any) -> Dict[str, str]:
        if not isinstance(term, self._oxigraph.Literal):
            return {}
        metadata = {}
        if term.language is not None:
            metadata["language"] = term.language
        elif term.datatype.value != self._XSD_STRING or self._is_uri_value(term.value):
            metadata["datatype"] = term.datatype.value
        return metadata

    def _term_value(self, term: Any) -> str:
        if isinstance(
            term,
            (
                self._oxigraph.NamedNode,
                self._oxigraph.BlankNode,
                self._oxigraph.Literal,
            ),
        ):
            return term.value
        return str(term)

    @staticmethod
    def _unwrap_iri(value: str) -> str:
        if value.startswith("<") and value.endswith(">"):
            return value[1:-1]
        return value

    @staticmethod
    def _is_uri_value(value: str) -> bool:
        if not isinstance(value, str) or not value:
            return False
        if value.startswith("<") and value.endswith(">"):
            return True
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https", "urn"} and not re.search(r"\s", value)
