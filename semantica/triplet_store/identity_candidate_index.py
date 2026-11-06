"""Reference-only contextual candidate connectivity in the native RDF owner."""
import hashlib
import heapq
import json

from ..semantic_worker_context import check_query_cancellation
from ..utils.exceptions import ProcessingError
from .extraction_records import F, RDF_TYPE
from .identity_context import NativeIdentityContext
from .publication_records import MAX_BYTES, MAX_ROWS, P, PublicationRecords


class IdentityCandidateIndex:
    """Index complete candidates; the existing resolver retains merge authority."""

    def __init__(self, owner, project, generation, detector):
        if not detector.contextual_identity:
            raise ProcessingError('Native candidate index requires contextual identity')
        self.owner, self.generation, self.detector = owner, generation, detector
        self.publication = PublicationRecords(owner, project)

    def build(self, rows, *, resolve_candidates=True):
        """Rows reopen as (native Entity IRI, resolver row); no DTOs are retained."""
        p = self.publication
        with self.owner._publication_lock, p.build_scope(self.generation):
            p._build_fence(self.generation)
            self.owner._update_derived_graph(p.graph, delete='?s ?predicate ?o',
                where=f'''GRAPH {p.graph} {{ ?s ?predicate ?o . VALUES ?predicate {{
                <{P}identityMember> <{P}identityKey> <{P}identityOrdinal>
                <{P}identityIndexSealed> <{P}identityEvidence>
                <{P}identityComponent> <{P}identityKeyComponent> }} }}''')
            self.owner.flush()
            if resolve_candidates:
                context = NativeIdentityContext(self.owner, p.project, self.generation)
                with context.resolution_scope(), context.publication.checkpointed(self.generation):
                    self.detector.disambiguator.prepare(lambda: (row for _, row in rows()),
                        context=context)
            count = 0
            pending_rows = pending_bytes = 0

            def checkpoint():
                nonlocal pending_rows, pending_bytes
                check_query_cancellation()
                p._build_fence(self.generation)
                self.owner.flush()
                pending_rows = pending_bytes = 0

            def stage(triples):
                nonlocal pending_bytes
                body = '\n'.join(triples)
                size = len(body.encode())
                if size > MAX_BYTES:
                    raise ProcessingError('Publication atomic write exceeds byte budget')
                if pending_bytes + size > MAX_BYTES:
                    checkpoint()
                check_query_cancellation()
                p._build_fence(self.generation)
                self.owner._update_derived_graph(p.graph, insert=body,
                    where=f'GRAPH {p.graph} {{ {p.head} <{P}generation> {p.scalar(self.generation)} ; <{P}state> "pending" }}')
                p._build_fence(self.generation)
                pending_bytes += size

            for ordinal, (identity, row) in enumerate(rows()):
                check_query_cancellation()
                p._build_fence(self.generation)
                node = p.iri(identity)
                p.member(node)
                if not next(self.owner.store.quads_for_pattern(node,
                        p.ox.NamedNode(RDF_TYPE), p.ox.NamedNode(F+'Entity'), p.facts), None):
                    raise ProcessingError('Candidate index requires native Entity membership')
                if next(self.owner.store.quads_for_pattern(node,
                        p.ox.NamedNode(P+'identityOrdinal'), None, p.graph), None):
                    raise ProcessingError('Duplicate native identity index member')
                triples = [p.triple(p.head, 'identityMember', node),
                           p.triple(node, 'identityOrdinal', p.ox.Literal(ordinal))]
                # Identical logical mentions may have several accepted native
                # references (overlapping windows). Their membership is complete
                # even when the deterministic recipe performs no identity merge.
                evidence = row.get('evidence_ids', [])
                if (not isinstance(evidence, list)
                        or any(not isinstance(value, str) for value in evidence)):
                    raise ProcessingError('Invalid native identity evidence references')
                for offset in range(0, len(evidence), MAX_ROWS):
                    stage([p.triple(node, 'identityEvidence', p.scalar(value))
                        for value in evidence[offset:offset+MAX_ROWS]])
                keys = [('mention', row['id'])]
                if resolve_candidates:
                    keys.extend(self.detector.candidate_keys(row))
                key_nodes = []
                roots = {}
                for key in keys:
                    digest = hashlib.sha256(json.dumps(key, ensure_ascii=False,
                        separators=(',', ':')).encode()).hexdigest()
                    key_node = p.ox.NamedNode(P+'identity-key:'+digest)
                    key_nodes.append(key_node)
                    triples.append(p.triple(node, 'identityKey', key_node))
                    existing = p.values(key_node, 'identityKeyComponent')
                    if len(existing) > 1:
                        raise ProcessingError('Native identity key has multiple components')
                    if existing:
                        root = existing[0]
                        roots[root] = int(p.one(root, 'identityOrdinal'))
                root = min(roots, key=roots.get) if roots else node
                # Materialize connectivity once while constructing the index.
                # Query-time property paths expand dense shared-key groups for
                # every candidate and turn bounded pages into repeated walks.
                for losing in roots:
                    if losing == root:
                        continue
                    rewrite = f'?s ?predicate {root}'
                    if pending_bytes + len(rewrite.encode()) > MAX_BYTES:
                        checkpoint()
                    self.owner._update_derived_graph(p.graph, delete=f'?s ?predicate {losing}',
                        insert=rewrite, where=f'''GRAPH {p.graph} {{ ?s ?predicate {losing} .
                        VALUES ?predicate {{ <{P}identityComponent> <{P}identityKeyComponent> }} }}''')
                    pending_bytes += len(rewrite.encode())
                triples.append(p.triple(node, 'identityComponent', root))
                triples.extend(p.triple(key_node, 'identityKeyComponent', root)
                               for key_node in key_nodes)
                stage(triples)
                count += 1
                pending_rows += 1
                if pending_rows >= MAX_ROWS:
                    checkpoint()
            expected = next(iter(self.owner.store.query(f'''SELECT (COUNT(DISTINCT ?record) AS ?count)
                WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}source> ?source .
                    ?source <{P}operation> ?operation }} GRAPH {p.facts} {{
                    ?operation <{F}ownedRecord> ?record . ?record <{RDF_TYPE}> <{F}Entity> }} }}''')))['count']
            if int(expected.value) != count:
                raise ProcessingError('Native identity candidate index is incomplete')
            checkpoint()
            p.mutate(self.generation, [p.triple(p.head, 'identityIndexSealed', p.ox.Literal(count))])

    def _fence(self):
        check_query_cancellation()
        self.publication._build_fence(self.generation)
        if not self.publication.values(self.publication.head, 'identityIndexSealed'):
            raise ProcessingError('Native identity candidate index is not sealed')

    def _page(self, seed, *, after, limit, max_bytes):
        p = self.publication
        with self.owner._publication_lock:
            self._fence()
            if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
                raise ProcessingError('Native identity page limit must be 1..128')
            if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
                raise ProcessingError('Invalid native identity byte budget')
            scope = hashlib.sha256(json.dumps([p.project, self.generation, seed]).encode()).hexdigest()
            prefix, position = 'identity:'+scope+':', -1
            if after is not None:
                if not isinstance(after, str) or not after.startswith(prefix):
                    raise ProcessingError('Native identity cursor belongs to another scope')
                try:
                    position = int(after[len(prefix):])
                except ValueError as exc:
                    raise ProcessingError('Invalid native identity cursor') from exc
                if position < 0:
                    raise ProcessingError('Invalid native identity cursor')
            if seed is None:
                component = f'?id <{P}identityComponent> ?id .'
            else:
                node = p.iri(seed)
                if not next(self.owner.store.quads_for_pattern(p.head,
                        p.ox.NamedNode(P+'identityMember'), node, p.graph), None):
                    raise ProcessingError('Unknown native identity component membership')
                root = p.iri(p.one(node, 'identityComponent'))
                component = f'?id <{P}identityComponent> {root} .'
            if seed is None:
                rows = [(int(row['ordinal'].value), row['id'].value) for row in
                    self.owner.store.query(f'''SELECT DISTINCT ?id ?ordinal WHERE {{
                    GRAPH {p.graph} {{ {p.head} <{P}identityMember> ?id .
                        ?id <{P}identityOrdinal> ?ordinal . {component}
                        FILTER(?ordinal > {position}) }} }} ORDER BY ?ordinal LIMIT {limit+1}''')]
            else:
                # Read the indexed object binding before looking up ordinals.
                # A SPARQL join may choose the project-wide ordinal index first,
                # repeating a full project walk for every singleton component.
                def candidates():
                    for member in self._component_nodes(root):
                        ordinal = int(p.one(member, 'identityOrdinal'))
                        if ordinal > position:
                            yield ordinal, member.value
                rows = heapq.nsmallest(limit+1, candidates())
            selected = rows[:limit]
            response = dict(records=[identity for _, identity in selected],
                next_cursor=prefix+str(selected[-1][0]) if len(rows)>limit else None)
            if len(json.dumps(response, ensure_ascii=False).encode()) > max_bytes:
                raise ProcessingError('Native identity page exceeds byte budget')
            self._fence()
            return response

    def _component_nodes(self, root):
        """Indexed reverse membership; retain no project-wide candidate set."""
        p = self.publication
        for quad in self.owner.store.quads_for_pattern(None,
                p.ox.NamedNode(P+'identityComponent'), root, p.graph):
            check_query_cancellation()
            if next(self.owner.store.quads_for_pattern(p.head,
                    p.ox.NamedNode(P+'identityMember'), quad.subject, p.graph), None):
                yield quad.subject

    def roots(self, *, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES):
        return self._page(None, after=after, limit=limit, max_bytes=max_bytes)

    def component(self, seed, *, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES):
        return self._page(seed, after=after, limit=limit, max_bytes=max_bytes)

    def iter_components(self, *, max_members=MAX_ROWS):
        """Yield complete components or fail before yielding an oversized group."""
        if type(max_members) is not int or max_members < 1:
            raise ProcessingError('Invalid native identity component budget')
        root_cursor = None
        while True:
            roots = self.roots(after=root_cursor)
            for root in roots['records']:
                members, cursor = [], None
                while True:
                    page = self.component(root, after=cursor, limit=min(MAX_ROWS, max_members+1))
                    members.extend(page['records'])
                    if len(members) > max_members:
                        raise ProcessingError('Native identity component budget exceeded')
                    cursor = page['next_cursor']
                    if cursor is None:
                        break
                yield members
            root_cursor = roots['next_cursor']
            if root_cursor is None:
                break


    def hydrate_component(self, seed, hydrate, *, max_members=4096,
                          max_bytes=16*1024*1024):
        """Load one complete semantic unit or fail before resolver/publication.

        Limits cover input native member count and serialized hydrated DTO bytes.
        They do not assert an RSS bound for the existing resolver's allocations.
        """
        if (type(max_members) is not int or not 1 <= max_members <= 4096
                or type(max_bytes) is not int or not 1 <= max_bytes <= 16*1024*1024):
            raise ProcessingError('Invalid native identity hydration budget')
        p=self.publication
        with self.owner._publication_lock:
            self._fence()
            node=p.iri(seed)
            if not next(self.owner.store.quads_for_pattern(p.head,
                    p.ox.NamedNode(P+'identityMember'),node,p.graph),None):
                raise ProcessingError('Unknown native identity component membership')
            root=p.iri(p.one(node, 'identityComponent'))
            for count, _ in enumerate(self._component_nodes(root), start=1):
                if count > max_members:
                    raise ProcessingError('Native identity component record budget exceeded')
        refs,mentions,cursor,size=[],{},None,0
        while True:
            page=self.component(seed,after=cursor)
            for ref in page['records']:
                entity=hydrate(ref)
                payload=entity.model_dump(mode='json') if hasattr(entity,'model_dump') else entity
                size+=len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())
                if size>max_bytes:
                    raise ProcessingError('Native identity component byte budget exceeded')
                refs.append(ref)
                mentions.setdefault(entity.id if hasattr(entity,'id') else entity['id'],entity)
            cursor=page['next_cursor']
            if cursor is None:
                break
        self._fence()
        return refs,mentions

    def canonical_references(self, *, evidence_ids=None, after=None, limit=MAX_ROWS,
                             max_bytes=MAX_BYTES):
        """Page staged canonical references, optionally touching cited evidence.

        This is an explicit pending-build traversal. Hydration and exact merging
        remain with the existing builder/resolver; this index returns addresses.
        """
        p = self.publication
        with self.owner._publication_lock:
            self._fence()
            if type(limit) is not int or not 1 <= limit <= MAX_ROWS:
                raise ProcessingError('Native canonical page limit must be 1..128')
            if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
                raise ProcessingError('Invalid native canonical byte budget')
            if evidence_ids is not None:
                if (not isinstance(evidence_ids, list) or len(evidence_ids) > MAX_ROWS
                        or any(not isinstance(value, str) for value in evidence_ids)):
                    raise ProcessingError('Invalid native canonical evidence filter')
                evidence_ids = sorted(set(evidence_ids))
            scope = hashlib.sha256(json.dumps([p.project, self.generation,
                evidence_ids], ensure_ascii=False).encode()).hexdigest()
            prefix, position = 'canonical-ref:'+scope+':', None
            if after is not None:
                if not isinstance(after, str) or not after.startswith(prefix):
                    raise ProcessingError('Native canonical cursor belongs to another scope')
                try:
                    position = bytes.fromhex(after[len(prefix):]).decode('utf-8')
                    p.iri(position)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ProcessingError('Invalid native canonical cursor') from exc
            evidence_clause = ''
            if evidence_ids is not None:
                values = ' '.join(str(p.scalar(value)) for value in evidence_ids)
                evidence_clause = f"""VALUES ?evidence {{ {values} }}
                    ?id <{P}member> ?native . ?native <{P}identityEvidence> ?evidence ."""
            cursor_clause = '' if position is None else f'FILTER(STR(?id) > {p.scalar(position)})'
            rows = list(self.owner.store.query(f"""SELECT DISTINCT ?id ?representative WHERE {{
                GRAPH {p.graph} {{ {p.head} <{P}canonical> ?id .
                ?id <{P}representative> ?representative . {evidence_clause}
                {cursor_clause} }} }} ORDER BY STR(?id) LIMIT {limit+1}"""))
            selected = rows[:limit]
            response = dict(records=[dict(id=row['id'].value,
                representative=row['representative'].value) for row in selected],
                next_cursor=prefix+selected[-1]['id'].value.encode().hex() if len(rows)>limit else None)
            if len(json.dumps(response, ensure_ascii=False).encode()) > max_bytes:
                raise ProcessingError('Native canonical reference page exceeds byte budget')
            self._fence()
            return response

    def canonical_reference(self, identity):
        """Return one canonical representative address from the current build."""
        p = self.publication
        with self.owner._publication_lock:
            self._fence()
            node = p.iri(identity)
            p.require_kind(node, 'canonical')
            if not next(self.owner.store.quads_for_pattern(p.head,
                    p.ox.NamedNode(P+'canonical'), node, p.graph), None):
                raise ProcessingError('Unknown native canonical identity')
            values = p.values(node, 'representative')
            if len(values) != 1:
                raise ProcessingError('Native canonical representative is missing or duplicated')
            response = dict(id=identity, representative=values[0].value)
            self._fence()
            return response
