"""Typed extraction contributions in the existing Oxigraph owner.

This module is the owner's field codec, not a fact store or a query engine.
Source text and model responses never enter RDF. Reads address one bounded
operation and reconstruct temporary evidence strings from the caller's window.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from itertools import islice

from ..semantic_extract.types import Entity, Relation
from ..utils.exceptions import ProcessingError

F = "urn:semantica:field:"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
BINDING = {"project", "source", "material", "representation", "recipe", "model", "specification", "parser", "grounding", "window_start", "window_end"}
MAX_RECORDS = 2048
MAX_OWNED = 8192
MAX_QUADS = 32768
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGE_ROWS = 128
MAX_PAGE_BYTES = 262144


class ExtractionIdentityStaleError(ProcessingError):
    """An acquired operation no longer belongs to its logical input identity."""


def operation_identity(binding, stage):
    if not isinstance(binding, dict) or set(binding) != BINDING:
        raise ProcessingError("Extraction binding requires the complete named input tuple")
    for key in BINDING - {"window_start", "window_end"}:
        if not isinstance(binding[key], str) or not binding[key] or len(binding[key]) > 4096:
            raise ProcessingError("Extraction binding has an invalid identity field")
    if any(type(binding[key]) is not int or binding[key] < 0 for key in ("window_start", "window_end")) or binding["window_end"] <= binding["window_start"]:
        raise ProcessingError("Extraction binding has an invalid source window")
    if stage not in {"entities", "relations"}:
        raise ProcessingError("Unknown native extraction stage")
    digest = hashlib.sha256(json.dumps([binding, stage], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return "urn:semantica:extraction:" + digest


def _hash(quads):
    return hashlib.sha256("\n".join(sorted(str(q) for q in quads)).encode()).hexdigest()


def _triple(quad):
    # The operation fixes the graph once. Charge its RDF payload identically on
    # insertion and verification instead of charging that URI again per row.
    return str(quad.subject) + " " + str(quad.predicate) + " " + str(quad.object)


def _range(text, start, end):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ProcessingError("Extraction evidence range is invalid")


class ExtractionRecords:
    @classmethod
    def source_projection(cls,owner,project,input_key,records=None,*,header_only=False,evidence_ids=None,passages_only=False):
        """Persist derived addresses only; completion follows durable projections."""
        with owner._publication_lock:
            from ..semantic_worker_context import check_query_cancellation
            if not isinstance(project,str) or not project or not isinstance(input_key,str) or not re.fullmatch('sha256:[0-9a-f]{64}',input_key):
                raise ProcessingError('Invalid native source projection identity')
            ox=owner._oxigraph
            node=ox.NamedNode('urn:semantica:source-projection:'+hashlib.sha256(
                json.dumps([project,input_key],separators=(',',':')).encode()).hexdigest())
            graph=ox.NamedNode(node.value+':addresses')
            def validate(value,number):
                from ..semantic_artifact_schema import DocumentRepresentation, EvidenceSpan
                from pydantic import ValidationError
                try:
                    if not isinstance(value,dict):
                        raise ValueError('address is not an object')
                    if number==0:
                        if set(value)!={'representation','artifact_id','operations'}:
                            raise ValueError('header fields differ')
                        representation=DocumentRepresentation.model_validate(value['representation'])
                        if representation.artifact_ref_id!=value['artifact_id']:
                            raise ValueError('representation artifact differs')
                        operations=value['operations']
                        if (not isinstance(operations,list) or len(operations)>100000 or
                            any(not isinstance(v,str) or not v.startswith('urn:semantica:extraction:') or len(v)>4096 for v in operations)):
                            raise ValueError('operation references invalid')
                    else:
                        if set(value)!={'fields','quote_length','quote_digest','passage'}:
                            raise ValueError('evidence fields differ')
                        fields=value['fields']
                        if not isinstance(fields,dict) or 'quote' in fields or 'quote' in fields.get('locator',{}):
                            raise ValueError('address includes a quote')
                        EvidenceSpan.model_validate({**fields,'quote':'','locator':{**fields['locator'],'quote':''}})
                        if (type(value['quote_length']) is not int or value['quote_length']<0 or
                            type(value['passage']) is not bool or not isinstance(value['quote_digest'],str) or
                            not re.fullmatch('sha256:[0-9a-f]{64}',value['quote_digest'])):
                            raise ValueError('quote address invalid')
                except (ValueError,TypeError,KeyError,ValidationError) as exc:
                    raise ProcessingError('Native source projection address schema invalid') from exc
                return value
            completed=ox.NamedNode(F+'completedProjection')
            values=list(islice(owner.store.quads_for_pattern(node,completed,None,graph),2))
            if len(values)>1:
                raise ProcessingError('Native source projection completion duplicated')
            if values:
                if records is not None:
                    raise ProcessingError('Native source projection already complete')
                try:
                    if not isinstance(values[0].object,ox.Literal) or values[0].object.datatype!=ox.NamedNode('http://www.w3.org/2001/XMLSchema#integer'):
                        raise ValueError('completion is not an integer literal')
                    count=int(values[0].object.value)
                except (TypeError,ValueError) as exc:
                    raise ProcessingError('Native source projection completion corrupt') from exc
                if not 1<=count<=100000:
                    raise ProcessingError('Native source projection count invalid')
                def read():
                    total=0
                    if header_only:
                        positions=[0]
                    elif evidence_ids is not None or passages_only:
                        indexed=list(owner.store.quads_for_pattern(node,ox.NamedNode(F+'projectionIndexed'),None,graph))
                        if len(indexed)!=1 or indexed[0].object!=ox.Literal(count):
                            raise ProcessingError('Native source projection requires offline address indexing')
                        if evidence_ids is not None:
                            if not isinstance(evidence_ids,(list,tuple)) or any(not isinstance(identity,str) or not identity or len(identity)>4096 for identity in evidence_ids):
                                raise ProcessingError('Native evidence selection identity invalid')
                            identities=list(dict.fromkeys(evidence_ids))
                            if len(evidence_ids)>MAX_PAGE_ROWS:
                                raise ProcessingError('Native evidence selection identity invalid')
                            if len(identities)>MAX_PAGE_ROWS:
                                raise ProcessingError('Native evidence selection exceeds row budget')
                            positions=[]
                            for identity in identities:
                                key=ox.NamedNode(node.value+':evidence:'+hashlib.sha256(identity.encode()).hexdigest())
                                links=list(islice(owner.store.quads_for_pattern(key,ox.NamedNode(F+'addressPosition'),None,graph),2))
                                if len(links)>1:
                                    raise ProcessingError('Native evidence selection duplicated')
                                if links:
                                    positions.append(int(links[0].object.value))
                        else:
                            positions=(int(row['position'].value) for row in owner.store.query(
                                f'SELECT ?position WHERE {{ GRAPH {graph} {{ {node} <{F}passagePosition> ?position }} }} ORDER BY ?position'))
                    else:
                        positions=range(count)
                    for number in positions:
                        if not 0<=number<count:
                            raise ProcessingError('Native evidence address position invalid')
                        check_query_cancellation()
                        field=ox.NamedNode(node.value+':'+str(number))
                        rows=list(islice(owner.store.quads_for_pattern(field,ox.NamedNode(F+'address'),None,graph),2))
                        if len(rows)!=1 or not isinstance(rows[0].object,ox.Literal) or len(rows[0].object.value.encode())>MAX_PAGE_BYTES:
                            raise ProcessingError('Native source projection address missing or oversized')
                        total+=len(rows[0].object.value.encode())
                        if total>16*1024*1024:
                            raise ProcessingError('Native source projection byte budget exceeded')
                        try:
                            value=validate(json.loads(rows[0].object.value),number)
                            if evidence_ids is not None and value['fields']['id'] not in identities:
                                raise ProcessingError('Native evidence selection identity differs')
                            yield value
                        except ValueError as exc:
                            raise ProcessingError('Native source projection address corrupt') from exc
                return read()
            if records is None:
                return None
            # A canceled write has no complete owner; discard only its partial addresses.
            owner.store.update('CLEAR SILENT GRAPH '+str(graph))
            batch=[]
            batch_bytes=0
            total=count=0
            for value in records:
                check_query_cancellation()
                validate(value,count)
                encoded=json.dumps(value,ensure_ascii=False,separators=(',',':'))
                size=len(encoded.encode())
                total+=size
                if size>MAX_PAGE_BYTES or total>16*1024*1024 or count>=100000:
                    raise ProcessingError('Native source projection address budget exceeded')
                if batch and batch_bytes+size>MAX_PAGE_BYTES:
                    owner.store.extend(batch)
                    batch=[]
                    batch_bytes=0
                batch_bytes+=size
                batch.append(ox.Quad(ox.NamedNode(node.value+':'+str(count)),ox.NamedNode(F+'address'),ox.Literal(encoded),graph))
                if count:
                    key=ox.NamedNode(node.value+':evidence:'+hashlib.sha256(value['fields']['id'].encode()).hexdigest())
                    if next(owner.store.quads_for_pattern(key,ox.NamedNode(F+'addressPosition'),None,graph),None) or any(q.subject==key for q in batch):
                        raise ProcessingError('Native source projection evidence duplicated')
                    batch.append(ox.Quad(key,ox.NamedNode(F+'addressPosition'),ox.Literal(count),graph))
                    if value['passage']:
                        batch.append(ox.Quad(node,ox.NamedNode(F+'passagePosition'),ox.Literal(count),graph))
                count+=1
                if len(batch)>=MAX_PAGE_ROWS:
                    owner.store.extend(batch)
                    batch=[]
                    batch_bytes=0
            if not count:
                raise ProcessingError('Native source projection has no addresses')
            owner.store.extend(batch)
            owner.flush()
            check_query_cancellation()
            owner.store.add(ox.Quad(node,ox.NamedNode(F+'projectionIndexed'),ox.Literal(count),graph))
            owner.store.add(ox.Quad(node,completed,ox.Literal(count),graph))
            owner.flush()
            return None

    @classmethod
    def index_source_projection(cls,owner,project,input_key):
        """Explicit offline maintenance: add address edges without copying results."""
        from ..semantic_worker_context import check_query_cancellation
        with owner._publication_lock:
            addresses=cls.source_projection(owner,project,input_key)
            if addresses is None:
                raise ProcessingError('Native source projection is not complete')
            ox=owner._oxigraph
            node=ox.NamedNode('urn:semantica:source-projection:'+hashlib.sha256(
                json.dumps([project,input_key],separators=(',',':')).encode()).hexdigest())
            graph=ox.NamedNode(node.value+':addresses')
            owner.store.update(f"""DELETE {{ GRAPH {graph} {{ ?s ?p ?o }} }} WHERE {{ GRAPH {graph} {{
                ?s ?p ?o . VALUES ?p {{ <{F}addressPosition> <{F}passagePosition> <{F}projectionIndexed> }} }} }}""")
            batch=[]
            count=0
            for number,value in enumerate(addresses):
                check_query_cancellation()
                count+=1
                if not number:
                    continue
                key=ox.NamedNode(node.value+':evidence:'+hashlib.sha256(value['fields']['id'].encode()).hexdigest())
                if next(owner.store.quads_for_pattern(key,ox.NamedNode(F+'addressPosition'),None,graph),None) or any(q.subject==key for q in batch):
                    raise ProcessingError('Native source projection evidence duplicated')
                batch.append(ox.Quad(key,ox.NamedNode(F+'addressPosition'),ox.Literal(number),graph))
                if value['passage']:
                    batch.append(ox.Quad(node,ox.NamedNode(F+'passagePosition'),ox.Literal(number),graph))
                if len(batch)>=MAX_PAGE_ROWS:
                    owner.store.extend(batch)
                    batch=[]
            owner.store.extend(batch)
            owner.flush()
            check_query_cancellation()
            owner.store.add(ox.Quad(node,ox.NamedNode(F+'projectionIndexed'),ox.Literal(count),graph))
            owner.flush()

    @classmethod
    def window_completion(cls, owner, binding, formula, groundings=None):
        """Ordered references to the accepted batches, in the existing identity index."""
        with owner._publication_lock:
            if not isinstance(binding, dict) or set(binding) != BINDING - {'grounding'}:
                raise ProcessingError('Native extraction window requires its exact input identity')
            operation_identity({**binding, 'grounding': 'validation'}, 'entities')
            if type(formula) is not bool:
                raise ProcessingError('Native extraction formula identity is invalid')
            ox = owner._oxigraph
            identity = json.dumps([binding, formula], sort_keys=True, separators=(',', ':'))
            node = ox.NamedNode('urn:semantica:extraction-window:' + hashlib.sha256(identity.encode()).hexdigest())
            graph = ox.NamedNode('urn:semantica:project:' + hashlib.sha256(binding['project'].encode()).hexdigest() + ':extraction-index')
            predicate = ox.NamedNode(F + 'completedBatches')
            values = list(islice(owner.store.quads_for_pattern(node, predicate, None, graph), 2))
            if len(values) > 1:
                raise ProcessingError('Native extraction window completion is duplicated')
            if values:
                value = values[0].object
                if not isinstance(value, ox.Literal) or len(value.value.encode()) > MAX_PAGE_BYTES:
                    raise ProcessingError('Native extraction window completion exceeds budget')
                try:
                    accepted = json.loads(value.value)
                except ValueError as exc:
                    raise ProcessingError('Native extraction window completion is corrupt') from exc
                if groundings is not None and accepted != groundings:
                    raise ProcessingError('Native extraction window completion differs')
            elif groundings is None:
                return None
            else:
                accepted = groundings
            if (not isinstance(accepted, list) or not 1 <= len(accepted) <= MAX_RECORDS
                    or any(not isinstance(item, str) or re.fullmatch('sha256:[0-9a-f]{64}', item) is None for item in accepted)):
                raise ProcessingError('Native extraction window batch references are invalid')
            bindings = []
            for grounding in accepted:
                current = {**binding, 'grounding': grounding}
                receipt = cls(owner, current, 'entities').receipt()
                if receipt is None or (receipt['count'] and cls(owner, current, 'relations').receipt() is None):
                    raise ProcessingError('Native extraction completed window has an incomplete batch')
                bindings.append(current)
            if groundings is not None and not values:
                encoded = json.dumps(accepted, separators=(',', ':'))
                if not 1 <= len(accepted) <= MAX_RECORDS or len(encoded.encode()) > MAX_PAGE_BYTES:
                    raise ProcessingError('Native extraction completed window exceeds budget')
                owner.store.update('INSERT DATA { GRAPH ' + str(graph) + ' { ' + str(node) + ' '
                    + str(predicate) + ' ' + str(ox.Literal(encoded)) + ' } }')
                owner.flush()
            return bindings

    def __init__(self, owner, binding, stage):
        self.owner = owner
        self.ox = owner._oxigraph
        self.binding, self.stage = binding, stage
        self.logical = self.ox.NamedNode(operation_identity(binding, stage))
        self.graph = self.ox.NamedNode("urn:semantica:project:" + hashlib.sha256(binding["project"].encode()).hexdigest())
        self.index_graph = self.ox.NamedNode(self.graph.value + ":extraction-index")
        links = list(islice(self.owner.store.quads_for_pattern(self.logical, self.ox.NamedNode(F + "physicalOperation"), None, self.index_graph), 2))
        if len(links) > 1 or any(not isinstance(q.object, self.ox.NamedNode) for q in links):
            raise ProcessingError("Native extraction identity index is corrupt")
        self.indexed = bool(links)
        self.operation = links[0].object if links else self.logical
        self.quads = []

    def node(self, suffix):
        return self.ox.NamedNode(self.operation.value + ":" + suffix)

    def add(self, subject, predicate, value):
        if not isinstance(value, (self.ox.NamedNode, self.ox.Literal)):
            if type(value) not in (str, int, float, bool) or (isinstance(value, float) and not math.isfinite(value)):
                raise ProcessingError("Native extraction field is not a typed scalar")
            if isinstance(value, str) and len(value.encode()) > 16384:
                raise ProcessingError("Native extraction scalar exceeds byte budget")
            value = self.ox.Literal(value)
        self.quads.append(self.ox.Quad(subject, self.ox.NamedNode(predicate if predicate == RDF_TYPE else F + predicate), value, self.graph))
        if len(self.quads) > MAX_QUADS:
            raise ProcessingError("Native extraction exceeds quad budget")

    def values(self, subject, predicate):
        result = []
        for q in self.owner.store.quads_for_pattern(subject, self.ox.NamedNode(predicate if predicate == RDF_TYPE else F + predicate), None, self.graph):
            result.append(q.object)
            if len(result) > (MAX_OWNED if predicate == "ownedRecord" else MAX_RECORDS):
                raise ProcessingError("Native extraction field exceeds cardinality budget")
        return result

    def one(self, subject, predicate, optional=False):
        result = self.values(subject, predicate)
        if optional and not result:
            return None
        if len(result) != 1:
            raise ProcessingError("Native extraction field missing or duplicated: " + predicate)
        value = result[0]
        if isinstance(value, self.ox.NamedNode):
            return value.value
        datatype = value.datatype.value
        if datatype.endswith("#integer"):
            return int(value.value)
        if datatype.endswith(("#double", "#decimal", "#float")):
            return float(value.value)
        if datatype.endswith("#boolean"):
            return value.value == "true"
        return value.value

    def own(self, node, kind):
        self.add(self.operation, "ownedRecord", node)
        self.add(node, RDF_TYPE, self.ox.NamedNode(F + kind))

    def metadata(self, node, data, allowed):
        if set(data) - set(allowed):
            raise ProcessingError("Unknown extraction metadata fields: " + ",".join(sorted(set(data) - set(allowed))))
        for key, predicate in allowed.items():
            if key in data and data[key] is not None:
                self.add(node, predicate, data[key])

    def evidence(self, node, text, start, end):
        _range(text, start, end)
        self.add(node, "representation", self.ox.NamedNode("urn:semantica:representation:" + hashlib.sha256(self.binding["representation"].encode()).hexdigest()))
        self.add(node, "start", start)
        self.add(node, "end", end)
        cursor = start
        selected = [value for value in self.native_ranges if value['windowStart'] < end and value['windowEnd'] > start]
        if not selected or selected[0]['windowStart'] > start or selected[-1]['windowEnd'] < end:
            raise ProcessingError("NATIVE_GROUNDING_UNSUPPORTED: evidence has no exact scalar proof")
        for index, value in enumerate(selected):
            lo, hi = max(start, value['windowStart']), min(end, value['windowEnd'])
            gap = text[cursor:lo]
            if gap not in {'', '\n', '\n\n'} or (gap and value.get('joinBefore') != gap):
                raise ProcessingError("NATIVE_GROUNDING_UNSUPPORTED: unproven serializer content")
            address = self.ox.NamedNode(node.value + ':range:' + str(index))
            self.own(address, "NativeRange")
            self.add(node, "nativeRange", address)
            self.add(address, "position", index)
            self.add(address, "nativeRef", value['nativeRef'])
            self.add(address, "start", value['start'] + lo - value['windowStart'])
            self.add(address, "end", value['start'] + hi - value['windowStart'])
            self.add(address, "windowStart", lo)
            self.add(address, "windowEnd", hi)
            if gap:
                self.add(address, "joinBefore", gap)
            cursor = hi
        self.add(node, "precision", self.ox.NamedNode(F + "native-scalar-range"))
        self.add(node, "origin", self.ox.NamedNode(F + "unknown"))

    def grounding(self, native_ranges, text):
        if not isinstance(native_ranges, list) or len(native_ranges) > 128:
            raise ProcessingError("Native scalar grounding requires at most 128 proven ranges")
        cursor = 0
        for value in native_ranges:
            if not isinstance(value, dict) or set(value) - {'nativeRef', 'start', 'end', 'windowStart', 'windowEnd', 'joinBefore'}:
                raise ProcessingError("Invalid native scalar grounding fields")
            if not isinstance(value.get('nativeRef'), str) or not value['nativeRef'].startswith('#/document/') or len(value['nativeRef']) > 4096:
                raise ProcessingError("Native grounding must address the canonical reader scalar")
            a, b, lo, hi = (value.get(key) for key in ('start', 'end', 'windowStart', 'windowEnd'))
            if any(type(v) is not int for v in (a, b, lo, hi)) or not (0 <= a < b and cursor <= lo < hi <= len(text) and b - a == hi - lo):
                raise ProcessingError("Invalid native scalar grounding extent")
            if 'joinBefore' in value and (value['joinBefore'] not in {'\n', '\n\n'} or text[cursor:lo] != value['joinBefore']):
                raise ProcessingError("Native scalar serializer separator differs")
            cursor = hi
        self.native_ranges = native_ranges
        return hashlib.sha256(json.dumps(native_ranges, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def entity_node(self, entity):
        mention = entity.metadata.get("mention_id")
        if not isinstance(mention, str) or not mention:
            raise ProcessingError("Native entity requires a located mention identity")
        base = self.owner.extraction_operation_id(self.binding, "entities")
        return self.ox.NamedNode(base + ":entity:" + hashlib.sha256(mention.encode()).hexdigest())

    def write_entity(self, entity, index, text, specification):
        if not isinstance(entity, Entity):
            raise ProcessingError("Native adoption requires Entity values")
        if not isinstance(entity.text, str) or not entity.text or not isinstance(entity.label, str) or not entity.label:
            raise ProcessingError("Native entity name/type must be non-empty strings")
        _range(text, entity.start_char, entity.end_char)
        if text[entity.start_char:entity.end_char] != entity.text:
            raise ProcessingError("Entity mention does not match source window")
        node = self.entity_node(entity)
        self.own(node, "Entity")
        self.add(node, "position", index)
        self.add(node, "name", entity.text)
        self.add(node, "entityType", entity.label)
        self.add(node, "status", self.ox.NamedNode(F + "active"))
        if entity.confidence is not None:
            self.confidence(node, entity.confidence)
        self.metadata(node, {k: v for k, v in entity.metadata.items() if k != "identity_profile"}, {
            "provider": "provider", "model": "model", "extraction_method": "extractionMethod",
            "mention_id": "mentionId", "span_occurrence": "spanOccurrence", "confidence_source": "confidenceSource"})
        mention = self.node("mention:" + str(index))
        self.own(mention, "Mention")
        self.evidence(mention, text, entity.start_char, entity.end_char)
        self.add(mention, "entity", node)
        self.add(node, "mention", mention)
        profile = entity.metadata.get("identity_profile")
        if profile is not None:
            allowed = {"description", "evidence", "evidence_occurrence", "referent_kind", "owner", "instance", "evidence_start", "evidence_end"}
            if not isinstance(profile, dict) or set(profile) - allowed:
                raise ProcessingError("Unknown identity profile field")
            start, end = profile.get("evidence_start"), profile.get("evidence_end")
            _range(text, start, end)
            if text[start:end] != profile.get("evidence"):
                raise ProcessingError("Identity profile evidence does not match source")
            pnode = self.node("profile:" + str(index))
            self.own(pnode, "IdentityProfile")
            self.add(node, "identityProfile", pnode)
            self.evidence(pnode, text, start, end)
            self.metadata(pnode, {k: v for k, v in profile.items() if k not in {"evidence", "evidence_start", "evidence_end"}}, {
                "description": "description", "evidence_occurrence": "evidenceOccurrence", "referent_kind": "referentKind", "owner": "identityOwner", "instance": "identityInstance"})
        definitions = {}
        if specification is not None:
            definitions = next((item.attributes for item in specification.entity_types if item.name == entity.label), {})
        if set(entity.attributes) - set(definitions):
            raise ProcessingError("Entity attributes require their native specification")
        for name, value in entity.attributes.items():
            definition = definitions[name]
            kind = definition.type
            vals = value if kind.endswith("_list") else [value]
            if kind.endswith("_list") and not isinstance(value, list):
                raise ProcessingError("Native attribute requires a list")
            anode = self.node("attribute:" + str(index) + ":" + hashlib.sha256(name.encode()).hexdigest())
            self.own(anode, "AttributeValue")
            self.add(node, "attribute", anode)
            self.add(anode, "definition", self.ox.NamedNode("urn:semantica:attribute:" + hashlib.sha256((self.binding["specification"] + entity.label + ":" + name).encode()).hexdigest()))
            self.add(anode, "attributeName", name)
            self.add(anode, "attributeType", kind)
            for pos, item in enumerate(vals):
                scalar = kind.removesuffix("_list")
                valid = (scalar == "string" and type(item) is str or scalar == "number" and type(item) in (int, float) or scalar == "integer" and type(item) is int or scalar == "boolean" and type(item) is bool)
                if not valid:
                    raise ProcessingError("Native attribute type does not match specification")
                if kind.endswith("_list"):
                    element = self.ox.NamedNode(anode.value + ":" + str(pos))
                    self.own(element, "AttributeElement")
                    self.add(anode, "element", element)
                    self.add(element, "position", pos)
                    self.add(element, "value", item)
                else:
                    self.add(anode, "value", item)

    @property
    def identity_projection_graph(self):
        """Derived addresses share the native owner; accepted facts stay immutable."""
        return self.ox.NamedNode(self.operation.value + ':identity-projection')

    def _owns(self, node):
        # Membership is a native exact lookup, independent of operation size.
        return next(self.owner.store.quads_for_pattern(self.operation,
            self.ox.NamedNode(F + 'ownedRecord'), node, self.graph), None) is not None

    def _identity_member(self, identity):
        if self.stage != 'entities' or self.receipt() is None:
            raise ProcessingError('Identity projection requires accepted native entities')
        if not isinstance(identity, str) or not identity.startswith(self.operation.value + ':'):
            raise ProcessingError('Identity projection requires native entity membership')
        node = self.ox.NamedNode(identity)
        if self.one(node, RDF_TYPE) != F + 'Entity' or not self._owns(node):
            raise ProcessingError('Identity projection requires native entity membership')
        return node

    @classmethod
    def from_identity_reference(cls, owner, project, identity):
        """Open an accepted native Entity by its current project-scoped address.

        Each binding field is a point read with bounded cardinality; callers page
        Entity addresses through the existing pending-build membership cursor.
        """
        if (not isinstance(project,str) or not project or not isinstance(identity,str)
                or len(identity.encode())>4096
                or not re.fullmatch(r'urn:semantica:extraction:[0-9a-f]{64}:entity:[0-9a-f]{64}',identity)):
            raise ProcessingError('Invalid native identity reference')
        ox=owner._oxigraph
        operation=ox.NamedNode(identity.rsplit(':entity:',1)[0])
        graph=ox.NamedNode('urn:semantica:project:'+hashlib.sha256(project.encode()).hexdigest())
        binding={}
        for key in BINDING:
            values=[]
            for quad in owner.store.quads_for_pattern(operation,
                    ox.NamedNode(F+'binding'+key[0].upper()+key[1:]),None,graph):
                if values:
                    raise ProcessingError('Native identity binding is duplicated')
                values.append(quad.object)
            if len(values)!=1 or not isinstance(values[0],ox.Literal):
                raise ProcessingError('Native identity binding is missing')
            value=values[0]
            if len(value.value.encode())>4096:
                raise ProcessingError('Native identity binding exceeds byte budget')
            binding[key]=int(value.value) if value.datatype.value.endswith('#integer') else value.value
        if binding['project']!=project:
            raise ProcessingError('Native identity project differs')
        result=cls(owner,binding,'entities')
        if result.operation!=operation:
            raise ProcessingError('Native identity operation differs from binding')
        result._identity_member(identity)
        return result

    def write_identity_projection(self, identity, *, mention_id, representation_id,
                                  context_start, context_end, evidence_ids, metadata):
        """Persist only derived identity scalars and source addresses, never text/DTOs.

        Coordinates are absolute reader character addresses. Attribute values and
        identity profiles remain solely in the accepted native extraction records.
        The source producer flushes derived projections before handing them off.
        """
        node = self._identity_member(identity)
        scalar_fields = {'identity_scope':'identityScope',
            'identity_context_evidence_id':'contextEvidenceId', 'extraction_method':'extractionMethod',
            'detected_label':'detectedLabel', 'description_mention_id':'descriptionMentionId'}
        if (not isinstance(metadata, dict) or set(metadata) -
                (set(scalar_fields) | {'source_ids','description_evidence_ids','identity_profile'})):
            raise ProcessingError('Unknown identity projection metadata')
        if metadata.get('source_ids') != [self.binding['source']]:
            raise ProcessingError('Identity projection source differs from accepted extraction')
        if metadata.get('identity_scope') != representation_id:
            raise ProcessingError('Identity projection representation differs')
        strings = [mention_id, representation_id, *[metadata[k] for k in scalar_fields if k in metadata]]
        if any(not isinstance(v,str) or not v or len(v.encode()) > 4096 for v in strings):
            raise ProcessingError('Identity projection requires bounded scalar identities')
        if (type(context_start) is not int or type(context_end) is not int
                or not 0 <= context_start < context_end or context_end-context_start > 65536):
            raise ProcessingError('Identity projection context range exceeds budget')
        mention = self.ox.NamedNode(self.one(node, 'mention'))
        lo = self.binding['window_start'] + self.one(mention,'start')
        hi = self.binding['window_start'] + self.one(mention,'end')
        if not context_start <= lo < hi <= context_end:
            raise ProcessingError('Identity projection context does not contain native mention')
        lists = {'evidenceId':evidence_ids,
                 'descriptionEvidenceId':metadata.get('description_evidence_ids',[])}
        for values in lists.values():
            if (not isinstance(values,list) or len(values)>128
                    or any(not isinstance(v,str) or not v or len(v.encode())>4096 for v in values)
                    or len(set(values)) != len(values)):
                raise ProcessingError('Identity projection evidence exceeds address budget')
        if not evidence_ids:
            raise ProcessingError('Identity projection requires evidence addresses')
        graph = self.identity_projection_graph
        quads = []
        def add(subject,key,value):
            if not isinstance(value,self.ox.NamedNode):
                value = self.ox.Literal(value)
            quads.append(self.ox.Quad(subject,self.ox.NamedNode(F+key),value,graph))
        add(node,'buildMentionId',mention_id)
        add(node,'buildRepresentationId',representation_id)
        add(node,'contextStart',context_start)
        add(node,'contextEnd',context_end)
        for key, predicate in scalar_fields.items():
            if key in metadata:
                add(node,predicate,metadata[key])
        for key, values in lists.items():
            for index,value in enumerate(values):
                address = self.ox.NamedNode(identity+':'+key+':'+str(index))
                add(node,key,address)
                add(address,'position',index)
                add(address,'referenceId',value)
        digest = _hash(quads)
        with self.owner._publication_lock:
            old = list(self.owner.store.quads_for_pattern(node,self.ox.NamedNode(F+'identityProjectionDigest'),None,graph))
            if old:
                if len(old)!=1 or old[0].object.value != digest:
                    raise ProcessingError('Native identity projection differs from existing derivation')
                self._read_identity_projection_fields(node)
                return
            add(node,'identityProjectionDigest',digest)
            serialized = ' .\n'.join(str(q.subject)+' '+str(q.predicate)+' '+str(q.object) for q in quads)
            if len(serialized.encode()) > MAX_PAGE_BYTES:
                raise ProcessingError('Identity projection exceeds byte budget')
            self.owner._update_derived_graph(graph, insert=serialized+' .')

    def _read_identity_projection_fields(self,node):
        graph = self.identity_projection_graph
        facts, size = [], 0
        def append(quad, limit):
            nonlocal size
            size += len(str(quad).encode())
            if len(facts) >= limit or size > MAX_PAGE_BYTES:
                raise ProcessingError('Identity projection exceeds field or byte budget')
            facts.append(quad)
        for quad in self.owner.store.quads_for_pattern(node,None,None,graph):
            append(quad,300)
        children = [q.object for q in facts if q.predicate.value in {F+'evidenceId',F+'descriptionEvidenceId'}]
        if len(children)>256:
            raise ProcessingError('Identity projection exceeds field budget')
        for child in children:
            for quad in self.owner.store.quads_for_pattern(child,None,None,graph):
                append(quad,1024)
        digests = [q.object.value for q in facts if q.predicate.value==F+'identityProjectionDigest']
        if len(digests)!=1 or _hash([q for q in facts if q.predicate.value!=F+'identityProjectionDigest'])!=digests[0]:
            raise ProcessingError('Native identity projection missing or corrupt')
        def one(subject,key):
            values=[q.object for q in facts if q.subject==subject and q.predicate.value==F+key]
            if len(values)!=1:
                raise ProcessingError('Identity projection field missing or duplicated: '+key)
            v=values[0]
            return int(v.value) if isinstance(v,self.ox.Literal) and v.datatype.value.endswith('#integer') else v.value
        def addresses(key):
            refs=[q.object for q in facts if q.subject==node and q.predicate.value==F+key]
            refs.sort(key=lambda ref:one(ref,'position'))
            if [one(ref,'position') for ref in refs]!=list(range(len(refs))):
                raise ProcessingError('Identity projection evidence order corrupt')
            return [one(ref,'referenceId') for ref in refs]
        return facts,one,addresses

    def read_identity_summary(self, identity, *, max_bytes=MAX_PAGE_BYTES):
        """Read only identity addresses and provenance, never original text.

        Canonical membership consumers need names and evidence references, not
        full entity restoration. The accepted projection is checked locally;
        unrelated owned facts and model receipts are not traversed.
        """
        self._read_options(None,max_bytes)
        node=self._identity_member(identity)
        facts,one,addresses=self._read_identity_projection_fields(node)
        metadata={'source_ids':[self.binding['source']]}
        for key,predicate in {'identity_scope':'identityScope',
                'identity_context_evidence_id':'contextEvidenceId','extraction_method':'extractionMethod',
                'detected_label':'detectedLabel','description_mention_id':'descriptionMentionId'}.items():
            if any(q.subject==node and q.predicate.value==F+predicate for q in facts):
                metadata[key]=one(node,predicate)
        result=dict(id=one(node,'buildMentionId'),canonical_name=self.one(node,'name'),
            type=self.one(node,'entityType'),aliases=[],evidence_ids=addresses('evidenceId'),metadata=metadata)
        if self.one(node,'identityProfile',optional=True):
            metadata['description_evidence_ids']=addresses('descriptionEvidenceId')
        if len(json.dumps(result,ensure_ascii=False).encode())>max_bytes:
            raise ProcessingError('Identity summary exceeds byte budget')
        return result

    def read_identity_projection(self, identity, *, read_text, max_bytes=MAX_PAGE_BYTES):
        """Hydrate one identity from accepted values and bounded canonical ranges."""
        return self._read_identity_values(identity,read_text=read_text,max_bytes=max_bytes)

    def read_identity_selection(self, identity, *, description_grounded, max_bytes=MAX_PAGE_BYTES):
        """Read existing field values for a decision without reopening original prose.

        Grounding is an observation produced during the sole source-feature read,
        not a replacement description or a second cached entity. Profile evidence
        stays at its native address and is restored only by its actual consumer.
        """
        if type(description_grounded) is not bool:
            raise ProcessingError('Identity selection requires an exact grounding observation')
        return self._read_identity_values(identity,read_text=None,max_bytes=max_bytes,
            description_grounded=description_grounded)

    def _read_identity_values(self, identity, *, read_text, max_bytes, description_grounded=None):
        self._read_options(None,max_bytes)
        node=self._identity_member(identity)
        facts,one,addresses=self._read_identity_projection_fields(node)
        start,end=one(node,'contextStart'),one(node,'contextEnd')
        if not 0 <= start < end or end-start>min(65536,max_bytes):
            raise ProcessingError('Identity projection context exceeds byte budget')
        context=read_text(start,end) if read_text is not None else ''
        if read_text is not None and (not isinstance(context,str) or len(context)!=end-start):
            raise ProcessingError('Identity projection source range differs')
        attrs={}
        for attr in self.values(node,'attribute'):
            name,kind=self.one(attr,'attributeName'),self.one(attr,'attributeType')
            if kind.endswith('_list'):
                elements=sorted(self.values(attr,'element'),key=lambda n:self.one(n,'position'))
                if [self.one(n,'position') for n in elements]!=list(range(len(elements))):
                    raise ProcessingError('Native attribute list positions invalid')
                attrs[name]=[self.one(n,'value') for n in elements]
            else:
                attrs[name]=self.one(attr,'value')
        metadata={'source_ids':[self.binding['source']]}
        for key,predicate in {'identity_scope':'identityScope',
                'identity_context_evidence_id':'contextEvidenceId','extraction_method':'extractionMethod',
                'detected_label':'detectedLabel','description_mention_id':'descriptionMentionId'}.items():
            if any(q.subject==node and q.predicate.value==F+predicate for q in facts):
                metadata[key]=one(node,predicate)
        description=str(attrs.get('description','')).strip()
        grounded=(description.casefold() in context.casefold() if read_text is not None
            else description_grounded)
        if not description or not grounded:
            description=''
        profile_id=self.one(node,'identityProfile',optional=True)
        if profile_id:
            profile=self.ox.NamedNode(profile_id)
            ps=self.one(profile,'start')+self.binding['window_start']
            pe=self.one(profile,'end')+self.binding['window_start']
            if not 0 <= ps < pe or pe-ps>min(65536,max_bytes):
                raise ProcessingError('Identity profile exceeds byte budget')
            value=self.read_metadata(profile,{'description':'description','evidence_occurrence':'evidenceOccurrence',
                'referent_kind':'referentKind','owner':'identityOwner','instance':'identityInstance'})
            value.update(evidence_start=ps,evidence_end=pe)
            if read_text is not None:
                quote=read_text(ps,pe)
                if not isinstance(quote,str) or len(quote)!=pe-ps:
                    raise ProcessingError('Identity profile source range differs')
                value['evidence']=quote
            metadata['identity_profile']=value
            metadata['description_evidence_ids']=addresses('descriptionEvidenceId')
            description=(value.get('description') or '').strip()
        result=dict(id=one(node,'buildMentionId'),canonical_name=self.one(node,'name'),
            type=self.one(node,'entityType'),description=description,context=context,
            attributes=attrs,aliases=[],evidence_ids=addresses('evidenceId'),status='candidate',metadata=metadata)
        if len(json.dumps(result,ensure_ascii=False).encode())>max_bytes:
            raise ProcessingError('Identity projection exceeds byte budget')
        self.receipt()
        return result

    @classmethod
    def from_fact_reference(cls, owner, project, identity):
        """Point-open one accepted native relation without retaining a source DTO."""
        if not isinstance(identity,str) or not re.fullmatch(
                r'urn:semantica:extraction:[0-9a-f]{64}:relation:[0-9]+',identity):
            raise ProcessingError('Invalid native fact reference')
        operation=identity.rsplit(':relation:',1)[0]
        ox=owner._oxigraph
        graph=ox.NamedNode('urn:semantica:project:'+hashlib.sha256(project.encode()).hexdigest())
        binding={}
        for key in BINDING:
            values=[]
            for quad in owner.store.quads_for_pattern(ox.NamedNode(operation),
                    ox.NamedNode(F+'binding'+key[0].upper()+key[1:]),None,graph):
                if values:
                    raise ProcessingError('Native fact binding duplicated')
                values.append(quad.object)
            if len(values)!=1 or not isinstance(values[0],ox.Literal) or len(values[0].value.encode())>4096:
                raise ProcessingError('Native fact binding missing or invalid')
            value=values[0]
            binding[key]=int(value.value) if value.datatype.value.endswith('#integer') else value.value
        result=cls(owner,binding,'relations')
        if binding['project']!=project or result.operation.value!=operation:
            raise ProcessingError('Native fact binding differs')
        result._fact_member(identity)
        return result

    def _fact_member(self, identity):
        if self.stage!='relations' or self.receipt() is None:
            raise ProcessingError('Fact projection requires accepted native Relation membership')
        return self._fact_member_node(identity)

    def _fact_member_node(self, identity):
        node=self.ox.NamedNode(identity)
        if (not identity.startswith(self.operation.value+':relation:')
                or self.one(node,RDF_TYPE)!=F+'Relation'
                or not self._owns(node)):
            raise ProcessingError('Fact projection requires accepted native Relation membership')
        return node

    @property
    def fact_projection_graph(self):
        return self.ox.NamedNode(self.operation.value+':fact-projection')

    def write_fact_projection(self, identity, *, assertion_id, relation_id,
                              source_id, target_id, predicate, qualifiers, evidence_ids):
        """Store derived addresses; the source producer flushes before handoff."""
        from ..semantic_extract.schemas import validate_fact_qualifiers
        validate_fact_qualifiers(qualifiers)
        node=self._fact_member(identity)
        if qualifiers != self.fact_qualifiers(node):
            raise ProcessingError('Fact projection qualifiers differ from native observation')
        scalars=dict(buildAssertionId=assertion_id,buildRelationId=relation_id,
            buildSourceId=source_id,buildTargetId=target_id,buildPredicate=predicate)
        if (not isinstance(evidence_ids,list) or not 0<len(evidence_ids)<=128
                or any(not isinstance(value,str) or not value or len(value.encode())>16384
                    for value in [*scalars.values(),*evidence_ids])):
            raise ProcessingError('Fact projection scalar/address budget exceeded')
        graph=self.fact_projection_graph
        quads=[]
        def add(subject,key,value):
            quads.append(self.ox.Quad(subject,self.ox.NamedNode(F+key),
                value if isinstance(value,self.ox.NamedNode) else self.ox.Literal(value),graph))
        for key,value in scalars.items():
            add(node,key,value)
        for position,value in enumerate(evidence_ids):
            address=self.ox.NamedNode(identity+':build-evidence:'+str(position))
            add(node,'buildEvidence',address)
            add(address,'position',position)
            add(address,'referenceId',value)
        digest=_hash(quads)
        add(node,'factProjectionDigest',digest)
        if sum(len(str(q).encode()) for q in quads)>MAX_PAGE_BYTES:
            raise ProcessingError('Fact projection byte budget exceeded')
        with self.owner._publication_lock:
            old=list(self.owner.store.quads_for_pattern(node,self.ox.NamedNode(F+'factProjectionDigest'),None,graph))
            if old:
                if len(old)!=1 or old[0].object.value!=digest:
                    raise ProcessingError('Native fact projection differs from existing derivation')
                self.read_fact_projection(identity,'relation')
                return
            serialized=' .\n'.join(str(q.subject)+' '+str(q.predicate)+' '+str(q.object) for q in quads)
            self.owner._update_derived_graph(graph, insert=serialized+' .')

    def fact_qualifiers(self,node):
        """The immutable extraction, not its address projection, owns semantics."""
        from ..semantic_extract.schemas import validate_fact_qualifiers
        values=self.read_metadata(node,dict(polarity='polarity',condition='condition',
            time='time',unit='unit',value='qualifiedValue'))
        if 'polarity' in values:
            values['polarity']=values['polarity'].removeprefix(F)
        return validate_fact_qualifiers(values)

    def migrate_fact_projection(self,identity):
        """Explicit offline metadata conversion; native facts and IDs stay put."""
        with self.owner._publication_lock:
            node=self._fact_member(identity)
            graph=self.fact_projection_graph
            payload=list(islice(self.owner.store.quads_for_pattern(node,None,None,graph),33))
            children=[q.object for q in payload if q.predicate.value==F+'buildEvidence']
            if len(payload)>32 or not 0<len(children)<=128:
                raise ProcessingError('Fact projection migration exceeds address budget')
            for child in children:
                fields=list(islice(self.owner.store.quads_for_pattern(child,None,None,graph),4))
                if len(fields)!=2:
                    raise ProcessingError('Fact projection migration evidence fields invalid')
                payload.extend(fields)
            if len(payload)>1024 or sum(len(str(q).encode()) for q in payload)>MAX_PAGE_BYTES:
                raise ProcessingError('Fact projection migration exceeds byte budget')
            digests=[q for q in payload if q.predicate.value==F+'factProjectionDigest']
            body=[q for q in payload if q not in digests]
            if len(digests)!=1 or _hash(body)!=digests[0].object.value:
                raise ProcessingError('Native fact projection corrupt')
            obsolete=[q for q in body if q.predicate.value.startswith(F+'buildQualifier')]
            if not obsolete:
                self.read_fact_projections(identity)
                return False
            expected={'buildQualifier'+k.title():v for k,v in self.fact_qualifiers(node).items()}
            actual={q.predicate.value[len(F):]:q.object.value for q in obsolete}
            if actual!=expected or len(actual)!=len(obsolete):
                raise ProcessingError('Projection migration qualifiers differ from native facts')
            current=[q for q in body if q not in obsolete]
            digest=self.ox.Quad(node,self.ox.NamedNode(F+'factProjectionDigest'),
                self.ox.Literal(_hash(current)),graph)
            def triples(quads):
                return ' '.join(f'{q.subject} {q.predicate} {q.object} .' for q in quads)
            self.owner._update_derived_graph(graph,delete=triples(obsolete+digests),insert=triples([digest]))
            self.owner.flush()
            self.read_fact_projections(identity)
            return True

    def read_fact_projection(self, identity, kind):
        """Hydrate exactly one source observation; canonical remapping is separate."""
        if kind not in {'assertion', 'relation'}:
            raise ProcessingError('Unknown native fact projection kind')
        return self._read_fact_projections(identity, (kind,))[kind]

    def read_fact_projections(self, identity):
        """Project the two public expressions from one immutable observation."""
        return self._read_fact_projections(identity, ('assertion', 'relation'))

    @classmethod
    def read_fact_projection_page(cls,owner,project,identities):
        """Share operation admission only within one bounded, locked read page."""
        if (not isinstance(identities,list) or len(identities)>128
                or any(not isinstance(value,str) or not re.fullmatch(
                    r'urn:semantica:extraction:[0-9a-f]{64}:relation:[0-9]+',value)
                    for value in identities) or len(set(identities))!=len(identities)):
            raise ProcessingError('Invalid native fact projection page')
        from ..semantic_worker_context import check_query_cancellation
        with owner._publication_lock:
            operations,result={},{}
            size=0
            for identity in identities:
                check_query_cancellation()
                operation=identity.rsplit(':relation:',1)[0]
                records=operations.get(operation)
                if records is None:
                    records=cls.from_fact_reference(owner,project,identity)
                    operations[operation]=records
                    node=records.ox.NamedNode(identity)
                else:
                    node=records._fact_member_node(identity)
                projections,amount=records._read_fact_projection_node(
                    node,None)
                size+=amount
                if size>16*1024*1024:
                    raise ProcessingError('Fact projection page byte budget exceeded')
                result[identity]=projections
            return result

    def _read_fact_projections(self, identity, kinds):
        node=self._fact_member(identity)
        return self._read_fact_projection_node(node,kinds)[0]

    def _read_fact_projection_node(self,node,kinds):
        graph=self.fact_projection_graph
        facts=[]
        projection_fields={}
        size=0
        def append(quad):
            nonlocal size
            size+=len(str(quad).encode())
            if len(facts)>=1024 or size>MAX_PAGE_BYTES:
                raise ProcessingError('Fact projection byte/cardinality budget exceeded')
            facts.append(quad)
            projection_fields.setdefault((quad.subject,quad.predicate.value),[]).append(quad.object.value)
        for quad in self.owner.store.quads_for_pattern(node,None,None,graph):
            append(quad)
        def one(subject,key,optional=False):
            values=projection_fields.get((subject,F+key),[])
            if optional and not values:
                return None
            if len(values)!=1:
                raise ProcessingError('Native fact projection field missing or duplicated')
            return values[0]
        children=[q.object for q in facts if q.predicate.value==F+'buildEvidence']
        if not 0<len(children)<=128:
            raise ProcessingError('Native fact projection missing evidence')
        for child in children:
            for quad in self.owner.store.quads_for_pattern(child,None,None,graph):
                append(quad)
        digest=one(node,'factProjectionDigest')
        if _hash([q for q in facts if q.predicate.value!=F+'factProjectionDigest'])!=digest:
            raise ProcessingError('Native fact projection corrupt')
        children.sort(key=lambda child:int(one(child,'position')))
        if [int(one(child,'position')) for child in children]!=list(range(len(children))):
            raise ProcessingError('Native fact projection evidence order corrupt')
        evidence=[one(child,'referenceId') for child in children]
        if any(key.startswith(F+'buildQualifier') for _,key in projection_fields):
            raise ProcessingError('Obsolete fact projection requires offline metadata migration')
        qualifiers=self.fact_qualifiers(node)
        physical=dict(id=one(node,'buildRelationId'),assertion=one(node,'buildAssertionId'),
            source=one(node,'buildSourceId'),target=one(node,'buildTargetId'),
            predicate=one(node,'buildPredicate'),qualifiers=qualifiers,evidence=evidence)
        if kinds is None or 'assertion' in kinds:
            target=self.ox.NamedNode(self.one(node,'targetEntity'))
            physical['object']=self.one(target,'name').strip()
        if kinds is None:
            return physical,size
        result={}
        shared=dict(qualifiers=qualifiers,evidence_ids=evidence,support_ids=evidence,
            status='candidate',metadata={})
        if 'relation' in kinds:
            result['relation']=dict(id=physical['id'],source_entity_id=physical['source'],
                target_entity_id=physical['target'],type=physical['predicate'],**shared)
        if 'assertion' in kinds:
            result['assertion']=dict(id=physical['assertion'],subject_id=physical['source'],
                object_entity_id=physical['target'],predicate=physical['predicate'],
                object=physical['object'],**shared)
        return result,size

    def confidence(self, node, value):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ProcessingError("Native confidence is invalid")
        self.add(node, "confidence", value)

    def write_relation(self, relation, index, text):
        if not isinstance(relation, Relation):
            raise ProcessingError("Native adoption requires Relation values")
        node = self.node("relation:" + str(index))
        self.own(node, "Relation")
        self.add(node, "position", index)
        for key, entity in (("sourceEntity", relation.subject), ("targetEntity", relation.object)):
            endpoint = self.entity_node(entity)
            if self.one(endpoint, "name", optional=True) != entity.text:
                raise ProcessingError("Relation endpoint has not been natively adopted")
            self.add(node, key, endpoint)
        self.add(node, "relationType", self.ox.NamedNode("urn:semantica:predicate:" + hashlib.sha256(relation.predicate.encode()).hexdigest()))
        self.add(node, "predicateName", relation.predicate)
        self.add(node, "status", self.ox.NamedNode(F + "active"))
        self.confidence(node, relation.confidence)
        data = relation.metadata
        allowed = {"provider", "model", "extraction_method", "subject_id", "object_id", "evidence_start", "evidence_end", "evidence_occurrence", "qualifiers", "supporting_refs"}
        if set(data) - allowed:
            raise ProcessingError("Unknown relation metadata fields")
        self.metadata(node, {k: data[k] for k in data if k not in {"evidence_start", "evidence_end", "qualifiers", "supporting_refs"}}, {
            "provider": "provider", "model": "model", "extraction_method": "extractionMethod", "subject_id": "subjectId", "object_id": "objectId", "evidence_occurrence": "evidenceOccurrence"})
        evidence = self.node("evidence:" + str(index))
        self.own(evidence, "Evidence")
        self.evidence(evidence, text, data.get("evidence_start"), data.get("evidence_end"))
        if text[data["evidence_start"]:data["evidence_end"]] != relation.context:
            raise ProcessingError("Relation evidence differs from source range")
        self.add(node, "evidence", evidence)
        from ..semantic_extract.schemas import validate_fact_qualifiers
        qualifiers = validate_fact_qualifiers(data.get("qualifiers"))
        for key, value in qualifiers.items():
            self.add(node, {"value": "qualifiedValue"}.get(key, key), self.ox.NamedNode(F + value) if key == "polarity" else value)
        refs = data.get("supporting_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs) or len(refs) > 256:
            raise ProcessingError("Invalid native relation support references")
        for ref in dict.fromkeys(refs):
            self.add(node, "supportingRef", ref)

    def write_receipts(self, receipts):
        if len(receipts) > 16:
            raise ProcessingError("Extraction receipt count exceeds budget")
        fields = {"id": "receiptId", "operation": "receiptOperation", "provider": "provider", "model": "model", "input_digest": "inputDigest", "output_digest": "outputDigest", "created_at": "createdAt"}
        for index, receipt in enumerate(receipts):
            if hasattr(receipt, "model_dump"):
                receipt = receipt.model_dump(mode="json")
            if not isinstance(receipt, dict) or set(receipt) - (set(fields) | {"parameters", "metadata"}):
                raise ProcessingError("Unknown model receipt fields")
            if any(not isinstance(receipt.get(key), str) or not receipt[key] for key in set(fields) - {"created_at"}):
                raise ProcessingError("Model receipt requires explicit typed identities")
            if receipt["model"] != self.binding["model"]:
                raise ProcessingError("Model receipt differs from extraction binding")
            node = self.node("model-receipt:" + str(index))
            self.own(node, "ModelReceipt")
            self.add(node, "position", index)
            self.add(self.operation, "modelReceipt", node)
            self.metadata(node, {k: v for k, v in receipt.items() if k in fields}, fields)
            parameters = receipt.get("parameters", {})
            if not isinstance(parameters, dict) or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in parameters.values()):
                raise ProcessingError("Model receipt parameters require finite nonnegative numeric fields")
            self.metadata(node, parameters, {"temperature": "temperature", "top_p": "topP", "max_tokens": "maxTokens", "max_output_tokens": "maxOutputTokens"})
            metadata = receipt.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ProcessingError("Model receipt metadata must use named typed fields")
            if set(metadata) - {"usage", "extraction_stage", "rejected_count"}:
                raise ProcessingError("Unknown model receipt metadata")
            self.metadata(node, {k: v for k, v in metadata.items() if k != "usage"}, {"extraction_stage": "extractionStage", "rejected_count": "rejectedCount"})
            usage = metadata.get("usage", {})
            if not isinstance(usage, dict) or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in usage.values()):
                raise ProcessingError("Model receipt usage requires finite nonnegative numeric fields")
            self.metadata(node, usage, {"prompt_tokens": "promptTokens", "completion_tokens": "completionTokens", "total_tokens": "totalTokens", "input_tokens": "inputTokens", "output_tokens": "outputTokens"})

    def receipt(self):
        if not self.indexed:
            return None
        # The atomic, persisted operation is authoritative; payload audit is explicit.
        with self.owner._publication_lock:
            links = list(islice(self.owner.store.quads_for_pattern(self.logical,
                self.ox.NamedNode(F + "physicalOperation"), None, self.index_graph), 2))
            if len(links) != 1 or links[0].object != self.operation:
                raise ExtractionIdentityStaleError("Native extraction identity binding is stale or corrupt")
            return self._completion_receipt()

    def audit(self):
        """Explicit integrity maintenance, including every owned fact and digest."""
        with self.owner._publication_lock:
            if self.receipt() is None:
                return None
            return self._verify_receipt()

    def _completion_receipt(self):
        present = self.values(self.operation, RDF_TYPE)
        if not present:
            if self.indexed:
                raise ProcessingError("Native extraction identity index references a missing paid operation")
            return None
        if present != [self.ox.NamedNode(F + "ExtractionOperation")]:
            raise ProcessingError("Invalid native extraction receipt type")
        if self.one(self.operation, "operationIdentity") != self.operation.value:
            raise ProcessingError("Native extraction receipt identity mismatch")
        for key, expected in self.binding.items():
            if self.one(self.operation, "binding" + key[0].upper() + key[1:]) != expected:
                raise ExtractionIdentityStaleError("Native extraction indexed binding differs")
        if self.stage in {"entities", "relations"} and self.one(self.operation, "extractionStage") != self.stage:
            raise ProcessingError("Native extraction indexed stage differs")
        for field in ("operationDigest", "factsDigest"):
            digest = self.one(self.operation, field)
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ProcessingError("Native extraction completion digest is corrupt")
        for field, maximum in (("resultCount", MAX_RECORDS), ("ownedCount", MAX_OWNED), ("quadCount", MAX_QUADS)):
            value = self.one(self.operation, field)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ProcessingError("Native extraction completion count is corrupt")
        accepted = self.one(self.operation, "acceptedDigest")
        if not isinstance(accepted, str) or not accepted:
            raise ProcessingError("Native extraction accepted digest is corrupt")
        return {"operation_id": self.operation.value, "accepted_digest": accepted, "count": self.one(self.operation, "resultCount")}

    def _verify_receipt(self):
        receipt = self._completion_receipt()
        if receipt is None:
            return None
        operation_facts = []
        operation_digest_predicate = self.ox.NamedNode(F + "operationDigest")
        for quad in self.owner.store.quads_for_pattern(self.operation, None, None, self.graph):
            if quad.predicate != operation_digest_predicate:
                operation_facts.append(quad)
            if len(operation_facts) > MAX_OWNED + MAX_RECORDS + 128:
                raise ProcessingError("Native extraction operation receipt exceeds budget")
        if _hash(operation_facts) != self.one(self.operation, "operationDigest"):
            raise ProcessingError("Native extraction operation receipt missing or corrupt")
        facts = []
        byte_count = 0
        subjects = self.values(self.operation, "ownedRecord")
        if len(subjects) != self.one(self.operation, "ownedCount"):
            raise ProcessingError("Native extraction records missing")
        for subject in subjects:
            for quad in self.owner.store.quads_for_pattern(subject, None, None, self.graph):
                facts.append(quad)
                byte_count += len(_triple(quad).encode()) + 3
                if len(facts) > MAX_QUADS or byte_count > MAX_BYTES:
                    raise ProcessingError("Native extraction fact read exceeds budget")
        if _hash(facts) != self.one(self.operation, "factsDigest") or len(facts) != self.one(self.operation, "quadCount"):
            raise ProcessingError("Native extraction facts missing or corrupt")
        return receipt

    @classmethod
    def rebind(cls, owner, previous, current, stage):
        """Offline metadata migration; owned facts and paid receipt nodes stay put."""
        old_key, new_key = operation_identity(previous, stage), operation_identity(current, stage)
        if any(previous[k] != current[k] for k in BINDING - {"recipe", "parser"}):
            raise ProcessingError("Extraction migration may change only verified recipe and parser identity")
        with owner._publication_lock:
            target = cls(owner, current, stage)
            original = cls(owner, previous, stage)
            if target.indexed:
                if original.operation != target.operation and (original.indexed or original.values(original.operation, RDF_TYPE)):
                    raise ProcessingError("Extraction migration target already owns another paid result")
                if target.one(target.operation, "bindingRecipe") != current["recipe"]:
                    raise ProcessingError("Extraction migration target binding differs")
                return target.audit()
            # A pre-index operation is admitted only by this explicit offline API.
            receipt = original._verify_receipt()
            if receipt is None:
                raise ProcessingError("Extraction migration source receipt is missing")
            for key, value in previous.items():
                if original.one(original.operation, "binding" + key[0].upper() + key[1:]) != value:
                    raise ProcessingError("Extraction migration source binding differs")
            ox = owner._oxigraph
            replace = {ox.NamedNode(F + k) for k in ("bindingRecipe", "bindingParser", "extractionStage", "operationDigest")}
            prior = list(owner.store.quads_for_pattern(original.operation, None, None, original.graph))
            kept = [q for q in prior if q.predicate not in replace]
            changed = [ox.Quad(original.operation, ox.NamedNode(F + "bindingParser"), ox.Literal(current["parser"]), original.graph),
                       ox.Quad(original.operation, ox.NamedNode(F + "bindingRecipe"), ox.Literal(current["recipe"]), original.graph),
                       ox.Quad(original.operation, ox.NamedNode(F + "extractionStage"), ox.Literal(stage), original.graph)]
            if original.one(original.operation, "paidRecipe", optional=True) is None:
                changed.append(ox.Quad(original.operation, ox.NamedNode(F + "paidRecipe"), ox.Literal(previous["recipe"]), original.graph))
            changed.append(ox.Quad(original.operation, ox.NamedNode(F + "operationDigest"), ox.Literal(_hash(kept + changed)), original.graph))
            deletes = " . ".join(_triple(q) for q in prior if q.predicate in replace)
            inserts = " . ".join(_triple(q) for q in changed)
            window_deletes, window_inserts = [], []
            for formula in (False, True):
                def window_node(binding):
                    identity = json.dumps([{k: v for k, v in binding.items() if k != 'grounding'}, formula], sort_keys=True, separators=(',', ':'))
                    return ox.NamedNode('urn:semantica:extraction-window:' + hashlib.sha256(identity.encode()).hexdigest())
                before, after = window_node(previous), window_node(current)
                predicate_node = ox.NamedNode(F + 'completedBatches')
                rows = list(islice(owner.store.quads_for_pattern(before, predicate_node, None, original.index_graph), 2))
                targets = list(islice(owner.store.quads_for_pattern(after, predicate_node, None, original.index_graph), 2))
                if len(rows) > 1 or len(targets) > 1 or (rows and targets and rows[0].object != targets[0].object):
                    raise ProcessingError('Extraction migration window completion conflicts')
                if rows and before != after:
                    if not isinstance(rows[0].object, ox.Literal) or len(rows[0].object.value.encode()) > MAX_PAGE_BYTES:
                        raise ProcessingError('Extraction migration window completion is invalid')
                    window_deletes.append(_triple(rows[0]))
                    window_inserts.append(_triple(ox.Quad(after, predicate_node, rows[0].object, original.index_graph)))
            predicate = "<" + F + "physicalOperation>"
            owner.store.update("DELETE { GRAPH " + str(original.graph) + " { " + deletes + " } GRAPH " + str(original.index_graph) + " { <" + old_key + "> " + predicate + " ?old . " + " . ".join(window_deletes) + " } } "
                + "INSERT { GRAPH " + str(original.graph) + " { " + inserts + " } GRAPH " + str(original.index_graph) + " { <" + new_key + "> " + predicate + " " + str(original.operation) + " . " + " . ".join(window_inserts) + " } } "
                + "WHERE { OPTIONAL { GRAPH " + str(original.index_graph) + " { <" + old_key + "> " + predicate + " ?old } } }")
            owner.flush()
            return cls(owner, current, stage).receipt()

    def adopt(self, values, *, text, accepted_digest, native_ranges, receipts=(), extraction_spec=None):
        if self.owner.path is None:
            raise ProcessingError("Paid extraction adoption requires persistent Oxigraph")
        grounding_digest = self.grounding(native_ranges, text)
        if not self.indexed and self.values(self.operation, RDF_TYPE):
            raise ProcessingError("Native extraction requires explicit offline identity migration")
        existing = self.receipt()
        if existing is not None:
            if existing["accepted_digest"] != accepted_digest:
                raise ProcessingError("Native extraction accepted digest differs")
            if self.one(self.operation, "nativeGroundingDigest") != grounding_digest:
                raise ProcessingError("Native extraction scalar grounding differs")
            self.owner.flush()
            return existing
        if not isinstance(values, list) or len(values) > MAX_RECORDS:
            raise ProcessingError("Native extraction result exceeds record budget")
        if len(text) != self.binding["window_end"] - self.binding["window_start"]:
            raise ProcessingError("Extraction source window length mismatch")
        for index, value in enumerate(values):
            if self.stage == "entities":
                self.write_entity(value, index, text, extraction_spec)
            else:
                self.write_relation(value, index, text)
        self.write_receipts(receipts)
        self.add(self.operation, "nativeGroundingDigest", grounding_digest)
        return self.commit(len(values), accepted_digest)

    def commit(self, result_count, accepted_digest):
        """One native atomic insertion binds typed facts and their audit receipt."""
        facts = [q for q in self.quads if q.subject != self.operation]
        if len({q.subject for q in facts}) > MAX_OWNED:
            raise ProcessingError("Native extraction exceeds owned record budget")
        self.add(self.operation, RDF_TYPE, self.ox.NamedNode(F + "ExtractionOperation"))
        self.add(self.operation, "operationIdentity", self.operation.value)
        if self.stage in {"entities", "relations"}:
            self.add(self.operation, "extractionStage", self.stage)
        self.add(self.operation, "acceptedDigest", accepted_digest)
        self.add(self.operation, "resultCount", result_count)
        self.add(self.operation, "ownedCount", len({q.subject for q in facts}))
        self.add(self.operation, "quadCount", len(facts))
        self.add(self.operation, "factsDigest", _hash(facts))
        self.add(self.operation, "paidRecipe", self.binding["recipe"])
        for key, value in self.binding.items():
            self.add(self.operation, "binding" + key[0].upper() + key[1:], value)
        self.add(self.operation, "operationDigest", _hash([q for q in self.quads if q.subject == self.operation]))
        serialized = " .\n".join(_triple(q) for q in self.quads)
        if len(serialized.encode()) > MAX_BYTES:
            raise ProcessingError("Native extraction exceeds atomic byte budget")
        index = (" GRAPH " + str(self.index_graph) + " { " + str(self.logical) + " <" + F + "physicalOperation> " + str(self.operation) + " . }"
                 if self.index_graph is not None else "")
        self.owner.store.update("INSERT DATA { GRAPH " + str(self.graph) + " { " + serialized + " . }" + index + " }")
        self.indexed = True
        self.owner.flush()
        return self.receipt()

    def read(self, *, text, native_ranges, entities=None, extraction_spec=None):
        receipt = self.receipt()
        if receipt is None:
            raise ProcessingError("Native extraction receipt missing")
        if self.one(self.operation, "nativeGroundingDigest") != self.grounding(native_ranges, text):
            raise ProcessingError("Native extraction scalar grounding differs")
        if len(text) != self.binding["window_end"] - self.binding["window_start"]:
            raise ProcessingError("Extraction read source window mismatch")
        kind = "Entity" if self.stage == "entities" else "Relation"
        nodes = [n for n in self.values(self.operation, "ownedRecord") if self.one(n, RDF_TYPE) == F + kind]
        nodes.sort(key=lambda n: self.one(n, "position"))
        if len(nodes) != receipt["count"]:
            raise ProcessingError("Native extraction result cardinality differs")
        result = []
        lookup = {self.entity_node(entity).value: entity for entity in (entities or [])}
        for node in nodes:
            if self.stage == "entities":
                mention = self.ox.NamedNode(self.one(node, "mention"))
                start, end = self.one(mention, "start"), self.one(mention, "end")
                _range(text, start, end)
                name = self.one(node, "name")
                if text[start:end] != name:
                    raise ProcessingError("Stored entity mention differs from source")
                metadata = self.read_metadata(node, {"provider": "provider", "model": "model", "extraction_method": "extractionMethod", "mention_id": "mentionId", "span_occurrence": "spanOccurrence", "confidence_source": "confidenceSource"})
                profile_id = self.one(node, "identityProfile", optional=True)
                if profile_id is not None:
                    profile = self.ox.NamedNode(profile_id)
                    ps, pe = self.one(profile, "start"), self.one(profile, "end")
                    _range(text, ps, pe)
                    metadata["identity_profile"] = {**self.read_metadata(profile, {"description": "description", "evidence_occurrence": "evidenceOccurrence", "referent_kind": "referentKind", "owner": "identityOwner", "instance": "identityInstance"}), "evidence_start": ps, "evidence_end": pe, "evidence": text[ps:pe]}
                attributes = {}
                for attr in self.values(node, "attribute"):
                    name, atype = self.one(attr, "attributeName"), self.one(attr, "attributeType")
                    if atype.endswith("_list"):
                        elements = sorted(self.values(attr, "element"), key=lambda n: self.one(n, "position"))
                        if [self.one(n, "position") for n in elements] != list(range(len(elements))):
                            raise ProcessingError("Native attribute list positions invalid")
                        attributes[name] = [self.one(element, "value") for element in elements]
                    else:
                        attributes[name] = self.one(attr, "value")
                result.append(Entity(self.one(node, "name"), self.one(node, "entityType"), start, end, self.one(node, "confidence", optional=True), metadata, attributes))
            else:
                source, target = self.one(node, "sourceEntity"), self.one(node, "targetEntity")
                if source not in lookup or target not in lookup:
                    raise ProcessingError("Native relation endpoint missing from accepted entities")
                evidence = self.ox.NamedNode(self.one(node, "evidence"))
                start, end = self.one(evidence, "start"), self.one(evidence, "end")
                _range(text, start, end)
                qualifiers = self.read_metadata(node, {"polarity": "polarity", "condition": "condition", "time": "time", "unit": "unit", "value": "qualifiedValue"})
                qualifiers["polarity"] = qualifiers["polarity"].removeprefix(F)
                metadata = self.read_metadata(node, {"provider": "provider", "model": "model", "extraction_method": "extractionMethod", "subject_id": "subjectId", "object_id": "objectId", "evidence_occurrence": "evidenceOccurrence"})
                metadata.update(evidence_start=start, evidence_end=end, qualifiers=qualifiers, supporting_refs=sorted(ref.value for ref in self.values(node, "supportingRef")))
                result.append(Relation(lookup[source], self.one(node, "predicateName"), lookup[target], self.one(node, "confidence"), text[start:end], metadata))
        return result

    @staticmethod
    def _read_options(fields, max_bytes):
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_PAGE_BYTES:
            raise ProcessingError("Native extraction read byte budget must be 1..262144")
        if fields is not None and (not isinstance(fields, list) or not 1 <= len(fields) <= MAX_PAGE_ROWS
                or any(not isinstance(field, str) or
                    (field != RDF_TYPE and re.fullmatch(re.escape(F) + r"[A-Za-z][A-Za-z0-9]*", field) is None)
                    for field in fields) or len(set(fields)) != len(fields)):
            raise ProcessingError("Native extraction field projection is invalid")

    def _read_nodes(self, record_ids, fields, max_bytes):
        result, size = [], 0
        for identity in record_ids:
            if not isinstance(identity, str) or len(identity) > 4096 or not identity.startswith(self.operation.value + ":"):
                raise ProcessingError("Native extraction record is not owned by this operation")
            node = self.ox.NamedNode(identity)
            owned = self.owner.store.quads_for_pattern(self.operation, self.ox.NamedNode(F + "ownedRecord"), node, self.graph)
            if next(iter(owned), None) is None:
                raise ProcessingError("Native extraction record is not owned by this operation")
            record = dict(id=identity, fields={})
            predicates = [self.ox.NamedNode(field) for field in fields] if fields is not None else [None]
            for predicate in predicates:
                for quad in self.owner.store.quads_for_pattern(node, predicate, None, self.graph):
                    value = dict(type="iri" if isinstance(quad.object, self.ox.NamedNode) else "literal", value=quad.object.value)
                    if isinstance(quad.object, self.ox.Literal):
                        value['datatype'] = quad.object.datatype.value
                        if quad.object.language is not None:
                            value['language'] = quad.object.language
                    size += len(json.dumps(value, ensure_ascii=False).encode()) + len(quad.predicate.value.encode()) + 16
                    if size > max_bytes:
                        raise ProcessingError("Native extraction read exceeds byte budget")
                    record['fields'].setdefault(quad.predicate.value, []).append(value)
            kind = self.one(node, RDF_TYPE)
            required = {"Entity": {"position", "name", "entityType", "mentionId", "mention"},
                        "Relation": {"position", "predicateName", "sourceEntity", "targetEntity", "relationType", "confidence", "evidence"}}.get(kind.removeprefix(F), set())
            for field in required:
                predicate = F + field
                if (fields is None or predicate in fields) and len(record['fields'].get(predicate, [])) != 1:
                    raise ProcessingError("Native extraction consumed field missing or corrupt: " + field)
            result.append(record)
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            raise ProcessingError("Native extraction read exceeds byte budget")
        return result

    def read_nodes(self, record_ids, *, fields=None, max_bytes=MAX_PAGE_BYTES):
        """Read projected fields of owned nodes, including linked evidence/attributes.

        No source text or unread payload is hydrated. Completion is a point read;
        validation covers only the owned records and fields being consumed.
        """
        self._read_options(fields, max_bytes)
        if not isinstance(record_ids, list) or not 1 <= len(record_ids) <= MAX_PAGE_ROWS:
            raise ProcessingError("Native extraction node batch must contain 1..128 records")
        if self.receipt() is None:
            raise ProcessingError("Native extraction receipt missing")
        result = self._read_nodes(record_ids, fields, max_bytes)
        if self.receipt() is None:
            raise ProcessingError("Native extraction receipt missing after read")
        return result

    def page(self, *, after=None, limit=MAX_PAGE_ROWS, fields=None, max_bytes=MAX_PAGE_BYTES):
        """Page main extraction records in persisted position order.

        Cursors bind to the complete input tuple and stage. Related nodes are
        addressed through read_nodes; values never become a second build store.
        """
        self._read_options(fields, max_bytes)
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_ROWS:
            raise ProcessingError("Native extraction page limit must be 1..128")
        position = -1
        prefix = self.operation.value + ":cursor:"
        if after is not None:
            if not isinstance(after, str) or not after.startswith(prefix) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", after[len(prefix):]):
                raise ProcessingError("Native extraction cursor belongs to another operation or is invalid")
            position = int(after[len(prefix):])
        receipt = self.receipt()
        if receipt is None:
            raise ProcessingError("Native extraction receipt missing")
        kind = "Entity" if self.stage == "entities" else "Relation"
        query = (f"SELECT ?record ?position WHERE {{ GRAPH {self.graph} {{ "
                 f"{self.operation} <{F}ownedRecord> ?record . ?record <{RDF_TYPE}> <{F}{kind}> ; <{F}position> ?position . "
                 f"FILTER(?position > {position}) }} }} ORDER BY ?position LIMIT {limit + 1}")
        rows = list(self.owner.store.query(query))
        expected = min(limit + 1, max(0, receipt['count'] - position - 1))
        if len(rows) != expected or any(int(row['position'].value) != position + i + 1 for i, row in enumerate(rows)):
            raise ProcessingError("Native extraction page records missing or corrupt")
        selected = rows[:limit]
        result = dict(records=self._read_nodes([row['record'].value for row in selected], fields, max_bytes),
                      next_cursor=prefix + rows[limit - 1]['position'].value if len(rows) > limit else None)
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            raise ProcessingError("Native extraction page exceeds byte budget")
        if self.receipt() is None:
            raise ProcessingError("Native extraction receipt missing after read")
        return result

    def read_metadata(self, node, fields):
        return {key: value for key, predicate in fields.items() if (value := self.one(node, predicate, optional=True)) is not None}

    def read_receipts(self):
        if self.receipt() is None:
            raise ProcessingError("Native extraction receipt missing")
        links = self.values(self.operation, "modelReceipt")
        owned = list(islice(self.owner.store.query(
            "SELECT ?node WHERE { GRAPH " + str(self.graph) + " { " + str(self.operation)
            + " <" + F + "ownedRecord> ?node . ?node <" + RDF_TYPE + "> <" + F + "ModelReceipt> } } LIMIT " + str(MAX_RECORDS + 1)), MAX_RECORDS + 1))
        if len(owned) > MAX_RECORDS or set(links) != {row["node"] for row in owned}:
            raise ProcessingError("Native extraction model receipt links missing or corrupt")
        result = []
        for node in sorted(links, key=lambda n: self.one(n, "position")):
            data = self.read_metadata(node, {"id": "receiptId", "operation": "receiptOperation", "provider": "provider", "model": "model", "input_digest": "inputDigest", "output_digest": "outputDigest", "created_at": "createdAt"})
            if self.one(node, RDF_TYPE) != F+'ModelReceipt' or any(not isinstance(data.get(key), str) or not data[key]
                    for key in ('id', 'operation', 'provider', 'model', 'input_digest', 'output_digest')):
                raise ProcessingError("Native extraction model receipt missing or corrupt")
            data["parameters"] = self.read_metadata(node, {"temperature": "temperature", "top_p": "topP", "max_tokens": "maxTokens", "max_output_tokens": "maxOutputTokens"})
            data["metadata"] = self.read_metadata(node, {"extraction_stage": "extractionStage", "rejected_count": "rejectedCount"})
            usage = self.read_metadata(node, {"prompt_tokens": "promptTokens", "completion_tokens": "completionTokens", "total_tokens": "totalTokens", "input_tokens": "inputTokens", "output_tokens": "outputTokens"})
            if usage:
                data["metadata"]["usage"] = usage
            result.append(data)
        return result
