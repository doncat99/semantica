"""Current publication fence and reference-only membership in Oxigraph.

Paid typed observations remain in their extraction owner. This codec stores
only the current publication's input identities and references to those facts.
"""
import io
import hashlib
import json
import uuid
from contextlib import contextmanager
from functools import wraps
from heapq import nsmallest
from itertools import chain, islice

from ..utils.exceptions import ProcessingError
from ..semantic_worker_context import check_query_cancellation
from ..semantic_extract.types import normalize_fact_predicate
from .extraction_records import BINDING, ExtractionRecords, F, RDF_TYPE, operation_identity

MAX_ROWS = 128
MAX_BYTES = 262144
P = "urn:semantica:publication:"


class ClassificationMissingError(ProcessingError):
    """No completed classification is bound to this published source."""


class _TripleStream(io.RawIOBase):
    def __init__(self, batches):
        self.batches=iter(batches)
        self.pending=memoryview(b'')

    def readable(self):
        return True

    def readinto(self, target):
        while not self.pending:
            check_query_cancellation()
            batch=next(self.batches,None)
            if batch is None:
                return 0
            body=('\n'.join(batch)+'\n').encode()
            if len(body)>MAX_BYTES+1:
                raise ProcessingError('Publication import window exceeds byte budget')
            self.pending=memoryview(body)
        count=min(len(target),len(self.pending))
        target[:count]=self.pending[:count]
        self.pending=self.pending[count:]
        return count


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.owner._publication_lock:
            return method(self, *args, **kwargs)
    return call


def _stage(kind):
    def decorate(method):
        @wraps(method)
        def call(self, *args, **kwargs):
            previous = self.stage
            self.stage = kind
            try:
                return method(self, *args, **kwargs)
            finally:
                self.stage = previous
        return call
    return decorate


