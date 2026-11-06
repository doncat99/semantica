"""Reference-only native partitions for the current qualified-fact owner."""
import hashlib
import json

from ..conflicts.conflict_detector import ConflictDetector
from ..semantic_extract.types import normalize_fact_predicate
from ..semantic_artifact_schema import KnowledgeAssertion, KnowledgeRelation
from ..semantic_worker_context import check_query_cancellation
from ..utils.exceptions import ProcessingError
from .publication_records import MAX_BYTES, MAX_ROWS, P, PublicationRecords
from .extraction_records import F, RDF_TYPE, ExtractionRecords


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()


class QualifiedFactIndex:
    """Partition references; ConflictDetector remains the only semantic reducer.

    A partition contains every object and polarity for a subject, predicate and
    identical remaining qualifiers. Both existing conflict rules are therefore
    local to a complete partition, including matching relation references.
    """

    def __init__(self, owner, project, generation):
        self.owner, self.generation = owner, generation
        self.publication = PublicationRecords(owner, project)

    @staticmethod
    def partition(item, kind):
        if kind not in {'assertion', 'relation'}:
            raise ProcessingError('Unknown qualified fact kind')
        subject, predicate = ((item['subject_id'], item['predicate']) if kind == 'assertion'
            else (item['source_entity_id'], item['type']))
        return _digest([subject, predicate,
            {key:value for key,value in item['qualifiers'].items() if key != 'polarity'}])

    def _fence(self, sealed=True):
        check_query_cancellation()
        p = self.publication
        p._build_fence(self.generation)
        if sealed and not p.values(p.head, 'qualifiedIndexSealed'):
            raise ProcessingError('Native qualified fact index is not sealed')

    def build(self, rows):
        """Consume (native relation IRI, kind, DTO); retain reference keys only."""
        p = self.publication
        with self.owner._publication_lock:
            self._fence(False)
            # The current generation's index is rebuilt explicitly, never mixed
            # with a partial previous attempt.
            self.owner.store.update(f'''DELETE {{ GRAPH {p.graph} {{ ?entry ?field ?value }} }}
                WHERE {{ GRAPH {p.graph} {{ ?entry ?field ?value . VALUES ?field {{
                <{P}qualifiedEntry> <{P}qualifiedPartition> <{P}qualifiedReference>
                <{P}qualifiedKind> <{P}qualifiedObservation> <{P}qualifiedIdentity>
                <{P}qualifiedIndexSealed> <{P}qualifiedSubject> <{P}qualifiedEvidence> <{P}qualifiedPredicate> <{P}qualifiedRepresentation> <{P}qualifiedReconciledStatus> }} }} }}''')
            self.owner.flush()
            count = 0
            pending, pending_ids, pending_bytes = [], set(), 0
            def flush():
                nonlocal pending, pending_ids, pending_bytes
                if pending:
                    self._fence(False)
                    p.mutate(self.generation,pending)
                    pending, pending_ids, pending_bytes = [], set(), 0
            for reference, kind, item in rows:
                self._fence(False)
                native = p.iri(reference)
                p.member(native)
                if not next(self.owner.store.quads_for_pattern(native, p.ox.NamedNode(RDF_TYPE),
                        p.ox.NamedNode(F+'Relation'), p.facts), None):
                    raise ProcessingError('Qualified index requires a native Relation')
                identity = ConflictDetector.qualified_fact_identity(p.project, item, kind)
                # The accepted identity projection owns the builder representation
                # identity; the extraction binding carries only its input revision.
                endpoints=list(self.owner.store.quads_for_pattern(native,
                    p.ox.NamedNode(F+'sourceEntity'),None,p.facts))
                if len(endpoints)!=1 or not isinstance(endpoints[0].object,p.ox.NamedNode):
                    raise ProcessingError('Native qualified source identity missing')
                source=endpoints[0].object
                records=ExtractionRecords.from_identity_reference(self.owner,p.project,source.value)
                _,one,_=records._read_identity_projection_fields(source)
                representation=one(source,'buildRepresentationId')
                entry = p.iri(P+'qualified-entry:'+_digest([reference, kind, item['id']]))
                if entry.value in pending_ids or p.values(entry, 'qualifiedReference'):
                    raise ProcessingError('Duplicate qualified fact observation')
                triples = [
                    p.triple(p.head, 'qualifiedEntry', entry),
                    p.triple(entry, 'qualifiedPartition', p.scalar(self.partition(item,kind))),
                    p.triple(entry, 'qualifiedReference', p.iri(reference)),
                    p.triple(entry, 'qualifiedKind', p.scalar(kind)),
                    p.triple(entry, 'qualifiedObservation', p.scalar(item['id'])),
                    p.triple(entry, 'qualifiedIdentity', p.scalar(identity)),
                    p.triple(entry,'qualifiedRepresentation',p.scalar(representation)),
                    p.triple(entry,'qualifiedPredicate',p.scalar(item['predicate'] if kind=='assertion' else item['type'])),
                    p.triple(entry, 'qualifiedSubject', p.scalar(item['subject_id'] if kind=='assertion' else item['source_entity_id'])),
                    *[p.triple(entry, 'qualifiedEvidence', p.scalar(value)) for value in item['evidence_ids']]]
                size=len('\n'.join(triples).encode())
                if size>MAX_BYTES:
                    raise ProcessingError('Publication atomic write exceeds byte budget')
                if pending and (len(pending_ids)>=MAX_ROWS or pending_bytes+1+size>MAX_BYTES):
                    flush()
                pending_bytes+=size+(1 if pending else 0)
                pending.extend(triples)
                pending_ids.add(entry.value)
                count += 1
            flush()
            self._fence(False)
            p.mutate(self.generation, [p.triple(p.head, 'qualifiedIndexSealed', p.ox.Literal(count))])

    def _partitions(self):
        p, after = self.publication, ''
        while True:
            with self.owner._publication_lock:
                self._fence()
                page = list(self.owner.store.query(f'''SELECT DISTINCT ?partition WHERE {{
                    GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> ?entry .
                        ?entry <{P}qualifiedPartition> ?partition .
                        FILTER(STR(?partition) > {p.ox.Literal(after)}) }}
                    }} ORDER BY ?partition LIMIT {MAX_ROWS}'''))
            for row in page:
                yield row['partition'].value
            if len(page) < MAX_ROWS:
                return
            after = page[-1]['partition'].value

    def _references(self, partition):
        p, after = self.publication, ''
        while True:
            with self.owner._publication_lock:
                self._fence()
                page = list(self.owner.store.query(f'''SELECT ?entry ?reference ?kind ?observation ?identity WHERE {{
                    GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> ?entry .
                        ?entry <{P}qualifiedPartition> {p.scalar(partition)} ;
                        <{P}qualifiedReference> ?reference ; <{P}qualifiedKind> ?kind ;
                        <{P}qualifiedObservation> ?observation ; <{P}qualifiedIdentity> ?identity .
                        FILTER(STR(?entry) > {p.ox.Literal(after)}) }}
                    }} ORDER BY ?entry LIMIT {MAX_ROWS}'''))
            size = 0
            for row in page:
                value = {key:row[key].value for key in ('reference','kind','observation','identity')}
                size += len(json.dumps(value,ensure_ascii=False).encode())
                if size > MAX_BYTES:
                    raise ProcessingError('Native qualified reference page byte budget exceeded')
                yield value
            if len(page) < MAX_ROWS:
                return
            after = page[-1]['entry'].value

    def canonical_endpoints(self, reference):
        """Read the unique current canonical membership of two native endpoints."""
        p=self.publication
        with self.owner._publication_lock:
            self._fence(False)
            p.member(p.iri(reference))
            rows=list(self.owner.store.query(f"""SELECT ?source ?target WHERE {{
                GRAPH {p.facts} {{ {p.iri(reference)} <{F}sourceEntity> ?s ; <{F}targetEntity> ?t }}
                GRAPH {p.graph} {{ {p.head} <{P}canonical> ?source, ?target .
                    ?source <{P}member> ?s . ?target <{P}member> ?t }}
                }} LIMIT 2"""))
            if len(rows)!=1:
                raise ProcessingError('Native fact requires unique canonical endpoint membership')
            return rows[0]['source'].value,rows[0]['target'].value

    def fact_members(self, identity, representative, read):
        """Read one already bounded canonical group, preserving oracle representative."""
        p=self.publication
        self._fence()
        partition=self.partition(representative,'relation')
        members=[]
        selected=None
        for row in self._references(partition):
            if row['kind']!='relation' or row['identity']!=identity:
                continue
            ref=row['reference']
            members.append(ref)
            value=read(ref,'relation',row['observation'])
            if value==representative and selected is None:
                selected=ref
        if not members or selected is None:
            raise ProcessingError('Native canonical fact support or representative missing')
        return list(dict.fromkeys(members)),selected

    def iter_reconciled(self, read, *, functional_predicates=(),
                        max_group_records=4096, max_group_bytes=16*1024*1024):
        """Yield complete oracle results; oversized partitions fail explicitly.

        `read(native_reference, kind, observation_id)` must reread the same
        current native observation and canonical endpoint binding. Limits are
        enforced before a partition can produce any semantic output.
        """
        if any(type(value) is not int or value < 1 for value in (max_group_records,max_group_bytes)):
            raise ProcessingError('Invalid qualified fact group budget')
        p = self.publication
        functional_predicates = tuple(functional_predicates)
        for partition in self._partitions():
            yield self._reconcile_partition(partition,read,functional_predicates,
                max_group_records,max_group_bytes)

    def _reconcile_partition(self,partition,read,functional_predicates=(),
                             max_group_records=4096,max_group_bytes=16*1024*1024):
        p=self.publication
        assertions, relations, size, count = [], [], 0, 0
        for row in self._references(partition):
            count += 1
            if count > max_group_records:
                raise ProcessingError('Native qualified fact group record budget exceeded')
            self._fence()
            item = read(row['reference'], row['kind'], row['observation'])
            size += len(json.dumps(item, ensure_ascii=False, separators=(',',':')).encode())
            if size > max_group_bytes:
                raise ProcessingError('Native qualified fact group byte budget exceeded')
            if (item['id'] != row['observation'] or self.partition(item,row['kind']) != partition
                or ConflictDetector.qualified_fact_identity(p.project,item,row['kind']) != row['identity']):
                raise ProcessingError('Native qualified fact observation identity changed')
            if row['kind'] == 'assertion':
                assertions.append(KnowledgeAssertion.model_validate(item))
            else:
                relations.append(KnowledgeRelation.model_validate(item))
        self._fence()
        return ConflictDetector.reconcile_qualified_facts(p.project,assertions,relations,
            functional_predicates=functional_predicates)

    @staticmethod
    def _page_budget(limit,max_bytes):
        if type(limit) is not int or not 1<=limit<=MAX_ROWS:
            raise ProcessingError('Invalid native canonical page limit')
        if type(max_bytes) is not int or not 1<=max_bytes<=MAX_BYTES:
            raise ProcessingError('Invalid native canonical page byte budget')

    def topology_page(self,*,after=None,limit=MAX_ROWS,max_bytes=MAX_BYTES):
        """Project staged canonical endpoints directly, before ready activation."""
        self._page_budget(limit,max_bytes)
        p=self.publication
        with self.owner._publication_lock:
            self._fence()
            cursor=f'FILTER(STR(?id) > {p.scalar(after)})' if after is not None else ''
            rows=list(self.owner.store.query(f'''SELECT ?id ?source ?target ?predicate WHERE {{
                GRAPH {p.graph} {{ {p.head} <{P}fact> ?id .
                    ?id <{P}source> ?source ; <{P}target> ?target ;
                    <{P}representative> ?representative . {cursor} }}
                GRAPH {p.facts} {{ ?representative <{F}predicateName> ?predicate }}
                }} ORDER BY ?id LIMIT {limit+1}'''))
        values=[]
        for row in rows[:limit]:
            value={key:row[key].value for key in ('id','source','target')}
            value['type']=normalize_fact_predicate(row['predicate'].value)
            if len(json.dumps(values+[value],ensure_ascii=False).encode())>max_bytes:
                if not values:
                    raise ProcessingError('Native topology item exceeds byte budget')
                break
            values.append(value)
        return dict(records=values,next_cursor=values[-1]['id'] if len(rows)>len(values) else None)

    def canonical_page(self,kind,read,*,after=None,limit=MAX_ROWS,max_bytes=MAX_BYTES,
                       subject_ids=None,evidence_ids=None,predicates=None,functional_predicates=(),
                       max_group_records=4096,max_group_bytes=16*1024*1024):
        """Select canonical identities natively, reduce only complete selected groups.

        Admission filters select identities through any supporting observation.
        All evidence and conflict peers in their partition remain in reduction.
        No DTO state is persisted or retained between calls.
        """
        self._page_budget(limit,max_bytes)
        if kind not in {'assertion','relation'}:
            raise ProcessingError('Unknown qualified fact kind')
        if any(type(v) is not int or v<1 for v in (max_group_records,max_group_bytes)):
            raise ProcessingError('Invalid qualified fact group budget')
        p=self.publication
        filters=[]
        for field,values in (('qualifiedSubject',subject_ids),('qualifiedEvidence',evidence_ids),('qualifiedPredicate',predicates)):
            if values is not None:
                if not isinstance(values,(list,tuple)) or len(values)>MAX_ROWS:
                    raise ProcessingError('Native canonical admission scope exceeds page limit')
                if not values:
                    return dict(records=[],next_cursor=None)
                name='selected'+field
                filters.append(f'?entry <{P}{field}> ?{name} . VALUES ?{name} {{ '+
                    ' '.join(str(p.scalar(value)) for value in values)+' }')
        cursor=f'FILTER(STR(?identity) > {p.scalar(after)})' if after is not None else ''
        with self.owner._publication_lock:
            self._fence()
            rows=list(self.owner.store.query(f'''SELECT DISTINCT ?identity ?partition WHERE {{
                GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> ?entry .
                    ?entry <{P}qualifiedKind> {p.scalar(kind)} ;
                    <{P}qualifiedIdentity> ?identity ; <{P}qualifiedPartition> ?partition .
                    {' '.join(filters)} {cursor} }}
                }} ORDER BY ?identity LIMIT {limit+1}'''))
        values=[]
        functional_predicates=tuple(functional_predicates)
        # Reuse only the most recent bounded group, never a project DTO cache.
        current_partition=None
        reduced=None
        for row in rows[:limit]:
            partition,identity=row['partition'].value,row['identity'].value
            if partition!=current_partition:
                reduced=self._reconcile_partition(partition,read,functional_predicates,
                    max_group_records,max_group_bytes)[0 if kind=='assertion' else 1]
                current_partition=partition
            item=next((value for value in reduced if value.id==identity),None)
            if item is None:
                raise ProcessingError('Native canonical identity missing from reducer')
            if len(json.dumps([value.model_dump() for value in values]+[item.model_dump()],ensure_ascii=False).encode())>max_bytes:
                if not values:
                    raise ProcessingError('Native canonical item exceeds byte budget')
                break
            values.append(item)
        self._fence()
        return dict(records=values,next_cursor=values[-1].id if len(rows)>len(values) else None)

    def stage_reconciled(self,assertions,relations):
        """Store only final status scalars on existing native observation keys."""
        p=self.publication
        with self.owner._publication_lock:
            self._fence()
            for kind,items in (('assertion',assertions),('relation',relations)):
                for item in items:
                    # All observations supporting this canonical identity share
                    # the exact reducer's final status. No semantic rule lives here.
                    self.owner.store.update(f'''INSERT {{ GRAPH {p.graph} {{
                        ?entry <{P}qualifiedReconciledStatus> {p.scalar(item.status)} }} }} WHERE {{
                        GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> ?entry .
                            ?entry <{P}qualifiedKind> {p.scalar(kind)} ;
                            <{P}qualifiedIdentity> {p.scalar(item.id)} }} }}''')
            self.owner.flush()

    def family_page(self,*,after=None,limit=MAX_ROWS,max_bytes=MAX_BYTES,
                    max_family_sources=4096,subject_ids=None):
        """Reference metadata for exact report admission, before DTO hydration.

        Families are (canonical subject,predicate). Required includes every
        contradicted/retracted/rejected reducer result. Representation support
        comes from each accepted native observation's immutable source binding.
        """
        self._page_budget(limit,max_bytes)
        # Ranking is supplied by the native summarizer. Join only a bounded
        # subject window, preserving that order without collecting every family.
        selection=''
        order='?subject ?predicate'
        ranks=None
        if subject_ids is not None:
            if (not isinstance(subject_ids,(list,tuple)) or len(subject_ids)>MAX_ROWS or
                any(not isinstance(value,str) or not value for value in subject_ids) or
                len(set(subject_ids))!=len(subject_ids)):
                raise ProcessingError('Invalid native family subject scope')
            if not subject_ids:
                return dict(records=[],next_cursor=None)
            ranks={subject:rank for rank,subject in enumerate(subject_ids)}
            selection='VALUES (?subject ?rank) { '+ ' '.join(
                f'({self.publication.scalar(subject)} {rank})' for subject,rank in ranks.items())+' }'
            order='?rank ?predicate'
        if type(max_family_sources) is not int or not 1<=max_family_sources<=4096:
            raise ProcessingError('Invalid qualified family source budget')
        p=self.publication
        with self.owner._publication_lock:
            self._fence()
            if bool(self.owner.store.query(f'''ASK {{ GRAPH {p.graph} {{
                {p.head} <{P}qualifiedEntry> ?entry . FILTER NOT EXISTS {{
                    ?entry <{P}qualifiedReconciledStatus> ?status }} }} }}''')):
                raise ProcessingError('Native qualified reconciliation incomplete')
            cursor=''
            if after is not None:
                try:
                    subject,predicate=json.loads(after)
                except (ValueError,TypeError):
                    raise ProcessingError('Invalid native family cursor') from None
                if not all(isinstance(v,str) for v in (subject,predicate)):
                    raise ProcessingError('Invalid native family cursor')
                if ranks is not None:
                    if subject not in ranks:
                        raise ProcessingError('Invalid native family cursor scope')
                    cursor=f'''FILTER(?rank > {ranks[subject]} ||
                        (?rank = {ranks[subject]} && STR(?predicate) > {p.scalar(predicate)}))'''
                else:
                    cursor=f'''FILTER(STR(?subject) > {p.scalar(subject)} ||
                        (STR(?subject) = {p.scalar(subject)} && STR(?predicate) > {p.scalar(predicate)}))'''
            rows=list(self.owner.store.query(f'''SELECT DISTINCT ?subject ?predicate WHERE {{
                {selection}
                GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> ?entry .
                    ?entry <{P}qualifiedSubject> ?subject ; <{P}qualifiedPredicate> ?predicate .
                    }} {cursor} }} ORDER BY {order} LIMIT {limit+1}'''))
            values=[]
            for row in rows[:limit]:
                subject,predicate=row['subject'].value,row['predicate'].value
                pattern=f'''{p.head} <{P}qualifiedEntry> ?entry .
                    ?entry <{P}qualifiedSubject> {p.scalar(subject)} ;
                    <{P}qualifiedPredicate> {p.scalar(predicate)} .'''
                sources=list(self.owner.store.query(f'''SELECT DISTINCT ?representation WHERE {{
                    GRAPH {p.graph} {{ {pattern}
                        ?entry <{P}qualifiedRepresentation> ?representation }}
                    }} ORDER BY ?representation LIMIT {max_family_sources+1}'''))
                if len(sources)>max_family_sources:
                    raise ProcessingError('Native qualified family source budget exceeded')
                required=bool(self.owner.store.query(f'''ASK {{ GRAPH {p.graph} {{
                    {pattern} ?entry <{P}qualifiedReconciledStatus> ?status .
                    VALUES ?status {{ "contradicted" "retracted" "rejected" }} }} }}'''))
                value=dict(subject=subject,predicate=predicate,
                    representations=[r['representation'].value for r in sources],required=required)
                if len(json.dumps(values+[value],ensure_ascii=False).encode())>max_bytes:
                    if not values:
                        raise ProcessingError('Native qualified family exceeds byte budget')
                    break
                values.append(value)
            cursor=(json.dumps([values[-1]['subject'],values[-1]['predicate']],
                ensure_ascii=False,separators=(',',':')) if len(rows)>len(values) else None)
            return dict(records=values,next_cursor=cursor)
