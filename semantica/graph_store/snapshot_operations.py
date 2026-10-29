"""Compose validated observations for GraphStore using native fact/version owners."""
from __future__ import annotations

from typing import Optional

from ..semantic_artifact_schema import SemanticArtifact, stable_digest
from ..conflicts.conflict_detector import ConflictDetector
from ..change_management.managers import TemporalVersionManager

reconcile_qualified_facts = ConflictDetector.reconcile_qualified_facts
_change_delta = TemporalVersionManager.semantic_delta


def extend_semantic_snapshot(base: Optional[SemanticArtifact], incoming: SemanticArtifact, *,
                             functional_predicates=(), retract_evidence_ids=()) -> SemanticArtifact:
    """Append validated observations through native fact and change owners.

    Located records are immutable. Explicitly withdrawing support retains its
    evidence and original observation. Entity IDs retain their type; incoming
    entity projections may change across revisions, never across identities.
    Storage still checks the base revision atomically when committing the result.
    """
    incoming = SemanticArtifact.model_validate(incoming.model_dump(mode="json"))
    withdrawn = set(retract_evidence_ids)
    operation_digest = stable_digest([incoming.model_dump(mode="json"), sorted(withdrawn),
                                      sorted(functional_predicates)])
    if base is None:
        if withdrawn:
            raise ValueError("withdrawn_evidence_not_found")
        incoming.metadata = {**incoming.metadata, "applied_observations": {incoming.id: {
            "digest": operation_digest, "retract_evidence_ids": [],
            "functional_predicates": sorted(functional_predicates)}}, "withdrawn_evidence_ids": []}
        return incoming
    base = SemanticArtifact.model_validate(base.model_dump(mode="json"))
    if base.project_id != incoming.project_id:
        raise ValueError("semantic_snapshot_scope_mismatch")
    if (base.classification_profile != incoming.classification_profile or
            base.extraction_spec != incoming.extraction_spec):
        raise ValueError("semantic_snapshot_contract_mismatch")
    applied = dict(base.metadata.get("applied_observations", {}))
    if incoming.id in applied:
        if applied[incoming.id]["digest"] != operation_digest:
            raise ValueError("immutable_observation_id_reused")
        return base
    if not withdrawn <= {item.id for item in base.evidence_spans}:
        raise ValueError("withdrawn_evidence_not_found")
    all_withdrawn = set(base.metadata.get("withdrawn_evidence_ids", [])) | withdrawn
    if all_withdrawn.intersection(item.id for item in incoming.evidence_spans):
        raise ValueError("withdrawn_evidence_reintroduced")
    data = base.model_dump(mode="json")
    for field in ("artifact_manifest", "document_representations", "evidence_spans", "entity_mentions",
                  "entities", "identity_registry", "communities", "topics",
                  "source_relations", "source_classifications", "retrieval_manifests", "model_receipts"):
        key = "mention_id" if field == "identity_registry" else "source_id" if field == "source_classifications" else "id"
        records = {getattr(item, key): item for item in getattr(base, field)}
        for item in getattr(incoming, field):
            identifier = getattr(item, key)
            if field == "entities" and identifier in records:
                if records[identifier].type != item.type:
                    raise ValueError("semantic_entity_type_changed:" + identifier)
            elif identifier in records and records[identifier] != item:
                raise ValueError("immutable_semantic_record_reused:" + field + ":" + identifier)
            records[identifier] = item
        data[field] = [records[key].model_dump(mode="json") for key in sorted(records)]
    def observations(items):
        for item in items:
            for original in item.metadata.get("support_observations", [item.model_dump(mode="json")]):
                original = dict(original)
                if withdrawn.intersection(original.get("evidence_ids", [])):
                    original["status"] = "retracted"
                yield type(item).model_validate(original)
    assertions, relations, conflicts = reconcile_qualified_facts(base.project_id,
        list(observations(base.assertions)) + incoming.assertions,
        list(observations(base.relations)) + incoming.relations,
        functional_predicates=functional_predicates)
    # Preserve externally supplied conflicts; native derived conflicts are recomputed.
    retained_conflicts = {item.id: item for item in [*base.conflicts, *incoming.conflicts]
                          if not item.id.startswith(("conflict:assertion:", "conflict:value:"))}
    retained_conflicts.update({item.id: item for item in conflicts})
    data.update(assertions=[item.model_dump(mode="json") for item in assertions],
                relations=[item.model_dump(mode="json") for item in relations],
                conflicts=[retained_conflicts[key].model_dump(mode="json") for key in sorted(retained_conflicts)])
    lineage = incoming.lineage.model_dump(mode="json")
    lineage["model_receipt_ids"] = sorted(set(base.lineage.model_receipt_ids + incoming.lineage.model_receipt_ids))
    data.update(snapshot_id="snapshot:" + stable_digest([base.id, operation_digest]).split(":")[1],
                base_snapshot_id=base.id, snapshot_version=base.snapshot_version + 1,
                created_at=incoming.created_at, lineage=lineage,
                metadata={**base.metadata, "applied_observations": {**applied, incoming.id: {
                    "digest": operation_digest, "retract_evidence_ids": sorted(withdrawn),
                    "functional_predicates": sorted(functional_predicates)}},
                          "withdrawn_evidence_ids": sorted(all_withdrawn),
                          "last_observation_metadata": incoming.metadata})
    data["change_delta"] = {}
    result = SemanticArtifact.model_validate(data)
    result.change_delta = _change_delta(base, result.id, result.document_representations,
        result.entities, result.assertions, result.relations, result.communities, result.topics,
        [item.id for item in result.retrieval_manifests], result.evidence_spans,
        result.source_classifications, conflicts=result.conflicts, identity_registry=result.identity_registry,
        source_relations=result.source_relations, entity_mentions=result.entity_mentions,
        classification_profile=result.classification_profile, extraction_spec=result.extraction_spec)
    return SemanticArtifact.model_validate(result.model_dump(mode="json"))
