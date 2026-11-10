"""Reference-only native partitions for the current qualified-fact owner."""
import hashlib
import json
from functools import lru_cache
from itertools import groupby
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
        self.publication = PublicationRecords(owner, project, stage='fact')

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
        p.require_qualified_layout()
        if sealed and not p.values(p.head, 'qualifiedDecisionCount'):
            raise ProcessingError('Native qualified fact decisions are not sealed')

    def _physical_rows(self):
        """Read only coordination columns; never restore or audit complete DTOs."""
        p=self.publication
        from ..semantic_extract.schemas import validate_fact_qualifiers
        graph,head=p.stage_graph('identity'),p.stage_head('identity')
        @lru_cache(maxsize=128)
        def endpoint(member):
            # Seek the indexed member first; never join every canonical graph.
            matches=set()
            for link in self.owner.store.quads_for_pattern(None,p.iri(P+'member'),member,None):
                check_query_cancellation()
                if (next(self.owner.store.quads_for_pattern(head,p.iri(P+'canonical'),link.subject,graph),None)
                        and p.values(link.subject,'canonicalGraph',graph=graph)==[link.graph_name]):
                    matches.add(link.subject)
                    if len(matches)>1:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
            if not matches:
                raise ProcessingError('Native fact field missing or duplicated; unique canonical endpoint membership required')
            return next(iter(matches))
        for canonical in self.owner.store.quads_for_pattern(head,p.iri(P+'canonical'),None,graph):
            check_query_cancellation()
            # Bound sorting to one canonical subject, as required by the conflict
            # rules. Missing columns stay visible and fail instead of losing rows.
            locations=p.values(canonical.object,'canonicalGraph',graph=graph)
            if len(locations)!=1:
                raise ProcessingError('Completed identity decision graph missing or duplicated')
            rows=[]
            size=0
            def field(node, name, location, required=True):
                values=[]
                for quad in self.owner.store.quads_for_pattern(node,p.iri(F+name),None,location):
                    values.append(quad.object)
                    if len(values)>1:
                        raise ProcessingError('Native fact field missing or duplicated')
                if required and not values:
                    raise ProcessingError('Native fact field missing or duplicated')
                return values[0] if values else None
            for membership in self.owner.store.quads_for_pattern(
                    canonical.object,p.iri(P+'member'),None,locations[0]):
                raw_source=membership.object
                for link in self.owner.store.quads_for_pattern(None,p.iri(F+'sourceEntity'),raw_source,p.facts):
                    check_query_cancellation()
                    reference=link.subject
                    if not next(self.owner.store.quads_for_pattern(reference,p.iri(RDF_TYPE),p.iri(F+'Relation'),p.facts),None):
                        continue
                    operation=p.iri(reference.value.rsplit(':relation:',1)[0])
                    if not any(next(self.owner.store.quads_for_pattern(p.publication_head,p.iri(P+'source'),q.subject,p.publication_graph),None)
                            for q in self.owner.store.quads_for_pattern(None,p.iri(P+'operation'),operation,p.publication_graph)):
                        continue
                    if not next(self.owner.store.quads_for_pattern(operation,p.iri(F+'ownedRecord'),reference,p.facts),None):
                        raise ProcessingError('Native fact field missing or duplicated')
                    if field(reference,'sourceEntity',p.facts)!=raw_source or endpoint(raw_source)!=canonical.object:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
                    target=field(reference,'targetEntity',p.facts)
                    projection=p.iri(operation.value+':fact-projection')
                    identity=p.iri(raw_source.value.rsplit(':entity:',1)[0]+':identity-projection')
                    evidence=[]
                    for q in self.owner.store.quads_for_pattern(reference,p.iri(F+'buildEvidence'),None,projection):
                        if len(evidence)>=128:
                            raise ProcessingError('Native fact evidence order missing or duplicated')
                        evidence.append((int(field(q.object,'position',projection).value),
                            field(q.object,'referenceId',projection).value))
                    evidence.sort()
                    if not evidence or [position for position,_ in evidence]!=list(range(len(evidence))):
                        raise ProcessingError('Native fact evidence order missing or duplicated')
                    qualifiers={}
                    for key,name in (('polarity','polarity'),('condition','condition'),('time','time'),('unit','unit'),('value','qualifiedValue')):
                        value=field(reference,name,p.facts,False)
                        if value is not None:
                            qualifiers[key]=value.value.removeprefix(F) if key=='polarity' else value.value
                    row=dict(source=canonical.object.value,target=endpoint(target).value,
                        predicate=field(reference,'buildPredicate',projection).value,
                        assertion=field(reference,'buildAssertionId',projection).value,
                        id=field(reference,'buildRelationId',projection).value,
                        object=field(target,'name',p.facts).value.strip(),
                        representation=field(raw_source,'buildRepresentationId',identity).value,
                        qualifiers=validate_fact_qualifiers(qualifiers),evidence=[value for _,value in evidence])
                    size+=len(reference.value.encode())+len(json.dumps(row,ensure_ascii=False).encode())
                    if len(rows)>=131072 or size>128*1024*1024:
                        raise ProcessingError('Native fact subject sort key byte/row budget exceeded')
                    rows.append((reference.value,row))
            rows.sort(key=lambda entry:(entry[1]['predicate'],tuple(sorted(
                (key,value) for key,value in entry[1]['qualifiers'].items() if key!='polarity')),entry[0]))
            yield from rows

    def _remove_partition(self, partition):
        p=self.publication
        # A semantic decision belongs to exactly one complete conflict partition.
        for q in list(self.owner.store.quads_for_pattern(partition,
                p.ox.NamedNode(P+'qualifiedDecision'),None,p.graph)):
            decision=q.object
            kind,identity=p.decision_identity(decision)
            if kind=='relation':
                fact=p.iri(identity)
                self.owner.store.remove(p.ox.Quad(p.head,p.ox.NamedNode(P+'fact'),fact,p.graph))
            self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {decision} ?p ?o }} }}')
            self.owner.store.remove(p.ox.Quad(p.head,p.ox.NamedNode(P+'qualifiedDecision'),decision,p.graph))
        self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {partition} ?p ?o }} }}')
        self.owner.store.remove(p.ox.Quad(p.head,p.ox.NamedNode(P+'qualifiedPartitionNode'),partition,p.graph))

    def _reduce_partition(self, rows, functional_predicates):
        """Reduce each physical observation once; graph fields are projections."""
        p=self.publication
        selected={}
        members={}
        representations={}
        relation_selections={}
        relation_ids={}
        seen_relations=set()
        def observations():
            for reference,row in rows:
                if row['assertion'] in selected or row['id'] in seen_relations:
                    raise ProcessingError('Duplicate native observation identity')
                seen_relations.add(row['id'])
                selected[row['assertion']]=reference
                relation_ids[row['assertion']]=row['id']
                yield 'assertion',dict(id=row['assertion'],subject_id=row['source'],
                    object_entity_id=row['target'],predicate=row['predicate'],object=row['object'],
                    qualifiers=row['qualifiers'],evidence_ids=row['evidence'],
                    support_ids=row['evidence'],status='candidate',metadata={})
        def admit(item,identity,encoded_bytes):
            reference=selected[item['id']]
            row=rows_by_reference[reference]
            members.setdefault(identity,[]).append(reference)
            representations.setdefault(identity,set()).add(row['representation'])
            # Preserve the public graph representative without a second merge,
            # validation, evidence accumulator or membership collection.
            # Sorted model JSON compares evidence_ids, then unique id. Later
            # graph fields cannot break that ordering; no second DTO is needed.
            graph_id=relation_ids[item['id']]
            key=json.dumps(dict(evidence_ids=item['evidence_ids'],id=graph_id),
                sort_keys=True,ensure_ascii=False,separators=(',',':'))
            if identity not in relation_selections or key<relation_selections[identity][0]:
                relation_selections[identity]=(key,reference,graph_id)
        rows_by_reference=dict(rows)
        assertions,_,_=ConflictDetector.reconcile_qualified_facts(p.project,
            observations=observations(),functional_predicates=functional_predicates,admit=admit)
        return assertions,selected,members,representations,relation_selections

    def _final_triples(self,partition,result):
        """One decision and support adjacency, with public field selectors."""
        p=self.publication
        assertions,selected,members,representations,relation_selections=result
        for item in assertions:
            # The existing graph ID is retained as the single physical address.
            identity=ConflictDetector.qualified_fact_identity(p.project,dict(
                source_entity_id=item.subject_id,target_entity_id=item.object_entity_id,
                type=item.predicate,qualifiers=item.qualifiers),'relation')
            decision=p.iri(identity)
            observation=item.metadata['representative_observation_id']
            reference=selected[observation]
            _,graph_reference,graph_observation=relation_selections[item.id]
            support=members[item.id]
            if reference not in support or len(set(support))!=len(support):
                raise ProcessingError('Native canonical decision membership differs')
            yield p.triple(partition,'qualifiedDecision',decision)
            yield p.triple(p.head,'qualifiedDecision',decision)
            yield p.triple(p.head,'fact',decision)
            yield p.triple(decision,'factDecisionGraph',p.graph)
            for field,value in (
                ('qualifiedAssertionId',p.scalar(item.id)),
                ('qualifiedSubject',p.scalar(item.subject_id)),
                ('qualifiedPredicate',p.scalar(item.predicate)),
                ('qualifiedSelectedReference',p.iri(graph_reference)),
                ('qualifiedSelectedObservation',p.scalar(graph_observation)),
                ('qualifiedSelectedStatus',p.scalar('candidate')),
                ('qualifiedAssertionReference',p.iri(reference)),
                ('qualifiedAssertionObservation',p.scalar(observation)),
                ('qualifiedAssertionStatus',p.scalar(item.status)),
                ('source',p.iri(item.subject_id)),('target',p.iri(item.object_entity_id)),
                ('representative',p.iri(graph_reference)),('status',p.scalar('candidate')),
                ('memberCount',p.scalar(str(len(support))))):
                yield p.triple(decision,field,value)
            for evidence in item.evidence_ids:
                yield p.triple(decision,'qualifiedSelectedEvidence',p.scalar(evidence))
            for representation in sorted(representations[item.id]):
                yield p.triple(decision,'qualifiedRepresentation',p.scalar(representation))
            for member in support:
                yield p.triple(decision,'member',p.iri(member))

    def reconcile_and_stage(self,*,input_key,on_partition=None,functional_predicates=(),
                            max_group_records=4096,max_group_bytes=16*1024*1024):
        """Consume native groups and commit only final decisions/member references."""
        if any(type(value) is not int or value<1 for value in (max_group_records,max_group_bytes)):
            raise ProcessingError('Invalid qualified fact group budget')
        p=self.publication
        policy=p.functional_policy(functional_predicates)
        with self.owner._publication_lock:
            if p.fact_stage_status(self.generation,input_key,functional_predicates=policy):
                return
            # Bind the new immutable stage before any mutation; an unbound
            # stage would route writes into the publication graph.
            p._bind_stage('fact', input_key, functional_predicates=policy)
            p._writable_stage()
            self._fence(False)
            previous=p._pointer(p.publication_head,'previousFactGraph',p.publication_graph)
            if previous is not None:
                previous_head=p.iri(previous.value+':head')
                inputs=p.values(previous_head,'factStageInput',graph=previous)
                policies=p.values(previous_head,'qualifiedFunctionalPredicates',graph=previous)
                if len(inputs)!=1 or len(policies)!=1:
                    previous=None
                else:
                    try:
                        previous_policy=json.loads(policies[0].value)
                    except (ValueError, TypeError) as error:
                        raise ProcessingError('Completed fact policy is corrupt') from error
                    completion=p._completion_key('fact',inputs[0].value,
                        functional_predicates=previous_policy)
                    if p._pointer(completion,'completedGraph',p.registry)!=previous:
                        previous=None
            # Input cardinality closes the projection's omission boundary; member
            # coverage is proved in each complete group before emitting decisions.
            expected=int(next(iter(self.owner.store.query(f'''SELECT (COUNT(DISTINCT ?reference) AS ?count) WHERE {{
                GRAPH {p.publication_graph} {{ {p.publication_head} <{P}source> ?source . ?source <{P}operation> ?operation }}
                GRAPH {p.facts} {{ ?operation <{F}ownedRecord> ?reference .
                    ?reference <{RDF_TYPE}> <{F}Relation> }} }}''')))['count'].value)
            for field in ('factStageInput','qualifiedDecisionCount','qualifiedPhysicalCount','qualifiedFunctionalPredicates'):
                self.owner.store.update(f'DELETE WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}{field}> ?v }} }}')
            if not p.values(p.head,'qualifiedIndexLayout'):
                p.mutate(self.generation,[p.triple(p.head,'qualifiedIndexLayout',p.scalar('native-single-fact-decisions'))])
            # A run token marks final partitions touched by this traversal. It is
            # publication state, never an input identity or a stored observation.
            run=p.scalar('visited')
            self.owner.store.update(f'DELETE {{ GRAPH {p.graph} {{ ?partition <{P}qualifiedVisit> ?v }} }} WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedPartitionNode> ?partition . ?partition <{P}qualifiedVisit> ?v }} }}')
            decision_count=count=0
            def group_key(value):
                row=value[1]
                return (row['source'],row['predicate'],
                    tuple(sorted((key,value) for key,value in row['qualifiers'].items() if key!='polarity')))
            def final_triples():
                nonlocal count,decision_count
                physical=self._physical_rows()
                for _,group in groupby(physical,key=group_key):
                    check_query_cancellation()
                    rows=[]
                    size=0
                    signature=hashlib.sha256()
                    for reference,row in group:
                        body=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))
                        size+=len(reference.encode())+len(body.encode())
                        if len(rows)>=max_group_records or size>max_group_bytes:
                            raise ProcessingError('Native qualified fact group record or byte budget exceeded')
                        signature.update(json.dumps([reference,body],ensure_ascii=False,separators=(',',':')).encode())
                        rows.append((reference,row))
                    if not rows:
                        continue
                    count+=len(rows)
                    first=rows[0][1]
                    key=_digest([first['source'],first['predicate'],{k:v for k,v in first['qualifiers'].items() if k!='polarity'}])
                    partition=p.iri(P+'qualified-partition:'+key)
                    signature.update(str(first['predicate'] in policy).encode())
                    digest=p.scalar(signature.hexdigest())
                    if p.values(partition,'qualifiedInput')==[digest]:
                        decision_count+=sum(1 for _ in self.owner.store.quads_for_pattern(partition,
                            p.ox.NamedNode(P+'qualifiedDecision'),None,p.graph))
                    elif previous is not None and p.values(partition,'qualifiedInput',graph=previous)==[digest]:
                        prior_graph=p._pointer(partition,'qualifiedDecisionGraph',previous)
                        if prior_graph is None:
                            raise ProcessingError('Completed fact partition lacks its decision graph')
                        yield p.triple(p.head,'qualifiedPartitionNode',partition)
                        yield p.triple(partition,'qualifiedInput',digest)
                        yield p.triple(partition,'qualifiedDecisionGraph',prior_graph)
                        for link in self.owner.store.quads_for_pattern(partition,
                                p.iri(P+'qualifiedDecision'),None,prior_graph):
                            decision=link.object
                            yield p.triple(p.head,'qualifiedDecision',decision)
                            yield p.triple(p.head,'fact',decision)
                            yield p.triple(partition,'qualifiedDecision',decision)
                            yield p.triple(decision,'factDecisionGraph',prior_graph)
                            decision_count+=1
                    else:
                        if next(self.owner.store.quads_for_pattern(partition,None,None,p.graph),None):
                            self._remove_partition(partition)
                        # Register before streaming, so even an arbitrary partial
                        # bulk import can be found and removed on retry.
                        self.owner.store.add(p.ox.Quad(p.head,p.ox.NamedNode(P+'qualifiedPartitionNode'),partition,p.graph))
                        result=self._reduce_partition(rows,policy)
                        support=[member for group in result[2].values() for member in group]
                        if (len(support)!=len(rows) or len(set(support))!=len(support)
                                or set(support)!={reference for reference,_ in rows}
                                or {item.id for item in result[0]}!=set(result[2])):
                            raise ProcessingError('Native fact decision coverage differs from input')
                        decision_count+=len(result[0])
                        yield from self._final_triples(partition,result)
                        yield p.triple(partition,'qualifiedDecisionGraph',p.graph)
                        # Pending commit metadata is not a reusable completion.
                        yield p.triple(partition,'qualifiedPendingInput',digest)
                        if on_partition is not None:
                            on_partition(len(result[0]))
                    yield p.triple(partition,'qualifiedVisit',run)
            def batches():
                batch=[]
                size=0
                for triple in final_triples():
                    amount=len(triple.encode())+1
                    if amount>MAX_BYTES:
                        raise ProcessingError('Native decision triple exceeds byte budget')
                    if batch and size+amount>MAX_BYTES:
                        yield batch
                        batch=[]
                        size=0
                    batch.append(triple)
                    size+=amount
                if batch:
                    yield batch
            p.import_batches(self.generation,batches())
            if count!=expected:
                raise ProcessingError('Native fact admitted coverage incomplete')
            self._fence(False)
            self.owner.flush()
            # Promote final group signatures in one storage transaction only
            # after the complete import succeeded and the plan is still current.
            self.owner.store.update(f'''DELETE {{ GRAPH {p.graph} {{ ?partition <{P}qualifiedPendingInput> ?digest }} }}
                INSERT {{ GRAPH {p.graph} {{ ?partition <{P}qualifiedInput> ?digest }} }}
                WHERE {{ GRAPH {p.graph} {{ {p.head} <{P}qualifiedPartitionNode> ?partition .
                    ?partition <{P}qualifiedVisit> {run} ; <{P}qualifiedPendingInput> ?digest }} }}''')
            # Delete disappeared final groups by bounded key pages. No raw data,
            # reference spool or whole-project Python collection is created.
            while True:
                stale=list(self.owner.store.query(f'''SELECT ?partition WHERE {{ GRAPH {p.graph} {{
                    {p.head} <{P}qualifiedPartitionNode> ?partition .
                    FILTER NOT EXISTS {{ ?partition <{P}qualifiedVisit> {run} }} }} }} LIMIT {MAX_ROWS}'''))
                if not stale:
                    break
                for row in stale:
                    self._fence(False)
                    self._remove_partition(row['partition'])
            p.mutate(self.generation,[p.triple(p.head,'qualifiedDecisionCount',p.scalar(str(decision_count))),
                p.triple(p.head,'qualifiedPhysicalCount',p.scalar(str(count))),
                p.triple(p.head,'qualifiedFunctionalPredicates',p.scalar(json.dumps(policy,separators=(',',':')))),
                p.triple(p.head,'factStageInput',p.scalar(input_key))])
            p._complete_stage('fact',input_key,functional_predicates=policy)

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
            p.members(native)
            result={}
            for node in native:
                endpoints=[]
                for field in ('sourceEntity','targetEntity'):
                    mentions=list(islice(self.owner.store.quads_for_pattern(node,
                        p.ox.NamedNode(F+field),None,p.facts),2))
                    if len(mentions)!=1:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
                    selected=None
                    for link in self.owner.store.query(f'SELECT ?canonical WHERE {{ {p.canonical_pattern("?canonical", f"?canonical <{P}member> {mentions[0].object}")} }} LIMIT 2'):
                        if selected is not None:
                            raise ProcessingError('Native fact requires unique canonical endpoint membership')
                        selected=link['canonical'].value
                    if selected is None:
                        raise ProcessingError('Native fact requires unique canonical endpoint membership')
                    endpoints.append(selected)
                result[node.value]=tuple(endpoints)
            return result

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
                {p.fact_pattern('?id', f'?id <{P}source> ?source ; <{P}target> ?target ; <{P}representative> ?representative . {cursor}')}
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
        for field,values in (('qualifiedSubject',subject_ids),('qualifiedSelectedEvidence',evidence_ids),('qualifiedPredicate',predicates)):
            if values is not None:
                if not isinstance(values,(list,tuple)) or len(values)>MAX_ROWS:
                    raise ProcessingError('Native canonical admission scope exceeds page limit')
                if not values:
                    return dict(records=[],next_cursor=None)
                name='selected'+field
                filters.append(f'?decision <{P}{field}> ?{name} . VALUES ?{name} {{ '+
                    ' '.join(str(p.scalar(value)) for value in values)+' }')
        cursor=f'FILTER(STR(?identity) > {p.scalar(after)})' if after is not None else ''
        with self.owner._publication_lock:
            self._fence()
            identity_binding=f'?decision <{P}qualifiedAssertionId> ?identity .' if kind=='assertion' else ''
            identity_projection='BIND(STR(?decision) AS ?identity)' if kind=='relation' else ''
            rows=list(self.owner.store.query(f'''SELECT DISTINCT ?decision ?identity WHERE {{
                {p.fact_pattern('?decision', f"{identity_binding} {' '.join(filters)}")}
                {identity_projection} {cursor}
                }} ORDER BY ?identity LIMIT {limit+1}'''))
        values=[]
        for row in rows[:limit]:
            identity = row['identity'].value
            decision = row['decision']
            prefix='qualifiedAssertion' if kind=='assertion' else 'qualifiedSelected'
            observation=p.one(decision,prefix+'Observation')
            reference=p.one(decision,prefix+'Reference')
            item = dict(self._selected_observation(reference,kind,observation))
            if item['id']!=observation or ConflictDetector.qualified_fact_identity(p.project,item,kind)!=identity:
                raise ProcessingError('Native canonical selected observation identity changed')
            def selected(field):
                result, size = [], 0
                for q in self.owner.store.quads_for_pattern(decision,p.ox.NamedNode(P+field),None,p.record_graph(decision)):
                    if not isinstance(q.object,p.ox.Literal):
                        raise ProcessingError('Native canonical selection value invalid')
                    size+=len(q.object.value.encode())
                    if len(result)>=4096 or size>max_bytes:
                        raise ProcessingError('Native canonical selection exceeds byte budget')
                    result.append(q.object.value)
                return sorted(result)
            item.update(id=identity,status=p.one(decision,prefix+'Status'),
                evidence_ids=selected('qualifiedSelectedEvidence'))
            item['evidence_ids'].sort()
            item['support_ids']=list(item['evidence_ids'])
            item['metadata']={**item.get('metadata',{}),
                'representative_observation_id':observation,
                'support_observation_ids':self._support_observations(decision,kind,identity,max_bytes)}
            item=(KnowledgeAssertion if kind=='assertion' else KnowledgeRelation).model_validate(item)
            if len(json.dumps([value.model_dump() for value in values]+[item.model_dump()],ensure_ascii=False).encode())>max_bytes:
                if not values:
                    raise ProcessingError('Native canonical item exceeds byte budget')
                break
            values.append(item)
        self._fence()
        return dict(records=values,next_cursor=values[-1].id if len(rows)>len(values) else None)

    def _support_observations(self,decision,kind,identity,max_bytes):
        """Consume existing membership, rather than persist a second support index."""
        p=self.publication
        result,size=[],0
        for visited,q in enumerate(p.qualified_members(decision=decision),1):
            check_query_cancellation()
            if visited>4096:
                raise ProcessingError('Native canonical support exceeds row budget')
            records=ExtractionRecords.from_fact_reference(self.owner,p.project,q.object.value)
            field='buildAssertionId' if kind=='assertion' else 'buildRelationId'
            values=list(islice(self.owner.store.quads_for_pattern(q.object,
                p.ox.NamedNode(F+field),None,records.fact_projection_graph),2))
            if len(values)!=1 or not isinstance(values[0].object,p.ox.Literal):
                raise ProcessingError('Native canonical support selection missing')
            observation=values[0].object.value
            size+=len(observation.encode())+1
            if size+2>max_bytes:
                raise ProcessingError('Native canonical support exceeds byte budget')
            result.append(observation)
        if not result:
            raise ProcessingError('Native canonical support missing')
        return sorted(set(result))

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
                {p.fact_pattern('?decision', f'?decision <{P}qualifiedSubject> ?subject ; <{P}qualifiedPredicate> ?predicate .')}
                {cursor} }} ORDER BY {order} LIMIT {limit+1}'''))
            values=[]
            for row in rows[:limit]:
                subject,predicate=row['subject'].value,row['predicate'].value
                pattern=f'''?decision <{P}qualifiedSubject> {p.scalar(subject)} ;
                    <{P}qualifiedPredicate> {p.scalar(predicate)} .'''
                sources=set()
                decisions=self.owner.store.query(f'SELECT ?decision WHERE {{ {p.fact_pattern("?decision",pattern)} }}')
                for row in decisions:
                    for q in self.owner.store.quads_for_pattern(row['decision'],p.ox.NamedNode(P+'qualifiedRepresentation'),None,p.record_graph(row['decision'])):
                        sources.add(q.object.value)
                        if len(sources)>max_family_sources:
                            raise ProcessingError('Native qualified family source budget exceeded')
                if len(sources)>max_family_sources:
                    raise ProcessingError('Native qualified family source budget exceeded')
                status_pattern=f'''{pattern} ?decision (<{P}qualifiedSelectedStatus>|<{P}qualifiedAssertionStatus>) ?status .
                    VALUES ?status {{ "contradicted" "retracted" "rejected" }}'''
                required=bool(self.owner.store.query(f'ASK {{ {p.fact_pattern("?decision",status_pattern)} }}'))
                value=dict(subject=subject,predicate=predicate,
                    representations=sorted(sources),required=required)
                if len(json.dumps(values+[value],ensure_ascii=False).encode())>max_bytes:
                    if not values:
                        raise ProcessingError('Native qualified family exceeds byte budget')
                    break
                values.append(value)
            cursor=(json.dumps([values[-1]['subject'],values[-1]['predicate']],
                ensure_ascii=False,separators=(',',':')) if len(rows)>len(values) else None)
            return dict(records=values,next_cursor=cursor)
