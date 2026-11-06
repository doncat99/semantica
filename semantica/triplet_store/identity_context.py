"""Generation-scoped semantic indexes for the existing entity disambiguator.

Only keyed semantic observations are persisted in the native publication graph.
The disambiguator remains the sole definition/owner/identity decision authority.
"""
import hashlib
import json
import time
from collections import OrderedDict
from contextlib import contextmanager
from collections.abc import MutableSet

from ..semantic_worker_context import check_query_cancellation
from ..utils.exceptions import ProcessingError
from .publication_records import MAX_BYTES, MAX_ROWS, P, PublicationRecords


def _encode(value):
    if isinstance(value, (set, frozenset)):
        return {'set': sorted((_encode(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(value, tuple):
        return {'tuple': [_encode(v) for v in value]}
    return value


def _decode(value):
    if isinstance(value, dict):
        if 'set' in value:
            return frozenset(_decode(v) for v in value['set'])
        return tuple(_decode(v) for v in value['tuple'])
    return value


def _json(value):
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class _Values(MutableSet):
    def __init__(self, mapping, key):
        self.mapping, self.key = mapping, key

    def __contains__(self, value):
        return value in self.mapping.get(self.key, set())

    def __iter__(self):
        return iter(self.mapping.get(self.key, set()))

    def __len__(self):
        return len(self.mapping.get(self.key, set()))

    def add(self, value):
        self.mapping.add(self.key, value)

    def discard(self, value):
        self.mapping.remove(self.key, value)

    def update(self, values):
        for value in values:
            self.add(value)


class _Index:
    def __init__(self, context, field, *, scalar=False):
        self.context, self.field, self.scalar = context, field, scalar
        self.p = context.publication
        self.predicate = self.p.ox.NamedNode(P+'identityContext:'+field)

    def _node(self, key):
        raw = _json(key)
        if len(raw.encode()) > MAX_BYTES:
            raise ProcessingError('Native identity context key exceeds byte budget')
        return self.p.ox.NamedNode(P+'identity-context:'+hashlib.sha256(
            (self.field+':'+raw).encode()).hexdigest())

    def get(self, key, default=None):
        self.context.fence()
        cache = self.context._lookup_cache
        cache_key = (self.field, _json(key))
        if cache is not None and cache_key in cache:
            result, _ = cache[cache_key]
            cache.move_to_end(cache_key)
            return self._value(result, default)
        result, size = set(), 0
        for quad in self.context.owner.store.quads_for_pattern(self._node(key), self.predicate, None, self.p.graph):
            size += len(quad.object.value.encode())
            if len(result) >= MAX_ROWS or size > MAX_BYTES:
                raise ProcessingError('Native identity semantic group exceeds resource budget')
            result.add(_decode(json.loads(quad.object.value)))
        if cache is not None:
            # Keep at most 128 keyed groups and one MiB of charged storage.
            # A larger valid group is read in full and simply not cached.
            from sys import getsizeof
            def charge(item):
                amount = getsizeof(item)
                if isinstance(item, (tuple, set, frozenset)):
                    amount += sum(charge(child) for child in item)
                return amount
            size = charge(cache_key) + charge(result) + 96
            if size <= 1024 * 1024:
                while cache and (len(cache) >= 128 or self.context._lookup_bytes + size > 1024 * 1024):
                    _, (_, old_size) = cache.popitem(last=False)
                    self.context._lookup_bytes -= old_size
                cache[cache_key] = (result, size)
                self.context._lookup_bytes += size
        return self._value(result, default)

    def _value(self, result, default):
        if not result:
            return default
        if self.scalar:
            if len(result) != 1:
                raise ProcessingError('Native identity scalar index is ambiguous')
            return next(iter(result))
        return result

    def __contains__(self, key):
        return self.get(key) is not None

    def setdefault(self, key, default):
        if default != set():
            raise ProcessingError('Native identity index expects set observations')
        return _Values(self, key)

    def add(self, key, value):
        self.context._lookup_cache = None
        self.context._lookup_bytes = 0
        self.context.fence()
        raw = _json(value)
        if len(raw.encode()) > MAX_BYTES // 2:
            raise ProcessingError('Native identity context value exceeds byte budget')
        node = self._node(key)
        triples = [f'{node} {self.predicate} {self.p.ox.Literal(raw)} .']
        if self.field in {'project_definitions', 'variant_groups'} or self.field.endswith('_members'):
            triples.append(self.p.triple(node, 'identityContextKey', self.p.ox.Literal(_json(key))))
        self.p.mutate(self.context.generation, triples)
        # Validate the complete semantic group; never silently truncate it.
        self.get(key)

    def remove(self, key, value):
        self.context._lookup_cache = None
        self.context._lookup_bytes = 0
        self.context.fence()
        self.context.owner.store.remove(self.p.ox.Quad(self._node(key), self.predicate,
            self.p.ox.Literal(_json(value)), self.p.graph))
        self.context.owner.flush()

    def __setitem__(self, key, value):
        self.context._lookup_cache = None
        self.context._lookup_bytes = 0
        self.context.fence()
        node = self._node(key)
        self.context.owner.store.update(f'DELETE WHERE {{ GRAPH {self.p.graph} {{ {node} {self.predicate} ?o }} }}')
        for item in [value] if self.scalar else value:
            self.add(key, item)

    def items(self):
        # Native iterator streams keys; no whole-project keys/values dictionary.
        for quad in self.context.owner.store.quads_for_pattern(None,
                self.p.ox.NamedNode(P+'identityContextKey'), None, self.p.graph):
            self.context.fence()
            if next(self.context.owner.store.quads_for_pattern(quad.subject, self.predicate, None, self.p.graph), None):
                key = _decode(json.loads(quad.object.value))
                yield key, self.get(key, set())

    def values(self):
        return (value for _, value in self.items())


class _Set(MutableSet):
    def __init__(self, context, field):
        self.mapping = _Index(context, field+'_members')

    def __contains__(self, value):
        return self.mapping.get(value) is not None

    def add(self, value):
        self.mapping.add(value, True)

    def discard(self, value):
        self.mapping.remove(value, True)

    def __iter__(self):
        return (key for key, _ in self.mapping.items())

    def __len__(self):
        return sum(1 for _ in self)



class NativeIdentityContext:
    """Persistent native context with bounded per-key reads and no DTO cache."""
    maps = ('scope_definitions', 'source_definitions', 'project_definitions',
            'context_definitions', 'local_owners', 'owner_aliases', 'identity_facts', 'instances')
    sets = ('defined_referents', 'described_scopes')

    def __init__(self, owner, project, generation):
        self.owner, self.generation = owner, generation
        self.publication = PublicationRecords(owner, project)
        self._resolution_depth = 0
        self._fence_reads = 0
        self._last_fence = 0.
        self._lookup_cache = None
        self._lookup_bytes = 0

    @contextmanager
    def resolution_scope(self):
        # Validate the immutable complete input plan at both handoff boundaries.
        # Intermediate lookups check the keyed generation/state every 128 reads
        # or 50ms; cancellation still runs at every lookup and pair comparison.
        self.publication._build_fence(self.generation)
        self._resolution_depth += 1
        self._lookup_cache = OrderedDict()
        self._lookup_bytes = 0
        self._fence_reads = 128
        try:
            yield
            self.publication._build_fence(self.generation)
        finally:
            self._resolution_depth -= 1
            self._lookup_cache = None
            self._lookup_bytes = 0

    def fence(self):
        check_query_cancellation()
        if not self._resolution_depth:
            self.publication._build_fence(self.generation)
            return
        self._fence_reads += 1
        now = time.monotonic()
        if self._fence_reads >= 128 or now - self._last_fence >= .05:
            self.publication.fence(self.generation, 'pending')
            self._fence_reads = 0
            self._last_fence = now

    def mapping(self, field, *, scalar=False):
        return _Index(self, field, scalar=scalar)

    def bind(self, disambiguator, *, preparing=False):
        self.fence()
        if not preparing and not self.publication.values(self.publication.head, "identityContextSealed"):
            raise ProcessingError("Native identity semantic context is not sealed")
        for field in self.maps:
            setattr(disambiguator, '_'+field, self.mapping(field))
        disambiguator._definition_variants = self.mapping('definition_variants', scalar=True)
        for field in self.sets:
            setattr(disambiguator, '_'+field, _Set(self, field))
        disambiguator._context_prepared = True
        disambiguator._native_context = self

    def reset(self, disambiguator):
        self.fence()
        p = self.publication
        self.owner.store.update(f'''DELETE {{ GRAPH {p.graph} {{ ?s ?predicate ?o }} }}
            WHERE {{ GRAPH {p.graph} {{ ?s ?predicate ?o .
                FILTER(STRSTARTS(STR(?predicate), "{P}identityContext")) }} }}''')
        self.owner.flush()
        self.bind(disambiguator, preparing=True)

    def seal(self):
        self.fence()
        p = self.publication
        p.mutate(self.generation, [p.triple(p.head, "identityContextSealed", p.ox.Literal(True))])
