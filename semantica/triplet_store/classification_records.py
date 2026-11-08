"""Native typed persistence of admitted source classification assignments."""
from __future__ import annotations

import hashlib
import json
from urllib.parse import quote, unquote
from itertools import islice

from .extraction_records import ExtractionRecords, F, RDF_TYPE, _hash, _triple
from ..semantic_artifact_schema import ClassificationProfile, SourceClassification, stable_digest
from ..utils.exceptions import ProcessingError

BINDING = {"project", "source", "material", "representation", "recipe", "model", "target", "taxonomy", "context_digest"}


def operation_identity(binding):
    if not isinstance(binding, dict) or set(binding) != BINDING or any(not isinstance(value, str) or not value or len(value) > 4096 for value in binding.values()):
        raise ProcessingError("Classification requires its complete named binding")
    digest = hashlib.sha256(json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return "urn:semantica:classification:" + digest


class ClassificationRecords(ExtractionRecords):
    def __init__(self, owner, binding):
        self.owner, self.ox, self.binding = owner, owner._oxigraph, binding
        self.logical = self.ox.NamedNode(operation_identity(binding))
        self.graph = self.ox.NamedNode("urn:semantica:project:" + hashlib.sha256(binding["project"].encode()).hexdigest())
        self.index_graph = self.ox.NamedNode(self.graph.value + ':classification-index')
        links = list(islice(owner.store.quads_for_pattern(self.logical,
            self.ox.NamedNode(F + 'physicalOperation'), None, self.index_graph), 2))
        if len(links) > 1 or any(not isinstance(q.object, self.ox.NamedNode) for q in links):
            raise ProcessingError('Native classification identity index is corrupt')
        self.indexed = bool(links)
        self.operation = links[0].object if links else self.logical
        self.stage = 'classification'
        self.quads = []

    @classmethod
    def source_completion(cls, owner, binding, *, reduction=None):
        """Index an accepted reduction by immutable source inputs, before quotes."""
        with owner._publication_lock:
            if set(binding) != BINDING - {'context_digest'}:
                raise ProcessingError('Classification source requires exact immutable binding')
            probe=cls(owner,{**binding,'context_digest':'source-completion'})
            key=probe.ox.NamedNode(probe.logical.value+':source')
            predicate=probe.ox.NamedNode(F+'completedReduction')
            links=list(islice(owner.store.quads_for_pattern(key,predicate,None,probe.index_graph),2))
            if len(links)>1 or any(not isinstance(q.object,probe.ox.NamedNode) for q in links):
                raise ProcessingError('Native classification source completion is duplicated')
            if links:
                operation=links[0].object
                actual={field:probe.one(operation,'binding'+field[0].upper()+field[1:]) for field in BINDING}
                if any(actual[field]!=value for field,value in binding.items()):
                    raise ProcessingError('Native classification source completion binding differs')
                result=cls(owner,actual)
                if result.operation!=operation or result.receipt() is None or not result.one(operation,'classificationReduction',optional=True):
                    raise ProcessingError('Native classification source completion is incomplete')
                if reduction is not None and reduction.operation!=operation:
                    raise ProcessingError('Native classification source already has another result')
                return result.operation.value
            if reduction is None:
                return None
            if (any(reduction.binding[field]!=value for field,value in binding.items()) or reduction.receipt() is None
                or not reduction.one(reduction.operation,'classificationReduction',optional=True)):
                raise ProcessingError('Classification source requires an accepted matching reduction')
            from ..semantic_worker_context import check_query_cancellation
            check_query_cancellation()
            owner.flush()
            owner.store.add(probe.ox.Quad(key,predicate,reduction.operation,probe.index_graph))
            owner.flush()
            return reduction.operation.value

    @classmethod
    def rebind(cls, owner, previous, current):
        """Offline recipe metadata migration; paid assignment/receipt nodes stay put."""
        old_key, new_key = operation_identity(previous), operation_identity(current)
        if any(previous[key] != current[key] for key in BINDING - {'recipe'}):
            raise ProcessingError('Classification migration may change only recipe identity')
        with owner._publication_lock:
            original, target = cls(owner, previous), cls(owner, current)
            if target.indexed:
                if original.operation != target.operation and (original.indexed or original.values(original.operation, RDF_TYPE)):
                    raise ProcessingError('Classification migration target already owns another paid result')
                if target.one(target.operation, 'bindingRecipe') != current['recipe']:
                    raise ProcessingError('Classification migration target binding differs')
                return target.audit()
            # Normal reads never admit pre-index data. The explicit offline
            # migration verifies its complete binding/receipt before indexation.
            if original._verify_receipt() is None:
                raise ProcessingError('Classification migration source receipt missing')
            for key, value in previous.items():
                if original.one(original.operation, 'binding' + key[0].upper() + key[1:]) != value:
                    raise ProcessingError('Classification migration source binding differs')
            ox = owner._oxigraph
            replace = {ox.NamedNode(F + key) for key in ('bindingRecipe', 'operationDigest')}
            prior = list(owner.store.quads_for_pattern(original.operation, None, None, original.graph))
            changed = [ox.Quad(original.operation, ox.NamedNode(F + 'bindingRecipe'), ox.Literal(current['recipe']), original.graph)]
            kept = [q for q in prior if q.predicate not in replace]
            if original.one(original.operation, 'paidRecipe', optional=True) is None:
                changed.append(ox.Quad(original.operation, ox.NamedNode(F + 'paidRecipe'), ox.Literal(previous['recipe']), original.graph))
            changed.append(ox.Quad(original.operation, ox.NamedNode(F + 'operationDigest'), ox.Literal(_hash(kept + changed)), original.graph))
            deletes = ' . '.join(_triple(q) for q in prior if q.predicate in replace)
            inserts = ' . '.join(_triple(q) for q in changed)
            predicate = '<' + F + 'physicalOperation>'
            owner.store.update('DELETE { GRAPH ' + str(original.graph) + ' { ' + deletes + ' } GRAPH ' + str(original.index_graph)
                + ' { <' + old_key + '> ' + predicate + ' ?old } } INSERT { GRAPH ' + str(original.graph) + ' { ' + inserts
                + ' } GRAPH ' + str(original.index_graph) + ' { <' + new_key + '> ' + predicate + ' ' + str(original.operation)
                + ' } } WHERE { OPTIONAL { GRAPH ' + str(original.index_graph) + ' { <' + old_key + '> ' + predicate + ' ?old } } }')
            owner.flush()
            return cls(owner, current).receipt()

    def reference(self, kind, identity):
        return self.ox.NamedNode("urn:semantica:reference:" + kind + ":" + quote(identity, safe=""))

    def reference_id(self, node, kind):
        prefix = "urn:semantica:reference:" + kind + ":"
        if not node.value.startswith(prefix):
            raise ProcessingError("Classification reference kind mismatch")
        return unquote(node.value[len(prefix):])

    def adopt_reduction(self, batch_operations, *, profile):
        """Own final classification as accepted batch references, without copies."""
        profile = profile if isinstance(profile, ClassificationProfile) else ClassificationProfile.model_validate(profile)
        if (not isinstance(batch_operations, list) or not 1 <= len(batch_operations) <= 128
                or len(set(batch_operations)) != len(batch_operations)):
            raise ProcessingError('Classification reduction batch reference budget exceeded')
        if len(profile.dimensions) > 128:
            raise ProcessingError('Classification reduction dimension budget exceeded')
        root = self.node('classification-reduction')
        digest = stable_digest(dict(batches=batch_operations, profile=profile.model_dump(mode='json', by_alias=True)))
        if not self.indexed and self.values(self.operation, RDF_TYPE):
            raise ProcessingError('Native classification requires explicit offline identity migration')
        existing = self.receipt()
        if existing is not None:
            if existing['accepted_digest'] != digest:
                raise ProcessingError('Classification reduction input identity differs')
            return existing
        self.own(root, 'ClassificationReduction')
        self.add(self.operation, 'classificationReduction', root)
        self.add(root, 'profileId', profile.id)
        self.add(root, 'profileVersion', profile.version)
        for identity in batch_operations:
            node = self.ox.NamedNode(identity)
            binding = {field: self.one(node, 'binding' + field[0].upper() + field[1:]) for field in BINDING}
            if ClassificationRecords(self.owner, binding).receipt() is None:
                raise ProcessingError('Classification reduction batch receipt missing')
            for field in ('project', 'source', 'material', 'representation', 'taxonomy'):
                if self.one(node, 'binding' + field[0].upper() + field[1:]) != self.binding[field]:
                    raise ProcessingError('Classification reduction batch binding differs')
            if not self.one(node, 'classificationResult', optional=True):
                raise ProcessingError('Classification reduction requires accepted batch results')
            self.add(root, 'batch', node)
        for dimension in profile.dimensions:
            node = self.node('reduction-dimension:' + quote(dimension.id, safe=''))
            self.own(node, 'ClassificationDimension')
            self.add(root, 'dimension', node)
            self.add(node, 'dimensionId', dimension.id)
            self.add(node, 'cardinality', dimension.cardinality)
        return self.commit(len(batch_operations), digest)

    def read_reduced_dimension(self, dimension_id, *, after=None, limit=128, max_bytes=262144):
        """Read one dimension's bounded native candidates before applying reduction."""
        if type(limit) is not int or not 1 <= limit <= 128 or type(max_bytes) is not int or not 1 <= max_bytes <= 262144:
            raise ProcessingError('Invalid classification reduction page budget')
        if (not isinstance(dimension_id, str) or not dimension_id or len(dimension_id.encode()) > 4096
                or after is not None and (not isinstance(after, str) or not after or len(after.encode()) > 4096)):
            raise ProcessingError('Invalid classification reduction dimension/cursor')
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        if self.receipt() is None:
            raise ProcessingError('Classification reduction receipt missing')
        root = self.ox.NamedNode(self.one(self.operation, 'classificationReduction'))
        dimensions = [node for node in self.values(root, 'dimension') if self.one(node, 'dimensionId') == dimension_id]
        if len(dimensions) != 1:
            raise ProcessingError('Classification dimension absent or duplicated')
        literal = self.ox.Literal(dimension_id)
        query = f'''SELECT ?assignment ?item ?confidence WHERE {{ GRAPH {self.graph} {{
            {root} <{F}batch> ?batch . ?batch <{F}classificationResult> ?result .
            ?result <{F}assignment> ?assignment . ?assignment <{F}dimension> ?dimension ;
                <{F}item> ?itemNode ; <{F}confidence> ?confidence .
            ?dimension <{F}dimensionId> {literal} . ?itemNode <{F}itemId> ?item .
        }} }} ORDER BY ?item ?assignment LIMIT 1025'''
        rows = list(self.owner.store.query(query))
        if len(rows) > 1024:
            raise ProcessingError('Classification dimension candidate reference budget exceeded')
        grouped = {}
        for row in rows:
            check_query_cancellation()
            item = row['item'].value
            current = grouped.setdefault(item, dict(dimensionId=dimension_id, itemId=item,
                confidence=1.0, evidenceRefs=[], method='model'))
            current['confidence'] = min(current['confidence'], float(row['confidence'].value))
            refs = {self.reference_id(ref, 'evidence') for ref in self.values(row['assignment'], 'evidence')}
            current['evidenceRefs'] = sorted(set(current['evidenceRefs']) | refs)
            if len(current['evidenceRefs']) > 256:
                raise ProcessingError('Reduced classification evidence budget exceeded')
            if len(json.dumps(grouped, ensure_ascii=False).encode()) > 2097152:
                raise ProcessingError('Classification reduction candidate byte budget exceeded')
        unclassified = not grouped or (self.one(dimensions[0], 'cardinality') == 'single' and len(grouped) != 1)
        items = [] if unclassified else [grouped[key] for key in sorted(grouped) if after is None or key > after]
        result = dict(dimensionId=dimension_id, unclassified=unclassified, assignments=[], nextCursor=None)
        for item in items[:limit]:
            result['assignments'].append(item)
            if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
                result['assignments'].pop()
                if not result['assignments']:
                    raise ProcessingError('Classification assignment exceeds byte budget')
                break
        if len(items) > len(result['assignments']):
            result['nextCursor'] = result['assignments'][-1]['itemId']
        return result

    def validate(self, value, profile, allowed_evidence_ids):
        value = value if isinstance(value, SourceClassification) else SourceClassification.model_validate(value)
        profile = profile if isinstance(profile, ClassificationProfile) else ClassificationProfile.model_validate(profile)
        if value.source_id != self.binding["source"] or value.profile_id != profile.id or value.profile_version != profile.version:
            raise ProcessingError("Classification source/profile identity mismatch")
        if stable_digest(profile.model_dump(mode="json", by_alias=True)) != self.binding["taxonomy"]:
            raise ProcessingError("Classification taxonomy digest mismatch")
        if len(value.assignments) > 1024 or len(profile.dimensions) > 128 or len(allowed_evidence_ids) > 8192:
            raise ProcessingError("Classification exceeds input cardinality budget")
        dimensions = {dimension.id: dimension for dimension in profile.dimensions}
        selected, seen = {}, set()
        evidence = set(allowed_evidence_ids)
        for assignment in value.assignments:
            dimension = dimensions.get(assignment.dimension_id)
            if dimension is None or assignment.item_id not in {item.id for item in dimension.vocabulary}:
                raise ProcessingError("Classification references unknown taxonomy item")
            key = (assignment.dimension_id, assignment.item_id)
            if key in seen:
                raise ProcessingError("Classification repeats an assignment")
            seen.add(key)
            selected[assignment.dimension_id] = selected.get(assignment.dimension_id, 0) + 1
            if dimension.cardinality == "single" and selected[dimension.id] > 1:
                raise ProcessingError("Classification violates single cardinality")
            if len(assignment.evidence_ids) > 256 or not set(assignment.evidence_ids) <= evidence:
                raise ProcessingError("Classification evidence outside admitted source context")
        if len(value.unclassified_dimension_ids) != len(set(value.unclassified_dimension_ids)) or set(value.unclassified_dimension_ids) != set(dimensions) - set(selected):
            raise ProcessingError("Classification unclassified dimensions are incomplete")
        return value, profile

    def adopt(self, value, *, profile, allowed_evidence_ids, accepted_digest, receipts=()):
        if self.owner.path is None:
            raise ProcessingError("Classification requires persistent native owner")
        value, profile = self.validate(value, profile, allowed_evidence_ids)
        if not self.indexed and self.values(self.operation, RDF_TYPE):
            raise ProcessingError('Native classification requires explicit offline identity migration')
        existing = self.receipt()
        if existing is not None:
            if existing["accepted_digest"] != accepted_digest:
                raise ProcessingError("Classification accepted digest mismatch")
            self.owner.flush()
            return existing
        source = self.reference("source", value.source_id)
        root = self.node("source-classification")
        self.own(root, "SourceClassification")
        self.add(self.operation, "classificationResult", root)
        self.add(root, "source", source)
        self.add(root, "profileId", value.profile_id)
        self.add(root, "profileVersion", value.profile_version)
        for dimension in profile.dimensions:
            node = self.node("dimension:" + quote(dimension.id, safe=""))
            self.own(node, "ClassificationDimension")
            self.add(node, "dimensionId", dimension.id)
            self.add(node, "cardinality", self.ox.NamedNode(F + dimension.cardinality))
            if dimension.id in value.unclassified_dimension_ids:
                self.add(root, "unclassifiedDimension", node)
        for index, assignment in enumerate(value.assignments):
            node = self.node("assignment:" + str(index))
            dimension = self.node("dimension:" + quote(assignment.dimension_id, safe=""))
            item = self.node("item:" + quote(assignment.dimension_id + ":" + assignment.item_id, safe=""))
            self.own(item, "ClassificationItem")
            self.add(item, "itemId", assignment.item_id)
            self.add(item, "dimension", dimension)
            self.own(node, "ClassificationAssignment")
            self.add(root, "assignment", node)
            self.add(node, "position", index)
            self.add(node, "source", source)
            self.add(node, "dimension", dimension)
            self.add(node, "item", item)
            self.confidence(node, assignment.confidence)
            for evidence_id in dict.fromkeys(assignment.evidence_ids):
                self.add(node, "evidence", self.reference("evidence", evidence_id))
        receipt_ids = [receipt.id if hasattr(receipt, "id") else receipt["id"] for receipt in receipts]
        if set(value.model_receipt_ids) != set(receipt_ids) or len(value.model_receipt_ids) != len(set(value.model_receipt_ids)):
            raise ProcessingError("Classification model receipt identities differ")
        self.write_receipts(receipts)
        return self.commit(len(value.assignments), accepted_digest)

    def read(self, *, profile, allowed_evidence_ids):
        receipt = self.receipt()
        if receipt is None:
            raise ProcessingError("Classification native receipt missing")
        root = self.ox.NamedNode(self.one(self.operation, "classificationResult"))
        assignments = []
        nodes = sorted(self.values(root, "assignment"), key=lambda node: self.one(node, "position"))
        if len(nodes) != receipt["count"]:
            raise ProcessingError("Classification native assignment count mismatch")
        for node in nodes:
            dimension = self.ox.NamedNode(self.one(node, "dimension"))
            item = self.ox.NamedNode(self.one(node, "item"))
            assignments.append(dict(dimension_id=self.one(dimension, "dimensionId"), item_id=self.one(item, "itemId"), confidence=self.one(node, "confidence"), evidence_ids=sorted(self.reference_id(ref, "evidence") for ref in self.values(node, "evidence"))))
        result = SourceClassification(source_id=self.binding["source"], profile_id=self.one(root, "profileId"), profile_version=self.one(root, "profileVersion"), assignments=assignments, unclassified_dimension_ids=sorted(self.one(node, "dimensionId") for node in self.values(root, "unclassifiedDimension")), model_receipt_ids=[receipt["id"] for receipt in self.read_receipts()])
        return self.validate(result, profile, allowed_evidence_ids)[0]
