"""
Temporal Query Module
"""

import copy
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from ..utils.progress_tracker import get_progress_tracker
from .temporal_model import (
    BiTemporalFact,
    TemporalBound,
    deserialize_relationship_temporal_fields,
    parse_temporal_bound,
    parse_temporal_value,
    serialize_temporal_value,
)
from .temporal_reasoning import IntervalRelation, TemporalInterval, TemporalReasoningEngine
from ..utils.exceptions import TemporalValidationError


@dataclass
class TemporalConsistencyIssue:
    message: str
    fact_id: str
    issue_type: str


@dataclass
class TemporalConsistencyReport:
    errors: List[Dict[str, str]]
    warnings: List[Dict[str, str]]


class TemporalGraphQuery:
    """
    Temporal knowledge graph query engine.

    This class provides time-aware querying capabilities for knowledge graphs
    with temporal information, enabling queries at specific time points, within
    time ranges, and temporal pattern detection.

    Features:
        - Time-range queries (filter relationships valid within range)
        - Temporal pattern detection (sequences, cycles, trends)
        - Graph evolution analysis
        - Temporal path finding (paths considering temporal validity)

    Example Usage:
        >>> query_engine = TemporalGraphQuery()
        >>> range_result = query_engine.query_time_range(graph, query, start_time, end_time)
        >>> evolution = query_engine.analyze_evolution(graph)
    """

    def __init__(
        self,
        enable_temporal_reasoning: bool = True,
        temporal_granularity: str = "day",
        max_temporal_depth: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize temporal query engine.

        Sets up the query engine with temporal reasoning configuration and
        pattern detector.

        Args:
            enable_temporal_reasoning: Enable temporal reasoning capabilities
                                    (default: True)
            temporal_granularity: Time granularity for queries
                                (default: "day", options: "second", "minute",
                                "hour", "day", "week", "month", "year")
            max_temporal_depth: Maximum depth for temporal queries (optional)
            **kwargs: Additional configuration options:
                - pattern_detection: Configuration for pattern detector (optional)
        """
        self.enable_temporal_reasoning = enable_temporal_reasoning
        self.temporal_granularity = temporal_granularity
        self.max_temporal_depth = max_temporal_depth

        # Initialize temporal query engine
        from ..utils.logging import get_logger

        self.logger = get_logger("temporal_query")

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize pattern detector
        self.pattern_detector = TemporalPatternDetector(
            **kwargs.get("pattern_detection", {})
        )
        self.reasoning_engine = TemporalReasoningEngine()



    def validate_temporal_consistency(self, graph: Any) -> TemporalConsistencyReport:
        errors: List[Dict[str, str]] = []
        warnings_list: List[Dict[str, str]] = []

        entities = {
            self._entity_id(entity): entity
            for entity in graph.get("entities", [])
        }
        rel_groups: Dict[tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

        for relationship in graph.get("relationships", []):
            rel_id = relationship.get("id") or self._relationship_key(relationship)
            rel_groups[
                (
                    relationship.get("source", ""),
                    relationship.get("type", relationship.get("relationship", "")),
                    relationship.get("target", ""),
                )
            ].append(relationship)

            try:
                start, end = self._get_axis_bounds(relationship, "valid")
            except TemporalValidationError as exc:
                errors.append(
                    asdict(
                        TemporalConsistencyIssue(
                            message=f"Unable to parse temporal fields: {exc}",
                            fact_id=rel_id,
                            issue_type="invalid_temporal_fields",
                        )
                    )
                )
                continue
            if start and isinstance(end, datetime) and self._compare_times(start, end) > 0:
                errors.append(
                    asdict(
                        TemporalConsistencyIssue(
                            message="Relationship has an inverted validity interval.",
                            fact_id=rel_id,
                            issue_type="inverted_interval",
                        )
                    )
                )

            for endpoint in ("source", "target"):
                entity = entities.get(relationship.get(endpoint))
                if entity is None:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Relationship references missing {endpoint} entity.",
                                fact_id=rel_id,
                                issue_type=f"missing_{endpoint}_entity",
                            )
                        )
                    )
                    continue
                try:
                    within_lifetime = self._window_within_entity_lifetime(entity, start, end)
                except TemporalValidationError as exc:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Unable to parse {endpoint} entity lifetime: {exc}",
                                fact_id=rel_id,
                                issue_type=f"invalid_{endpoint}_temporal_fields",
                            )
                        )
                    )
                    continue
                if not within_lifetime:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Relationship validity falls outside {endpoint} entity lifetime.",
                                fact_id=rel_id,
                                issue_type=f"{endpoint}_lifetime_mismatch",
                            )
                        )
                    )
        for relationships in rel_groups.values():
            safe_relationships = []
            for relationship in relationships:
                rel_id = relationship.get("id") or self._relationship_key(relationship)
                try:
                    start, end = self._get_axis_bounds(relationship, "valid")
                except TemporalValidationError as exc:
                    errors.append(
                        asdict(
                            TemporalConsistencyIssue(
                                message=f"Unable to parse temporal fields: {exc}",
                                fact_id=rel_id,
                                issue_type="invalid_temporal_fields",
                            )
                        )
                    )
                    continue
                safe_relationships.append((relationship, start, end))
            ordered = sorted(
                safe_relationships,
                key=lambda item: self._sort_key(item[1]),
            )
            for index, (current, current_start, current_end) in enumerate(ordered):
                current_id = current.get("id") or self._relationship_key(current)
                if index > 0:
                    _, previous_start, previous_end = ordered[index - 1]
                    if self._range_overlaps_bounds(
                        current_start or datetime.min.replace(tzinfo=timezone.utc),
                        current_end if isinstance(current_end, datetime) else datetime.max.replace(tzinfo=timezone.utc),
                        previous_start,
                        previous_end,
                    ):
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship overlaps another relationship with the same edge and type.",
                                    fact_id=current_id,
                                    issue_type="overlapping_same_edge",
                                )
                            )
                        )
                    elif (
                        isinstance(previous_end, datetime)
                        and current_start
                        and self._compare_times(current_start, previous_end) > 0
                    ):
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship restarts after a temporal gap.",
                                    fact_id=current_id,
                                    issue_type="gap_after_restart",
                                )
                            )
                        )
                    elif current_start and previous_start and self._compare_times(current_start, previous_start) == 0:
                        warnings_list.append(
                            asdict(
                                TemporalConsistencyIssue(
                                    message="Relationship interval overlaps another interval on the same edge.",
                                    fact_id=current_id,
                                    issue_type="overlapping_same_edge",
                                )
                            )
                        )

        return TemporalConsistencyReport(errors=errors, warnings=warnings_list)

    def query_time_range(
        self,
        graph: Any,
        query: str,
        start_time: Any,
        end_time: Any,
        temporal_aggregation: str = "union",
        include_intervals: bool = True,
        time_axis: str = "valid",
        **options,
    ) -> Dict[str, Any]:
        """
        Query graph within time range.

        This method filters relationships that are valid within the specified
        time range, with different aggregation strategies.

        Args:
            graph: Knowledge graph to query
            query: Query string (currently unused, reserved for future)
            start_time: Start of time range (datetime, timestamp, or ISO string)
            end_time: End of time range (datetime, timestamp, or ISO string)
            temporal_aggregation: Aggregation strategy:
                - "union": Include all relationships overlapping with range (default)
                - "intersection": Only relationships valid throughout entire range
                - "evolution": Group relationships by time periods
            include_intervals: Include partial matches within range (default: True)
            **options: Additional query options (unused)

        Returns:
            dict: Query results containing:
                - query: Original query string
                - start_time: Parsed start time
                - end_time: Parsed end time
                - relationships: Filtered relationships
                - num_relationships: Number of relationships
                - aggregation: Aggregation strategy used
        """
        self.logger.info(f"Querying graph in time range: {start_time} to {end_time}")

        # Parse times
        normalized_range = self.reasoning_engine.normalize_interval(
            start_time,
            end_time,
            self.temporal_granularity,
        )
        start = normalized_range.start
        end = normalized_range.end

        # Filter relationships valid in time range
        relationships = []
        relationship_buckets = None
        if "relationships" in graph:
            for rel in graph.get("relationships", []):
                if self._relationship_overlaps_range(
                    rel,
                    start,
                    end,
                    time_axis=time_axis,
                ):
                    relationships.append(rel)

        # Aggregate based on strategy
        if temporal_aggregation == "intersection":
            # Only relationships valid throughout the entire range
            relationships = [
                rel
                for rel in relationships
                if self._relationship_covers_range(rel, start, end, time_axis=time_axis)
            ]
        elif temporal_aggregation == "evolution":
            # Group by time periods
            relationship_buckets = self._group_by_time_periods(relationships, start, end)

        return {
            "query": query,
            "start_time": start,
            "end_time": end,
            "relationships": relationships,
            "relationship_buckets": relationship_buckets,
            "num_relationships": len(relationships),
            "aggregation": temporal_aggregation,
        }

    def query_temporal_pattern(
        self,
        graph: Any,
        pattern: str,
        time_window: Optional[Any] = None,
        min_support: int = 1,
        **options,
    ) -> Dict[str, Any]:
        """
        Query for temporal patterns in graph.

        This method detects temporal patterns (sequences, cycles, trends) in
        the knowledge graph using the temporal pattern detector.

        Args:
            graph: Knowledge graph to query
            pattern: Pattern type to search for ("sequence", "cycle", "trend", "anomaly")
            time_window: Time window for pattern matching (optional)
            min_support: Minimum frequency/support for pattern (default: 1)
            **options: Additional pattern query options

        Returns:
            dict: Pattern query results containing:
                - pattern: Pattern type searched
                - patterns: List of detected patterns
                - num_patterns: Number of patterns found
        """
        self.logger.info(f"Querying temporal patterns: {pattern}")

        # Use pattern detector
        patterns = self.pattern_detector.detect_temporal_patterns(
            graph,
            pattern_type=pattern,
            min_frequency=min_support,
            time_window=time_window,
            **options,
        )

        return {
            "pattern": pattern,
            "patterns": patterns,
            "num_patterns": len(patterns) if isinstance(patterns, list) else 0,
        }

    def analyze_evolution(
        self,
        graph: Any,
        entity: Optional[str] = None,
        relationship: Optional[str] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        metrics: Optional[List[str]] = None,
        **options,
    ) -> Dict[str, Any]:
        """
        Analyze graph evolution over time.

        This method analyzes how the knowledge graph (or specific entities/relationships)
        evolves over a time period, calculating various evolution metrics.

        Args:
            graph: Knowledge graph to analyze
            entity: Specific entity ID to track (optional, None for entire graph)
            relationship: Specific relationship type to track (optional, None for all)
            start_time: Start of analysis period (optional)
            end_time: End of analysis period (optional)
            metrics: List of metrics to calculate (default: ["count", "diversity", "stability"])
                    - "count": Number of relationships
                    - "diversity": Number of unique relationship types
                    - "stability": Relationship duration/stability measure
                      (mean valid-time duration in seconds across
                      relationships that have both ``valid_from`` and
                      ``valid_until`` set)
            **options: Additional analysis options (unused)

        Returns:
            dict: Evolution analysis results containing:
                - entity: Entity ID tracked (if specified)
                - relationship: Relationship type tracked (if specified)
                - time_range: Dictionary with start and end times
                - num_relationships: Number of relationships in period
                - count: Relationship count (if "count" in metrics)
                - diversity: Relationship type diversity (if "diversity" in metrics)
                - stability: Stability measure (if "stability" in metrics)
        """
        self.logger.info("Analyzing graph evolution")

        # Set default metrics if None
        if metrics is None:
            metrics = ["count", "diversity", "stability"]

        # Filter relationships
        relationships = graph.get("relationships", [])

        if entity:
            relationships = [
                rel
                for rel in relationships
                if (rel.get("source") or rel.get("source_id")) == entity
                or (rel.get("target") or rel.get("target_id")) == entity
            ]

        if relationship:
            relationships = [
                rel for rel in relationships if rel.get("type") == relationship
            ]

        # Filter by time range
        if start_time or end_time:
            start = self._parse_time(start_time) if start_time else None
            end = self._parse_time(end_time) if end_time else None

            filtered = []
            for rel in relationships:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))

                if (
                    start
                    and valid_until
                    and self._compare_times(valid_until, start) < 0
                ):
                    continue
                if end and valid_from and self._compare_times(valid_from, end) > 0:
                    continue

                filtered.append(rel)
            relationships = filtered

        # Calculate metrics
        result = {
            "entity": entity,
            "relationship": relationship,
            "time_range": {"start": start_time, "end": end_time},
            "num_relationships": len(relationships),
        }

        if "count" in metrics:
            result["count"] = len(relationships)

        if "diversity" in metrics:
            rel_types = set(rel.get("type") for rel in relationships)
            result["diversity"] = len(rel_types)

        if "stability" in metrics:
            # Stability is the mean duration (in seconds) that relationships
            # remain valid. Relationships without a bounded validity interval
            # (missing/open ``valid_from`` or ``valid_until``) are skipped, and
            # non-positive intervals are clamped to zero.
            durations = []
            for rel in relationships:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))
                if valid_from and valid_until:
                    duration_seconds = (valid_until - valid_from).total_seconds()
                    durations.append(max(0.0, duration_seconds))
            result["stability"] = sum(durations) / len(durations) if durations else 0

        return result

    def find_temporal_paths(
        self,
        graph: Any,
        source: str,
        target: str,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        max_path_length: Optional[int] = None,
        temporal_constraints: Optional[Dict[str, Any]] = None,
        enforce_causal_ordering: bool = True,
        ordering_strategy: Literal["strict", "overlap", "loose"] = "strict",
        **options,
    ) -> Dict[str, Any]:
        """
        Find paths between entities considering temporal validity.

        This method finds paths between source and target entities, considering
        only relationships that are temporally valid within the specified
        time range. Uses BFS for path finding.

        Args:
            graph: Knowledge graph to search
            source: Source entity ID
            target: Target entity ID
            start_time: Start time for path validity (optional)
            end_time: End time for path validity (optional)
            max_path_length: Maximum path length in edges (optional)
            temporal_constraints: Additional temporal constraints (optional, unused)
            **options: Additional path finding options (unused)

        Returns:
            dict: Temporal path results containing:
                - source: Source entity ID
                - target: Target entity ID
                - paths: List of path dictionaries, each containing:
                    - path: List of node IDs forming the path
                    - edges: List of relationship dictionaries
                    - length: Path length in edges
                - num_paths: Total number of paths found
        """
        self.logger.info(f"Finding temporal paths from {source} to {target}")

        # Build adjacency with temporal constraints
        adjacency = {}
        relationships = graph.get("relationships", [])
        parsed_start_time = self._parse_time(start_time) if start_time else None
        parsed_end_time = self._parse_time(end_time) if end_time else None

        for rel in relationships:
            # Accept both the legacy ``source``/``target`` keys and the
            # canonical ``source_id``/``target_id`` keys from ``to_kg_dict()``.
            s = rel.get("source")
            if s is None:
                s = rel.get("source_id")
            t = rel.get("target")
            if t is None:
                t = rel.get("target_id")

            # Check temporal validity
            if start_time or end_time:
                valid_from = self._parse_time(rel.get("valid_from"))
                valid_until = self._parse_time(rel.get("valid_until"))

                if (
                    parsed_start_time
                    and valid_until
                    and self._compare_times(valid_until, parsed_start_time) < 0
                ):
                    continue
                if (
                    parsed_end_time
                    and valid_from
                    and self._compare_times(valid_from, parsed_end_time) > 0
                ):
                    continue

            if s not in adjacency:
                adjacency[s] = []
            adjacency[s].append((t, rel))

        # BFS to find paths
        from collections import deque

        paths = []
        queue = deque([(source, [source], [])])
        visited = set()
        max_length = max_path_length or float("inf")

        while queue:
            node, path, edges = queue.popleft()

            if len(path) > max_length:
                continue

            if node == target:
                paths.append({"path": path, "edges": edges, "length": len(path) - 1})
                continue

            if node in visited:
                continue
            visited.add(node)

            for neighbor, rel in adjacency.get(node, []):
                if neighbor not in path:  # Avoid cycles
                    next_edges = edges + [rel]
                    if self._path_respects_causal_order(
                        next_edges,
                        enforce_causal_ordering=enforce_causal_ordering,
                        ordering_strategy=ordering_strategy,
                    ):
                        queue.append((neighbor, path + [neighbor], next_edges))

        return {
            "source": source,
            "target": target,
            "paths": paths,
            "num_paths": len(paths),
        }

    def _parse_time(self, time_value):
        """Parse time value into a UTC-normalized datetime."""
        if time_value in (None, TemporalBound.OPEN, TemporalBound.OPEN.value):
            return None
        try:
            return parse_temporal_value(time_value)
        except TemporalValidationError:
            raise
        except Exception as exc:
            raise TemporalValidationError(
                "Invalid temporal value",
                temporal_context={"value": time_value},
            ) from exc

    def _compare_times(self, time1, time2):
        """Compare two UTC datetimes after granularity truncation."""
        if time1 is None or time2 is None:
            return 0
        time1 = self._truncate_to_granularity(time1)
        time2 = self._truncate_to_granularity(time2)
        return (time1 > time2) - (time1 < time2)

    def _truncate_to_granularity(self, value: datetime) -> datetime:
        granularity = getattr(self, "temporal_granularity", "second")
        return self.reasoning_engine.normalize_timestamp(value, granularity)

    def _get_axis_bounds(self, relationship: Dict[str, Any], axis: str):
        normalized = deserialize_relationship_temporal_fields(relationship)
        fact = BiTemporalFact.from_relationship(normalized)
        if axis == "valid":
            return fact.valid_from, fact.valid_until
        if axis == "transaction":
            return fact.recorded_at, fact.superseded_at
        raise ValueError(f"Unsupported time axis: {axis}")

    def _is_point_in_bounds(self, point: datetime, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        if start is None:
            start = datetime.min.replace(tzinfo=timezone.utc)
        return self.reasoning_engine.active_at(
            TemporalInterval(start=start, end=end or TemporalBound.OPEN),
            point,
            granularity=self.temporal_granularity,
        )

    def _range_overlaps_bounds(self, query_start: datetime, query_end: datetime | TemporalBound, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        query_end_value = datetime.max.replace(tzinfo=timezone.utc) if query_end is TemporalBound.OPEN else query_end
        if query_end_value < query_start:
            return False
        if isinstance(end, datetime) and start is not None and end < start:
            return False
        candidate = TemporalInterval(
            start=start or datetime.min.replace(tzinfo=timezone.utc),
            end=end or TemporalBound.OPEN,
        )
        query_interval = TemporalInterval(start=query_start, end=query_end)
        relation = self.reasoning_engine.relation(candidate, query_interval)
        return relation not in {
            IntervalRelation.BEFORE,
            IntervalRelation.AFTER,
        }

    def _range_covered_by_bounds(self, query_start: datetime, query_end: datetime | TemporalBound, start: Optional[datetime], end: Optional[datetime | TemporalBound]) -> bool:
        query_end_value = datetime.max.replace(tzinfo=timezone.utc) if query_end is TemporalBound.OPEN else query_end
        if query_end_value < query_start:
            return False
        if isinstance(end, datetime) and start is not None and end < start:
            return False
        candidate = TemporalInterval(
            start=start or datetime.min.replace(tzinfo=timezone.utc),
            end=end or TemporalBound.OPEN,
        )
        return self.reasoning_engine.contains(candidate, TemporalInterval(start=query_start, end=query_end))

    def _relationship_active_at_time(self, relationship: Dict[str, Any], query_time: datetime, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._is_point_in_bounds(query_time, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _relationship_overlaps_range(self, relationship: Dict[str, Any], start: datetime, end: datetime | TemporalBound, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._range_overlaps_bounds(start, end, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _relationship_covers_range(self, relationship: Dict[str, Any], start: datetime, end: datetime | TemporalBound, *, time_axis: str) -> bool:
        axes = ["valid", "transaction"] if time_axis == "both" else [time_axis]
        return all(
            self._range_covered_by_bounds(start, end, *self._get_axis_bounds(relationship, axis))
            for axis in axes
        )

    def _entity_id(self, entity: Dict[str, Any]) -> str:
        return str(entity.get("id", entity.get("name", "")))

    def _entity_active_at_time(self, entity: Dict[str, Any], query_time: datetime, *, time_axis: str) -> bool:
        relationship_like = {
            "valid_from": entity.get("valid_from"),
            "valid_until": entity.get("valid_until", TemporalBound.OPEN),
            "recorded_at": entity.get("recorded_at", entity.get("valid_from")),
            "superseded_at": entity.get("superseded_at", TemporalBound.OPEN),
        }
        return self._relationship_active_at_time(relationship_like, query_time, time_axis=time_axis)

    def _window_within_entity_lifetime(
        self,
        entity: Dict[str, Any],
        rel_start: Optional[datetime],
        rel_end: Optional[datetime | TemporalBound],
    ) -> bool:
        entity_start = self._parse_time(entity.get("valid_from")) if entity.get("valid_from") is not None else None
        entity_end = parse_temporal_bound(entity.get("valid_until"), default=TemporalBound.OPEN)
        if rel_start and entity_start and self._compare_times(rel_start, entity_start) < 0:
            return False
        if isinstance(entity_end, datetime):
            if rel_start and self._compare_times(rel_start, entity_end) > 0:
                return False
            if isinstance(rel_end, datetime) and self._compare_times(rel_end, entity_end) > 0:
                return False
            if rel_end is TemporalBound.OPEN:
                return False
        return True

    def _sort_key(self, value: Optional[datetime]) -> datetime:
        return value or datetime.min.replace(tzinfo=timezone.utc)

    def _period_floor(self, value: datetime) -> datetime:
        return self._truncate_to_granularity(value)

    def _next_period(self, value: datetime) -> datetime:
        if self.temporal_granularity == "day":
            return value + timedelta(days=1)
        if self.temporal_granularity == "week":
            return value + timedelta(weeks=1)
        if self.temporal_granularity == "month":
            if value.month == 12:
                return value.replace(year=value.year + 1, month=1)
            return value.replace(month=value.month + 1)
        if self.temporal_granularity == "year":
            return value.replace(year=value.year + 1)
        return value + timedelta(days=1)

    def _period_label(self, value: datetime) -> str:
        if self.temporal_granularity == "week":
            return f"{value.isocalendar().year}-W{value.isocalendar().week:02d}"
        if self.temporal_granularity == "month":
            return value.strftime("%Y-%m")
        if self.temporal_granularity == "year":
            return value.strftime("%Y")
        return value.strftime("%Y-%m-%d")

    def _path_respects_causal_order(
        self,
        edges: List[Dict[str, Any]],
        *,
        enforce_causal_ordering: bool,
        ordering_strategy: Literal["strict", "overlap", "loose"],
    ) -> bool:
        if not enforce_causal_ordering or ordering_strategy == "loose" or len(edges) < 2:
            return True

        previous = edges[-2]
        current = edges[-1]
        previous_start, previous_end = self._get_axis_bounds(previous, "valid")
        current_start, _ = self._get_axis_bounds(current, "valid")

        if ordering_strategy == "strict":
            if previous_start and current_start and self._compare_times(current_start, previous_start) < 0:
                return False
            return True
        if ordering_strategy == "overlap":
            if current_start is None:
                return True
            if isinstance(previous_end, datetime):
                return self._compare_times(current_start, previous_end) <= 0
            return True
        return True

    def _group_by_time_periods(self, relationships, start, end):
        """Group relationships into calendar-aligned buckets."""
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        current = self._period_floor(start)
        end_bound = self._period_floor(end)

        while current <= end_bound:
            bucket_end = self._next_period(current)
            label = self._period_label(current)
            for relationship in relationships:
                if self._relationship_overlaps_range(
                    relationship,
                    current,
                    bucket_end,
                    time_axis="valid",
                ):
                    buckets[label].append(relationship)
            current = bucket_end

        return dict(buckets)


class TemporalPatternDetector:
    """
    Temporal pattern detection engine.

    This class provides temporal pattern detection capabilities for knowledge
    graphs, identifying recurring patterns, sequences, cycles, and trends in
    temporal data.

    Features:
        - Sequence pattern detection
        - Cycle pattern detection
        - Trend analysis
        - Anomaly detection (planned)

    Example Usage:
        >>> detector = TemporalPatternDetector()
        >>> patterns = detector.detect_temporal_patterns(
        ...     graph, pattern_type="sequence", min_frequency=2
        ... )
    """

    def __init__(self, **config):
        """
        Initialize temporal pattern detector.

        Sets up the detector with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        from ..utils.logging import get_logger

        self.logger = get_logger("temporal_pattern_detector")
        self.config = config

        self.logger.debug("Temporal pattern detector initialized")

    def detect_temporal_patterns(
        self,
        graph: Any,
        pattern_type: str = "sequence",
        min_frequency: int = 2,
        time_window: Optional[Any] = None,
        **options,
    ) -> List[Dict[str, Any]]:
        """
        Detect temporal patterns in graph.

        This method detects various types of temporal patterns in the knowledge
        graph, including sequences and cycles.

        Args:
            graph: Knowledge graph to analyze
            pattern_type: Type of pattern to detect:
                - "sequence": Sequential relationship patterns
                - "cycle": Cyclic relationship patterns
                - "trend": Trend patterns (planned)
                - "anomaly": Anomaly patterns (planned)
            min_frequency: Minimum frequency/support for pattern (default: 2)
            time_window: Time window for pattern detection (optional)
            **options: Additional detection options (unused)

        Returns:
            list: List of detected pattern dictionaries
        """
        self.logger.info(f"Detecting temporal patterns: {pattern_type}")
        if "gap_tolerance" in options:
            self.config["gap_tolerance"] = options["gap_tolerance"]

        relationships = graph.get("relationships", [])

        # Simple pattern detection
        patterns = []

        if pattern_type == "sequence":
            # Find sequential relationships
            sequences = self._find_sequences(relationships, min_frequency)
            patterns.extend(sequences)
        elif pattern_type == "cycle":
            # Find cyclic patterns
            cycles = self._find_cycles(relationships, min_frequency)
            patterns.extend(cycles)

        return patterns

    def _find_sequences(self, relationships, min_frequency):
        """Find sequential patterns."""
        # Pattern output design:
        # - sequences return dicts with pattern_type/signature/frequency/occurrences
        # - each occurrence stores ordered nodes, ordered edges, and start/end timestamps
        gap_tolerance = self._resolve_gap_tolerance()
        outgoing: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for relationship in relationships:
            outgoing[relationship.get("source")].append(relationship)

        occurrences = defaultdict(list)
        for relationship in relationships:
            sequence = [relationship]
            current = relationship
            while True:
                next_candidates = []
                _, current_end = self._get_axis_bounds(current)
                if current_end is TemporalBound.OPEN:
                    break
                for candidate in outgoing.get(current.get("target"), []):
                    if candidate is current:
                        continue
                    candidate_start, _ = self._get_axis_bounds(candidate)
                    if not isinstance(current_end, datetime) or candidate_start is None:
                        continue
                    gap = candidate_start - current_end
                    if gap < timedelta(0) or gap > gap_tolerance:
                        continue
                    next_candidates.append((candidate_start, candidate))
                if not next_candidates:
                    break
                next_candidates.sort(key=lambda item: item[0])
                current = next_candidates[0][1]
                sequence.append(current)

            if len(sequence) < 2:
                continue

            signature = tuple(
                [sequence[0].get("source")] + [edge.get("target") for edge in sequence]
            )
            occurrences[signature].append(
                {
                    "nodes": list(signature),
                    "edges": [copy.deepcopy(edge) for edge in sequence],
                    "start_time": serialize_temporal_value(self._get_axis_bounds(sequence[0])[0]),
                    "end_time": serialize_temporal_value(self._sequence_end(sequence)),
                }
            )

        return [
            {
                "pattern_type": "sequence",
                "signature": signature,
                "frequency": len(items),
                "occurrences": items,
            }
            for signature, items in occurrences.items()
            if len(items) >= min_frequency
        ]

    def _find_cycles(self, relationships, min_frequency):
        """Find cyclic patterns."""
        # Pattern output design mirrors sequences:
        # - cycles return pattern_type/signature/frequency/occurrences
        # - each occurrence records the ordered cycle nodes, edges, and time span
        outgoing: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for relationship in relationships:
            outgoing[relationship.get("source")].append(relationship)

        occurrences = defaultdict(list)
        for relationship in relationships:
            start_node = relationship.get("source")
            path_edges = [relationship]
            visited_nodes = [start_node, relationship.get("target")]
            current = relationship

            while len(path_edges) <= 6:
                if visited_nodes[-1] == start_node:
                    signature = tuple(visited_nodes)
                    occurrences[signature].append(
                        {
                            "nodes": visited_nodes[:],
                            "edges": [copy.deepcopy(edge) for edge in path_edges],
                            "start_time": serialize_temporal_value(self._get_axis_bounds(path_edges[0])[0]),
                            "end_time": serialize_temporal_value(self._sequence_end(path_edges)),
                        }
                    )
                    break

                next_candidates = []
                _, current_end = self._get_axis_bounds(current)
                for candidate in outgoing.get(visited_nodes[-1], []):
                    candidate_start, _ = self._get_axis_bounds(candidate)
                    if isinstance(current_end, datetime) and candidate_start and self._compare_times(candidate_start, current_end) < 0:
                        continue
                    next_candidates.append((self._sort_key(candidate_start), candidate))
                if not next_candidates:
                    break
                next_candidates.sort(key=lambda item: item[0])
                current = next_candidates[0][1]
                next_target = current.get("target")
                if next_target in visited_nodes[1:-1] and next_target != start_node:
                    break
                path_edges.append(current)
                visited_nodes.append(next_target)

        return [
            {
                "pattern_type": "cycle",
                "signature": signature,
                "frequency": len(items),
                "occurrences": items,
            }
            for signature, items in occurrences.items()
            if len(items) >= min_frequency
        ]

    def _resolve_gap_tolerance(self) -> timedelta:
        gap_tolerance = self.config.get("gap_tolerance", timedelta(days=0))
        if isinstance(gap_tolerance, timedelta):
            return gap_tolerance
        if isinstance(gap_tolerance, (int, float)):
            return timedelta(days=gap_tolerance)
        return timedelta(days=0)

    def _sequence_end(self, edges: List[Dict[str, Any]]) -> Optional[datetime]:
        last_start, last_end = self._get_axis_bounds(edges[-1])
        if isinstance(last_end, datetime):
            return last_end
        return last_start

    def _get_axis_bounds(self, relationship: Dict[str, Any]) -> tuple[Optional[datetime], Optional[datetime | TemporalBound]]:
        normalized = deserialize_relationship_temporal_fields(relationship)
        fact = BiTemporalFact.from_relationship(normalized)
        return fact.valid_from, fact.valid_until

    def _compare_times(self, time1: Optional[datetime], time2: Optional[datetime]) -> int:
        if time1 is None or time2 is None:
            return 0
        return (time1 > time2) - (time1 < time2)

    def _sort_key(self, value: Optional[datetime]) -> datetime:
        return value or datetime.min.replace(tzinfo=timezone.utc)


def validate_temporal_consistency(graph: Any) -> TemporalConsistencyReport:
    """Module-level validator entry point required by the temporal query API."""
    return TemporalGraphQuery().validate_temporal_consistency(graph)
