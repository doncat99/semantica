"""Reference-only contextual candidate connectivity in the native RDF owner."""
import hashlib
import json
from contextlib import contextmanager

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
        self.publication = PublicationRecords(owner, project, stage='identity')

    def build(self, rows, *, resolve_candidates=True, policy_key=None, progress=None):
        """Read native rows once; replay only bounded compact identity features."""
        p = self.publication
        with self.owner._publication_lock, p.build_scope(self.generation):
            p._build_fence(self.generation)
            # Reserve the generation-local stage before writing any index rows.
            # Completion later binds this same graph to the semantic input key.
            if p._pointer(p.publication_head, 'identityGraph', p.publication_graph) is None:
                graph = p.ox.NamedNode(p.publication_graph.value + ':identity')
                self.owner.store.add(p.ox.Quad(p.publication_head,
                    p.ox.NamedNode(P+'identityGraph'), graph, p.publication_graph))
                self.owner.flush()
            p._writable_stage()
            self._policy_key = policy_key
            self._previous_graph = p._pointer(p.publication_head, 'previousIdentityGraph', p.publication_graph)
            prior_graph = self._previous_graph or p.graph
            prior_head = p.ox.NamedNode(prior_graph.value + ':head')
            reusable = bool(p.values(prior_head, 'identityStageInput', graph=prior_graph)) and policy_key is not None
            previous_policy = p.values(prior_head, 'identityDecisionPolicy', graph=prior_graph)
            reuse_features = policy_key is not None and len(previous_policy) == 1 and previous_policy[0].value == policy_key
            reusable = reusable and reuse_features
            local_policy = p.values(p.head, 'identityDecisionPolicy', graph=p.graph)
            reuse_local_features = policy_key is not None and local_policy == [p.scalar(policy_key)]
            self._context = None
            self.owner._update_derived_graph(p.graph, delete='?s ?predicate ?o',
                where=f'''GRAPH {p.graph} {{ ?s ?predicate ?o . VALUES ?predicate {{
                <{P}identityMember> <{P}identityKey> <{P}identityOrdinal>
                <{P}identityIndexSealed> <{P}identityEvidence>
                <{P}identityStageInput> <{P}identityStageCount>
                <{P}identityComponent> <{P}identityKeyComponent>
                <{P}identityParent> <{P}identitySize> <{P}identityRepresentative>
                <{P}identityKeyParent> <{P}identityNextMember> <{P}identityHead> <{P}identityOrdinalMember>
                <{P}identityRootHead> <{P}identityNextRoot> <{P}identityRetained> }} }}''')
            self.owner.flush()
            if not reuse_local_features:
                self.owner._update_derived_graph(p.graph, delete='?s ?predicate ?o',
                    where=f'GRAPH {p.graph} {{ ?s ?predicate ?o . VALUES ?predicate {{ <{P}identityFeatures> <{P}identityDecisionPolicy> }} }}')
            # Reused features still belong to this stage's explicit rule policy.
            if policy_key is not None:
                p.mutate(self.generation, [p.triple(p.head, 'identityDecisionPolicy', p.scalar(policy_key))])
            indexed_rows = rows
            if resolve_candidates:
                schema = self.detector.similarity_calculator.property_schema
                fields = {name for name, spec in schema.items() if spec.get('identity')}
                fields.update(key for name in tuple(fields) for key in schema[name].get('scope', []))
                # Commit compact features to their existing owner, not a second
                # temporary carrier. An unfinished decision does not invalidate
                # an immutable mention's feature under the same rule policy.
                with p.checkpointed(self.generation):
                    for ordinal, (identity, row) in enumerate(rows()):
                        check_query_cancellation()
                        node = p.iri(identity)
                        p.member(node)
                        if p.values(node, 'identityOrdinal'):
                            raise ProcessingError('Duplicate native identity index member')
                        prior = p.values(node, 'identityFeatures', graph=p.graph) if reuse_local_features else []
                        if not prior and reuse_features and prior_graph != p.graph:
                            prior = p.values(node, 'identityFeatures', graph=prior_graph)
                        if prior:
                            if len(prior) != 1:
                                raise ProcessingError('Native identity features are duplicated')
                            feature = json.loads(prior[0].value)
                        else:
                            feature = self.detector.disambiguator.identity_projection(row() if callable(row) else row)
                        feature = {**feature, 'properties': {key: value
                            for key, value in feature.get('properties', {}).items() if key in fields}}
                        payload = json.dumps(feature, ensure_ascii=False, separators=(',', ':'))
                        p.mutate(self.generation, [p.triple(node, 'identityFeatures', p.ox.Literal(payload)),
                            p.triple(p.head, 'identityMember', node),
                            p.triple(node, 'identityOrdinal', p.ox.Literal(ordinal))])
                        if progress is not None:
                            progress(preparedMentions=ordinal+1, preparationPhase='features')

                def indexed_rows():
                    for result in self.owner.store.query(f'''SELECT ?member WHERE {{ GRAPH {p.graph} {{
                        {p.head} <{P}identityMember> ?member .
                        ?member <{P}identityOrdinal> ?ordinal }} }} ORDER BY ?ordinal'''):
                        check_query_cancellation()
                        node = result['member']
                        yield node.value, json.loads(p.one(node, 'identityFeatures'))

                context = NativeIdentityContext(self.owner, p.project, self.generation)
                self._context = context
                with context.resolution_scope(), context.publication.checkpointed(self.generation):
                    self.detector.disambiguator.prepare(lambda: (row for _, row in indexed_rows()),
                        context=context, features_prepared=True)
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
                    where=f'GRAPH {p.publication_graph} {{ {p.publication_head} <{P}generation> {p.scalar(self.generation)} ; <{P}state> "pending" }}')
                p._build_fence(self.generation)
                pending_bytes += size

            def replace(node, predicate, value):
                self.owner._update_derived_graph(p.graph,
                    delete=f'{node} <{P}{predicate}> ?old',
                    insert=p.triple(node, predicate, value),
                    where=f'OPTIONAL {{ GRAPH {p.graph} {{ {node} <{P}{predicate}> ?old }} }}')

            def find(node):
                path = []
                while True:
                    parent = p.iri(p.one(node, 'identityParent'))
                    if parent == node:
                        break
                    path.append(node)
                    node = parent
                for child in path[:-1]:
                    replace(child, 'identityParent', node)
                return node

            for ordinal, (identity, row) in enumerate(indexed_rows()):
                check_query_cancellation()
                p._build_fence(self.generation)
                node = p.iri(identity)
                if callable(row):
                    row = row()
                p.member(node)
                if not next(self.owner.store.quads_for_pattern(node,
                        p.ox.NamedNode(RDF_TYPE), p.ox.NamedNode(F+'Entity'), p.facts), None):
                    raise ProcessingError('Candidate index requires native Entity membership')
                if not resolve_candidates and next(self.owner.store.quads_for_pattern(node,
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
                # Native disjoint sets use union by size and path compression;
                # retain no project-wide Python membership map.
                triples.extend([p.triple(node, 'identityParent', node),
                    p.triple(node, 'identitySize', p.ox.Literal(1)),
                    p.triple(node, 'identityRepresentative', node),
                    p.triple(p.ox.NamedNode(P+'identity-ordinal:'+str(ordinal)),
                             'identityOrdinalMember', node)])
                stage(triples)
                root = node
                for key in keys:
                    digest = hashlib.sha256(json.dumps(key, ensure_ascii=False,
                        separators=(',', ':')).encode()).hexdigest()
                    key_node = p.ox.NamedNode(P+'identity-key:'+digest)
                    stage([p.triple(node, 'identityKey', key_node)])
                    existing = p.values(key_node, 'identityKeyParent')
                    if len(existing) > 1:
                        raise ProcessingError('Native identity key has multiple components')
                    if not existing:
                        stage([p.triple(key_node, 'identityKeyParent', node)])
                        continue
                    other = find(existing[0])
                    root = find(root)
                    if other == root:
                        continue
                    size = int(p.one(root, 'identitySize'))
                    other_size = int(p.one(other, 'identitySize'))
                    representative = p.iri(p.one(root, 'identityRepresentative'))
                    other_rep = p.iri(p.one(other, 'identityRepresentative'))
                    if int(p.one(other_rep, 'identityOrdinal')) < int(p.one(representative, 'identityOrdinal')):
                        representative = other_rep
                    if other_size > size:
                        root, other = other, root
                    replace(other, 'identityParent', root)
                    replace(root, 'identitySize', p.ox.Literal(size + other_size))
                    replace(root, 'identityRepresentative', representative)
                count += 1
                if progress is not None:
                    progress(indexedMentions=count, preparationPhase='candidates')
                pending_rows += 1
                if pending_rows >= MAX_ROWS:
                    checkpoint()
            # Materialize final membership exactly once. Ordered native reads
            # then construct forward links with O(1) retained state per group.
            for result in self.owner.store.query(f"""SELECT ?member WHERE {{ GRAPH {p.graph} {{
                {p.head} <{P}identityMember> ?member }} }}"""):
                member = result['member']
                root = find(member)
                stage([p.triple(member, 'identityComponent',
                                p.iri(p.one(root, 'identityRepresentative')))])
                pending_rows += 1
                if pending_rows >= MAX_ROWS:
                    checkpoint()
            previous_root = previous_member = None
            for result in self.owner.store.query(f"""SELECT ?member ?component ?ordinal WHERE {{
                GRAPH {p.graph} {{ {p.head} <{P}identityMember> ?member .
                    ?member <{P}identityOrdinal> ?ordinal ; <{P}identityComponent> ?component }}
                }} ORDER BY ?component ?ordinal"""):
                member, root = result['member'], result['component']
                if root != previous_root:
                    stage([p.triple(root, 'identityHead', member)])
                else:
                    stage([p.triple(previous_member, 'identityNextMember', member)])
                previous_root, previous_member = root, member
                pending_rows += 1
                if pending_rows >= MAX_ROWS:
                    checkpoint()
            previous_root = None
            for result in self.owner.store.query(f"""SELECT ?member ?ordinal WHERE {{
                GRAPH {p.graph} {{ {p.head} <{P}identityMember> ?member .
                    ?member <{P}identityOrdinal> ?ordinal ; <{P}identityComponent> ?member }}
                }} ORDER BY ?ordinal"""):
                root = result['member']
                stage([p.triple(p.head if previous_root is None else previous_root,
                    'identityRootHead' if previous_root is None else 'identityNextRoot', root)])
                previous_root = root
                pending_rows += 1
                if pending_rows >= MAX_ROWS:
                    checkpoint()
            expected = next(iter(self.owner.store.query(f'''SELECT (COUNT(DISTINCT ?record) AS ?count)
                WHERE {{ GRAPH {p.publication_graph} {{ {p.publication_head} <{P}source> ?source .
                    ?source <{P}operation> ?operation }} GRAPH {p.facts} {{
                    ?operation <{F}ownedRecord> ?record . ?record <{RDF_TYPE}> <{F}Entity> }} }}''')))['count']
            if int(expected.value) != count:
                raise ProcessingError('Native identity candidate index is incomplete')
            self.owner._update_derived_graph(p.graph, delete='?s ?predicate ?o',
                where=f'''GRAPH {p.graph} {{ ?s ?predicate ?o . VALUES ?predicate {{
                    <{P}identityParent> <{P}identitySize> <{P}identityRepresentative>
                    <{P}identityKeyParent> }} }}''')
            self.owner._update_derived_graph(p.graph, delete=f'?member <{P}identityFeatures> ?payload',
                where=f'''GRAPH {p.graph} {{ ?member <{P}identityFeatures> ?payload .
                    FILTER NOT EXISTS {{ {p.head} <{P}identityMember> ?member }} }}''')
            checkpoint()
            p.mutate(self.generation, [p.triple(p.head, 'identityIndexSealed', p.ox.Literal(count))])
            return self._reconcile_decisions(reusable)

    def _group(self, root):
        """Bounded resolver input determines an exact, order-independent group."""
        p = self.publication
        count = xor = total = 0
        for node in self._component_nodes(p.iri(root)):
            payload = p.one(node, 'identityFeatures') if self._context else ''
            if len(payload.encode()) > MAX_BYTES:
                raise ProcessingError('Identity feature exceeds resource budget')
            item = int.from_bytes(hashlib.sha256(json.dumps([node.value,
                hashlib.sha256(payload.encode()).hexdigest()], separators=(',', ':')).encode()).digest(), 'big')
            count += 1
            xor ^= item
            total = (total + item) % (1 << 256)
        digest = hashlib.sha256(json.dumps([self._policy_key, count, xor, total],
            separators=(',', ':')).encode()).hexdigest()
        return p.ox.NamedNode(P+'identity-decision:'+digest)

    def _reconcile_decisions(self, reusable):
        p = self.publication
        previous = self._previous_graph or p.graph
        previous_head = p.ox.NamedNode(previous.value + ':head')
        retained, components = 0, 0
        for quad in self.owner.store.quads_for_pattern(None,
                p.ox.NamedNode(P+'identityComponent'), None, p.graph):
            if quad.subject != quad.object:
                continue
            root, group = quad.subject, self._group(quad.subject.value)
            linked = next(self.owner.store.quads_for_pattern(previous_head,
                p.ox.NamedNode(P+'identityDecisionGroup'), group, previous), None)
            valid = reusable and linked is not None
            decision_graph = p._pointer(group, 'identityDecisionGraph', previous)
            if valid:
                if decision_graph is None:
                    raise ProcessingError('Completed identity group lacks its decision graph')
                dependencies = (json.loads(quad.object.value) for quad in
                    self.owner.store.quads_for_pattern(group,
                        p.ox.NamedNode(P+'identityDecisionDependencies'), None, decision_graph))
                valid = all(self._context is not None and
                    self._context.dependency_digest(field, key) == digest
                    for field, key, digest in dependencies)
            if valid:
                p.mutate(self.generation, [p.triple(root, 'identityRetained', group)])
                p.mutate(self.generation, [p.triple(p.head, 'identityDecisionGroup', group),
                    p.triple(group, 'identityDecisionGraph', decision_graph)])
                for item in self.owner.store.quads_for_pattern(group,
                        p.ox.NamedNode(P+'identityDecisionCanonical'), None, decision_graph):
                    canonical = item.object
                    location = p._pointer(canonical, 'canonicalGraph', previous)
                    if location is None:
                        raise ProcessingError('Completed canonical lacks its decision graph')
                    p.mutate(self.generation, [p.triple(p.head, 'canonical', canonical),
                        p.triple(canonical, 'canonicalGraph', location)])
                    retained += 1
                components += 1
        # Point-scoped deletes keep the publication fence outside the deletion
        # domain. Never use uncorrelated UNION branches with head variables.
        def remove_canonical(canonical):
            self.owner._update_derived_graph(p.graph,
                delete=f'{canonical} ?predicate ?o . ?selector ?sp ?so . {p.head} <{P}canonical> {canonical}',
                where=f"""GRAPH {p.graph} {{ {canonical} ?predicate ?o .
                    OPTIONAL {{ {canonical} <{P}selector> ?selector . ?selector ?sp ?so }} }}""")

        groups = self.owner.store.quads_for_pattern(p.head,
            p.ox.NamedNode(P+'identityDecisionGroup'), None, p.graph)
        for quad in groups:
            group = quad.object
            if next(self.owner.store.quads_for_pattern(None,
                    p.ox.NamedNode(P+'identityRetained'), group, p.graph), None):
                continue
            for canonical in self.owner.store.quads_for_pattern(group,
                    p.ox.NamedNode(P+'identityDecisionCanonical'), None, p.graph):
                remove_canonical(canonical.object)
            self.owner._update_derived_graph(p.graph,
                delete=f'{group} ?predicate ?o . {p.head} <{P}identityDecisionGroup> {group}',
                where=f'GRAPH {p.graph} {{ {group} ?predicate ?o }}')
        # Explicitly rebuild plans without current component dependency metadata.
        for row in self.owner.store.query(f"""SELECT ?canonical WHERE {{ GRAPH {p.graph} {{
                {p.head} <{P}canonical> ?canonical }}
                FILTER NOT EXISTS {{ GRAPH {p.graph} {{ ?root <{P}identityRetained> ?group .
                    ?group <{P}identityDecisionGraph> ?decisionGraph }}
                    GRAPH ?decisionGraph {{ ?group <{P}identityDecisionCanonical> ?canonical }} }} }}"""):
            remove_canonical(row['canonical'])
        self.owner._update_derived_graph(p.graph, delete=f'{p.head} ?predicate ?o',
            where=f'''GRAPH {p.graph} {{ {p.head} ?predicate ?o . VALUES ?predicate {{
                <{P}identityStageInput> <{P}identityStageCount> <{P}canonicalCount> }} }}''')
        self.owner.flush()
        return dict(retained_canonical_count=retained, retained_components=components)

    @contextmanager
    def resolution_scope(self, root):
        self._fence()
        self._active_group = self._group(root)
        context = self._context
        if context is None:
            try:
                yield
            finally:
                self._active_group = None
            return
        p = self.publication
        group = self._active_group
        # A failed unsealed attempt can leave dependency rows, never a usable decision.
        self.owner._update_derived_graph(p.graph,
            delete=f'{group} <{P}identityDecisionDependencies> ?value',
            where=f'GRAPH {p.graph} {{ {group} <{P}identityDecisionDependencies> ?value }}')
        context._dependencies, context._dependency_bytes = {}, 0
        def persist(dependencies):
            p.mutate(self.generation, [p.triple(group, 'identityDecisionDependencies',
                p.ox.Literal(json.dumps([field, key, digest], separators=(',', ':'))))
                for (field, key), digest in dependencies.items()])
        context._dependency_sink = persist
        try:
            with context.resolution_scope(), p.checkpointed(self.generation):
                yield
        finally:
            context._dependencies = context._dependency_sink = None
            context._dependency_bytes = 0
            self._active_group = None

    def seal_component(self, root, canonical_ids):
        p = self.publication
        self._fence()
        group = self._group(root)
        if getattr(self, '_active_group', None) != group:
            raise ProcessingError('Identity component seal requires its resolution scope')
        if self._context is not None:
            self._context.flush_dependencies()
        for offset in range(0, len(canonical_ids), MAX_ROWS):
            triples = []
            for identity in canonical_ids[offset:offset+MAX_ROWS]:
                canonical = p.iri(identity)
                if not next(self.owner.store.quads_for_pattern(p.head,
                        p.ox.NamedNode(P+'canonical'), canonical, p.graph), None):
                    raise ProcessingError('Identity decision references an unstaged canonical')
                triples.append(p.triple(group, 'identityDecisionCanonical', canonical))
            p.mutate(self.generation, triples)
        p.mutate(self.generation, [p.triple(p.head, 'identityDecisionGroup', group),
            p.triple(group, 'identityDecisionGraph', p.graph)])

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
                head, next_predicate = p.head, 'identityNextRoot'
                first = p.values(head, 'identityRootHead')
                member = first[0] if first else None
            else:
                node = p.iri(seed)
                if not next(self.owner.store.quads_for_pattern(p.head,
                        p.ox.NamedNode(P+'identityMember'), node, p.graph), None):
                    raise ProcessingError('Unknown native identity component membership')
                root = p.iri(p.one(node, 'identityComponent'))
                member = p.iri(p.one(root, 'identityHead'))
                next_predicate = 'identityNextMember'
            if position >= 0:
                ordinal_node = p.ox.NamedNode(P+'identity-ordinal:'+str(position))
                prior = p.iri(p.one(ordinal_node, 'identityOrdinalMember'))
                component = p.iri(p.one(prior, 'identityComponent'))
                if component != (prior if seed is None else root):
                    raise ProcessingError('Native identity cursor belongs to another component')
                following = p.values(prior, next_predicate)
                member = following[0] if following else None
            rows = []
            while member is not None and len(rows) <= limit:
                check_query_cancellation()
                ordinal = int(p.one(member, 'identityOrdinal'))
                if ordinal <= position:
                    raise ProcessingError('Invalid native identity member ordering')
                rows.append((ordinal, member.value))
                position = ordinal
                if len(rows) > limit:
                    break
                following = p.values(member, next_predicate)
                member = following[0] if following else None
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
        member = p.iri(p.one(root, 'identityHead'))
        while member is not None:
            check_query_cancellation()
            yield member
            following = p.values(member, 'identityNextMember')
            member = following[0] if following else None

    def roots(self, *, after=None, limit=MAX_ROWS, max_bytes=MAX_BYTES, affected_only=False):
        page = self._page(None, after=after, limit=limit, max_bytes=max_bytes)
        if affected_only:
            p = self.publication
            page['records'] = [root for root in page['records'] if not p.values(p.iri(root), 'identityRetained')]
        return page

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


    def hydrate_component(self, seed, hydrate, *, max_members=None,
                          max_bytes=16*1024*1024):
        """Load one complete semantic unit or fail before resolver/publication.

        Limits cover retained native references and serialized hydrated DTO bytes.
        An explicit member limit is optional; repeated compact mentions are not
        rejected merely because their count exceeds an arbitrary fixed cap.
        They do not assert an RSS bound for the existing resolver's allocations.
        """
        if ((max_members is not None and
                (type(max_members) is not int or max_members < 1))
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
            refs, reference_bytes = [], 0
            for member in self._component_nodes(root):
                # Charge a four-byte Unicode representation plus string/list
                # overhead before retaining each reference. This independent
                # allocation budget leaves the exact DTO byte contract intact.
                reference_bytes += 4*len(member.value) + 128
                if reference_bytes > 16*1024*1024:
                    raise ProcessingError('Native identity component reference byte budget exceeded')
                refs.append(member.value)
                if max_members is not None and len(refs) > max_members:
                    raise ProcessingError('Native identity component record budget exceeded')
        mentions, size = {}, 0
        for ref in refs:
            check_query_cancellation()
            entity = hydrate(ref)
            payload = entity.model_dump(mode='json') if hasattr(entity, 'model_dump') else entity
            size += len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode())
            if size > max_bytes:
                raise ProcessingError('Native identity component byte budget exceeded')
            mentions.setdefault(entity.id if hasattr(entity, 'id') else entity['id'], entity)
        self._fence()
        return refs,mentions

    def read_identity_features(self, reference):
        """Point-read the compact observations already prepared for this index."""
        p = self.publication
        with self.owner._publication_lock:
            self._fence()
            node = p.iri(reference)
            if not next(self.owner.store.quads_for_pattern(p.head,
                    p.ox.NamedNode(P+'identityMember'), node, p.graph), None):
                raise ProcessingError('Unknown native identity component membership')
            payload = p.one(node, 'identityFeatures')
            if len(payload.encode()) > MAX_BYTES:
                raise ProcessingError('Native identity feature exceeds byte budget')
            try:
                feature = json.loads(payload)
            except (ValueError, TypeError) as exc:
                raise ProcessingError('Invalid native identity features') from exc
            if (not isinstance(feature, dict) or '_identity_features' not in feature
                    or 'context' in feature or 'description' in feature):
                raise ProcessingError('Invalid native identity features')
            self._fence()
            return feature

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
                    {p.canonical_pattern('?id', f'?id <{P}member> ?native')}
                    GRAPH {p.graph} {{ ?native <{P}identityEvidence> ?evidence }}"""
            cursor_clause = '' if position is None else f'FILTER(STR(?id) > {p.scalar(position)})'
            window_scope = ('canonical-references', scope)
            rows, stream = p.query_window(self.generation, window_scope, after, f"""SELECT DISTINCT ?id ?representative WHERE {{
                {p.canonical_pattern('?id', f'?id <{P}representative> ?representative')}
                {evidence_clause} {cursor_clause} }} ORDER BY STR(?id)""", limit)
            selected = rows[:limit]
            response = dict(records=[dict(id=row['id'].value,
                representative=row['representative'].value) for row in selected],
                next_cursor=prefix+selected[-1]['id'].value.encode().hex() if len(rows)>limit else None)
            if len(json.dumps(response, ensure_ascii=False).encode()) > max_bytes:
                raise ProcessingError('Native canonical reference page exceeds byte budget')
            p.retain_window(self.generation, window_scope, response['next_cursor'], rows, len(selected), stream)
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
