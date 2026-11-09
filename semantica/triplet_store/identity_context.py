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
            self.context.observe(self.field, key, result)
            return self._value(result, default)
        result, size = set(), 0
        for quad in self.context.owner.store.quads_for_pattern(self._node(key), self.predicate, None, self.p.graph):
            size += len(quad.object.value.encode())
            if len(result) >= MAX_ROWS or size > MAX_BYTES:
                raise ProcessingError('Native identity semantic group exceeds resource budget')
            result.add(_decode(json.loads(quad.object.value)))
        self.context.observe(self.field, key, result)
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
        cache = self.context._lookup_cache
        if cache is not None:
            old = cache.pop((self.field, _json(key)), None)
            if old is not None:
                self.context._lookup_bytes -= old[1]
        self.context.fence()
        raw = _json(value)
        if len(raw.encode()) > MAX_BYTES // 2:
            raise ProcessingError('Native identity context value exceeds byte budget')
        node = self._node(key)
        triples = [f'{node} {self.predicate} {self.p.ox.Literal(raw)} .']
        triples.append(self.p.triple(node, 'identityContextKey', self.p.ox.Literal(_json(key))))
        triples.append(self.p.triple(node, 'identityContextField', self.p.ox.Literal(self.field)))
        self.p.mutate(self.context.generation, triples)

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
        if self.context._dependencies is not None:
            self.context.observe_digest(self.field, None, self.context.dependency_digest(self.field, None))
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
        self.publication = PublicationRecords(owner, project, stage='identity')
        self._resolution_depth = 0
        self._fence_reads = 0
        self._last_fence = 0.
        self._lookup_cache = None
        self._lookup_bytes = 0
        self._dependencies = None
        self._dependency_bytes = 0
        self._dependency_sink = None

    def observe(self, field, key, result):
        if self._dependencies is None:
            return
        self.observe_digest(field, _json(key), hashlib.sha256(_json(result).encode()).hexdigest())

    def observe_digest(self, field, encoded_key, digest):
        token = (field, encoded_key)
        size = len(field.encode()) + len((encoded_key or '').encode()) + 128
        if size > MAX_BYTES // 2:
            raise ProcessingError('Identity dependency key exceeds byte budget')
        if token not in self._dependencies:
            if len(self._dependencies) >= MAX_ROWS or self._dependency_bytes + size > MAX_BYTES // 2:
                self.flush_dependencies()
            self._dependency_bytes += size
        self._dependencies[token] = digest

    def flush_dependencies(self):
        if self._dependencies:
            self._dependency_sink(self._dependencies)
            self._dependencies.clear()
            self._dependency_bytes = 0

    def dependency_digest(self, field, encoded_key):
        """Hash final native keyed values, including absence and enumeration."""
        dependencies, self._dependencies = self._dependencies, None
        try:
            mapping = self.mapping(field)
            if encoded_key is not None:
                return hashlib.sha256(_json(mapping.get(_decode(json.loads(encoded_key)), set())).encode()).hexdigest()
            # Commutative multiset digest streams arbitrary native key counts;
            # key+value boundaries are encoded before hashing.
            count = xor = total = 0
            for key, values in mapping.items():
                item = int.from_bytes(hashlib.sha256(_json((key, frozenset(values))).encode()).digest(), 'big')
                count += 1
                xor ^= item
                total = (total + item) % (1 << 256)
            return hashlib.sha256(f'{count}:{xor}:{total}'.encode()).hexdigest()
        finally:
            self._dependencies = dependencies

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
        # Validate each complete observation group once, not after every insertion.
        for quad in self.owner.store.quads_for_pattern(None,
                p.ox.NamedNode(P+'identityContextField'), None, p.graph):
            self.fence()
            key = p.values(quad.subject, 'identityContextKey')
            if len(key) != 1:
                raise ProcessingError('Native identity context key is incomplete')
            self.mapping(quad.object.value).get(_decode(json.loads(key[0].value)))
        p.mutate(self.generation, [p.triple(p.head, "identityContextSealed", p.ox.Literal(True))])
