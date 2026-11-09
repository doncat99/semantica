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
from itertools import chain, islice

from ..utils.exceptions import ProcessingError
from ..semantic_worker_context import check_query_cancellation
from ..semantic_extract.types import normalize_fact_predicate
from .extraction_records import BINDING, ExtractionRecords, F, RDF_TYPE, operation_identity

MAX_ROWS = 128
MAX_BYTES = 262144
P = "urn:semantica:publication:"


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


class PublicationRecords:
    def __init__(self, owner, project):
        if not isinstance(project, str) or not project or len(project.encode()) > 4096:
            raise ProcessingError("Invalid publication project")
        self.owner, self.ox, self.project = owner, owner._oxigraph, project
        digest = hashlib.sha256(project.encode()).hexdigest()
        self.graph = self.ox.NamedNode(P + digest)
        self.facts = self.ox.NamedNode("urn:semantica:project:" + digest)
        self.head = self.ox.NamedNode(self.graph.value + ":head")

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
        result = []
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P + field), None, graph or self.graph):
            result.append(quad.object)
            if len(result) > MAX_ROWS:
                raise ProcessingError("Publication field exceeds 128 references")
        return result

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
                for quad in self.owner.store.quads_for_pattern(node,predicate,None,graph or self.graph):
                    values=result[node][field]
                    size+=len(str(quad.object).encode())
                    if len(values)>=MAX_ROWS or size>MAX_BYTES:
                        raise ProcessingError('Publication field page exceeds byte or row budget')
                    values.append(quad.object)
        return result

    def qualified_members(self, *, decision):
        """Final native support adjacency; no intermediate view entries exist."""
        self.decision_identity(decision)
        yield from self.owner.store.quads_for_pattern(decision,self.ox.NamedNode(P+'member'),None,self.graph)

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
        if not self.values(self.head, "generation"):
            return None
        result = dict(project=self.project, generation=self.one(self.head, "generation"),
                      state=self.one(self.head, "state"), source_count=int(self.one(self.head, "sourceCount")),
                      canonical_count=(int(self.one(self.head, "canonicalCount"))
                          if self.values(self.head, "canonicalCount") else None), indexes={})
        if result["state"] == "ready":
            for kind in ("keyword", "semantic"):
                node = self.iri(self.one(self.head, kind))
                identity = {key: self.one(node, key) for key in ("kind", "store_id", "recipe_digest")}
                if self.values(node, "space_id"):
                    identity["space_id"] = self.one(node, "space_id")
                result["indexes"][kind] = identity
        return result

    def fence(self, generation, state="ready"):
        status = self.status()
        if status is None or status["generation"] != generation or status["state"] != state:
            raise ProcessingError("Publication generation stale or not " + state)
        return status

    def _check_generation(self, generation, state):
        if self.one(self.head,'generation')!=generation or self.one(self.head,'state')!=state:
            raise ProcessingError('Publication generation stale or not '+state)

    def triple(self, node, field, value):
        return f"{node} <{P + field}> {value} ."

    @_locked
    def mutate(self, generation, triples, *, state="pending"):
        body = "\n".join(triples)
        if len(body.encode()) > MAX_BYTES:
            raise ProcessingError("Publication atomic write exceeds byte budget")
        check_query_cancellation()
        self.fence(generation, state)
        checkpoint = getattr(self, '_checkpoint', None)
        if checkpoint is not None:
            if checkpoint['generation'] != generation or state != 'pending':
                raise ProcessingError('Publication checkpoint generation changed')
        self.owner._update_derived_graph(self.graph, insert=body, where=f"GRAPH {self.graph} {{ {self.head} <{P}generation> {self.scalar(generation)} ; <{P}state> {self.scalar(state)} . }}")
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
        # One stage-wide import; _TripleStream bounds Python's current window.
        # The caller commits completion metadata only after this stream succeeds.
        with io.BufferedReader(_TripleStream(batches)) as stream:
            self.owner.store.bulk_load(input=stream,format=self.ox.RdfFormat.N_TRIPLES,to_graph=self.graph)
        self._build_fence(generation)

    def require_kind(self, node, kind):
        other_kinds={self.ox.NamedNode(P+other) for other in
            {'canonical', 'community', 'topic', 'fact'} - {kind}}
        # Seek roles pointing to this address once, rather than probing each role.
        for count,link in enumerate(self.owner.store.quads_for_pattern(self.head,None,node,self.graph),1):
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
    def begin(self, *, expected_generation, source_count, canonical_count):
        if self.owner.path is None:
            raise ProcessingError("Publication requires persistent Oxigraph")
        if any(type(n) is not int or n < 0 or n > 1000000 for n in (source_count, *([canonical_count] if canonical_count is not None else []))):
            raise ProcessingError("Invalid publication counts")
        current = self.status()
        if (current or {}).get("generation") != expected_generation:
            raise ProcessingError("Publication CAS conflict")
        generation = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        triples = [self.triple(self.head, k, self.ox.Literal(v)) for k, v in dict(
            generation=generation, state="pending", sourceCount=source_count).items()]
        if canonical_count is not None:
            triples.append(self.triple(self.head, "canonicalCount", self.ox.Literal(canonical_count)))
        guard = (f"GRAPH {self.graph} {{ {self.head} <{P}generation> {self.scalar(expected_generation)} }}" if expected_generation is not None
                 else f"FILTER NOT EXISTS {{ GRAPH {self.graph} {{ {self.head} <{P}generation> ?generation }} }}")
        # Completed identity decisions are immutable references independent of
        # publication generation. Keep them in place while replacing all other
        # derived output; incomplete stages are discarded atomically.
        reusable = (len(self.values(self.head, 'identityStageInput')) == 1
                    and len(self.values(self.head, 'identityStageCount')) == 1
                    and len(self.values(self.head, 'identityIndexSealed')) == 1)
        # Fact decisions own their input and dirty markers independently. A later
        # interrupted identity attempt must not erase that completed/partial work.
        selections = [self._fact_selection('?s','?p')]
        if reusable:
            selections.append(self._identity_selection('?s', '?p'))
        discard = 'FILTER(!(' + ' || '.join(selections) + '))' if selections else ''
        self.owner._update_derived_graph(self.graph, delete="?s ?p ?o", insert=" ".join(triples),
            where=f"{guard} OPTIONAL {{ GRAPH {self.graph} {{ ?s ?p ?o }} {discard} }}")
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
        layout=self.values(self.head,'qualifiedIndexLayout')
        if layout==[self.ox.Literal('native-single-fact-decisions')]:
            return
        if layout or any(self.values(self.head,field) for field in
                ('qualifiedIndexSealed','factStageInput','qualifiedEntry','qualifiedPartitionNode')):
            raise ProcessingError('Obsolete qualified index requires explicit offline reset')

    @_locked
    def fact_stage_status(self, generation, input_key, *, functional_predicates=()):
        self.fence(generation,'pending')
        self.scalar(input_key)
        self.require_qualified_layout()
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
    def reset_fact_stage(self,generation):
        self.fence(generation,'pending')
        self.owner._update_derived_graph(self.graph,delete='?s ?p ?o',
            where=f'GRAPH {self.graph} {{ ?s ?p ?o }} FILTER({self._fact_selection("?s","?p")})')
        self.owner.flush()

    @_locked
    def identity_stage_status(self, generation, input_key):
        """Point-read a complete decision stage; never restore or audit entities."""
        self.fence(generation, 'pending')
        self.scalar(input_key)
        values = self.values(self.head, 'identityStageInput')
        if not values:
            return None
        if len(values) != 1:
            raise ProcessingError('Invalid native identity completion marker')
        if values[0].value != input_key:
            return None
        if not self.values(self.head, 'identityIndexSealed'):
            raise ProcessingError('Native identity completion lacks sealed index')
        return dict(input_key=input_key,
                    canonical_count=int(self.one(self.head, 'identityStageCount')))

    @_locked
    def reset_identity_stage(self, generation):
        """Invalidate only identity output after an explicit dependency mismatch."""
        self.fence(generation, 'pending')
        self.owner._update_derived_graph(self.graph, delete='?s ?predicate ?o',
            where=f"""GRAPH {self.graph} {{ ?s ?predicate ?o }}
                FILTER({self._identity_selection('?s', '?predicate')} ||
                    (?s = {self.head} && ?predicate = <{P}canonicalCount>))""")
        self.owner.flush()
        self.fence(generation, 'pending')

    @_locked
    def seal_identity_stage(self, generation, input_key):
        """Commit completion only after every decision reference is durable."""
        self.fence(generation, 'pending')
        self.scalar(input_key)
        if self.values(self.head, 'identityStageInput'):
            raise ProcessingError('Native identity stage already sealed')
        if not self.values(self.head, 'identityIndexSealed'):
            raise ProcessingError('Native identity candidate index is not sealed')
        for field, count in [('member', 'memberCount'), ('selector', 'selectorCount')]:
            incomplete = self.owner.store.query(f"""SELECT ?canonical WHERE {{ GRAPH {self.graph} {{
                {self.head} <{P}canonical> ?canonical . ?canonical <{P+count}> ?expected .
                OPTIONAL {{ ?canonical <{P+field}> ?ref }} }} }} GROUP BY ?canonical ?expected
                HAVING(COUNT(?ref) != ?expected) LIMIT 1""")
            if next(iter(incomplete), None) is not None:
                raise ProcessingError('Canonical identity '+field+' plan is incomplete')
        member, canonical = self.ox.NamedNode(P+'member'), self.ox.NamedNode(P+'canonical')
        for mention in self.owner.store.quads_for_pattern(
                self.head, self.ox.NamedNode(P+'identityMember'), None, self.graph):
            check_query_cancellation()
            # Reverse member lookup avoids joining every canonical for each mention.
            if not any(next(self.owner.store.quads_for_pattern(
                    self.head, canonical, reference.subject, self.graph), None) is not None
                    for reference in self.owner.store.quads_for_pattern(
                        None, member, mention.object, self.graph)):
                raise ProcessingError('Canonical identity membership coverage is incomplete')
        count = int(next(iter(self.owner.store.query(f"""SELECT (COUNT(?canonical) AS ?count)
            WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> ?canonical }} }}""")))['count'].value)
        self.mutate(generation, [self.triple(self.head, 'identityStageInput', self.scalar(input_key)),
            self.triple(self.head, 'identityStageCount', self.ox.Literal(count))])
        return count

    @_locked
    def seal_canonical_count(self, generation, count):
        """Seal the output count after streaming computation, before activation."""
        self.fence(generation, "pending")
        if type(count) is not int or not 0 <= count <= 1000000:
            raise ProcessingError("Invalid canonical publication count")
        if self.values(self.head, "canonicalCount"):
            raise ProcessingError("Canonical publication count already sealed")
        actual = next(iter(self.owner.store.query(f"SELECT (COUNT(?record) AS ?count) WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> ?record }} }}")))["count"]
        if int(actual.value) != count:
            raise ProcessingError("Canonical publication count does not match staged records")
        self.mutate(generation, [self.triple(self.head, "canonicalCount", self.ox.Literal(count))])

    @staticmethod
    def batch(values):
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_ROWS:
            raise ProcessingError("Publication batch must contain 1..128 records")

    def verify_operation(self, identity, source):
        """Verify native completion and source binding; offline maintenance calls audit."""
        operation = self.iri(identity)
        for field, expected in dict(project=self.project, **{k: source[k] for k in ("source", "material", "representation")}).items():
            predicate = self.ox.NamedNode(F + "binding" + field[0].upper() + field[1:])
            actual = list(islice(self.owner.store.quads_for_pattern(operation, predicate, None, self.facts), 2))
            if len(actual) != 1 or actual[0].object.value != expected:
                raise ProcessingError("Publication operation belongs to another source or binding")
        classification = identity.startswith("urn:semantica:classification:")
        if classification:
            from .classification_records import BINDING as classification_fields, ClassificationRecords
        binding = {}
        for field in classification_fields if classification else BINDING:
            predicate = self.ox.NamedNode(F + "binding" + field[0].upper() + field[1:])
            values = list(islice(self.owner.store.quads_for_pattern(operation, predicate, None, self.facts), 2))
            if len(values) != 1:
                raise ProcessingError("Publication operation binding incomplete")
            binding[field] = int(values[0].object.value) if field in {"window_start", "window_end"} else values[0].object.value
        stage = None
        if not classification:
            stages = list(islice(self.owner.store.quads_for_pattern(operation, self.ox.NamedNode(F + "extractionStage"), None, self.facts), 2))
            if len(stages) != 1 or stages[0].object.value not in {"entities", "relations"}:
                raise ProcessingError("Publication extraction requires offline identity migration")
            stage = stages[0].object.value
        records = ClassificationRecords(self.owner, binding) if classification else ExtractionRecords(self.owner, binding, stage) if stage else None
        if records is None or records.operation.value != identity or records.receipt() is None:
            raise ProcessingError("Publication operation has no valid native receipt")
        return records

    @_locked
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
            for identity in source["operations"]:
                operation = self.iri(identity)
                # Admission validates the owner's accepted receipt, not merely
                # its binding labels or row count. A dangling or corrupted paid
                # contribution must never become a current publication.
                self.verify_operation(identity, source)
                triples.append(self.triple(source_node, "operation", operation))
        self.mutate(generation, triples)

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
            selected = {self.ox.NamedNode(self.graph.value + ":source:" + hashlib.sha256(source.encode()).hexdigest()) for source in source_ids}
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
                for binding in self.owner.store.quads_for_pattern(None, operation, owned.subject, self.graph):
                    check_query_cancellation()
                    if selected is not None and binding.subject not in selected:
                        continue
                    if next(self.owner.store.quads_for_pattern(self.head, source, binding.subject, self.graph), None) is not None:
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
                if not list(islice(self.owner.store.quads_for_pattern(self.head, self.ox.NamedNode(P+'canonical'), member, self.graph), 1)):
                    raise ProcessingError('Community member is not a current canonical entity')
                triples.append(self.triple(node, 'member', member))
        self.mutate(generation, triples)

    @_locked
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
                        if not list(islice(self.owner.store.quads_for_pattern(self.head, self.ox.NamedNode(P+'canonical'), ref, self.graph), 1)):
                            raise ProcessingError('Topic member is not a current canonical entity')
                    else:
                        self.member(ref)
                        if not any(list(islice(self.owner.store.quads_for_pattern(ref, self.ox.NamedNode(RDF_TYPE), self.ox.NamedNode(F+kind), self.facts), 1))
                                for kind in ('Evidence', 'Mention')):
                            raise ProcessingError('Topic reference is not native evidence')
                    triples.append(self.triple(node, field, ref))
        self.mutate(generation, triples)


    @_locked
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
        rows = list(self.owner.store.query(f'SELECT ?member WHERE {{ GRAPH {self.graph} {{ {node} <{P}member> ?member }} {cursor} }} ORDER BY ?member LIMIT {limit+1}'))
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

    def _fact_scene_link(self, generation, row):
        identity = row["id"].value
        node = self.iri(identity)
        representative = self.one(node, "representative")
        record = self.read(generation, [representative], max_bytes=MAX_BYTES)[0]
        # Provenance is a bounded display projection. Large fact support is
        # retained in RDF and must be requested through a bounded member page.
        query = f"""SELECT DISTINCT ?source ?evidence WHERE {{
            GRAPH {self.graph} {{ {node} <{P}member> ?record .
                {self.head} <{P}source> ?membership .
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
    def activate(self, generation, *, indexes):
        status = self.fence(generation, "pending")
        if status["canonical_count"] is None:
            raise ProcessingError("Canonical publication count is not sealed")
        if not isinstance(indexes, dict) or set(indexes) != {"keyword", "semantic"}:
            raise ProcessingError("Publication requires both native indexes")
        triples = []
        for kind, identity in indexes.items():
            required = {"kind", "store_id", "recipe_digest"} | ({"space_id"} if kind == "semantic" else set())
            if not isinstance(identity, dict) or set(identity) != required:
                raise ProcessingError("Incomplete native index receipt")
            node = self.ox.NamedNode(self.graph.value + ":index:" + kind)
            triples.append(self.triple(self.head, kind, node))
            triples.extend(self.triple(node, field, self.scalar(value)) for field, value in identity.items())
        for field, expected in (("source", status["source_count"]), ("canonical", status["canonical_count"])):
            count = next(iter(self.owner.store.query(f"SELECT (COUNT(?record) AS ?count) WHERE {{ GRAPH {self.graph} {{ {self.head} <{P + field}> ?record }} }}")))["count"]
            if int(count.value) != expected:
                raise ProcessingError("Publication staged record count is incomplete")
        incomplete = self.owner.store.query(f"SELECT ?source WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}source> ?source . ?source <{P}operationCount> ?expected . OPTIONAL {{ ?source <{P}operation> ?operation }} }} }} GROUP BY ?source ?expected HAVING(COUNT(?operation) != ?expected) LIMIT 1")
        if next(iter(incomplete), None) is not None:
            raise ProcessingError("Publication source operation plan is incomplete")
        for field,count,label in (('member','memberCount','membership'),('selector','selectorCount','selector')):
            incomplete=self.owner.store.query(f'SELECT ?canonical WHERE {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> ?canonical . ?canonical <{P+count}> ?expected . OPTIONAL {{ ?canonical <{P+field}> ?ref }} }} }} GROUP BY ?canonical ?expected HAVING(COUNT(?ref) != ?expected) LIMIT 1')
            if next(iter(incomplete),None) is not None:
                raise ProcessingError('Canonical '+label+' plan is incomplete')
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
        incomplete = self.owner.store.query(f"""SELECT ?fact WHERE {{ GRAPH {self.graph} {{
            {self.head} <{P}fact> ?fact . ?fact <{P}memberCount> ?expected .
            OPTIONAL {{ ?fact <{P}member> ?member }} }} }}
            GROUP BY ?fact ?expected HAVING(COUNT(?member) != xsd:integer(?expected)) LIMIT 1""",
            prefixes={"xsd": "http://www.w3.org/2001/XMLSchema#"})
        if next(iter(incomplete), None) is not None:
            raise ProcessingError("Canonical fact membership plan is incomplete")
        invalid = self.owner.store.query(f"""ASK {{ GRAPH {self.graph} {{
            {self.head} <{P}fact> ?fact . ?fact <{P}representative> ?representative .
            FILTER NOT EXISTS {{ ?fact <{P}member> ?representative }} }} }}""")
        if bool(invalid):
            raise ProcessingError("Canonical fact representative is not a member")
        invalid_member = self.owner.store.query(f"""ASK {{ GRAPH {self.graph} {{
            {self.head} <{P}fact> ?fact . ?fact <{P}member> ?relation }}
            FILTER NOT EXISTS {{ GRAPH {self.facts} {{
                ?operation <{F}ownedRecord> ?relation . ?relation <{RDF_TYPE}> <{F}Relation> }}
                GRAPH {self.graph} {{ {self.head} <{P}source> ?sourceOwner .
                    ?sourceOwner <{P}operation> ?operation }} }} }}""")
        if bool(invalid_member):
            raise ProcessingError("Canonical fact member is outside the current publication")
        duplicate_member = self.owner.store.query(f"""ASK {{ GRAPH {self.graph} {{
            {self.head} <{P}fact> ?left, ?right . ?left <{P}member> ?relation .
            ?right <{P}member> ?relation . FILTER(?left != ?right) }} }}""")
        if bool(duplicate_member):
            raise ProcessingError("Native Relation belongs to multiple canonical facts")
        relation_scope = f"""GRAPH {self.graph} {{ {self.head} <{P}source> ?membership .
            ?membership <{P}operation> ?operation }} GRAPH {self.facts} {{
            ?operation <{F}ownedRecord> ?relation . ?relation <{RDF_TYPE}> <{F}Relation> }}"""
        owned_count = next(iter(self.owner.store.query(f"SELECT (COUNT(DISTINCT ?relation) AS ?count) WHERE {{ {relation_scope} }}")))["count"]
        # The production fact owner admits owned relations with unique assignment;
        # the check above verifies each fact's actual membership count. Their sum
        # therefore proves exact coverage without joining every relation again.
        planned_count = next(iter(self.owner.store.query(f"""SELECT (COALESCE(SUM(xsd:integer(?expected)), 0) AS ?count) WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P}fact> ?fact .
                ?fact <{P}memberCount> ?expected }} }}""", prefixes={"xsd": "http://www.w3.org/2001/XMLSchema#"})))["count"]
        check_query_cancellation()
        if int(owned_count.value) != int(planned_count.value):
            raise ProcessingError("Canonical fact coverage is incomplete")
        body = " ".join(triples)
        self.owner._update_derived_graph(self.graph, delete=f"{self.head} <{P}state> 'pending'", insert=f"{self.head} <{P}state> 'ready' . {body}", where=f"GRAPH {self.graph} {{ {self.head} <{P}generation> {self.scalar(generation)} ; <{P}state> 'pending' }}")
        self.owner.flush()
        return self.fence(generation)

    @_locked
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
            self.owner._build_plan_scope = (self.graph.value, generation)
            try:
                yield
            finally:
                self.owner._build_plan_scope = None
            self._build_fence(generation)

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
    def build_page(self, generation, *, kind, source=None, after=None, limit=MAX_ROWS,
                   fields=None, max_bytes=MAX_BYTES):
        """Seek projected accepted records directly in native pending membership."""
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        self._build_fence(generation)
        ExtractionRecords._read_options(fields, max_bytes)
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
        ids = []
        inclusive = identity is not None
        # Native record IRIs extend their operation IRI; preserve lexical order
        # while sorting only bounded operation pages and one operation's records.
        while len(ids) <= limit:
            check_query_cancellation()
            seek = (f"FILTER(STR(?operation) {'>=' if inclusive else '>'} {self.scalar(operation_after)})"
                    if operation_after is not None else '')
            operations = [row['operation'] for row in self.owner.store.query(f"""
                SELECT DISTINCT ?operation WHERE {{ GRAPH {self.graph} {{
                    {self.head} <{P}source> ?source .
                    ?source <{P}operation> ?operation . {source_filter}
                }} {seek} }} ORDER BY ?operation LIMIT {MAX_ROWS}""")]
            if not operations:
                break
            for operation in operations:
                check_query_cancellation()
                cursor = f"FILTER(STR(?record) > {self.scalar(identity)})" if identity is not None else ''
                query = f"""SELECT DISTINCT ?record WHERE {{ GRAPH {self.facts} {{
                    {operation} <{F}ownedRecord> ?record .
                    ?record <{RDF_TYPE}> <{F}{kind}> }} {cursor}
                }} ORDER BY ?record LIMIT {limit + 1 - len(ids)}"""
                records = [row['record'].value for row in self.owner.store.query(query)]
                if any(not record.startswith(operation.value + ':') for record in records):
                    raise ProcessingError('Native record does not belong to its operation namespace')
                ids.extend(records)
                if len(ids) > limit:
                    break
            if len(ids) > limit or len(operations) < MAX_ROWS:
                break
            operation_after = operations[-1].value
            inclusive = False
        selected = ids[:limit]
        records = self._read(selected, fields=fields, max_bytes=max_bytes) if selected else []
        result = dict(records=records, next_cursor=prefix + selected[-1] if len(ids) > limit else None)
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            raise ProcessingError("Native build page exceeds byte budget")
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

    def source_binding(self, generation, source):
        self.fence(generation)
        node = self.ox.NamedNode(self.graph.value + ':source:' + hashlib.sha256(source.encode()).hexdigest())
        if not list(islice(self.owner.store.quads_for_pattern(self.head,self.ox.NamedNode(P+'source'),node,self.graph),1)):
            raise ProcessingError('Source is not a current publication member')
        return {key:self.one(node,key) for key in ('source','material','representation')}

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
            member = self.ox.NamedNode(self.graph.value+':source:'+hashlib.sha256(position['source'].encode()).hexdigest())
            query=f'''SELECT DISTINCT ?record ?evidence WHERE {{
                GRAPH {self.graph} {{ {member} <{P}operation> ?operation }}
                GRAPH {self.facts} {{
                    ?range <{F}nativeRef> {self.scalar(position['nativeRef'])} ; <{F}start> ?start ; <{F}end> ?end .
                    FILTER(?start < {position['end']} && ?end > {position['start']})
                    ?evidence <{F}nativeRange> ?range .
                    ?operation <{F}ownedRecord> ?evidence ; <{F}ownedRecord> ?record .
                    {{ ?record <{F}mention> ?evidence }} UNION {{ ?record <{F}evidence> ?evidence }}
                }} }} LIMIT {limit+1}'''
            for row in self.owner.store.query(query):
                check_query_cancellation()
                identity, ev=row['record'].value,row['evidence'].value
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

    def grounded_reference_page(self, generation, position, *, after=None, limit=MAX_ROWS):
        """Maintenance-only, keyset pages of native record/evidence addresses."""
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation, 'pending')
        if (type(limit) is not int or not 1 <= limit <= MAX_ROWS
                or not isinstance(position, dict) or set(position) != {'source','nativeRef','start','end'}
                or type(position['start']) is not int or type(position['end']) is not int
                or not 0 <= position['start'] < position['end']):
            raise ProcessingError('Invalid native grounding page')
        member = self.ox.NamedNode(self.graph.value+':source:'+hashlib.sha256(position['source'].encode()).hexdigest())
        cursor = ''
        if after is not None:
            if not isinstance(after, (tuple,list)) or len(after) != 2:
                raise ProcessingError('Invalid native grounding cursor')
            a,b = (self.scalar(item) for item in after)
            cursor = f'FILTER(STR(?record) > {a} || (STR(?record) = {a} && STR(?evidence) > {b}))'
        query=f'''SELECT DISTINCT ?record ?evidence WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P}source> {member} . {member} <{P}operation> ?operation }}
            GRAPH {self.facts} {{
                ?range <{F}nativeRef> {self.scalar(position['nativeRef'])} ; <{F}start> ?start ; <{F}end> ?end .
                FILTER(?start < {position['end']} && ?end > {position['start']})
                ?evidence <{F}nativeRange> ?range .
                ?operation <{F}ownedRecord> ?evidence ; <{F}ownedRecord> ?record .
                ?record (<{F}mention>|<{F}evidence>) ?evidence .
            }} {cursor} }} ORDER BY ?record ?evidence LIMIT {limit+1}'''
        values, size = [], 0
        for row in self.owner.store.query(query):
            check_query_cancellation()
            item = dict(id=row['record'].value,evidence=row['evidence'].value,source=position['source'])
            size += len(json.dumps(item).encode())
            if len(values) == limit or size > MAX_BYTES:
                if not values:
                    raise ProcessingError('Native grounding reference exceeds byte budget')
                self.fence(generation,'pending')
                return dict(items=values,next_cursor=[values[-1]['id'],values[-1]['evidence']])
            values.append(item)
        self.fence(generation,'pending')
        return dict(items=values,next_cursor=None)

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

    def _canonical_references(self, node, max_bytes=MAX_BYTES):
        """Collect this complete canonical item under its response byte budget.

        Membership may span many staging pages. Indexed reads stop before
        retaining more than the requested response budget, never at page128.
        """
        from ..semantic_worker_context import check_query_cancellation
        size, members, selectors = 0, [], []
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P+'member'), None, self.graph):
            check_query_cancellation()
            size += len(json.dumps(quad.object.value).encode()) + 2
            if size > max_bytes:
                raise ProcessingError('Canonical read exceeds byte budget')
            members.append(quad.object.value)
        for quad in self.owner.store.quads_for_pattern(node, self.ox.NamedNode(P+'selector'), None, self.graph):
            check_query_cancellation()
            item = dict(field=self.one(quad.object,'field'), record=self.one(quad.object,'record'))
            size += len(json.dumps(item).encode()) + 2
            if size > max_bytes:
                raise ProcessingError('Canonical read exceeds byte budget')
            selectors.append((int(self.one(quad.object,'position')), item))
        return sorted(members), [item for _,item in sorted(selectors,key=lambda value:value[0])]

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
                GRAPH {self.graph} {{ {self.head} <{P}source> ?membership .
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
    def source_scene(self, generation, selection):
        """Bounded source membership addresses; no synthetic similarity edges."""
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        self.fence(generation)
        if not isinstance(selection, dict) or set(selection) - {'kind','after','limit','maxBytes'}:
            raise ProcessingError('Invalid source scene selection')
        limit, budget = selection.get('limit', MAX_ROWS), selection.get('maxBytes', MAX_BYTES)
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS or type(budget) is not int or not 1 <= budget <= MAX_BYTES:
            raise ProcessingError('Invalid source scene budget')
        after = selection.get('after')
        if after is not None and (not isinstance(after, str) or not after or len(after) > 1024):
            raise ProcessingError('Invalid source scene cursor')
        cursor = f'FILTER(STR(?source) > {self.scalar(after)})' if after is not None else ''
        query = f'''SELECT ?source ?material ?representation WHERE {{ GRAPH {self.graph} {{
            {self.head} <{P}source> ?membership . ?membership <{P}source> ?source ;
            <{P}material> ?material ; <{P}representation> ?representation . }} {cursor}
            }} ORDER BY ?source LIMIT {limit + 1}'''
        rows = list(self.owner.store.query(query))
        result = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        for row in rows[:limit]:
            check_query_cancellation()
            item = dict(id=row['source'].value, kind='source', material=row['material'].value,
                representation=row['representation'].value, source_ids=[row['source'].value], evidence_ids=[])
            result['nodes'].append(item)
            if len(json.dumps(result, ensure_ascii=False).encode()) > budget:
                result['nodes'].pop()
                if not result['nodes']:
                    raise ProcessingError('Source scene record exceeds byte budget')
                break
        if len(rows) > len(result['nodes']):
            result['next_cursor'] = result['nodes'][-1]['id']
        self.fence(generation)
        return result

    @_locked
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
        if len(rows) != 1:
            raise ProcessingError('Current source classification reduction missing or duplicated')
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
            profileVersion=owner.one(root, 'profileVersion'))
        if dimension_id is None:
            result['dimensionIds'] = sorted(owner.one(node, 'dimensionId') for node in owner.values(root, 'dimension'))
        else:
            result.update(owner.read_reduced_dimension(dimension_id, **page))
        self.fence(generation)
        return result

    def organization_scene(self, generation, selection):
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
        rows = self.owner.store.query(f'''SELECT ?id ?count {projection} WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P+kind}> ?id .
                ?id <{P}memberCount> ?count . {patterns} }} {cursor}
            }} ORDER BY ?id LIMIT {limit+1}''')
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
            if len(json.dumps(response,ensure_ascii=False).encode()) > budget:
                response['nodes'].pop()
                if not response['nodes']:
                    raise ProcessingError('Native organization item exceeds byte budget')
                response['next_cursor'] = response['nodes'][-1]['id']
                break
        self.fence(generation)
        return response

    def _scene_projection(self, selection):
        fields = selection.get('fields')
        if 'fields' not in selection:
            return None
        allowed = ([['id'], ['id','name','sourceIds']] if selection.get('kind') == 'nodes'
                   else [['id','source','target','predicate']] if selection.get('kind') == 'incident' else [])
        if fields not in allowed:
            raise ProcessingError('Invalid native scene field projection')
        return fields

    def _scene_name(self, node, source_ids):
        # Read only name selectors, not descriptions, attributes or complete membership.
        scope = ''
        if source_ids is not None:
            sources = ' '.join(str(self.scalar(source)) for source in source_ids)
            scope = f"""GRAPH {self.graph} {{ {self.head} <{P}source> ?membership .
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

    def _scene_sources(self, node, source_ids):
        scope = ('VALUES ?source { ' + ' '.join(str(self.scalar(s)) for s in source_ids) + ' }') if source_ids else ''
        query = f"""SELECT DISTINCT ?source WHERE {{ GRAPH {self.graph} {{
            {node} <{P}member> ?record . {self.head} <{P}source> ?membership .
            ?membership <{P}source> ?source ; <{P}operation> ?operation . }}
            {scope} GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record }} }} ORDER BY ?source"""
        sources, size = [], 0
        for row in self.owner.store.query(query):
            check_query_cancellation()
            source = row['source'].value
            size += len(json.dumps(source).encode()) + 2
            if size > MAX_BYTES:
                raise ProcessingError('Native scene sources exceed byte budget')
            sources.append(source)
        return sources

    @_locked
    def scene(self, generation, selection):
        """Page the current native canonical references, never assemble a graph.

        Node and visible-link pages have independent stable keysets. Raw RDF
        terms preserve typed fact fields and qualifiers; this is a display
        boundary, not a persisted or independently editable knowledge model.
        """
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        if not isinstance(selection, dict):
            raise ProcessingError('Invalid native scene selection')
        kind = selection.get('kind')
        projection = self._scene_projection(selection)
        if kind == 'sources':
            return self.source_scene(generation, selection)
        if kind in {'communities', 'topics'}:
            return self.organization_scene(generation, selection)
        if kind == 'incident':
            return self._incident(generation, selection)
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
                community_filter = f'GRAPH {self.graph} {{ {self.head} <{P}community> {community} . {community} <{P}member> ?id }}'
            if selection.get('topicId') is not None:
                topic = self.iri(selection['topicId'])
                community_filter += f'GRAPH {self.graph} {{ {self.head} <{P}topic> {topic} . {topic} <{P}member> ?id }}'
            if source_ids is not None:
                self.batch(source_ids)
                if len(set(source_ids)) != len(source_ids):
                    raise ProcessingError('Duplicate scene source identities')
                source_filter = f'''GRAPH {self.graph} {{ {self.head} <{P}source> ?membership .
                    VALUES ?source {{ {' '.join(str(self.scalar(s)) for s in source_ids)} }}
                    ?membership <{P}source> ?source ; <{P}operation> ?operation .
                    ?id <{P}member> ?member . }}
                    GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?member }}'''
            exact_filter = ('VALUES ?id { ' + ' '.join(str(self.iri(n)) for n in exact) + ' }') if exact else ''
            records_filter = ''
            if selection.get('recordIds') is not None:
                records = selection['recordIds']
                self.batch(records)
                if len(set(records)) != len(records) or exact is not None:
                    raise ProcessingError('Invalid native member selection')
                records_filter = f'''VALUES ?selectedRecord {{ {' '.join(str(self.iri(r)) for r in records)} }}
                    {{ GRAPH {self.graph} {{ {self.head} <{P}fact> ?selectedRecord .
                        ?selectedRecord (<{P}source>|<{P}target>) ?id }} }} UNION {{
                    GRAPH {self.graph} {{ ?id <{P}member> ?selectedEntity }}
                    GRAPH {self.facts} {{ ?selectedRecord (<{F}sourceEntity>|<{F}targetEntity>)? ?selectedEntity }} }}'''
            query = f'''SELECT DISTINCT ?id WHERE {{ GRAPH {self.graph} {{
                {self.head} <{P}canonical> ?id }} {exact_filter} {records_filter} {source_filter} {community_filter} {cursor}
                }} ORDER BY ?id LIMIT {limit + 1}'''
        else:
            visible = selection.get('visibleIds')
            self.batch(visible)
            if len(set(visible)) != len(visible):
                raise ProcessingError('Duplicate visible scene identities')
            nodes = ' '.join(str(self.iri(n)) for n in visible)
            admitted = list(self.owner.store.query(f'''SELECT ?id WHERE {{
                VALUES ?id {{ {nodes} }} GRAPH {self.graph} {{ {self.head} <{P}canonical> ?id }}
            }} LIMIT {MAX_ROWS + 1}'''))
            if len(admitted) != len(visible):
                raise ProcessingError('Visible scene identities are outside the current publication')
            query = f'''SELECT DISTINCT ?id ?source ?target WHERE {{
                VALUES ?source {{ {nodes} }} VALUES ?target {{ {nodes} }}
                GRAPH {self.graph} {{ {self.head} <{P}fact> ?id .
                    ?id <{P}source> ?source ; <{P}target> ?target . }}
                {cursor} }} ORDER BY ?id LIMIT {limit + 1}'''
        rows = list(self.owner.store.query(query))
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
                    if 'name' in projection:
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
                item = self._fact_scene_link(generation, row)
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

    def _incident(self, generation, selection):
        """Seek incident native relations and only their canonical endpoints."""
        from ..semantic_worker_context import check_query_cancellation
        self.fence(generation)
        projection = self._scene_projection(selection)
        if set(selection) - {'kind', 'nodeId', 'after', 'limit', 'maxBytes', 'fields'}:
            raise ProcessingError('Invalid incident selection fields')
        focus = self.iri(selection.get('nodeId'))
        limit, budget = selection.get('limit', 32), selection.get('maxBytes', MAX_BYTES)
        if type(limit) is not int or not 1 <= limit <= 32 or type(budget) is not int or not 1 <= budget <= MAX_BYTES:
            raise ProcessingError('Invalid incident selection budget')
        after = selection.get('after')
        if after is not None:
            self.iri(after)
        admitted = self.owner.store.query(f'ASK {{ GRAPH {self.graph} {{ {self.head} <{P}canonical> {focus} }} }}')
        if not bool(admitted):
            raise ProcessingError('Incident focus is outside current publication')
        cursor = f'FILTER(STR(?id) > {self.scalar(after)})' if after is not None else ''
        query = f'''SELECT DISTINCT ?id ?source ?target WHERE {{
            GRAPH {self.graph} {{ {self.head} <{P}fact> ?id .
                ?id <{P}source> ?source ; <{P}target> ?target . }}
            FILTER(?source = {focus} || ?target = {focus})
            {cursor} }} ORDER BY ?id LIMIT {limit + 1}'''
        rows = list(self.owner.store.query(query))
        if len({row['id'].value for row in rows}) != len(rows):
            raise ProcessingError('Native incident endpoints require unique canonical membership')
        response = dict(project=self.project, generation=generation, nodes=[], links=[], next_cursor=None)
        identities = {focus.value}
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
                representative = self.one(self.iri(row['id'].value), 'representative')
                record = self._read([representative], fields=[F+'predicateName'])[0]
                predicates = record['fields'].get(F+'predicateName', [])
                if len(predicates) != 1 or predicates[0]['type'] != 'literal':
                    raise ProcessingError('Native relation predicate missing or duplicated')
                link = dict(id=row['id'].value, source=row['source'].value, target=row['target'].value,
                            predicate=normalize_fact_predicate(predicates[0]['value']))
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
                return response
            response['nodes'].extend(added)
            response['links'].append(link)
            identities.update(missing)
            emitted.append(link['id'])
        response['next_cursor'] = emitted[-1] if len(rows) > limit else None
        self.fence(generation)
        return response

    def page(self, generation, *, source=None, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES, canonical=False):
        self.fence(generation)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ProcessingError("Native read byte budget must be 1..262144")
        if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
            raise ProcessingError("Native page limit must be 1..128")
        if canonical:
            pattern = f"{self.head} <{P}canonical> ?record"
        else:
            pattern = f"{self.head} <{P}source> ?source . ?source <{P}operation> ?operation ."
            if source is not None:
                pattern += f"?source <{P}source> {self.scalar(source)} ."
            pattern = f"GRAPH {self.graph} {{ {pattern} }} GRAPH {self.facts} {{ ?operation <{F}ownedRecord> ?record }}"
        if canonical:
            pattern = f"GRAPH {self.graph} {{ {pattern} }}"
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
