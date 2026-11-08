"""Reference-only native partitions for the current qualified-fact owner."""
import hashlib
import json
import uuid
from itertools import islice

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
            # Completion belongs to immutable input, not this publication attempt.
            # Dirty partitions survive cancellation until their decisions are sealed.
            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}factStageInput> ?value }} }}')
            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedIndexSealed> ?value }} }}')
            seen=p.scalar(uuid.uuid4().hex)
            count = 0
            pending, pending_ids, pending_bytes = [], set(), 0
            def flush():
                nonlocal pending, pending_ids, pending_bytes
                if pending:
                    self._fence(False)
                    p.mutate(self.generation,pending)
                    pending, pending_ids, pending_bytes = [], set(), 0
            def batches():
                batch, size = [], 0
                for row in rows:
                    amount=len(json.dumps(row,ensure_ascii=False).encode())
                    if amount>MAX_BYTES:
                        raise ProcessingError('Native qualified input exceeds byte budget')
                    if batch and (len(batch)>=MAX_ROWS or size+amount>MAX_BYTES):
                        yield batch
                        batch, size = [], 0
                    batch.append(row)
                    size+=amount
                if batch:
                    yield batch
            for batch in batches():
                representations={}
                verified=set()
                self._fence(False)
                for reference,kind,item in batch:
                    check_query_cancellation()
                    native = p.iri(reference)
                    if reference not in verified:
                        p.member(native)
                    if reference not in verified and not next(self.owner.store.quads_for_pattern(native, p.ox.NamedNode(RDF_TYPE),
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
                    if source.value not in representations:
                        records=ExtractionRecords.from_identity_reference(self.owner,p.project,source.value)
                        _,one,_=records._read_identity_projection_fields(source)
                        representations[source.value]=one(source,'buildRepresentationId')
                    representation=representations[source.value]
                    verified.add(reference)
                    entry = p.iri(P+'qualified-entry:'+_digest([reference, kind, item['id']]))
                    if entry.value in pending_ids or p.values(entry,'qualifiedSeen')==[seen]:
                        raise ProcessingError('Duplicate qualified fact observation')
                    partition=p.iri(P+'qualified-partition:'+self.partition(item,kind))
                    previous=p.values(entry,'qualifiedPartition')
                    same=(previous==[p.scalar(self.partition(item,kind))]
                        and p.values(entry,'qualifiedIdentity')==[p.scalar(identity)]
                        and p.values(entry,'qualifiedRepresentation')==[p.scalar(representation)]
                        and p.values(entry,'qualifiedRawStatus')==[p.scalar(item.get('status','candidate'))]
                        and {q.object.value for q in self.owner.store.quads_for_pattern(entry,
                            p.ox.NamedNode(P+'qualifiedEvidence'),None,p.graph)}==set(item['evidence_ids']))
                    if previous:
                        if not same:
                            self._dirty(p.iri(P+'qualified-partition:'+p.one(entry,'qualifiedPartition')))
                            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ ?partition <{P}qualifiedPartitionEntry> {entry} }} }}')
                            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {entry} ?field ?value }} }}')
                        else:
                            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {entry} <{P}qualifiedSeen> ?value }} }}')
                            p.mutate(self.generation,[p.triple(entry,'qualifiedSeen',seen)])
                            if not p.values(entry,'qualifiedDecision'):
                                self._dirty(partition)
                            count+=1
                            continue
                    self._dirty(partition)
                    triples = [
                        p.triple(entry,'qualifiedSeen',seen),
                        p.triple(p.head, 'qualifiedPartitionNode', partition),
                        p.triple(partition, 'qualifiedPartitionEntry', entry),
                        p.triple(p.head, 'qualifiedEntry', entry),
                        p.triple(entry, 'qualifiedPartition', p.scalar(self.partition(item,kind))),
                        p.triple(entry, 'qualifiedReference', p.iri(reference)),
                        p.triple(entry, 'qualifiedKind', p.scalar(kind)),
                        p.triple(entry, 'qualifiedObservation', p.scalar(item['id'])),
                        p.triple(entry, 'qualifiedIdentity', p.scalar(identity)),
                        p.triple(entry,'qualifiedRepresentation',p.scalar(representation)),
                        p.triple(entry,'qualifiedRawStatus',p.scalar(item.get('status','candidate'))),
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
            # Removed observations invalidate their old conflict scope too.
            for link in self.owner.store.quads_for_pattern(p.head,p.ox.NamedNode(P+'qualifiedEntry'),None,p.graph):
                entry=link.object
                if p.values(entry,'qualifiedSeen')!=[seen]:
                    self._dirty(p.iri(P+'qualified-partition:'+p.one(entry,'qualifiedPartition')))
                    self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ ?partition <{P}qualifiedPartitionEntry> {entry} }} }}')
                    self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedEntry> {entry} }} }}')
                    self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {entry} ?field ?value }} }}')
            self._discard_dirty_decisions()
            self._fence(False)
            p.mutate(self.generation, [p.triple(p.head, 'qualifiedIndexSealed', p.ox.Literal(count))])

    def _dirty(self,partition):
        p=self.publication
        if next(self.owner.store.quads_for_pattern(partition,p.ox.NamedNode(P+'qualifiedDirty'),None,p.graph),None):
            return
        partition_id=partition.value.removeprefix(P+'qualified-partition:')
        self.owner.store.update(f"""INSERT {{ GRAPH {p.graph} {{ {partition} <{P}qualifiedDirtyDecision> ?decision }} }}
            WHERE {{ GRAPH {p.graph} {{ ?entry <{P}qualifiedPartition> {p.scalar(partition_id)} ; <{P}qualifiedDecision> ?decision }} }}""")
        p.mutate(self.generation,[p.triple(partition,'qualifiedDirty',p.ox.Literal(True))])

    def _discard_dirty_decisions(self):
        """Replace only the actual old/new dependency closure, never other facts."""
        p=self.publication
        # Bind decisions by selected entry OR current members: a selected entry
        # can have moved or been withdrawn since the previous completed decision.
        for link in self.owner.store.quads_for_pattern(None,p.ox.NamedNode(P+'qualifiedDirty'),None,p.graph):
            partition=link.subject
            if not p.values(partition,'qualifiedDirtyDecision'):
                continue
            partition_id=partition.value.removeprefix(P+'qualified-partition:')
            pattern=f'{partition} <{P}qualifiedDirtyDecision> ?decision .'
            self.owner.store.update(f"""DELETE {{ GRAPH {p.graph} {{ {p.head} <{P}fact> ?fact . ?fact ?field ?value }} }}
                WHERE {{ GRAPH {p.graph} {{ {pattern}
                ?decision <{P}qualifiedSelectedKind> "relation" ; <{P}qualifiedSelectedIdentity> ?id .
                BIND(IRI(?id) AS ?fact) ?fact ?field ?value }} }}""")
            self.owner.store.update(f"""DELETE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedDecision> ?decision . ?decision ?field ?value }} }}
                WHERE {{ GRAPH {p.graph} {{ {pattern} ?decision ?field ?value }} }}""")
            self.owner.store.update(f"""DELETE {{ GRAPH {p.graph} {{ ?entry ?field ?value }} }}
                WHERE {{ GRAPH {p.graph} {{ ?entry <{P}qualifiedPartition> {p.scalar(partition_id)} ; ?field ?value .
                VALUES ?field {{ <{P}qualifiedDecision> <{P}qualifiedReconciledStatus> }} }} }}""")

    def _references(self, partition):
        p, after = self.publication, ''
        while True:
            with self.owner._publication_lock:
                self._fence()
                page = list(self.owner.store.query(f'''SELECT ?entry ?reference ?kind ?observation ?identity WHERE {{
                    GRAPH {p.graph} {{ ?entry <{P}qualifiedPartition> {p.scalar(partition)} ;
                        <{P}qualifiedReference> ?reference ; <{P}qualifiedKind> ?kind ;
                        <{P}qualifiedObservation> ?observation ; <{P}qualifiedIdentity> ?identity .
                        FILTER(STR(?entry) > {p.ox.Literal(after)})
                        FILTER EXISTS {{ {p.head} <{P}qualifiedEntry> ?entry }} }}
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

    def _reference_pages(self):
        """Traverse the native partition adjacency once, without global sorting."""
        p = self.publication
        self._fence()
        visited=0
        partitions=self.owner.store.quads_for_pattern(p.head,
            p.ox.NamedNode(P+'qualifiedPartitionNode'),None,p.graph)
        for link in partitions:
            if not isinstance(link.object,p.ox.NamedNode):
                raise ProcessingError('Native qualified partition address invalid')
            page, size = [], 0
            for member in self.owner.store.quads_for_pattern(link.object,
                    p.ox.NamedNode(P+'qualifiedPartitionEntry'),None,p.graph):
                check_query_cancellation()
                entry=member.object
                if not isinstance(entry,p.ox.NamedNode) or not next(self.owner.store.quads_for_pattern(
                        p.head,p.ox.NamedNode(P+'qualifiedEntry'),entry,p.graph),None):
                    raise ProcessingError('Native qualified partition member invalid')
                value={key:p.one(entry,field) for key,field in (
                    ('partition','qualifiedPartition'),('reference','qualifiedReference'),
                    ('kind','qualifiedKind'),('observation','qualifiedObservation'),('identity','qualifiedIdentity'))}
                if link.object!=p.iri(P+'qualified-partition:'+value['partition']):
                    raise ProcessingError('Native qualified partition binding differs')
                amount=len(json.dumps(value,ensure_ascii=False).encode())
                if amount>MAX_BYTES:
                    raise ProcessingError('Native qualified reference exceeds byte budget')
                if page and (len(page)>=MAX_ROWS or size+amount>MAX_BYTES):
                    self._fence()
                    yield page
                    page, size = [], 0
                visited+=1
                if not next(self.owner.store.quads_for_pattern(link.object,
                        p.ox.NamedNode(P+'qualifiedDirty'),None,p.graph),None):
                    continue
                page.append(value)
                size+=amount
            if page:
                yield page
        if visited!=int(p.one(p.head,'qualifiedIndexSealed')):
            raise ProcessingError('Native qualified partition coverage incomplete')

    def canonical_endpoints(self, reference):
        return self.canonical_endpoint_page([reference])[reference]

    def canonical_endpoint_page(self, references):
        """Resolve one bounded page by native address seeks, preserving unique membership."""
        if not isinstance(references,list) or len(references)>MAX_ROWS or len(set(references))!=len(references):
            raise ProcessingError('Invalid native endpoint page')
        if not references:
            return {}
        p=self.publication
        with self.owner._publication_lock:
            self._fence(False)
            native=[p.iri(reference) for reference in references]
            for node in native:
                p.member(node)
            result={}
            for node in native:
                endpoints=[]
                for field in ('sourceEntity','targetEntity'):
                    mentions=list(islice(self.owner.store.quads_for_pattern(node,
                        p.ox.NamedNode(F+field),None,p.facts),2))
                    if len(mentions)!=1:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
                    selected=None
                    for link in self.owner.store.quads_for_pattern(None,p.ox.NamedNode(P+'member'),mentions[0].object,p.graph):
                        check_query_cancellation()
                        if next(self.owner.store.quads_for_pattern(p.head,
                                p.ox.NamedNode(P+'canonical'),link.subject,p.graph),None):
                            if selected is not None:
                                raise ProcessingError('Native fact requires unique canonical endpoint membership')
                            selected=link.subject.value
                    if selected is None:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
                    endpoints.append(selected)
                result[node.value]=tuple(endpoints)
            return result

    def iter_reconciled(self, read, *, functional_predicates=(),
                        max_group_records=4096, max_group_bytes=16*1024*1024):
        """Yield assertions, relations, conflicts and native relation support plans.

        `read(native_reference, kind, observation_id)` must reread the same
        current native observation and canonical endpoint binding. Limits are
        enforced before a partition can produce any semantic output.
        """
        if any(type(value) is not int or value < 1 for value in (max_group_records,max_group_bytes)):
            raise ProcessingError('Invalid qualified fact group budget')
        p = self.publication
        functional_predicates = p.functional_policy(functional_predicates)
        policy=p.scalar(json.dumps(functional_predicates,separators=(',',':')))
        previous=p.values(p.head,'qualifiedFunctionalPredicates')
        if len(previous)>1:
            raise ProcessingError('Native functional predicate policy duplicated')
        if previous != [policy]:
            old=set(json.loads(previous[0].value)) if previous else set()
            changed=old.symmetric_difference(functional_predicates)
            with self.owner._publication_lock:
                self._fence()
                self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}factStageInput> ?value }} }}')
                for link in self.owner.store.quads_for_pattern(p.head,p.ox.NamedNode(P+'qualifiedEntry'),None,p.graph):
                    if p.one(link.object,'qualifiedPredicate') in changed:
                        self._dirty(p.iri(P+'qualified-partition:'+p.one(link.object,'qualifiedPartition')))
                self._discard_dirty_decisions()
                self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedFunctionalPredicates> ?value }} }}')
                p.mutate(self.generation,[p.triple(p.head,'qualifiedFunctionalPredicates',policy)])
        partition = None
        references = []
        for page in self._reference_pages():
            for row in page:
                if partition is not None and row['partition'] != partition:
                    yield self._reconcile_partition(partition, read, functional_predicates,
                        max_group_records, max_group_bytes, references)
                    references = []
                partition = row['partition']
                references.append(row)
                if len(references) > max_group_records:
                    raise ProcessingError('Native qualified fact group record budget exceeded')
        if partition is not None:
            yield self._reconcile_partition(partition, read, functional_predicates,
                max_group_records, max_group_bytes, references)

    def _reconcile_partition(self,partition,read,functional_predicates=(),
                             max_group_records=4096,max_group_bytes=16*1024*1024,references=None):
        p=self.publication
        assertions, relations, size, count = [], [], 0, 0
        supports = {}
        selections = {}
        # Consume both logical views consecutively so one observation is restored once.
        rows=list(self._references(partition)) if references is None else references
        for row in sorted(rows,key=lambda value:(value['reference'],value['kind'])):
            count += 1
            if count > max_group_records:
                raise ProcessingError('Native qualified fact group record budget exceeded')
            check_query_cancellation()
            item = read(row['reference'], row['kind'], row['observation'])
            size += len(json.dumps(item, ensure_ascii=False, separators=(',',':')).encode())
            if size > max_group_bytes:
                raise ProcessingError('Native qualified fact group byte budget exceeded')
            if (item['id'] != row['observation'] or self.partition(item,row['kind']) != partition
                or ConflictDetector.qualified_fact_identity(p.project,item,row['kind']) != row['identity']):
                raise ProcessingError('Native qualified fact observation identity changed')
            key=(row['kind'],row['identity'])
            choice=(json.dumps(item,sort_keys=True,ensure_ascii=False,separators=(',',':')),row['reference'])
            if key not in selections or choice<selections[key]:
                selections[key]=choice
            if row['kind'] == 'assertion':
                assertions.append(KnowledgeAssertion.model_validate(item))
            else:
                relations.append(KnowledgeRelation.model_validate(item))
                members, observations = supports.setdefault(row['identity'], ({}, {}))
                members[row['reference']] = None
                observations.setdefault(item['id'], row['reference'])
        self._fence()
        result = ConflictDetector.reconcile_qualified_facts(p.project,assertions,relations,
            functional_predicates=functional_predicates)
        plans = {}
        for relation in result[1]:
            members, observations = supports[relation.id]
            representative = selections['relation',relation.id][1]
            if not members or representative is None:
                raise ProcessingError('Native canonical fact support or representative missing')
            plans[relation.id] = (list(members), representative)
        return (*result, plans, {key:value[1] for key,value in selections.items()})

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

    def _selected_observation(self,reference,kind,observation):
        records=ExtractionRecords.from_fact_reference(self.owner,self.publication.project,reference)
        item=records.read_fact_projection(reference,kind)
        source,target=self.canonical_endpoints(reference)
        if kind=='assertion':
            item.update(subject_id=source,object_entity_id=target)
        else:
            item.update(source_entity_id=source,target_entity_id=target)
        return item

    def canonical_page(self,kind,*,after=None,limit=MAX_ROWS,max_bytes=MAX_BYTES,
                       subject_ids=None,evidence_ids=None,predicates=None):
        """Read committed field selections; never execute semantic reduction."""
        self._page_budget(limit,max_bytes)
        if kind not in {'assertion','relation'}:
            raise ProcessingError('Unknown qualified fact kind')
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
        for row in rows[:limit]:
            identity = row['identity'].value
            decision = p.iri(P+'qualified-decision:'+_digest([identity,kind]))
            observation = p.one(decision,'qualifiedSelectedObservation')
            reference = p.one(decision,'qualifiedSelectedReference')
            item = dict(self._selected_observation(reference,kind,observation))
            if item['id']!=observation or ConflictDetector.qualified_fact_identity(p.project,item,kind)!=identity:
                raise ProcessingError('Native canonical selected observation identity changed')
            def selected(field):
                result, size = [], 0
                for q in self.owner.store.quads_for_pattern(decision,p.ox.NamedNode(P+field),None,p.graph):
                    if not isinstance(q.object,p.ox.Literal):
                        raise ProcessingError('Native canonical selection value invalid')
                    size+=len(q.object.value.encode())
                    if len(result)>=4096 or size>max_bytes:
                        raise ProcessingError('Native canonical selection exceeds byte budget')
                    result.append(q.object.value)
                return sorted(result)
            item.update(id=identity,status=p.one(decision,'qualifiedSelectedStatus'),
                evidence_ids=selected('qualifiedSelectedEvidence'))
            item['evidence_ids'].sort()
            item['support_ids']=list(item['evidence_ids'])
            item['metadata']={**item.get('metadata',{}),
                'representative_observation_id':observation,
                'support_observation_ids':selected('qualifiedSelectedSupport')}
            item=(KnowledgeAssertion if kind=='assertion' else KnowledgeRelation).model_validate(item)
            if len(json.dumps([value.model_dump() for value in values]+[item.model_dump()],ensure_ascii=False).encode())>max_bytes:
                if not values:
                    raise ProcessingError('Native canonical item exceeds byte budget')
                break
            values.append(item)
        self._fence()
        return dict(records=values,next_cursor=values[-1].id if len(rows)>len(values) else None)

    def stage_reconciled(self,assertions,relations,*,references):
        """Store only final status scalars on existing native observation keys."""
        p=self.publication
        with self.owner._publication_lock:
            self._fence()
            pending, pending_bytes = [], 0
            selections, selection_bytes = [], 0
            def flush_selections():
                nonlocal selections, selection_bytes
                if selections:
                    p.mutate(self.generation,selections)
                    selections, selection_bytes = [], 0
            def flush():
                nonlocal pending, pending_bytes
                if not pending:
                    return
                self._fence()
                p.mutate(self.generation,pending)
                pending, pending_bytes = [], 0
            for kind,items in (('assertion',assertions),('relation',relations)):
                for item in items:
                    observation=item.metadata.get('representative_observation_id')
                    supports=item.metadata.get('support_observation_ids')
                    if not observation or not supports or observation not in supports:
                        raise ProcessingError('Native canonical decision lacks observation selection')
                    decision=p.iri(P+'qualified-decision:'+_digest([item.id,kind]))
                    selected_entry=p.iri(P+'qualified-entry:'+_digest([references[kind,item.id],kind,observation]))
                    partition=p.iri(P+'qualified-partition:'+p.one(selected_entry,'qualifiedPartition'))
                    triples=[p.triple(partition,'qualifiedDirtyDecision',decision),
                        p.triple(p.head,'qualifiedDecision',decision),
                        p.triple(decision,'qualifiedSelectedKind',p.scalar(kind)),
                        p.triple(decision,'qualifiedSelectedEntry',p.iri(P+'qualified-entry:'+_digest([references[kind,item.id],kind,observation]))),
                        p.triple(decision,'qualifiedSelectedIdentity',p.scalar(item.id)),
                        p.triple(decision,'qualifiedSelectedReference',p.iri(references[kind,item.id])),
                        p.triple(decision,'qualifiedSelectedObservation',p.scalar(observation)),
                        p.triple(decision,'qualifiedSelectedStatus',p.scalar(item.status)),
                        *[p.triple(decision,'qualifiedSelectedEvidence',p.scalar(value)) for value in item.evidence_ids],
                        *[p.triple(decision,'qualifiedSelectedSupport',p.scalar(value)) for value in supports]]
                    # Selections are immutable in this index, never overwritten by reads.
                    if p.values(decision,'qualifiedSelectedObservation'):
                        raise ProcessingError('Native canonical decision already staged')
                    for triple in triples:
                        amount=len(triple.encode())+1
                        if amount>MAX_BYTES:
                            raise ProcessingError('Native canonical selection exceeds byte budget')
                        if selections and (len(selections)>=MAX_ROWS or selection_bytes+amount>MAX_BYTES):
                            flush_selections()
                        selections.append(triple)
                        selection_bytes+=amount
                    for link in self.owner.store.quads_for_pattern(None,
                            p.ox.NamedNode(P+'qualifiedIdentity'),p.scalar(item.id),p.graph):
                        entry=link.subject
                        if p.one(entry,'qualifiedKind')!=kind:
                            continue
                        if not next(self.owner.store.quads_for_pattern(p.head,
                                p.ox.NamedNode(P+'qualifiedEntry'),entry,p.graph),None):
                            continue
                        for field,value in (('qualifiedReconciledStatus',p.scalar(item.status)),
                                            ('qualifiedDecision',decision)):
                            triple=p.triple(entry,field,value)
                            size=len(triple.encode())+1
                            if pending and (len(pending)>=MAX_ROWS or pending_bytes+size>MAX_BYTES):
                                flush()
                            if size>MAX_BYTES:
                                raise ProcessingError('Qualified reconciliation status exceeds byte budget')
                            pending.append(triple)
                            pending_bytes+=size
            flush_selections()
            flush()
            if getattr(p, '_checkpoint', None) is None:
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