class PublicationRecords:
    def __init__(self, owner, project, *, stage=None):
        if not isinstance(project, str) or not project or len(project.encode()) > 4096:
            raise ProcessingError("Invalid publication project")
        self.owner, self.ox, self.project = owner, owner._oxigraph, project
        digest = hashlib.sha256(project.encode()).hexdigest()
        self.registry = self.ox.NamedNode(P + digest)
        self.registry_head = self.ox.NamedNode(self.registry.value + ':head')
        self.facts = self.ox.NamedNode("urn:semantica:project:" + digest)
        self.stage = stage
        self.generation = self._pointer(self.registry_head, 'latest', self.registry)

    def _pointer(self, node, field, graph):
        values = list(islice(self.owner.store.quads_for_pattern(
            node, self.ox.NamedNode(P + field), None, graph), 2))
        if len(values) > 1:
            raise ProcessingError('Publication pointer is duplicated: ' + field)
        return values[0].object if values else None

    @property
    def publication_graph(self):
        generation = self.generation
        return self.ox.NamedNode(self.registry.value + ':generation:' + generation.value) if generation else self.registry

    @property
    def publication_head(self):
        return self.ox.NamedNode(self.publication_graph.value + ':head')

    def stage_graph(self, kind):
        if self.generation is None:
            return self.publication_graph
        return self._pointer(self.publication_head, kind + 'Graph', self.publication_graph) or self.publication_graph

    def stage_head(self, kind):
        return self.ox.NamedNode(self.stage_graph(kind).value + ':head')

    @property
    def graph(self):
        return self.stage_graph(self.stage) if self.stage else self.publication_graph

    @property
    def head(self):
        return self.ox.NamedNode(self.graph.value + ':head')

    def _completion_key(self, kind, input_key, *, functional_predicates=()):
        identity = [input_key, self.functional_policy(functional_predicates)] if kind == 'fact' else input_key
        return self.ox.NamedNode(self.registry.value + ':' + kind + ':' + hashlib.sha256(
            json.dumps(identity, separators=(',', ':')).encode()).hexdigest())

    def _bind_stage(self, kind, input_key, *, functional_predicates=()):
        """A publication references a completed stage; it never copies its rows."""
        key = self._completion_key(kind, input_key, functional_predicates=functional_predicates)
        completed = self._pointer(key, 'completedGraph', self.registry)
        graph = completed or self.ox.NamedNode(self.publication_graph.value + ':' + kind)
        previous = self._pointer(self.publication_head, kind + 'Graph', self.publication_graph)
        if previous is not None and previous != graph:
            raise ProcessingError('Publication stage input changed within an attempt')
        self.owner.store.add(self.ox.Quad(self.publication_head,
            self.ox.NamedNode(P + kind + 'Graph'), graph, self.publication_graph))
        return key, graph

    def _complete_stage(self, kind, input_key, *, functional_predicates=()):
        key, graph = self._bind_stage(kind, input_key, functional_predicates=functional_predicates)
        self.owner.flush()
        self.owner.store.add(self.ox.Quad(key, self.ox.NamedNode(P + 'completedGraph'), graph, self.registry))
        self.owner.flush()

    def _writable_stage(self):
        if self.stage is not None and self.graph != self.publication_graph:
            completion = 'identityStageInput' if self.stage == 'identity' else 'factStageInput'
            if self.values(self.head, completion):
                raise ProcessingError('Completed publication stage is immutable')

    def iri(self, value):
        if not isinstance(value, str) or not value or len(value.encode()) > 8192:
            raise ProcessingError("Invalid publication reference")
        try:
            return self.ox.NamedNode(value)
        except ValueError as exc:
            raise ProcessingError("Invalid publication IRI") from exc

    def scalar(self, value):
        if not isinstance(value, str) or not value or len(value.encode()) > 4096:
            raise ProcessingError("Invalid publication identity")
        return self.ox.Literal(value)

    def values(self, node, field, graph=None):
        if graph is None and self.stage in {'identity', 'fact'} and node != self.head:
            graph = self.record_graph(node)
        if graph is None and self.stage is None:
            if node == self.publication_head and (field.startswith('identity') or field == 'canonical'):
                node, graph = self.stage_head('identity'), self.stage_graph('identity')
            elif node == self.publication_head and (field.startswith('qualified') or field in {'fact', 'factStageInput'}):
                node, graph = self.stage_head('fact'), self.stage_graph('fact')
            elif node != self.publication_head:
                graph = self.record_graph(node)
        result = []
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P + field), None, graph or self.graph):
            result.append(quad.object)
            if len(result) > MAX_ROWS:
                raise ProcessingError("Publication field exceeds 128 references")
        return result

    def record_graph(self, node):
        canonical = self.ox.NamedNode(node.value.split(':selector:')[0])
        location = self._pointer(canonical, 'canonicalGraph', self.stage_graph('identity'))
        if location is not None:
            return location
        location = self._pointer(node, 'factDecisionGraph', self.stage_graph('fact'))
        if location is not None:
            return location
        for kind, role in (('identity', 'canonical'), ('fact', 'fact')):
            graph, head = self.stage_graph(kind), self.stage_head(kind)
            if next(self.owner.store.quads_for_pattern(head, self.ox.NamedNode(P + role), node, graph), None):
                raise ProcessingError('Completed '+kind+' decision graph missing')
        return self.graph

    def canonical_pattern(self, node, pattern, *, variable='?canonicalRecordGraph'):
        """Join current membership to its immutable decision, without copying it."""
        return f'''GRAPH {self.stage_graph('identity')} {{
            {self.stage_head('identity')} <{P}canonical> {node} .
            {node} <{P}canonicalGraph> {variable} }} GRAPH {variable} {{ {pattern} }}'''

    def fact_pattern(self, node, pattern, *, variable='?factRecordGraph'):
        return f'''GRAPH {self.stage_graph('fact')} {{
            {self.stage_head('fact')} <{P}fact> {node} .
            {node} <{P}factDecisionGraph> {variable} }} GRAPH {variable} {{ {pattern} }}'''

    def _check_decision_plans(self, kind, *, graph=None):
        role, pointer = ('canonical', 'canonicalGraph') if kind == 'identity' else ('fact', 'factDecisionGraph')
        graph = graph or self.stage_graph(kind)
        head = self.ox.NamedNode(graph.value + ':head')
        invalid=self.owner.store.query(f'''SELECT ?node WHERE {{ GRAPH {graph} {{
            {head} <{P+role}> ?node . OPTIONAL {{ ?node <{P+pointer}> ?location }} }} }}
            GROUP BY ?node HAVING(COUNT(?location) != 1) LIMIT 1''')
        if next(iter(invalid),None) is not None:
            raise ProcessingError('Completed '+kind+' decision graph missing or duplicated')
        for field,count in [('member','memberCount')]+([('selector','selectorCount')] if kind=='identity' else []):
            body=f'''GRAPH {graph} {{ {head} <{P+role}> ?node .
                    ?node <{P+pointer}> ?location }}
                OPTIONAL {{ GRAPH ?location {{ ?node <{P+count}> ?expected }} }}
                OPTIONAL {{ GRAPH ?location {{ ?node <{P+field}> ?ref }} }}'''
            invalid=self.owner.store.query(f'''SELECT ?node WHERE {{
                {{ SELECT ?node (COUNT(DISTINCT ?expected) AS ?expectedCount)
                    (SAMPLE(?expected) AS ?value) (COUNT(?ref) AS ?actual)
                    WHERE {{ {body} }} GROUP BY ?node }}
                BIND(IF(datatype(?value) IN (xsd:integer, xsd:string),
                    xsd:integer(?value), 1/0) AS ?integer)
                FILTER(?expectedCount != 1 || !BOUND(?integer) ||
                    ?integer < 0 || ?actual != ?integer) }} LIMIT 1''',
                prefixes={'xsd':'http://www.w3.org/2001/XMLSchema#'})
            if next(iter(invalid),None) is not None:
                label = 'Canonical' if kind == 'identity' else 'Canonical fact'
                label += ' membership' if field == 'member' else ' selector'
                raise ProcessingError(label+' plan is incomplete')

    def fields(self, node, fields, *, graph=None, prefix=P):
        """Point-read selected fields without traversing support membership."""
        return self.field_page([node], fields, graph=graph, prefix=prefix)[node]

    def field_page(self,nodes,fields,*,graph=None,prefix=P):
        """Project a bounded address page inside the native engine."""
        if len(nodes)>MAX_ROWS or len(set(nodes))!=len(nodes):
            raise ProcessingError('Publication field page exceeds row budget')
        result={node:{field:[] for field in fields} for node in nodes}
        if not nodes or not fields:
            return result
        names={field if field==RDF_TYPE else prefix+field:field for field in fields}
        size=0
        predicates=[(self.ox.NamedNode(name),field) for name,field in names.items()]
        # Bind both indexes explicitly; a VALUES cross-product can select a
        # whole-graph join plan even though the returned page is small.
        for node in nodes:
            check_query_cancellation()
            for predicate,field in predicates:
                for quad in self.owner.store.quads_for_pattern(node,predicate,None,graph or self.record_graph(node)):
                    values=result[node][field]
                    size+=len(str(quad.object).encode())
                    if len(values)>=MAX_ROWS or size>MAX_BYTES:
                        raise ProcessingError('Publication field page exceeds byte or row budget')
                    values.append(quad.object)
        return result

    def qualified_members(self, *, decision):
        """Final native support adjacency; no intermediate view entries exist."""
        self.decision_identity(decision)
        yield from self.owner.store.quads_for_pattern(decision,self.ox.NamedNode(P+'member'),None,self.record_graph(decision))

    def decision_identity(self, node):
        """The address contains the semantic identity, never a second scalar copy."""
        if not isinstance(node,self.ox.NamedNode):
            raise ProcessingError('Native fact reconciliation incomplete')
        identity=node.value
        kind,_,digest=identity.partition(':')
        if kind!='relation' or len(digest)!=32 or any(c not in '0123456789abcdef' for c in digest):
            raise ProcessingError('Native fact reconciliation incomplete')
        return kind,identity

    def one(self, node, field):
        values = self.values(node, field)
        if len(values) != 1:
            raise ProcessingError("Publication field missing or duplicated: " + field)
        return values[0].value

    @_locked
    def status(self):
        head, graph = self.publication_head, self.publication_graph
        if not self.values(head, "generation", graph=graph):
            return None
        def one(node, field):
            values = self.values(node, field, graph=graph)
            if len(values) != 1:
                raise ProcessingError('Publication field missing or duplicated: ' + field)
            return values[0].value
        result = dict(project=self.project, generation=one(head, "generation"),
                      state=one(head, "state"), source_count=int(one(head, "sourceCount")),
                      canonical_count=(int(one(head, "canonicalCount"))
                          if self.values(head, "canonicalCount", graph=graph) else None), indexes={})
        if result["state"] == "ready":
            for kind in ("keyword", "semantic"):
                node = self.iri(one(head, kind))
                identity = {key: one(node, key) for key in ("kind", "store_id", "recipe_digest")}
                if self.values(node, "space_id", graph=graph):
                    identity["space_id"] = one(node, "space_id")
                result["indexes"][kind] = identity
        return result

    def fence(self, generation, state="ready"):
        self.scalar(generation)
        self.generation = self.scalar(generation)
        status = self.status()
        if status is None or status["generation"] != generation or status["state"] != state:
            raise ProcessingError("Publication generation stale or not " + state)
        pointer = self._pointer(self.registry_head, 'active' if state == 'ready' else 'latest', self.registry)
        if pointer != self.scalar(generation):
            raise ProcessingError('Publication generation stale or not ' + state)
        return status

    @_locked
    def completed_publication(self, input_key):
        """Read an atomically activated input binding; never reconstruct results."""
        self.generation = self._pointer(self.registry_head, 'active', self.registry)
        if self.generation is None:
            return None
        status = self.status()
        if status is None or status['state'] != 'ready':
            return None
        keys = self.values(self.head, 'completedInput')
        if len(keys) > 1:
            raise ProcessingError('Completed publication input is duplicated')
        if not keys or keys != [self.scalar(input_key)]:
            return None
        encoded = self.one(self.head, 'completedIndexes')
        if len(encoded.encode()) > MAX_BYTES:
            raise ProcessingError('Completed publication addresses exceed budget')
        if hashlib.sha256(encoded.encode()).hexdigest() != self.one(self.head, 'completedIndexesDigest'):
            raise ProcessingError('Completed publication addresses are corrupt')
        try:
            indexes = json.loads(encoded)
        except ValueError as exc:
            raise ProcessingError('Completed publication addresses are corrupt') from exc
        self._check_index_addresses(indexes, status['indexes'])
        return indexes

    def _check_index_addresses(self, addresses, receipts):
        if not isinstance(addresses, dict) or set(addresses) != {'keyword', 'semantic'}:
            raise ProcessingError('Completed publication indexes are incomplete')
        for kind, descriptor in addresses.items():
            if not isinstance(descriptor, dict) or descriptor.get('receipt') != receipts[kind]:
                raise ProcessingError('Completed publication index receipt differs')

    def _check_generation(self, generation, state):
        self.fence(generation, state)

    def triple(self, node, field, value):
        return f"{node} <{P + field}> {value} ."

    @_locked
    def mutate(self, generation, triples, *, state="pending"):
        body = "\n".join(triples)
        if len(body.encode()) > MAX_BYTES:
            raise ProcessingError("Publication atomic write exceeds byte budget")
        check_query_cancellation()
        self.fence(generation, state)
        self._writable_stage()
        checkpoint = getattr(self, '_checkpoint', None)
        if checkpoint is not None:
            if checkpoint['generation'] != generation or state != 'pending':
                raise ProcessingError('Publication checkpoint generation changed')
        self.owner._update_derived_graph(self.graph, insert=body, where=f"GRAPH {self.publication_graph} {{ {self.publication_head} <{P}generation> {self.scalar(generation)} ; <{P}state> {self.scalar(state)} . }}")
        if checkpoint is None:
            self.owner.flush()
        else:
            checkpoint['writes'] += 1
            if checkpoint['writes'] >= MAX_ROWS:
                self.owner.flush()
                checkpoint.update(writes=0)
        self.fence(generation, state)

    @_locked
    def import_batches(self, generation, batches):
        """Stream bounded pending windows into the existing native graph."""
        self._build_fence(generation)
        self._writable_stage()
        # One stage-wide import; _TripleStream bounds Python's current window.
        # The caller commits completion metadata only after this stream succeeds.
        with io.BufferedReader(_TripleStream(batches)) as stream:
            self.owner.store.bulk_load(input=stream,format=self.ox.RdfFormat.N_TRIPLES,to_graph=self.graph)
        self._build_fence(generation)

    def require_kind(self, node, kind):
        other_kinds={self.ox.NamedNode(P+other) for other in
            {'canonical', 'community', 'topic', 'fact'} - {kind}}
        # Seek roles pointing to this address once, rather than probing each role.
        graphs = {self.publication_graph, self.stage_graph('identity'), self.stage_graph('fact')}
        for graph in graphs:
            head = self.ox.NamedNode(graph.value + ':head')
            for count,link in enumerate(self.owner.store.quads_for_pattern(head,None,node,graph),1):
                if count>MAX_ROWS:
                    raise ProcessingError('Publication identity role fanout exceeds row budget')
                if link.predicate in other_kinds:
                    raise ProcessingError('Publication identity already has another kind')

    @contextmanager
    def checkpointed(self, generation):
        """Durably checkpoint streaming pending writes without retaining DTOs.

        Every mutation remains immediately visible under the publication lock.
        Each write is at most 256KiB; flush every 128 writes (at most 32MiB)
        and on scope exit. Transport size is not a durability checkpoint.
        The caller seals/activates only after this scope has completed.
        """
        with self.owner._publication_lock:
            if getattr(self, '_checkpoint', None) is not None:
                raise ProcessingError('Nested publication checkpoint scope')
            check_query_cancellation()
            self.fence(generation, 'pending')
            self._checkpoint = dict(generation=generation, writes=0)
            try:
                yield self
                check_query_cancellation()
                self.fence(generation, 'pending')
                self.owner.flush()
            finally:
                self._checkpoint = None

    @_locked
    def migrate_pending_registry(self):
        """Offline admission of a flat interrupted publication by reference."""
        if self._pointer(self.registry_head, 'latest', self.registry) is not None:
            return False
        self.generation = None
        current = self.status()
        if current is None:
            return False
        if current['state'] != 'pending':
            raise ProcessingError('Offline publication migration requires an interrupted pending publication')
        old_head, old_graph = self.head, self.graph
        identity_input = self.values(old_head, 'identityStageInput', graph=old_graph)
        if identity_input:
            if len(identity_input) != 1 or not self.values(old_head, 'identityIndexSealed', graph=old_graph):
                raise ProcessingError('Offline publication migration identity completion is incomplete')
            # Index seeks avoid a Cartesian plan over unrelated support edges.
            canonical = self.iri(P+'canonical')
            canonical_count = 0
            for link in self.owner.store.quads_for_pattern(old_head, canonical, None, old_graph):
                check_query_cancellation()
                canonical_count += 1
                for field, count in [('member', 'memberCount'), ('selector', 'selectorCount')]:
                    values = self.values(link.object, count, graph=old_graph)
                    try:
                        if len(values) != 1 or values[0].datatype.value not in {
                            'http://www.w3.org/2001/XMLSchema#integer',
                            'http://www.w3.org/2001/XMLSchema#string',
                        }:
                            raise ValueError
                        expected = int(values[0].value)
                    except (AttributeError, ValueError):
                        raise ProcessingError('Offline publication migration identity plan is incomplete')
                    actual = sum(1 for _ in self.owner.store.quads_for_pattern(
                        link.object, self.iri(P+field), None, old_graph))
                    if expected < 0 or actual != expected:
                        raise ProcessingError('Offline publication migration identity plan is incomplete')
            if canonical_count != int(self.one(old_head, 'identityStageCount')):
                raise ProcessingError('Offline publication migration identity count differs')
            for link in self.owner.store.quads_for_pattern(old_head, self.iri(P+'identityMember'), None, old_graph):
                check_query_cancellation()
                if not any(next(self.owner.store.quads_for_pattern(
                    old_head, canonical, member.subject, old_graph), None) is not None
                    for member in self.owner.store.quads_for_pattern(None, self.iri(P+'member'), link.object, old_graph)):
                    raise ProcessingError('Offline publication migration identity coverage is incomplete')
        self.generation = self.scalar(current['generation'])
        graph, head = self.publication_graph, self.publication_head
        if self.owner.store.contains_named_graph(graph):
            raise ProcessingError('Offline publication migration destination already exists')
        completion = (self.triple(self._completion_key('identity', identity_input[0].value),
            'completedGraph', old_graph) if identity_input else '')
        header = ' '.join(self.triple(head, key, self.ox.Literal(value)) for key, value in {
            'generation': current['generation'], 'state': 'pending',
            'sourceCount': current['source_count'],
        }.items())
        identity = self.triple(head, 'identityGraph', old_graph) if identity_input else ''
        # Admit the existing immutable stage without copying its rows. The new
        # pending publication has no reference to any unfinished fact stage.
        self.owner.store.update(f'''
            INSERT DATA {{ GRAPH {self.registry} {{
                {self.registry_head} <{P}latest> {self.generation} . {completion} }}
                GRAPH {graph} {{ {header} {identity} }} }};
            INSERT {{ GRAPH {old_graph} {{ ?node <{P}canonicalGraph> {old_graph} }} }}
            WHERE {{ GRAPH {old_graph} {{ {old_head} <{P}canonical> ?node }} }}''')
        self.owner.flush()
        return True

    @_locked
    def begin(self, *, expected_generation, source_count, canonical_count):
        if self.owner.path is None:
            raise ProcessingError("Publication requires persistent Oxigraph")
        if any(type(n) is not int or n < 0 or n > 1000000 for n in (source_count, *([canonical_count] if canonical_count is not None else []))):
            raise ProcessingError("Invalid publication counts")
        current = self.status()
        if current is not None and self._pointer(self.registry_head, 'latest', self.registry) is None:
            raise ProcessingError('Native store requires offline publication migration')
        if (current or {}).get("generation") != expected_generation:
            raise ProcessingError("Publication CAS conflict")
        generation = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        previous_identity = self.stage_graph('identity') if current else None
        if current and not (self.values(self.stage_head('identity'), 'identityStageInput', graph=previous_identity)
                or next(self.owner.store.quads_for_pattern(None, self.iri(P+'identityFeatures'), None, previous_identity), None)):
            previous_identity = self._pointer(self.publication_head, 'previousIdentityGraph', self.publication_graph) or previous_identity
        previous_fact = self.stage_graph('fact') if current else None
        self.generation = self.scalar(generation)
        triples = [self.triple(self.head, k, self.ox.Literal(v)) for k, v in dict(
            generation=generation, state="pending", sourceCount=source_count).items()]
        if canonical_count is not None:
            triples.append(self.triple(self.head, "canonicalCount", self.ox.Literal(canonical_count)))
        if previous_identity is not None:
            triples.append(self.triple(self.head, 'previousIdentityGraph', previous_identity))
        if previous_fact is not None:
            triples.append(self.triple(self.head, 'previousFactGraph', previous_fact))
        guard = (f"GRAPH {self.registry} {{ {self.registry_head} <{P}latest> {self.scalar(expected_generation)} }}" if expected_generation is not None
                 else f"FILTER NOT EXISTS {{ GRAPH {self.registry} {{ {self.registry_head} <{P}latest> ?generation }} }}")
        # Pending output has its own address. The active pointer and immutable
        # completed stages are untouched until a validated atomic activation.
        old = f'{self.registry_head} <{P}latest> {self.scalar(expected_generation)}' if expected_generation is not None else ''
        self.owner.store.update(f'''DELETE {{ GRAPH {self.registry} {{ {old} }} }}
            INSERT {{ GRAPH {self.registry} {{ {self.registry_head} <{P}latest> {self.scalar(generation)} }}
                GRAPH {self.graph} {{ {' '.join(triples)} }} }} WHERE {{ {guard} }}''')
        self.owner.flush()
        return self.fence(generation, "pending")

    def _identity_selection(self, subject, predicate):
        """The sole native identity-stage ownership boundary inside this graph."""
        return f"""STRSTARTS(STR({predicate}), "{P}identity") ||
            ({subject} = {self.head} && {predicate} = <{P}canonical>) ||
            EXISTS {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> {subject} }} }} ||
            EXISTS {{ GRAPH {self.graph} {{ ?identityCanonical <{P}selector> {subject} }}
                FILTER EXISTS {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> ?identityCanonical }} }} }}"""

    def _fact_selection(self, subject, predicate):
        return f'''STRSTARTS(STR({predicate}), "{P}qualified") ||
            ({subject} = {self.head} && {predicate} IN (<{P}fact>, <{P}factStageInput>)) ||
            EXISTS {{ GRAPH {self.graph} {{ {self.head} <{P}fact> {subject} }} }}'''

    @staticmethod
    def functional_policy(values):
        if isinstance(values,(str,bytes,dict)):
            raise ProcessingError('Invalid functional predicate policy')
        try:
            values=tuple(islice(values,4097))
        except TypeError as exc:
            raise ProcessingError('Invalid functional predicate policy') from exc
        if len(values)>4096 or any(not isinstance(value,str) or not value or len(value)>4096 for value in values):
            raise ProcessingError('Invalid functional predicate policy')
        return tuple(sorted(set(values)))

    def require_qualified_layout(self):
        """Reject incompatible derived indices; reads never migrate or rebuild."""
        # Old all-in-one publications stored the marker on the publication
        # graph.  Check that graph before a pending attempt binds a private
        # fact stage, otherwise the obsolete layout is hidden by the new scope.
        graph = self.graph
        head = self.head
        layout=self.values(head,'qualifiedIndexLayout')
        if graph != self.publication_graph:
            legacy_head = self.publication_head
            legacy = list(self.owner.store.quads_for_pattern(
                legacy_head, self.ox.NamedNode(P+'qualifiedIndexLayout'), None,
                self.publication_graph))
            if legacy:
                layout = [quad.object for quad in legacy]
                head, graph = legacy_head, self.publication_graph
        if layout==[self.ox.Literal('native-single-fact-decisions')]:
            return
        if layout or any(self.values(head,field,graph=graph) for field in
                ('qualifiedIndexSealed','factStageInput','qualifiedEntry','qualifiedPartitionNode')):
            raise ProcessingError('Obsolete qualified index requires explicit offline reset')

    @_locked
    @_stage('fact')
    def fact_stage_status(self, generation, input_key, *, functional_predicates=()):
        self.fence(generation,'pending')
        self.scalar(input_key)
        self.require_qualified_layout()
        stage_key = self._completion_key('fact', input_key, functional_predicates=functional_predicates)
        if (self._pointer(stage_key, 'completedGraph', self.registry) is None and
                self._pointer(self.publication_head, 'factGraph', self.publication_graph) is None):
            return False
        self._bind_stage('fact', input_key, functional_predicates=functional_predicates)
        values=self.values(self.head,'factStageInput')
        if not values:
            return False
        if len(values)!=1:
            raise ProcessingError('Native fact completion marker is duplicated')
        if values[0].value!=input_key:
            return False
        policy=self.scalar(json.dumps(self.functional_policy(functional_predicates),separators=(',',':')))
        if self.values(self.head,'qualifiedFunctionalPredicates') != [policy]:
            return False
        if len(self.values(self.head,'qualifiedDecisionCount'))!=1:
            raise ProcessingError('Native fact completion lacks sealed index')
        return True

    @_locked
    @_stage('fact')
    def reset_fact_stage(self,generation):
        self.fence(generation,'pending')
        self._writable_stage()
        self.owner._update_derived_graph(self.graph,delete='?s ?p ?o',
            where=f'GRAPH {self.graph} {{ ?s ?p ?o }} FILTER({self._fact_selection("?s","?p")})')
        # Explicit offline reset also removes the pre-stage qualified index
        # marker left on the old publication graph. Normal reads never do this.
        if self.graph != self.publication_graph:
            self.owner.store.update(f'''DELETE {{ GRAPH {self.publication_graph} {{
                {self.publication_head} ?predicate ?value }} }}
                WHERE {{ GRAPH {self.publication_graph} {{
                {self.publication_head} ?predicate ?value .
                FILTER(?predicate IN (<{P}qualifiedIndexLayout>, <{P}qualifiedIndexSealed>,
                    <{P}factStageInput>, <{P}qualifiedEntry>, <{P}qualifiedPartitionNode>)) }} }}''')
        self.owner.flush()

    @_locked
    @_stage('identity')
    def identity_stage_status(self, generation, input_key):
        """Point-read a complete decision stage; never restore or audit entities."""
        self.fence(generation, 'pending')
        self.scalar(input_key)
        stage_key = self._completion_key('identity', input_key)
        if (self._pointer(stage_key, 'completedGraph', self.registry) is None and
                self._pointer(self.publication_head, 'identityGraph', self.publication_graph) is None):
            return None
        self._bind_stage('identity', input_key)
        values = self.values(self.head, 'identityStageInput')
        if not values:
            return None
        if len(values) != 1:
            raise ProcessingError('Invalid native identity completion marker')
        if values[0].value != input_key and self._pointer(
                stage_key, 'completedGraph', self.registry) != self.graph:
            return None
        if not self.values(self.head, 'identityIndexSealed'):
            raise ProcessingError('Native identity completion lacks sealed index')
        return dict(input_key=input_key,
                    canonical_count=int(self.one(self.head, 'identityStageCount')))

    @_locked
    def migrate_identity_completion(self, generation, *, input_key, completed_input, policy_key):
        """Offline rebind after an identity-contract change; audit exact native membership."""
        self._build_fence(generation)
        for value in (input_key, completed_input, policy_key):
            self.scalar(value)
        old = self._pointer(self._completion_key('identity', completed_input), 'completedGraph', self.registry)
        if old is None:
            raise ProcessingError('Offline identity migration requires a completed stage')
        old_head = self.iri(old.value + ':head')
        if (self.values(old_head, 'identityStageInput', graph=old) != [self.scalar(completed_input)]
                or self.values(old_head, 'identityDecisionPolicy', graph=old) != [self.scalar(policy_key)]
                or len(self.values(old_head, 'identityIndexSealed', graph=old)) != 1):
            raise ProcessingError('Offline identity migration completion or policy differs')
        key = self._completion_key('identity', input_key)
        existing = self._pointer(key, 'completedGraph', self.registry)
        if existing is not None:
            if existing != old:
                raise ProcessingError('Offline identity migration destination differs')
            return False
        self._check_decision_plans('identity', graph=old)
        current = f"""GRAPH {self.publication_graph} {{
            {self.publication_head} <{P}source> ?source . ?source <{P}operation> ?operation }}
            GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?mention .
                ?mention <{RDF_TYPE}> <{F}Entity> }}"""
        previous = f'GRAPH {old} {{ {old_head} <{P}identityMember> ?mention }}'
        for left, right in ((current, previous), (previous, current)):
            if bool(self.owner.store.query(f'ASK {{ {{ SELECT DISTINCT ?mention WHERE {{ {left} }} }} MINUS {{ SELECT DISTINCT ?mention WHERE {{ {right} }} }} }}')):
                raise ProcessingError('Offline identity migration native membership differs')
        canonical = f"""GRAPH {old} {{ {old_head} <{P}canonical> ?canonical .
            ?canonical <{P}canonicalGraph> ?location }}
            GRAPH ?location {{ ?canonical <{P}member> ?mention }}"""
        for left, right in ((previous, canonical), (canonical, previous)):
            if bool(self.owner.store.query(f'ASK {{ {{ SELECT DISTINCT ?mention WHERE {{ {left} }} }} MINUS {{ SELECT DISTINCT ?mention WHERE {{ {right} }} }} }}')):
                raise ProcessingError('Offline identity migration decision coverage differs')
        duplicate = self.owner.store.query(f'''SELECT ?mention WHERE {{ {canonical} }}
            GROUP BY ?mention HAVING(COUNT(?canonical) != 1) LIMIT 1''')
        if next(iter(duplicate), None) is not None:
            raise ProcessingError('Offline identity migration decision membership is not unique')
        members = next(iter(self.owner.store.query(f'''SELECT (COUNT(?mention) AS ?count)
            WHERE {{ {previous} }}''')))['count'].value
        if self.values(old_head, 'identityIndexSealed', graph=old) != [self.ox.Literal(int(members))]:
            raise ProcessingError('Offline identity migration index count differs')
        actual = next(iter(self.owner.store.query(f"""SELECT (COUNT(?canonical) AS ?count)
            WHERE {{ GRAPH {old} {{ {old_head} <{P}canonical> ?canonical }} }}""")))['count'].value
        if self.values(old_head, 'identityStageCount', graph=old) != [self.ox.Literal(int(actual))]:
            raise ProcessingError('Offline identity migration decision count differs')
        self._build_fence(generation)
        self.owner.store.add(self.ox.Quad(key, self.iri(P+'completedGraph'), old, self.registry))
        self.owner.flush()
        return True

    @_locked
    @_stage('identity')
    def reset_identity_stage(self, generation):
        """Invalidate only identity output after an explicit dependency mismatch."""
        self.fence(generation, 'pending')
        local = self.ox.NamedNode(self.publication_graph.value + ':identity')
        if self.graph not in (self.publication_graph, local):
            # Detach this attempt; never delete a shared completed decision.
            self.owner.store.remove(self.ox.Quad(self.publication_head,
                self.ox.NamedNode(P+'identityGraph'), self.graph, self.publication_graph))
            self.owner.store.add(self.ox.Quad(self.publication_head,
                self.ox.NamedNode(P+'identityGraph'), local, self.publication_graph))
        self._writable_stage()
        self.owner._update_derived_graph(self.graph, delete='?s ?predicate ?o',
            where=f"""GRAPH {self.graph} {{ ?s ?predicate ?o }}
                FILTER({self._identity_selection('?s', '?predicate')} ||
                    (?s = {self.head} && ?predicate = <{P}canonicalCount>))""")
        self.owner.flush()
        self.fence(generation, 'pending')

    @_locked
    @_stage('identity')
    def seal_identity_stage(self, generation, input_key):
        """Commit completion only after every decision reference is durable."""
        self.fence(generation, 'pending')
        self.scalar(input_key)
        if self.values(self.head, 'identityStageInput'):
            raise ProcessingError('Native identity stage already sealed')
        if not self.values(self.head, 'identityIndexSealed'):
            raise ProcessingError('Native identity candidate index is not sealed')
        self._check_decision_plans('identity')
        # Evaluate registered decision membership once; correlated NOT EXISTS
        # makes Oxigraph enumerate canonical graph combinations per mention.
        uncovered=self.owner.store.query(f'''ASK {{ GRAPH {self.graph} {{
            {self.head} <{P}identityMember> ?mention }} MINUS {{ SELECT ?mention WHERE {{
            {self.canonical_pattern('?canonical', f'?canonical <{P}member> ?mention')} }} }} }}''')
        if bool(uncovered):
            raise ProcessingError('Canonical identity membership coverage is incomplete')
        count = int(next(iter(self.owner.store.query(f"""SELECT (COUNT(?canonical) AS ?count)
            WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> ?canonical }} }}""")))['count'].value)
        self.mutate(generation, [self.triple(self.head, 'identityStageInput', self.scalar(input_key)),
            self.triple(self.head, 'identityStageCount', self.ox.Literal(count))])
        self._complete_stage('identity', input_key)
        return count

    @_locked
    @_stage(None)
    def seal_canonical_count(self, generation, count):
        """Seal the output count after streaming computation, before activation."""
        self.fence(generation, "pending")
        if type(count) is not int or not 0 <= count <= 1000000:
            raise ProcessingError("Invalid canonical publication count")
        if self.values(self.head, "canonicalCount"):
            raise ProcessingError("Canonical publication count already sealed")
        actual = next(iter(self.owner.store.query(f"SELECT (COUNT(?record) AS ?count) WHERE {{ GRAPH {self.stage_graph('identity')} {{ {self.stage_head('identity')} <{P}canonical> ?record }} }}")))["count"]
        if int(actual.value) != count:
            raise ProcessingError("Canonical publication count does not match staged records")
        self.mutate(generation, [self.triple(self.head, "canonicalCount", self.ox.Literal(count))])

    @staticmethod
    def batch(values):
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_ROWS:
            raise ProcessingError("Publication batch must contain 1..128 records")

    def verify_operation(self, identity, source):
        return self.verify_operations([identity], source)[0]

    def verify_operations(self, identities, source):
        """Verify native completion and exact bindings in bounded address pages."""
        from .classification_records import ClassificationRecords
        self.batch(identities)
        for identity in identities:
            self.iri(identity)
        admitted = {}
        for cls in (ExtractionRecords, ClassificationRecords):
            selected = [identity for identity in identities
                if identity.startswith('urn:semantica:classification:') == (cls is ClassificationRecords)]
            if not selected:
                continue
            for records in cls.from_operations(self.owner, selected, self.project):
                if any(records.binding[field] != expected for field, expected in
                        dict(project=self.project, **{key: source[key] for key in
                            ('source', 'material', 'representation')}).items()):
                    raise ProcessingError('Publication operation belongs to another source or binding')
                admitted[records.operation.value] = records
        return [admitted[identity] for identity in identities]

    @_locked
    @_stage(None)
    def stage_sources(self, generation, sources):
        self.fence(generation, "pending")
        self.batch(sources)
        triples, seen = [], set()
        for source in sources:
            if not isinstance(source, dict) or set(source) != {"source", "material", "representation", "recipe", "operations", "operation_count"}:
                raise ProcessingError("Publication source requires exact native binding")
            self.batch(source["operations"])
            if type(source["operation_count"]) is not int or not len(source["operations"]) <= source["operation_count"] <= 1000000:
                raise ProcessingError("Invalid publication source operation count")
            if source["source"] in seen or len(set(source["operations"])) != len(source["operations"]):
                raise ProcessingError("Duplicate publication source or operation")
            seen.add(source["source"])
            source_node = self.ox.NamedNode(self.graph.value + ":source:" + hashlib.sha256(source["source"].encode()).hexdigest())
            if self.values(source_node, "source") and any(self.one(source_node, field) != source[field] for field in ("source", "material", "representation", "recipe")):
                raise ProcessingError("Publication source staged with another binding")
            if self.values(source_node, "operationCount") and int(self.one(source_node, "operationCount")) != source["operation_count"]:
                raise ProcessingError("Publication source operation plan changed")
            triples.append(self.triple(self.head, "source", source_node))
            triples.append(self.triple(source_node, "operationCount", self.ox.Literal(source["operation_count"])))
            for field in ("source", "material", "representation", "recipe"):
                triples.append(self.triple(source_node, field, self.scalar(source[field])))
            # Validate the accepted receipts before admitting their references.
            self.verify_operations(source["operations"], source)
            for identity in source["operations"]:
                operation = self.iri(identity)
                triples.append(self.triple(source_node, "operation", operation))
        window, size = [], 0
        for triple in triples:
            width = len(triple.encode()) + 1
            if window and size + width > MAX_BYTES:
                self.mutate(generation, window)
                window, size = [], 0
            window.append(triple)
            size += width
        if window:
            self.mutate(generation, window)

    def member(self, record, source_ids=None):
        self.members([record], source_ids)

    def members(self, records, source_ids=None):
        """Validate each record, sharing operation admission only within this page."""
        self.batch(records)
        selected = None
        if source_ids is not None:
            self.batch(source_ids)
            if len(set(source_ids)) != len(source_ids):
                raise ProcessingError("Duplicate native source selection")
            for source in source_ids:
                self.scalar(source)
            selected = {self.ox.NamedNode(self.publication_graph.value + ":source:" + hashlib.sha256(source.encode()).hexdigest()) for source in source_ids}
        admitted = set()
        owned_record = self.ox.NamedNode(F+'ownedRecord')
        operation = self.ox.NamedNode(P+'operation')
        source = self.ox.NamedNode(P+'source')
        for record in records:
            found = False
            for owned in self.owner.store.quads_for_pattern(None, owned_record, record, self.facts):
                check_query_cancellation()
                if owned.subject in admitted:
                    found = True
                    break
                for binding in self.owner.store.quads_for_pattern(None, operation, owned.subject, self.publication_graph):
                    check_query_cancellation()
                    if selected is not None and binding.subject not in selected:
                        continue
                    if next(self.owner.store.quads_for_pattern(self.publication_head, source, binding.subject, self.publication_graph), None) is not None:
                        admitted.add(owned.subject)
                        found = True
                        break
                if found:
                    break
            if not found:
                raise ProcessingError("Record outside current publication")

    @_locked
    def attribute_reference(self, generation, entity, name):
        self.fence(generation, "pending")
        node = self.iri(entity)
        self.member(node)
        self.scalar(name)
        matches = []
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(F + "attribute"), None, self.facts):
            fields = list(islice(self.owner.store.quads_for_pattern(quad.object, self.ox.NamedNode(F + "attributeName"), None, self.facts), 2))
            if len(fields) == 1 and fields[0].object.value == name:
                matches.append(quad.object.value)
            if len(matches) > 1:
                break
        if len(matches) != 1:
            raise ProcessingError("Native selected attribute missing or duplicated")
        return matches[0]

    @_locked
    @_stage('identity')
    def stage_canonical(self, generation, records):
        """Append bounded reference pages against one exact membership plan."""
        self.fence(generation, "pending")
        self.batch(records)
        triples, seen, assigned = [], set(), set()
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                    "id", "representative", "members", "member_count", "selectors", "selector_count"}:
                raise ProcessingError("Canonical membership is reference-only")
            if not isinstance(record['members'],list) or len(record['members']) > MAX_ROWS or not (record['members'] or record['selectors']):
                raise ProcessingError('Canonical page requires 1..128 member or selector references')
            if not isinstance(record["selectors"], list) or len(record["selectors"]) > MAX_ROWS:
                raise ProcessingError("Canonical selectors exceed budget")
            if (type(record['member_count']) is not int or record['member_count'] < 1
                    or type(record['selector_count']) is not int or record['selector_count'] < 0):
                raise ProcessingError('Invalid canonical completion plan')
            node = self.iri(record["id"])
            representative = self.iri(record['representative'])
            self.require_kind(node, 'canonical')
            if record["id"] in seen or any(not isinstance(m,str) for m in record['members']) or len(set(record["members"])) != len(record["members"]):
                raise ProcessingError("Duplicate canonical identity or member")
            seen.add(record["id"])
            fields = dict(representative=representative,memberCount=self.ox.Literal(record['member_count']),
                selectorCount=self.ox.Literal(record['selector_count']))
            existing = self.values(node, 'representative')
            if existing:
                if any(self.values(node,field) != [value] for field,value in fields.items()):
                    raise ProcessingError('Canonical membership plan changed')
            else:
                if record['representative'] not in record['members']:
                    raise ProcessingError('Canonical representative must be a member')
                triples.append(self.triple(self.head, "canonical", node))
                triples.append(self.triple(node, 'canonicalGraph', self.graph))
                triples.extend(self.triple(node,field,value) for field,value in fields.items())
            counts = {}
            for field in ('member','selector'):
                result=next(iter(self.owner.store.query(f'SELECT (COUNT(?ref) AS ?count) WHERE {{ GRAPH {self.graph} {{ {node} <{P+field}> ?ref }} }}')))
                counts[field]=int(result['count'].value)
            if counts['member']+len(record['members']) > record['member_count'] or counts['selector']+len(record['selectors']) > record['selector_count']:
                raise ProcessingError('Canonical completion plan exceeded')
            for identity in record["members"]:
                member = self.iri(identity)
                # Bind the member first; a SPARQL join can scan all canonical records.
                if identity in assigned or any(next(self.owner.store.quads_for_pattern(
                        self.head, self.ox.NamedNode(P+'canonical'), reference.subject, self.graph), None)
                        is not None for reference in self.owner.store.quads_for_pattern(
                            None, self.ox.NamedNode(P+'member'), member, self.graph)):
                    raise ProcessingError('Native Entity already belongs to a canonical member')
                assigned.add(identity)
                self.member(member)
                if not next(self.owner.store.quads_for_pattern(member, self.ox.NamedNode(RDF_TYPE), self.ox.NamedNode(F + "Entity"), self.facts),None):
                    raise ProcessingError("Canonical member must be a native Entity")
                triples.append(self.triple(node, "member", member))
            selected_fields = set()
            for ordinal, selector in enumerate(record["selectors"],start=counts['selector']):
                if not isinstance(selector, dict) or set(selector) != {"field", "record"} or any(not isinstance(v,str) for v in selector.values()) or (selector["field"], selector["record"]) in selected_fields:
                    raise ProcessingError("Invalid canonical field selector")
                selected_fields.add((selector["field"], selector["record"]))
                selected = self.iri(selector["record"])
                self.member(selected)
                field_value=self.scalar(selector['field'])
                duplicate=self.owner.store.query(f'ASK {{ GRAPH {self.graph} {{ {node} <{P}selector> ?selector . ?selector <{P}field> {field_value} ; <{P}record> {selected} }} }}')
                if bool(duplicate):
                    raise ProcessingError('Duplicate canonical field selector')
                if selector['record'] not in record['members']:
                    member=bool(self.owner.store.query(f'ASK {{ GRAPH {self.graph} {{ {node} <{P}member> {selected} }} }}'))
                    attribute=any(next(self.owner.store.quads_for_pattern(self.iri(m),self.ox.NamedNode(F+'attribute'),selected,self.facts),None) for m in record['members'])
                    if not member and not attribute:
                        attribute=bool(self.owner.store.query(f'ASK {{ GRAPH {self.graph} {{ {node} <{P}member> ?member }} GRAPH {self.facts} {{ ?member <{F}attribute> {selected} }} }}'))
                    if not member and not attribute:
                        raise ProcessingError("Selector must reference a member field or its AttributeValue")
                selector_node = self.ox.NamedNode(node.value + ":selector:" + str(ordinal))
                triples.extend([self.triple(node, "selector", selector_node), self.triple(selector_node, "position", self.ox.Literal(ordinal)), self.triple(selector_node, "field", field_value), self.triple(selector_node, "record", selected)])
        self.mutate(generation, triples)

    @_locked
    @_stage(None)
    def stage_communities(self, generation, records):
        """Persist native detector membership references, never a graph copy."""
        self.fence(generation, 'pending')
        self.batch(records)
        triples = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {'id', 'members', 'member_count'}:
                raise ProcessingError('Community membership is reference-only')
            self.batch(record['members'])
            if type(record['member_count']) is not int or not len(record['members']) <= record['member_count'] <= 1000000:
                raise ProcessingError('Invalid community membership count')
            if len(set(record['members'])) != len(record['members']):
                raise ProcessingError('Duplicate community member')
            node = self.iri(record['id'])
            self.require_kind(node, 'community')
            if self.values(node, 'memberCount') and int(self.one(node, 'memberCount')) != record['member_count']:
                raise ProcessingError('Community membership plan changed')
            triples.extend([self.triple(self.head, 'community', node),
                self.triple(node, 'memberCount', self.ox.Literal(record['member_count'])),
                self.triple(node, 'titleState', self.scalar('unavailable_title'))])
            for identity in record['members']:
                member = self.iri(identity)
                if not list(islice(self.owner.store.quads_for_pattern(self.stage_head('identity'), self.ox.NamedNode(P+'canonical'), member, self.stage_graph('identity')), 1)):
                    raise ProcessingError('Community member is not a current canonical entity')
                triples.append(self.triple(node, 'member', member))
        self.mutate(generation, triples)

    @_locked
    @_stage(None)
    def stage_topics(self, generation, records):
        """Retain the existing grounded organizer's result and native references."""
        self.fence(generation, 'pending')
        self.batch(records)
        triples, plans = [], {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                    'id', 'title', 'report_id', 'input_digest', 'members', 'member_count',
                    'evidence_ids', 'evidence_count'}:
                raise ProcessingError('Invalid grounded topic fields')
            node = self.iri(record['id'])
            self.require_kind(node, 'topic')
            metadata = dict(title=record['title'], reportId=record['report_id'], inputDigest=record['input_digest'],
                memberCount=record['member_count'], evidenceCount=record['evidence_count'])
            if record['id'] in plans and plans[record['id']] != metadata:
                raise ProcessingError('Topic membership plan changed within batch')
            plans[record['id']] = metadata
            for field, value in metadata.items():
                if field.endswith('Count'):
                    if type(value) is not int or not 1 <= value <= 1000000:
                        raise ProcessingError('Invalid topic reference count')
                else:
                    self.scalar(value)
                if self.values(node, field) and self.one(node, field) != str(value):
                    raise ProcessingError('Topic membership plan changed')
                triples.append(self.triple(node, field, self.ox.Literal(value)))
            triples.append(self.triple(self.head, 'topic', node))
            for field, values, count in (('member', record['members'], record['member_count']),
                    ('evidence', record['evidence_ids'], record['evidence_count'])):
                if (not isinstance(values, list) or len(values) > min(MAX_ROWS, count)
                        or any(not isinstance(value, str) for value in values) or len(set(values)) != len(values)):
                    raise ProcessingError('Invalid topic reference batch')
                for identity in values:
                    ref = self.iri(identity)
                    if field == 'member':
                        if not list(islice(self.owner.store.quads_for_pattern(self.stage_head('identity'), self.ox.NamedNode(P+'canonical'), ref, self.stage_graph('identity')), 1)):
                            raise ProcessingError('Topic member is not a current canonical entity')
                    else:
                        self.member(ref)
                        if not any(list(islice(self.owner.store.quads_for_pattern(ref, self.ox.NamedNode(RDF_TYPE), self.ox.NamedNode(F+kind), self.facts), 1))
                                for kind in ('Evidence', 'Mention')):
                            raise ProcessingError('Topic reference is not native evidence')
                    triples.append(self.triple(node, field, ref))
        self.mutate(generation, triples)


    @_locked
    @_stage('fact')
    def fact_members(self, generation, identity, *, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES):
        """Seek support observations without loading a canonical fact group."""
        self.fence(generation)
        node = self.iri(identity)
        if (type(limit) is not int or not 1 <= limit <= MAX_ROWS
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES):
            raise ProcessingError("Invalid canonical fact support page budget")
        if not bool(self.owner.store.query(f'ASK {{ GRAPH {self.graph} {{ {self.head} <{P}fact> {node} }} }}')):
            raise ProcessingError("Canonical fact outside current publication")
        cursor = f'FILTER(STR(?member) > {self.scalar(after)})' if after is not None else ''
        if after is not None:
            self.iri(after)
        rows = list(self.owner.store.query(f'SELECT ?member WHERE {{ {self.fact_pattern(node, f"{node} <{P}member> ?member")} {cursor} }} ORDER BY ?member LIMIT {limit+1}'))
        response = dict(id=identity, members=[], member_count=int(self.one(node, "memberCount")), next_cursor=None)
        for row in rows[:limit]:
            member = row["member"].value
            response["members"].append(member)
            if len(json.dumps(response, ensure_ascii=False).encode()) > max_bytes:
                response["members"].pop()
                if not response["members"]:
                    raise ProcessingError("Canonical fact support item exceeds byte budget")
                response["next_cursor"] = response["members"][-1]
                break
        else:
            if len(rows) > limit:
                response["next_cursor"] = response["members"][-1]
        self.fence(generation)
        return response

    @_stage('fact')
    def _projected_scene_link(self, row, *, status=False):
        node = self.iri(row['id'].value)
        representative = self.iri(self.one(node, 'representative'))
        predicates = list(islice(self.owner.store.quads_for_pattern(
            representative, self.ox.NamedNode(F+'predicateName'), None, self.facts), 2))
        if len(predicates) != 1 or not isinstance(predicates[0].object, self.ox.Literal):
            raise ProcessingError('Native relation predicate missing or duplicated')
        predicate = predicates[0].object.value
        item = dict(id=node.value, source=row['source'].value, target=row['target'].value,
                    predicate=normalize_fact_predicate(predicate))
        if status:
            item['status'] = self.one(node, 'status')
        return item

    @_stage('fact')
    def _fact_scene_link(self, generation, row):
        identity = row["id"].value
        node = self.iri(identity)
        representative = self.one(node, "representative")
        record = self.read(generation, [representative], max_bytes=MAX_BYTES)[0]
        # Provenance is a bounded display projection. Large fact support is
        # retained in RDF and must be requested through a bounded member page.
        query = f"""SELECT DISTINCT ?source ?evidence WHERE {{
            {self.fact_pattern(node, f'{node} <{P}member> ?record')}
            GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?membership .
                ?membership <{P}source> ?source ; <{P}operation> ?operation }}
            GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record .
                OPTIONAL {{ ?record <{F}evidence> ?evidence }} }}
        }} LIMIT {MAX_ROWS+1}"""
        rows = list(self.owner.store.query(query))
        if len(rows) > MAX_ROWS:
            raise ProcessingError("Canonical fact provenance exceeds bounded scene selection")
        predicates = record["fields"].get(F+"predicateName", [])
        if len(predicates) != 1:
            raise ProcessingError("Native relation predicate missing or duplicated")
        fields = dict(record["fields"])
        fields[F+"status"] = [dict(type="iri", value=F+self.one(node, "status"))]
        return dict(id=identity, source=row["source"].value, target=row["target"].value,
            predicate=normalize_fact_predicate(predicates[0]["value"]), fields=fields,
            sourceIds=sorted({r["source"].value for r in rows}),
            evidenceIds=sorted({r["evidence"].value for r in rows if r["evidence"] is not None}))

    @_locked
    @_stage(None)
    def activate(self, generation, *, indexes, completed_input=None, index_addresses=None):
        status = self.fence(generation, "pending")
        if status["canonical_count"] is None:
            raise ProcessingError("Canonical publication count is not sealed")
        if not isinstance(indexes, dict) or set(indexes) != {"keyword", "semantic"}:
            raise ProcessingError("Publication requires both native indexes")
        triples = []
        if (completed_input is None) != (index_addresses is None):
            raise ProcessingError('Publication completion requires input and index addresses')
        if completed_input is not None:
            self.scalar(completed_input)
            self._check_index_addresses(index_addresses, indexes)
            encoded = json.dumps(index_addresses, ensure_ascii=False, separators=(',', ':'))
            if len(encoded.encode()) > MAX_BYTES:
                raise ProcessingError('Completed publication addresses exceed budget')
            triples.extend(self.triple(self.head, key, self.ox.Literal(value)) for key, value in dict(
                completedInput=completed_input, completedIndexes=encoded,
                completedIndexesDigest=hashlib.sha256(encoded.encode()).hexdigest()).items())
        for kind, identity in indexes.items():
            required = {"kind", "store_id", "recipe_digest"} | ({"space_id"} if kind == "semantic" else set())
            if not isinstance(identity, dict) or set(identity) != required:
                raise ProcessingError("Incomplete native index receipt")
            node = self.ox.NamedNode(self.graph.value + ":index:" + kind)
            triples.append(self.triple(self.head, kind, node))
            triples.extend(self.triple(node, field, self.scalar(value)) for field, value in identity.items())
        identity_graph, identity_head = self.stage_graph('identity'), self.stage_head('identity')
        fact_graph, fact_head = self.stage_graph('fact'), self.stage_head('fact')
        for field, expected, graph, head in (
                ("source", status["source_count"], self.publication_graph, self.publication_head),
                ("canonical", status["canonical_count"], identity_graph, identity_head)):
            count = next(iter(self.owner.store.query(f"SELECT (COUNT(?record) AS ?count) WHERE {{ GRAPH {graph} {{ {head} <{P + field}> ?record }} }}")))["count"]
            if int(count.value) != expected:
                raise ProcessingError("Publication staged record count is incomplete")
        incomplete = self.owner.store.query(f"SELECT ?source WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}source> ?source . ?source <{P}operationCount> ?expected . OPTIONAL {{ ?source <{P}operation> ?operation }} }} }} GROUP BY ?source ?expected HAVING(COUNT(?operation) != ?expected) LIMIT 1")
        if next(iter(incomplete), None) is not None:
            raise ProcessingError("Publication source operation plan is incomplete")
        self._check_decision_plans('identity')
        self._check_decision_plans('fact')
        incomplete = self.owner.store.query(f'SELECT ?community WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}community> ?community . ?community <{P}memberCount> ?expected . OPTIONAL {{ ?community <{P}member> ?member }} }} }} GROUP BY ?community ?expected HAVING(COUNT(?member) != ?expected) LIMIT 1')
        if next(iter(incomplete), None) is not None:
            raise ProcessingError('Community membership plan is incomplete')
        for field, count in (('member', 'memberCount'), ('evidence', 'evidenceCount')):
            incomplete = self.owner.store.query(f'''SELECT ?topic WHERE {{ GRAPH {self.graph} {{
                {self.head} <{P}topic> ?topic . ?topic <{P+count}> ?expected .
                OPTIONAL {{ ?topic <{P+field}> ?ref }} }} }}
                GROUP BY ?topic ?expected HAVING(COUNT(?ref) != ?expected) LIMIT 1''')
            if next(iter(incomplete), None) is not None:
                raise ProcessingError('Topic membership plan is incomplete')
        invalid = self.owner.store.query(f'''ASK {{ GRAPH {fact_graph} {{
            {fact_head} <{P}fact> ?fact . ?fact <{P}factDecisionGraph> ?decision }}
            FILTER NOT EXISTS {{ GRAPH ?decision {{ ?fact <{P}representative> ?representative ;
                <{P}member> ?representative }} }} }}''')
        if bool(invalid):
            raise ProcessingError("Canonical fact representative is not a member")
        invalid_member = self.owner.store.query(f"""ASK {{ {self.fact_pattern('?fact', f'?fact <{P}member> ?relation')}
            MINUS {{ SELECT ?relation WHERE {{ GRAPH {self.facts} {{
                ?operation <{F}ownedRecord> ?relation . ?relation <{RDF_TYPE}> <{F}Relation> }}
                GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?sourceOwner .
                    ?sourceOwner <{P}operation> ?operation }} }} }} }}""")
        if bool(invalid_member):
            raise ProcessingError("Canonical fact member is outside the current publication")
        duplicate_member = self.owner.store.query(f"""SELECT ?relation WHERE {{
            {self.fact_pattern('?fact', f'?fact <{P}member> ?relation')}
            }} GROUP BY ?relation HAVING(COUNT(DISTINCT ?fact) > 1) LIMIT 1""")
        if next(iter(duplicate_member), None) is not None:
            raise ProcessingError("Native Relation belongs to multiple canonical facts")
        relation_scope = f"""GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?membership .
            ?membership <{P}operation> ?operation }} GRAPH {self.facts} {{
            ?operation <{F}ownedRecord> ?relation . ?relation <{RDF_TYPE}> <{F}Relation> }}"""
        owned_count = next(iter(self.owner.store.query(f"SELECT (COUNT(DISTINCT ?relation) AS ?count) WHERE {{ {relation_scope} }}")))["count"]
        # The production fact owner admits owned relations with unique assignment;
        # the check above verifies each fact's actual membership count. Their sum
        # therefore proves exact coverage without joining every relation again.
        planned_count = next(iter(self.owner.store.query(f"""SELECT (COALESCE(SUM(xsd:integer(?expected)), 0) AS ?count) WHERE {{
            {self.fact_pattern('?fact', f'?fact <{P}memberCount> ?expected')} }}""", prefixes={"xsd": "http://www.w3.org/2001/XMLSchema#"})))["count"]
        check_query_cancellation()
        if int(owned_count.value) != int(planned_count.value):
            raise ProcessingError("Canonical fact coverage is incomplete")
        body = " ".join(triples)
        self.owner.store.update(f'''DELETE {{
                GRAPH {self.graph} {{ {self.head} <{P}state> 'pending' }}
                GRAPH {self.registry} {{ {self.registry_head} <{P}active> ?old }} }}
            INSERT {{ GRAPH {self.graph} {{ {self.head} <{P}state> 'ready' . {body} }}
                GRAPH {self.registry} {{ {self.registry_head} <{P}active> {self.scalar(generation)} }} }}
            WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}generation> {self.scalar(generation)} ; <{P}state> 'pending' }}
                OPTIONAL {{ GRAPH {self.registry} {{ {self.registry_head} <{P}active> ?old }} }} }}''')
        self.owner.flush()
        return self.fence(generation)

    @_locked
    @_stage(None)
    def withdraw(self, *, expected_generation):
        self.fence(expected_generation)
        self.owner._update_derived_graph(self.graph, delete=f"{self.head} <{P}state> 'ready'", insert=f"{self.head} <{P}state> 'withdrawn'", where=f"GRAPH {self.graph} {{ {self.head} <{P}generation> {self.scalar(expected_generation)} ; <{P}state> 'ready' }}")
        self.owner.flush()
        return self.fence(expected_generation, "withdrawn")

    def read(self, generation, record_ids, *, max_bytes=MAX_BYTES, source_ids=None):
        self.fence(generation)
        result = self._read(record_ids, max_bytes=max_bytes, source_ids=source_ids)
        self.fence(generation)
        return result

    @contextmanager
    def build_scope(self, generation):
        """Validate immutable inputs at handoffs; keep keyed checks per operation."""
        with self.owner._publication_lock:
            if getattr(self.owner, '_build_plan_scope', None) is not None:
                raise ProcessingError('Nested native build plan scope')
            self._build_fence(generation)
            self.owner._build_plan_scope = (self.publication_graph.value, generation)
            self.owner._publication_cursor = None
            try:
                yield
            finally:
                self.owner._build_plan_scope = None
                self.owner._publication_cursor = None
            self._build_fence(generation)

    @_stage(None)
    def _build_fence(self, generation):
        """A complete immutable input plan is required before any build traversal."""
        if getattr(self.owner, '_build_plan_scope', None) == (self.graph.value, generation):
            self._check_generation(generation,'pending')
            return
        status = self.fence(generation, "pending")
        sources = next(iter(self.owner.store.query(f"SELECT (COUNT(?source) AS ?count) WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}source> ?source }} }}")))
        if int(sources['count'].value) != status['source_count']:
            raise ProcessingError("Native build source plan is incomplete")
        incomplete = self.owner.store.query(f"SELECT ?source WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}source> ?source . ?source <{P}operationCount> ?expected . OPTIONAL {{ ?source <{P}operation> ?operation }} }} }} GROUP BY ?source ?expected HAVING(COUNT(?operation) != ?expected) LIMIT 1")
        if next(iter(incomplete), None) is not None:
            raise ProcessingError("Native build operation plan is incomplete")

    def query_window(self, generation, scope, after, query, limit, *, streaming=False):
        """One bounded DB cursor over an immutable publication, never result copies."""
        scoped = streaming or getattr(self.owner, '_build_plan_scope', None) == (self.publication_graph.value, generation)
        current = getattr(self.owner, '_publication_cursor', None) if scoped else None
        if scoped:
            self.owner._publication_cursor = None
        stream = (current[2] if current is not None and current[:2] == (scope, after)
                  else iter(self.owner.store.query(query + ('' if scoped else f' LIMIT {limit+1}'))))
        return list(islice(stream, limit+1)), stream

    def retain_window(self, generation, scope, cursor, rows, consumed, stream, *, streaming=False):
        if streaming or getattr(self.owner, '_build_plan_scope', None) == (self.publication_graph.value, generation):
            self.owner._publication_cursor = ((scope, cursor, chain(rows[consumed:], stream))
                                       if cursor is not None else None)

    @_locked
    def build_read(self, generation, record_ids, *, fields=None, max_bytes=MAX_BYTES):
        """Point reads for computation; public consumers still require ready state."""
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        self._build_fence(generation)
        result = self._read(record_ids, fields=fields, max_bytes=max_bytes)
        self._build_fence(generation)
        check_query_cancellation()
        return result

    @_locked
    @_stage(None)
    def build_page(self, generation, *, kind, source=None, after=None, limit=MAX_ROWS,
                   fields=None, max_bytes=MAX_BYTES):
        """Seek projected accepted records directly in native pending membership."""
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        self._build_fence(generation)
        ExtractionRecords._read_options(None if fields == [] else fields, max_bytes)
        if kind not in {"Entity", "Relation", "Mention", "Evidence", "IdentityProfile",
                        "AttributeValue", "AttributeElement", "NativeRange", "Qualifier"}:
            raise ProcessingError("Invalid native build record kind")
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
            raise ProcessingError("Native build page limit must be 1..128")
        source_filter = f"?source <{P}source> {self.scalar(source)} ." if source is not None else ""
        scope = hashlib.sha256(json.dumps([self.project, generation, kind, source, fields],
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        prefix = 'build:' + scope + ':'
        identity = None
        operation_after = None
        if after is not None:
            if not isinstance(after, str) or not after.startswith(prefix):
                raise ProcessingError("Native build cursor belongs to another scope")
            identity = after[len(prefix):]
            self.iri(identity)
            parts = identity.split(':', 4)
            if (len(parts) != 5 or parts[:3] != ['urn', 'semantica', 'extraction']
                    or len(parts[3]) != 64 or any(c not in '0123456789abcdef' for c in parts[3])):
                raise ProcessingError('Invalid native build record cursor')
            operation_after = ':'.join(parts[:4])
        def traverse():
            # A computation traverses its immutable plan once. Re-running a
            # sorted query for every transport page sorts the whole plan again.
            seek = (f"FILTER(STR(?operation) >= {self.scalar(operation_after)})"
                    if operation_after is not None else '')
            operations = self.owner.store.query(f"""
                SELECT DISTINCT ?operation WHERE {{ GRAPH {self.graph} {{
                    {self.head} <{P}source> ?source .
                    ?source <{P}operation> ?operation . {source_filter}
                }} {seek} }} ORDER BY ?operation""")
            while batch := list(islice(operations, MAX_ROWS)):
                check_query_cancellation()
                values = ' '.join(str(item['operation']) for item in batch)
                cursor = f'FILTER(STR(?record) > {self.scalar(identity)})' if identity is not None else ''
                # Push kind selection into native indexes. The join and sort
                # are bounded by one admitted operation window, not the project.
                for item in self.owner.store.query(f'''SELECT ?operation ?record WHERE {{
                    VALUES ?operation {{ {values} }} GRAPH {self.facts} {{
                    ?operation <{F}ownedRecord> ?record . ?record <{RDF_TYPE}> <{F}{kind}> }}
                    {cursor} }} ORDER BY ?record'''):
                    check_query_cancellation()
                    if not item['record'].value.startswith(item['operation'].value + ':'):
                        raise ProcessingError('Native record does not belong to its operation namespace')
                    yield item['record'].value

        scoped = getattr(self.owner, '_build_plan_scope', None) == (self.graph.value, generation)
        current = getattr(self.owner, '_publication_cursor', None) if scoped else None
        stream = current[2] if current is not None and current[:2] == (scope, after) else traverse()
        ids = list(islice(stream, limit + 1))
        selected = ids[:limit]
        records = ([dict(id=identity, fields={}) for identity in selected] if fields == [] else
                   self._read(selected, fields=fields, max_bytes=max_bytes) if selected else [])
        result = dict(records=records, next_cursor=prefix + selected[-1] if len(ids) > limit else None)
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            raise ProcessingError("Native build page exceeds byte budget")
        if scoped:
            # Retain one iterator and one lookahead reference, never result DTOs.
            self.owner._publication_cursor = ((scope, result['next_cursor'], chain(ids[limit:], stream))
                if result['next_cursor'] is not None else None)
        self._build_fence(generation)
        check_query_cancellation()
        return result

    def _read(self, record_ids, *, max_bytes=MAX_BYTES, source_ids=None, fields=None):
        ExtractionRecords._read_options(fields, max_bytes)
        self.batch(record_ids)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ProcessingError("Native read byte budget must be 1..262144")
        result, size = [], 0
        for identity in record_ids:
            node = self.iri(identity)
            self.member(node, source_ids)
            record = dict(id=identity, fields={})
            rows = 0
            predicates = [self.iri(field) for field in fields] if fields is not None else [None]
            for quad in (quad for predicate in predicates
                         for quad in self.owner.store.quads_for_pattern(node, predicate, None, self.facts)):
                rows += 1
                if rows > MAX_ROWS:
                    raise ProcessingError("Native record exceeds field budget")
                value = dict(type="iri" if isinstance(quad.object, self.ox.NamedNode) else "literal", value=quad.object.value)
                if isinstance(quad.object, self.ox.Literal):
                    value["datatype"] = quad.object.datatype.value
                    if quad.object.language is not None:
                        value["language"] = quad.object.language
                size += len(quad.predicate.value.encode()) + len(json.dumps(value, ensure_ascii=False).encode()) + 16
                if size > max_bytes:
                    raise ProcessingError("Native read exceeds byte budget")
                record["fields"].setdefault(quad.predicate.value, []).append(value)
            if not rows and fields is None:
                raise ProcessingError("Native publication record is missing")
            result.append(record)
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            raise ProcessingError("Native read exceeds byte budget")
        return result

    @_stage(None)
    def source_binding(self, generation, source):
        self.fence(generation)
        node = self.ox.NamedNode(self.graph.value + ':source:' + hashlib.sha256(source.encode()).hexdigest())
        if not list(islice(self.owner.store.quads_for_pattern(self.head,self.ox.NamedNode(P+'source'),node,self.graph),1)):
            raise ProcessingError('Source is not a current publication member')
        return {key:self.one(node,key) for key in ('source','material','representation')}

    def _grounded_references(self, position):
        """Seek scalar ranges first, then prove record/evidence share an admitted operation."""
        source=self.scalar(position['source']).value
        member=self.ox.NamedNode(self.graph.value+':source:'+hashlib.sha256(source.encode()).hexdigest())
        seek=self.owner.store.quads_for_pattern
        if not next(seek(self.head,self.iri(P+'source'),member,self.graph),None):
            return
        ref=self.scalar(position['nativeRef'])
        def overlaps(node):
            if not next(seek(node,self.iri(F+'nativeRef'),ref,self.facts),None):
                return False
            bounds=[]
            for field in ('start','end'):
                values=[q.object for q in islice(seek(node,self.iri(F+field),None,self.facts),2)]
                if len(values)!=1 or not isinstance(values[0],self.ox.Literal):
                    raise ProcessingError('Native scalar range bounds missing or duplicated')
                try:
                    bounds.append(int(values[0].value))
                except ValueError:
                    raise ProcessingError('Invalid native scalar range bounds') from None
            return bounds[0]<position['end'] and bounds[1]>position['start']
        for address in seek(None,self.iri(F+'nativeRef'),ref,self.facts):
            check_query_cancellation()
            # Prove source admission before decoding another document's range.
            operations = list(islice((q.subject for q in seek(None,self.iri(F+'ownedRecord'),address.subject,self.facts)
                if next(seek(member,self.iri(P+'operation'),q.subject,self.graph),None)),2))
            if len(operations)>1:
                raise ProcessingError('Native range has multiple admitted owners')
            if not operations or not overlaps(address.subject):
                continue
            for evidence_link in seek(None,self.iri(F+'nativeRange'),address.subject,self.facts):
                evidence=evidence_link.subject
                # Multiple intersecting ranges must still emit the evidence only once.
                if any(q.object.value<address.subject.value and overlaps(q.object)
                    for q in seek(evidence,self.iri(F+'nativeRange'),None,self.facts)):
                    continue
                for field in ('mention','evidence'):
                    for link in seek(None,self.iri(F+field),evidence,self.facts):
                        check_query_cancellation()
                        record=link.subject
                        if field=='evidence' and next(seek(record,self.iri(F+'mention'),evidence,self.facts),None):
                            continue
                        for operation in operations:
                            if (next(seek(operation,self.iri(F+'ownedRecord'),evidence,self.facts),None)
                                    and next(seek(operation,self.iri(F+'ownedRecord'),record,self.facts),None)):
                                yield dict(id=record.value,evidence=evidence.value,source=source)
                                break

    @_stage(None)
    def grounded_candidates(self, generation, positions, *, limit=MAX_ROWS, max_bytes=MAX_BYTES):
        """Exact source/scalar addresses join to native typed observations.

        The bound source membership and nativeRef are storage predicates. No
        document bodies or unscoped graph projection are read or constructed.
        """
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        self.batch(positions)
        if type(limit) is not int or not 1<=limit<=MAX_ROWS or not 1<=max_bytes<=MAX_BYTES:
            raise ProcessingError('Native candidate budget is invalid')
        selected, evidence, sources = [], {}, {}
        for position in positions:
            check_query_cancellation()
            if (set(position)-{'source','nativeRef','start','end','joinBefore'}
                    or not {'source','nativeRef','start','end'}<=set(position)
                    or type(position['start']) is not int or type(position['end']) is not int
                    or not 0<=position['start']<position['end']):
                raise ProcessingError('Native candidate scalar address is invalid')
            self.source_binding(generation,position['source'])
            for row in self._grounded_references(position):
                check_query_cancellation()
                identity, ev=row['id'],row['evidence']
                if identity not in selected:
                    if len(selected)>=limit:
                        raise ProcessingError('Native knowledge candidates require a bounded continuation')
                    selected.append(identity)
                evidence.setdefault(identity,set()).add(ev)
                sources.setdefault(identity,set()).add(position['source'])
        records=self.read(generation,selected,max_bytes=max_bytes) if selected else []
        for item in records:
            item.update(evidenceIds=sorted(evidence[item['id']]),sourceIds=sorted(sources[item['id']]))
        if len(json.dumps(records,ensure_ascii=False).encode())>max_bytes:
            raise ProcessingError('Native candidates exceed byte budget')
        self.fence(generation)
        return records

    @_stage(None)
    def grounded_reference_page(self, generation, position, *, after=None, limit=MAX_ROWS):
        """Maintenance-only, keyset pages of native record/evidence addresses."""
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation, 'pending')
        if (type(limit) is not int or not 1 <= limit <= MAX_ROWS
                or not isinstance(position, dict) or set(position) != {'source','nativeRef','start','end'}
                or type(position['start']) is not int or type(position['end']) is not int
                or not 0 <= position['start'] < position['end']):
            raise ProcessingError('Invalid native grounding page')
        if after is not None:
            if not isinstance(after, (tuple,list)) or len(after) != 2:
                raise ProcessingError('Invalid native grounding cursor')
            after=tuple(self.scalar(item).value for item in after)
        key=lambda item:(item['id'],item['evidence'])
        rows=nsmallest(limit+1,(item for item in self._grounded_references(position)
            if after is None or key(item)>after),key=key)
        values, size = [], 0
        for item in rows:
            check_query_cancellation()
            size += len(json.dumps(item).encode())
            if len(values) == limit or size > MAX_BYTES:
                if not values:
                    raise ProcessingError('Native grounding reference exceeds byte budget')
                self.fence(generation,'pending')
                return dict(items=values,next_cursor=[values[-1]['id'],values[-1]['evidence']])
            values.append(item)
        self.fence(generation,'pending')
        return dict(items=values,next_cursor=None)

    @_stage(None)
    def section_records(self, generation, selection):
        """Page exact native facts intersecting consumer-selected reader ranges."""
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        if not isinstance(selection,dict) or set(selection)-{'sourceId','positions','after','limit','maxBytes'}:
            raise ProcessingError('Invalid native section selection')
        source = selection.get('sourceId')
        self.scalar(source)
        if len(json.dumps(selection,ensure_ascii=False).encode())>MAX_BYTES:
            raise ProcessingError('Native section selection exceeds byte budget')
        self.source_binding(generation,source)
        positions = selection.get('positions')
        self.batch(positions)
        limit,budget = selection.get('limit',MAX_ROWS),selection.get('maxBytes',MAX_BYTES)
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS or type(budget) is not int or not 1 <= budget <= MAX_BYTES:
            raise ProcessingError('Invalid native section budget')
        ranges=[]
        for position in positions:
            if (not isinstance(position,dict) or set(position)!={'nativeRef','start','end'}
                    or type(position['start']) is not int or type(position['end']) is not int
                    or not 0 <= position['start'] < position['end']):
                raise ProcessingError('Invalid native section scalar range')
            ranges.append(f'({self.scalar(position["nativeRef"])} {position["start"]} {position["end"]})')
        cursor=''
        after=selection.get('after')
        if after is not None:
            if not isinstance(after,(tuple,list)) or len(after)!=2:
                raise ProcessingError('Invalid native section cursor')
            a,b=(self.scalar(value) for value in after)
            cursor=f'FILTER(STR(?record)>{a} || (STR(?record)={a} && STR(?evidence)>{b}))'
        member=self.ox.NamedNode(self.graph.value+':source:'+hashlib.sha256(source.encode()).hexdigest())
        query=f'''SELECT DISTINCT ?record ?evidence WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P}source> {member} . {member} <{P}operation> ?operation }}
            GRAPH {self.facts} {{
                VALUES (?ref ?lo ?hi) {{ {' '.join(ranges)} }}
                ?range <{F}nativeRef> ?ref ; <{F}start> ?start ; <{F}end> ?end .
                FILTER(?start < ?hi && ?end > ?lo)
                ?evidence <{F}nativeRange> ?range .
                ?operation <{F}ownedRecord> ?evidence ; <{F}ownedRecord> ?record .
                ?record (<{F}mention>|<{F}evidence>) ?evidence .
            }} {cursor} }} ORDER BY ?record ?evidence LIMIT {limit+1}'''
        response=dict(project=self.project,generation=generation,sourceId=source,records=[],next_cursor=None)
        last=None
        for row in self.owner.store.query(query):
            check_query_cancellation()
            if len(response['records'])==limit:
                response['next_cursor']=last
                break
            record=self.read(generation,[row['record'].value],max_bytes=budget,source_ids=[source])[0]
            record.update(evidenceIds=[row['evidence'].value],sourceIds=[source])
            response['records'].append(record)
            if len(json.dumps(response,ensure_ascii=False).encode())>budget:
                response['records'].pop()
                if last is None:
                    raise ProcessingError('Native section record exceeds byte budget')
                response['next_cursor']=last
                break
            last=[row['record'].value,row['evidence'].value]
        self.fence(generation)
        return response

    @_stage(None)
    def record_binding(self, generation, identity):
        """Resolve one current fact's exact source binding through native membership."""
        self.fence(generation)
        record = self.iri(identity)
        rows = list(self.owner.store.query(f"""SELECT DISTINCT ?source ?material ?representation WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P}source> ?membership .
                ?membership <{P}source> ?source ; <{P}material> ?material ;
                    <{P}representation> ?representation ; <{P}operation> ?operation . }}
            GRAPH {self.facts} {{ ?operation <{F}ownedRecord> {record} }} }} LIMIT 2"""))
        if len(rows) != 1:
            raise ProcessingError("Native record requires one current source binding")
        self.fence(generation)
        return {key: rows[0][key].value for key in ('source', 'material', 'representation')}

    @_stage('identity')
    def _canonical_references(self, node, max_bytes=MAX_BYTES):
        """Collect this complete canonical item under its response byte budget.

        Membership may span many staging pages. Indexed reads stop before
        retaining more than the requested response budget, never at page128.
        """
        from ..semantic_worker_context import check_query_cancellation
        size, members, selectors = 0, [], []
        graph = self.record_graph(node)
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P+'member'), None, graph):
            check_query_cancellation()
            size += len(json.dumps(quad.object.value).encode()) + 2
            if size > max_bytes:
                raise ProcessingError('Canonical read exceeds byte budget')
            members.append(quad.object.value)
        return sorted(members), self._canonical_selectors(node, max_bytes-size)

    @_stage('identity')
    def _canonical_selectors(self, node, max_bytes=MAX_BYTES):
        """Read field decisions only; support membership has its own paged API."""
        from ..semantic_worker_context import check_query_cancellation
        size, selectors = 0, []
        graph = self.record_graph(node)
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P+'selector'), None, graph):
            check_query_cancellation()
            item = dict(field=self.one(quad.object,'field'), record=self.one(quad.object,'record'))
            size += len(json.dumps(item).encode()) + 2
            if size > max_bytes:
                raise ProcessingError('Canonical read exceeds byte budget')
            selectors.append((int(self.one(quad.object,'position')), item))
        return [item for _,item in sorted(selectors,key=lambda value:value[0])]

    def _selected_scene_fields(self, generation, representative, selectors, source_ids):
        """Hydrate native owner's field selections without materializing facts.

        The cache lasts for this one scene item, with joint row/byte limits.
        Attribute selectors remain native references; their bodies are never
        copied into publication metadata or merged into a persisted entity.
        """
        from ..semantic_worker_context import check_query_cancellation
        cache, cache_bytes, read_bytes = {}, 0, 0

        def fields(identity):
            nonlocal cache_bytes, read_bytes
            check_query_cancellation()
            if identity not in cache:
                record = self.read(generation, [identity], max_bytes=MAX_BYTES, source_ids=source_ids)[0]
                size = len(json.dumps(record, ensure_ascii=False).encode())
                read_bytes += size
                if read_bytes > MAX_BYTES:
                    raise ProcessingError('Canonical field hydration exceeds byte budget')
                while cache and (len(cache) >= MAX_ROWS or cache_bytes + size > MAX_BYTES):
                    _, evicted = cache.popitem()
                    cache_bytes -= len(json.dumps(evicted, ensure_ascii=False).encode())
                cache_bytes += len(json.dumps(record['fields'], ensure_ascii=False).encode())
                cache[identity] = record['fields']
            return cache[identity]

        result = {key:list(values) for key, values in fields(representative).items()}
        selected, properties = {}, {}
        for selector in selectors:
            name, identity = selector['field'], selector['record']
            record = fields(identity)
            if name.startswith('properties.') and name[11:]:
                attribute = record.get(F+'attributeName', [])
                if len(attribute) != 1 or attribute[0]['value'] != name[11:]:
                    raise ProcessingError('Canonical property selector differs from native attribute')
                properties.setdefault(name[11:], []).append(dict(type='iri', value=identity))
                continue
            if name in ('name', 'type'):
                predicate = F + ('entityType' if name == 'type' else 'name')
                values = record.get(predicate, [])
            elif name == 'description':
                predicate, values = F+'description', []
                profiles = record.get(F+'identityProfile', [])
                if len(profiles) > 1:
                    raise ProcessingError('Canonical description requires one identity profile')
                if profiles:
                    values = fields(profiles[0]['value']).get(F+'description', [])
                if not values:
                    for reference in record.get(F+'attribute', []):
                        attribute = fields(reference['value'])
                        names = attribute.get(F+'attributeName', [])
                        if len(names) != 1:
                            raise ProcessingError('Canonical attribute requires one native name')
                        if names[0]['value'] == 'description':
                            values = attribute.get(F+'value', [])
                            break
            else:
                raise ProcessingError('Unsupported native canonical field selector')
            if len(values) != 1 or values[0]['type'] != 'literal':
                raise ProcessingError('Canonical field selector requires one native scalar')
            target = selected.setdefault(predicate, [])
            if values[0] not in target:
                target.append(values[0])
            if len(target) != 1:
                raise ProcessingError('Canonical scalar selection has conflicting native values')
        result.update(selected)
        if properties:
            retained = []
            for reference in result.get(F+'attribute', []):
                attribute = fields(reference['value'])
                names = attribute.get(F+'attributeName', [])
                if len(names) != 1:
                    raise ProcessingError('Canonical attribute requires one native name')
                if names[0]['value'] not in properties:
                    retained.append(reference)
            for references in properties.values():
                retained.extend(reference for reference in references if reference not in retained)
            result[F+'attribute'] = retained
        return result

    def _scene_references(self, identities, source_ids=None):
        """Only provenance addresses, scoped through current admitted operations."""
        sources, evidence, retained_bytes = set(), set(), 0
        for offset in range(0, len(identities), MAX_ROWS):
            values = ' '.join(str(self.iri(identity)) for identity in identities[offset:offset+MAX_ROWS])
            scope = ('VALUES ?source { ' + ' '.join(str(self.scalar(s)) for s in source_ids) + ' }') if source_ids else ''
            query = f"""SELECT DISTINCT ?source ?evidence WHERE {{
                VALUES ?record {{ {values} }} {scope}
                GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?membership .
                    ?membership <{P}source> ?source ; <{P}operation> ?operation . }}
                GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record .
                    OPTIONAL {{ {{ ?record <{F}mention> ?evidence }} UNION {{ ?record <{F}evidence> ?evidence }} }} }}
            }}"""
            for row in self.owner.store.query(query):
                for field, retained in (('source', sources), ('evidence', evidence)):
                    if row[field] is not None and row[field].value not in retained:
                        retained_bytes += len(row[field].value.encode()) + 4
                        retained.add(row[field].value)
                if retained_bytes > MAX_BYTES:
                    raise ProcessingError('Native scene provenance exceeds byte budget')
        return sorted(sources), sorted(evidence)

    @_locked
    @_stage(None)
    def source_scene(self, generation, selection, traversal=None):
        """Bounded source membership addresses; no synthetic similarity edges."""
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        self.fence(generation)
        if not isinstance(selection, dict) or set(selection) - {'kind','sourceIds','after','limit','maxBytes'}:
            raise ProcessingError('Invalid source scene selection')
        limit, budget = selection.get('limit', MAX_ROWS), selection.get('maxBytes', MAX_BYTES)
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS or type(budget) is not int or not 1 <= budget <= MAX_BYTES:
            raise ProcessingError('Invalid source scene budget')
        after = selection.get('after')
        if after is not None and (not isinstance(after, str) or not after or len(after) > 1024):
            raise ProcessingError('Invalid source scene cursor')
        cursor = f'FILTER(STR(?source) > {self.scalar(after)})' if after is not None else ''
        selected = selection.get('sourceIds')
        scope = ''
        if selected is not None:
            self.batch(selected)
            if len(set(selected)) != len(selected):
                raise ProcessingError('Duplicate source scene identities')
            scope = 'VALUES ?source { ' + ' '.join(str(self.scalar(source)) for source in selected) + ' }'
        query = f'''SELECT ?source ?material ?representation WHERE {{ GRAPH {self.graph} {{
            {self.head} <{P}source> ?membership . ?membership <{P}source> ?source ;
            <{P}material> ?material ; <{P}representation> ?representation . }} {scope} {cursor}
            }} ORDER BY ?source LIMIT {limit + 1}'''
        rows = traversal.window(self.owner.store, query, limit) if traversal else list(self.owner.store.query(query))
        result = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        for row in rows[:limit]:
            check_query_cancellation()
            item = dict(id=row['source'].value, kind='source', material=row['material'].value,
                representation=row['representation'].value, source_ids=[row['source'].value], evidence_ids=[])
            result['nodes'].append(item)
            if len(json.dumps(dict(result, next_cursor=item['id']), ensure_ascii=False).encode()) > budget:
                result['nodes'].pop()
                if not result['nodes']:
                    raise ProcessingError('Source scene record exceeds byte budget')
                break
        if len(rows) > len(result['nodes']):
            result['next_cursor'] = result['nodes'][-1]['id']
        self.fence(generation)
        return result

    @_locked
    @_stage(None)
    def classification_dimension(self, generation, source, dimension_id=None, **page):
        """Resolve the one current source reduction and one requested dimension."""
        from .classification_records import ClassificationRecords, BINDING as fields
        self.fence(generation)
        self.source_binding(generation, source)
        query = f'''SELECT ?operation ?root WHERE {{ GRAPH {self.graph} {{
            {self.head} <{P}source> ?member . ?member <{P}source> {self.scalar(source)} ;
                <{P}operation> ?operation . }} GRAPH {self.facts} {{
                ?operation <{F}classificationReduction> ?root . }} }} LIMIT 2'''
        rows = list(self.owner.store.query(query))
        if not rows:
            raise ClassificationMissingError('Current source classification reduction is not bound')
        if len(rows) != 1:
            raise ProcessingError('Current source classification reduction duplicated')
        operation, root = rows[0]['operation'], rows[0]['root']
        binding = {}
        for field in fields:
            values = list(islice(self.owner.store.quads_for_pattern(operation,
                self.ox.NamedNode(F + 'binding' + field[0].upper() + field[1:]), None, self.facts), 2))
            if len(values) != 1:
                raise ProcessingError('Classification reduction binding incomplete')
            binding[field] = values[0].object.value
        owner = ClassificationRecords(self.owner, binding)
        if owner.receipt() is None:
            raise ProcessingError('Classification reduction receipt missing')
        result = dict(project=self.project, generation=generation, sourceId=source,
            operationId=operation.value, profileId=owner.one(root, 'profileId'),
            profileVersion=owner.one(root, 'profileVersion'), taxonomyDigest=binding['taxonomy'])
        if dimension_id is None:
            result['dimensionIds'] = sorted(owner.one(node, 'dimensionId') for node in owner.values(root, 'dimension'))
        else:
            result.update(owner.read_reduced_dimension(dimension_id, **page))
        self.fence(generation)
        return result

    @_stage(None)
    def organization_scene(self, generation, selection, traversal=None):
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        limit, budget = selection.get('limit', MAX_ROWS), selection.get('maxBytes', MAX_BYTES)
        if (set(selection)-{'kind','after','limit','maxBytes'} or type(limit) is not int
                or not 1 <= limit <= MAX_ROWS or type(budget) is not int or not 1 <= budget <= MAX_BYTES):
            raise ProcessingError('Invalid native community page')
        after = selection.get('after')
        cursor = f'FILTER(STR(?id) > {self.scalar(after)})' if after is not None else ''
        topic = selection['kind'] == 'topics'
        kind = 'topic' if topic else 'community'
        fields = ('title', 'reportId', 'inputDigest', 'evidenceCount') if topic else ('titleState',)
        projection = ' '.join('?'+field for field in fields)
        patterns = ' '.join(f'?id <{P+field}> ?{field} .' for field in fields)
        query = f'''SELECT ?id ?count {projection} WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P+kind}> ?id .
                ?id <{P}memberCount> ?count . {patterns} }} {cursor}
            }} ORDER BY ?id LIMIT {limit+1}'''
        rows = traversal.window(self.owner.store, query, limit) if traversal else self.owner.store.query(query)
        response = dict(project=self.project,generation=generation,nodes=[],links=[],next_cursor=None)
        for row in rows:
            check_query_cancellation()
            item = dict(id=row['id'].value,kind=kind,memberCount=int(row['count'].value))
            if topic:
                item.update(title=row['title'].value, evidenceCount=int(row['evidenceCount'].value),
                    organization=dict(basis='grounded-overview-section', report_id=row['reportId'].value,
                        input_digest=row['inputDigest'].value, coverage='cited-knowledge-only'))
            else:
                item['titleState'] = row['titleState'].value
            if len(response['nodes']) == limit:
                response['next_cursor'] = response['nodes'][-1]['id']
                break
            response['nodes'].append(item)
            if len(json.dumps(dict(response, next_cursor=item['id']),ensure_ascii=False).encode()) > budget:
                response['nodes'].pop()
                if not response['nodes']:
                    raise ProcessingError('Native organization item exceeds byte budget')
                response['next_cursor'] = response['nodes'][-1]['id']
                break
        self.fence(generation)
        return response

    @_locked
    @_stage(None)
    def stream_members(self, generation, selection, traversal):
        self.fence(generation)
        query = f"""SELECT DISTINCT ?parent ?child WHERE {{ GRAPH {self.graph} {{
            {self.head} (<{P}community>|<{P}topic>) ?parent . ?parent <{P}member> ?child }}
            GRAPH {self.stage_graph('identity')} {{ {self.stage_head('identity')} <{P}canonical> ?child }}
            }} ORDER BY ?parent ?child"""
        rows = traversal.window(self.owner.store, query, selection['limit'])
        result = dict(project=self.project, generation=generation, members=[], next_cursor=None)
        for row in rows[:selection['limit']]:
            item = dict(parent=row['parent'].value, child=row['child'].value)
            candidate = dict(result, members=result['members'] + [item])
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > selection['maxBytes']:
                if not result['members']:
                    raise ProcessingError('Native membership item exceeds byte budget')
                break
            result['members'].append(item)
        # Stream continuation is opaque; no concatenated business-identity cursor.
        result['next_cursor'] = 'more' if len(rows) > len(result['members']) else None
        self.fence(generation)
        return result

    def _scene_projection(self, selection):
        fields = selection.get('fields')
        if 'fields' not in selection:
            return None
        allowed = ([['id'], ['id','name','sourceIds'], ['id','name','entityType'], ['id','name','entityType','sourceIds']] if selection.get('kind') == 'nodes'
                   else [['id','source','target','predicate'], ['id','source','target','predicate','status']] if selection.get('kind') in {'links','incident','topology'} else [])
        if fields not in allowed:
            raise ProcessingError('Invalid native scene field projection')
        return fields

    @_stage('identity')
    def canonical_names(self, identities):
        """Read selected title scalars by exact graph/address, without support joins."""
        self.batch(identities)
        names, size = {}, 0
        for identity in identities:
            node = self.iri(identity)
            if next(self.owner.store.quads_for_pattern(
                    self.stage_head('identity'), self.ox.NamedNode(P+'canonical'),
                    node, self.stage_graph('identity')), None) is None:
                raise ProcessingError('Canonical name selection is missing from current stage')
            value = self._canonical_scalar(node, 'name')
            size += len(identity.encode()) + len(value.encode())
            if size > MAX_BYTES:
                raise ProcessingError('Canonical name hydration exceeds byte budget')
            names[identity] = value
        return names

    @_stage('identity')
    def _canonical_scalar(self, node, field):
        # A completed decision selects fields; graph reads never restore its supports.
        graph = self.record_graph(node)
        chosen, size, count = None, 0, 0
        for link in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P+'selector'), None, graph):
            check_query_cancellation()
            count += 1
            if count > MAX_ROWS:
                raise ProcessingError('Canonical field selection exceeds byte/row budget')
            selector = link.object
            fields = self.values(selector, 'field', graph=graph)
            if len(fields) != 1:
                raise ProcessingError('Canonical field selector missing or duplicated')
            if fields[0].value != field:
                continue
            selected = self.values(selector, 'record', graph=graph)
            if len(selected) != 1:
                raise ProcessingError('Canonical field selection missing or duplicated')
            record = selected[0]
            if next(self.owner.store.quads_for_pattern(
                    node, self.ox.NamedNode(P+'member'), record, graph), None) is None:
                raise ProcessingError('Canonical field selection is missing from membership')
            value = self._native_scalar(record, field)
            if chosen is not None and chosen != value:
                raise ProcessingError('Canonical scalar selection has conflicting native values')
            chosen = value
            size += len(str(selector).encode()) + len(str(value).encode())
            if count > MAX_ROWS or size > MAX_BYTES:
                raise ProcessingError('Canonical field selection exceeds byte/row budget')
        if chosen is None:
            records = self.values(node, 'representative', graph=graph)
            if len(records) != 1:
                raise ProcessingError('Canonical field selection missing or duplicated')
            chosen = self._native_scalar(records[0], field)
        return chosen.value

    def _native_scalar(self, record, field):
        values = list(islice(self.owner.store.quads_for_pattern(
            record, self.ox.NamedNode(F+field), None, self.facts), 2))
        if len(values) != 1 or not isinstance(values[0].object, self.ox.Literal):
            raise ProcessingError('Canonical field selector requires one native scalar')
        return values[0].object

    @_stage('identity')
    def _scene_name(self, node, source_ids):
        # Read only name selectors, not descriptions, attributes or complete membership.
        scope = ''
        if source_ids is not None:
            sources = ' '.join(str(self.scalar(source)) for source in source_ids)
            scope = f"""GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?membership .
                ?membership <{P}source> ?source ; <{P}operation> ?operation . }}
                VALUES ?source {{ {sources} }} GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record }}"""
        query = f"""SELECT DISTINCT ?record WHERE {{ GRAPH {self.graph} {{
            {node} <{P}selector> ?selector . ?selector <{P}field> 'name' ; <{P}record> ?record . }}
            {scope} }} ORDER BY ?record"""
        chosen, read_bytes = None, 0
        def accept(identity):
            nonlocal chosen, read_bytes
            check_query_cancellation()
            record = self._read([identity], fields=[F+'name'], source_ids=source_ids)[0]
            read_bytes += len(json.dumps(record, ensure_ascii=False).encode())
            if read_bytes > MAX_BYTES:
                raise ProcessingError('Canonical name hydration exceeds byte budget')
            names = record['fields'].get(F+'name', [])
            if len(names) != 1 or names[0]['type'] != 'literal':
                raise ProcessingError('Canonical field selector requires one native scalar')
            if chosen is not None and chosen != names[0]:
                raise ProcessingError('Canonical scalar selection has conflicting native values')
            chosen = names[0]
        found = False
        for row in self.owner.store.query(query):
            found = True
            accept(row['record'].value)
        if not found:
            representative = self.one(node, 'representative')
            if source_ids is not None:
                # Match full-scene scoped representative selection without retaining members.
                query = f"""SELECT DISTINCT ?record WHERE {{ GRAPH {self.graph} {{ {node} <{P}member> ?record }}
                    {scope} }} ORDER BY ?record"""
                first = None
                for row in self.owner.store.query(query):
                    check_query_cancellation()
                    identity = row['record'].value
                    if first is None: first = identity
                    if identity == representative:
                        break
                else:
                    representative = first
                if representative is None:
                    raise ProcessingError('Native scene source scope has no member')
            accept(representative)
        return chosen['value']

    @_stage('identity')
    def _scene_sources(self, node, source_ids):
        seek = self.owner.store.quads_for_pattern
        member, owned = self.iri(P+'member'), self.iri(F+'ownedRecord')
        operation, source = self.iri(P+'operation'), self.iri(P+'source')
        selected = set(source_ids) if source_ids is not None else None
        sources, size = set(), 0
        for link in seek(node, member, None, self.graph):
            check_query_cancellation()
            for record in seek(None, owned, link.object, self.facts):
                check_query_cancellation()
                for binding in seek(None, operation, record.subject, self.publication_graph):
                    check_query_cancellation()
                    if next(seek(self.publication_head, source, binding.subject, self.publication_graph), None) is None:
                        continue
                    for value in seek(binding.subject, source, None, self.publication_graph):
                        identity = value.object.value
                        if (selected is not None and identity not in selected) or identity in sources:
                            continue
                        size += len(json.dumps(identity).encode()) + 2
                        if size > MAX_BYTES:
                            raise ProcessingError('Native scene sources exceed byte budget')
                        sources.add(identity)
        return sorted(sources)

    @_locked
    @_stage(None)
    def scene(self, generation, selection, traversal=None):
        """Page the current native canonical references, never assemble a graph.

        Node and visible-link pages have independent stable keysets. Raw RDF
        terms preserve typed fact fields and qualifiers; this is a display
        boundary, not a persisted or independently editable knowledge model.
        """
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        identity_graph, identity_head = self.stage_graph('identity'), self.stage_head('identity')
        fact_graph, fact_head = self.stage_graph('fact'), self.stage_head('fact')
        if not isinstance(selection, dict):
            raise ProcessingError('Invalid native scene selection')
        kind = selection.get('kind')
        projection = self._scene_projection(selection)
        if kind == 'facts':
            return self._fact_cards(generation, selection, traversal)
        if kind == 'sources':
            return self.source_scene(generation, selection, traversal)
        if kind in {'communities', 'topics'}:
            return self.organization_scene(generation, selection, traversal)
        if kind in {'incident','topology'}:
            return self._relation_page(generation, selection, traversal)
        permitted = {'kind','after','limit','maxBytes','fields'} | ({'nodeIds','recordIds','sourceIds','communityId','topicId'} if kind == 'nodes' else {'visibleIds'})
        limit, max_bytes = selection.get('limit', MAX_ROWS), selection.get('maxBytes', MAX_BYTES)
        if (kind not in {'nodes','links'} or set(selection) - permitted
                or type(limit) is not int or not 1 <= limit <= MAX_ROWS
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES):
            raise ProcessingError('Invalid native scene budget or fields')
        after = selection.get('after')
        if after is not None:
            self.iri(after)
        cursor = f'FILTER(STR(?id) > {self.scalar(after)})' if after is not None else ''
        response = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        if projection is not None:
            response['fields'] = projection
        source_ids = None
        if kind == 'nodes':
            exact = selection.get('nodeIds')
            if exact is not None:
                self.batch(exact)
                if after is not None or len(set(exact)) != len(exact):
                    raise ProcessingError('Invalid exact native scene selection')
            source_ids = selection.get('sourceIds')
            source_filter = ''
            community_filter = ''
            if selection.get('communityId') is not None:
                community = self.iri(selection['communityId'])
                community_filter = f'GRAPH {self.publication_graph} {{ {self.publication_head} <{P}community> {community} . {community} <{P}member> ?id }}'
            if selection.get('topicId') is not None:
                topic = self.iri(selection['topicId'])
                community_filter += f'GRAPH {self.publication_graph} {{ {self.publication_head} <{P}topic> {topic} . {topic} <{P}member> ?id }}'
            if source_ids is not None:
                self.batch(source_ids)
                if len(set(source_ids)) != len(source_ids):
                    raise ProcessingError('Duplicate scene source identities')
                source_filter = f'''GRAPH {self.publication_graph} {{ {self.publication_head} <{P}source> ?membership .
                    VALUES ?source {{ {' '.join(str(self.scalar(s)) for s in source_ids)} }}
                    ?membership <{P}source> ?source ; <{P}operation> ?operation . }}
                    {self.canonical_pattern('?id', f'?id <{P}member> ?member')}
                    GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?member }}'''
            exact_filter = ('VALUES ?id { ' + ' '.join(str(self.iri(n)) for n in exact) + ' }') if exact else ''
            records_filter = ''
            if selection.get('recordIds') is not None:
                records = selection['recordIds']
                self.batch(records)
                if len(set(records)) != len(records) or exact is not None:
                    raise ProcessingError('Invalid native member selection')
                records_filter = f'''VALUES ?selectedRecord {{ {' '.join(str(self.iri(r)) for r in records)} }}
                    {{ {self.fact_pattern('?selectedRecord', f'?selectedRecord (<{P}source>|<{P}target>) ?id')} }} UNION {{
                    {self.canonical_pattern('?id', f'?id <{P}member> ?selectedEntity')}
                    GRAPH {self.facts} {{ ?selectedRecord (<{F}sourceEntity>|<{F}targetEntity>)? ?selectedEntity }} }}'''
            query = f'''SELECT DISTINCT ?id WHERE {{ GRAPH {identity_graph} {{
                {identity_head} <{P}canonical> ?id }} {exact_filter} {records_filter} {source_filter} {community_filter} {cursor}
                }} ORDER BY ?id LIMIT {limit + 1}'''
        else:
            visible = selection.get('visibleIds')
            self.batch(visible)
            if len(set(visible)) != len(visible):
                raise ProcessingError('Duplicate visible scene identities')
            nodes = ' '.join(str(self.iri(n)) for n in visible)
            admitted = list(self.owner.store.query(f'''SELECT ?id WHERE {{
                VALUES ?id {{ {nodes} }} GRAPH {identity_graph} {{ {identity_head} <{P}canonical> ?id }}
            }} LIMIT {MAX_ROWS + 1}'''))
            if len(admitted) != len(visible):
                raise ProcessingError('Visible scene identities are outside the current publication')
            query = f'''SELECT DISTINCT ?id ?source ?target WHERE {{
                VALUES ?source {{ {nodes} }} VALUES ?target {{ {nodes} }}
                {self.fact_pattern('?id', f'?id <{P}source> ?source ; <{P}target> ?target .')}
                {cursor} }} ORDER BY ?id LIMIT {limit + 1}'''
        rows = traversal.window(self.owner.store, query, limit) if traversal else list(self.owner.store.query(query))
        if kind == 'nodes' and exact is not None and len(rows) != len(exact):
            raise ProcessingError('Exact scene identities are outside the current source scope or page limit')
        if kind == 'links' and len({row['id'].value for row in rows}) != len(rows):
            raise ProcessingError('Native relation endpoints require unique canonical membership')
        emitted = []
        for row in rows[:limit]:
            check_query_cancellation()
            identity = row['id'].value
            remaining = max_bytes - len(json.dumps(response, ensure_ascii=False).encode())
            if remaining <= 0:
                raise ProcessingError('Native scene envelope exceeds byte budget')
            if kind == 'nodes':
                node = self.iri(identity)
                if projection is not None:
                    item = dict(id=identity)
                    if 'entityType' in projection:
                        item.update(name=self._canonical_scalar(node, 'name'), entityType=self._canonical_scalar(node, 'entityType'))
                        if 'sourceIds' in projection:
                            item['sourceIds'] = self._scene_sources(node, source_ids)
                    elif 'name' in projection:
                        item.update(name=self._scene_name(node, source_ids), sourceIds=self._scene_sources(node, source_ids))
                    target = response['nodes']
                else:
                    representative = self.one(node, 'representative')
                    members, selectors = self._canonical_references(node, remaining)
                    if source_ids is not None:
                        members = [member for member in members if self._scene_references([member], source_ids)[0]]
                        if representative not in members:
                            representative = sorted(members)[0]
                    sources, evidence = self._scene_references(members, source_ids)
                    if source_ids is not None:
                        selectors = [s for s in selectors if self._scene_references([s['record']], source_ids)[0]]
                    fields = self._selected_scene_fields(generation, representative, selectors, source_ids)
                    types = fields.get(RDF_TYPE, [])
                    if len(types) != 1 or types[0]['type'] != 'iri':
                        raise ProcessingError('Native scene entity requires one native type')
                    item = dict(id=identity, type=types[0]['value'],
                        recordId=representative, fields=fields, sourceIds=sources,
                        evidenceIds=evidence, members=members, selectors=selectors)
                    target = response['nodes']
            else:
                item = self._projected_scene_link(row, status='status' in projection) if projection is not None else self._fact_scene_link(generation, row)
                target = response['links']
            target.append(item)
            response['next_cursor'] = identity
            if len(json.dumps(response, ensure_ascii=False).encode()) > max_bytes:
                target.pop()
                if kind == 'nodes' and exact is not None:
                    raise ProcessingError('Exact native scene selection exceeds byte budget')
                if not emitted:
                    raise ProcessingError('Native scene item exceeds byte budget')
                response['next_cursor'] = emitted[-1]
                self.fence(generation)
                return response
            emitted.append(identity)
        response['next_cursor'] = emitted[-1] if len(rows) > limit and emitted else None
        self.fence(generation)
        return response

    @_stage('fact')
    def _fact_cards(self, generation, selection, traversal=None):
        """Project completed decisions only; support membership stays behind its pager."""
        limit, budget = selection.get('limit', MAX_ROWS), selection.get('maxBytes', MAX_BYTES)
        if (set(selection) - {'kind', 'factIds', 'after', 'limit', 'maxBytes'}
                or type(limit) is not int or not 1 <= limit <= MAX_ROWS
                or type(budget) is not int or not 1 <= budget <= MAX_BYTES):
            raise ProcessingError('Invalid native fact card budget or fields')
        exact, after = selection.get('factIds'), selection.get('after')
        if exact is not None:
            self.batch(exact)
            if after is not None or len(set(exact)) != len(exact) or len(exact) > limit:
                raise ProcessingError('Invalid exact native fact selection')
        if after is not None:
            self.iri(after)
        values = 'VALUES ?id { ' + ' '.join(str(self.iri(i)) for i in exact) + ' }' if exact else ''
        cursor = f'FILTER(STR(?id) > {self.scalar(after)})' if after else ''
        query = f"""SELECT DISTINCT ?id ?source ?target WHERE {{
            {values} {self.fact_pattern('?id', f'?id <{P}source> ?source ; <{P}target> ?target .')}
            {cursor} }} ORDER BY ?id"""
        scope = ('scene-facts', self.project, generation)
        if traversal:
            rows = traversal.window(self.owner.store, query, limit)
        elif exact is None:
            rows, stream = self.query_window(generation, scope, after, query, limit, streaming=True)
        else:
            rows = list(self.owner.store.query(query + f' LIMIT {limit + 1}'))
        if len({row['id'].value for row in rows}) != len(rows):
            raise ProcessingError('Native fact endpoints require unique canonical membership')
        if exact is not None and (len(rows) != len(exact) or {r['id'].value for r in rows} != set(exact)):
            raise ProcessingError('Exact fact identities are outside the current publication')
        response = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        names = {}
        endpoints = list(dict.fromkeys(endpoint for row in rows[:limit]
                         for endpoint in (row['source'].value, row['target'].value)))
        for start in range(0, len(endpoints), MAX_ROWS):
            names.update(self.canonical_names(endpoints[start:start + MAX_ROWS]))
        for row in rows[:limit]:
            check_query_cancellation()
            node = self.iri(row['id'].value)
            predicate = self.one(node, 'qualifiedPredicate')
            item = dict(id=node.value, kind='fact', source=row['source'].value, target=row['target'].value,
                        predicate=predicate, status=self.one(node, 'qualifiedAssertionStatus'),
                        label=f"{names[row['source'].value]} {predicate} {names[row['target'].value]}")
            response['nodes'].append(item)
            candidate = dict(response, next_cursor=node.value)
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > budget:
                response['nodes'].pop()
                if exact is not None or not response['nodes']:
                    raise ProcessingError('Native fact cards exceed byte budget')
                response['next_cursor'] = response['nodes'][-1]['id']
                break
        else:
            if len(rows) > limit:
                response['next_cursor'] = response['nodes'][-1]['id']
        self.fence(generation)
        if exact is None and traversal is None:
            self.retain_window(generation, scope, response['next_cursor'], rows, len(response['nodes']), stream, streaming=True)
        return response

    def _relation_page(self, generation, selection, traversal=None):
        """Read topology once, or seek one incident neighborhood; hydrate only selected fields."""
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        projection = self._scene_projection(selection)
        topology=selection.get('kind')=='topology'
        allowed={'kind','after','limit','maxBytes','fields'} | (set() if topology else {'nodeId'})
        if set(selection)-allowed or topology and projection is None:
            raise ProcessingError('Invalid incident selection fields')
        focus = None if topology else self.iri(selection.get('nodeId'))
        maximum=MAX_ROWS if topology else 32
        limit, budget = selection.get('limit', maximum), selection.get('maxBytes', MAX_BYTES)
        if type(limit) is not int or not 1 <= limit <= maximum or type(budget) is not int or not 1 <= budget <= MAX_BYTES:
            raise ProcessingError('Invalid incident selection budget')
        after = selection.get('after')
        if after is not None:
            self.iri(after)
        if focus is not None:
            admitted = self.owner.store.query(f'ASK {{ GRAPH {self.stage_graph("identity")} {{ {self.stage_head("identity")} <{P}canonical> {focus} }} }}')
            if not bool(admitted):
                raise ProcessingError('Incident focus is outside current publication')
        cursor = f'FILTER(STR(?id) > {self.scalar(after)})' if after is not None else ''
        endpoint_filter=f'FILTER(?source = {focus} || ?target = {focus})' if focus is not None else ''
        query = f'''SELECT DISTINCT ?id ?source ?target WHERE {{
            {self.fact_pattern('?id', f'?id <{P}source> ?source ; <{P}target> ?target .')}
            {endpoint_filter} {cursor} }} ORDER BY ?id'''
        scope = ('scene-topology', self.project, generation)
        if traversal:
            rows = traversal.window(self.owner.store, query, limit)
        elif topology:
            rows, stream = self.query_window(generation, scope, after, query, limit, streaming=True)
        else:
            rows = list(self.owner.store.query(query + f' LIMIT {limit + 1}'))
        if len({row['id'].value for row in rows}) != len(rows):
            raise ProcessingError('Native incident endpoints require unique canonical membership')
        response = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        identities = {focus.value} if focus is not None else set()
        if projection is not None:
            response['fields'] = projection
        else:
            response['nodes'] = self.scene(generation, dict(kind='nodes', nodeIds=[focus.value], limit=1, maxBytes=MAX_BYTES))['nodes']
        if len(json.dumps(response, ensure_ascii=False).encode()) > budget:
            raise ProcessingError('Native incident focus exceeds byte budget')
        emitted = []
        for row in rows[:limit]:
            check_query_cancellation()
            if projection is not None:
                link = self._projected_scene_link(row, status='status' in projection)
                missing = []
            else:
                link = self._fact_scene_link(generation, row)
                missing = sorted({row['source'].value, row['target'].value} - identities)
            # Read endpoints individually so a combined exact request cannot exceed
            # its budget before we decide the incident page boundary.
            added = []
            for identity in missing:
                added.extend(self.scene(generation, dict(kind='nodes', nodeIds=[identity], limit=1, maxBytes=MAX_BYTES))['nodes'])
            candidate = dict(response, nodes=response['nodes'] + added, links=response['links'] + [link], next_cursor=link['id'])
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > budget:
                if not emitted:
                    raise ProcessingError('Native incident item exceeds byte budget')
                response['next_cursor'] = emitted[-1]
                self.fence(generation)
                if topology and traversal is None:
                    self.retain_window(generation, scope, response['next_cursor'], rows, len(emitted), stream, streaming=True)
                return response
            response['nodes'].extend(added)
            response['links'].append(link)
            identities.update(missing)
            emitted.append(link['id'])
        response['next_cursor'] = emitted[-1] if len(rows) > limit else None
        self.fence(generation)
        if topology and traversal is None:
            self.retain_window(generation, scope, response['next_cursor'], rows, len(emitted), stream, streaming=True)
        return response

    @_stage(None)
    def page(self, generation, *, source=None, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES, canonical=False):
        self.fence(generation)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ProcessingError("Native read byte budget must be 1..262144")
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
            raise ProcessingError("Native page limit must be 1..128")
        if canonical:
            pattern = f"{self.stage_head('identity')} <{P}canonical> ?record"
        else:
            pattern = f"{self.head} <{P}source> ?source . ?source <{P}operation> ?operation ."
            if source is not None:
                pattern += f"?source <{P}source> {self.scalar(source)} ."
            pattern = f"GRAPH {self.graph} {{ {pattern} }} GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record }}"
        if canonical:
            pattern = f"GRAPH {self.stage_graph('identity')} {{ {pattern} }}"
        cursor = f"FILTER(STR(?record) > {self.scalar(after)})" if after else ""
        ids = [row["record"].value for row in self.owner.store.query(f"SELECT DISTINCT ?record WHERE {{ {pattern} {cursor} }} ORDER BY ?record LIMIT {limit + 1}")]
        selected = ids[:limit]
        if canonical:
            records = []
            for identity in selected:
                node = self.iri(identity)
                remaining = max_bytes - len(json.dumps(records).encode())
                members, selectors = self._canonical_references(node, remaining)
                records.append(dict(id=identity, representative=self.one(node, "representative"),
                    members=members, selectors=selectors))
            if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES or len(json.dumps(records).encode()) > max_bytes:
                raise ProcessingError("Canonical read exceeds byte budget")
        else:
            records = self.read(generation, selected, max_bytes=max_bytes) if selected else []
        self.fence(generation)
        return dict(records=records, next_cursor=selected[-1] if len(ids) > limit else None)
