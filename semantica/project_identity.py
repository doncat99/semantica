"""Evidence-admitted project identities, independent of source mention IDs."""
from __future__ import annotations

from typing import Any

from .project_snapshot_schema import IdentityDecision, KnowledgeEntity, ProjectSnapshot, stable_digest


def resolve_project_identities(*, project_id: str, mentions: list[KnowledgeEntity], judgments: list[dict[str, Any]],
                               base_snapshot: ProjectSnapshot | None, receipt_id: str | None
                               ) -> tuple[list[KnowledgeEntity], dict[str, str], list[IdentityDecision]]:
    """Admit explicit model judgments; label similarity never authorizes a merge.

    The canonical ID survives revisions and removal of its original source as
    long as at least one previously resolved mention remains in the project.
    """
    by_id = {mention.id: mention for mention in mentions}
    used: set[str] = set()
    groups: list[tuple[list[str], str, list[str]]] = []
    for judgment in judgments:
        if not isinstance(judgment, dict):
            raise ValueError("identity judgment must be an object")
        ids = judgment.get("mention_ids")
        reason = judgment.get("reason")
        evidence_ids = judgment.get("evidence_ids")
        if (not isinstance(ids, list) or len(ids) < 2 or any(not isinstance(item, str) or item not in by_id for item in ids)
                or len(set(ids)) != len(ids) or used.intersection(ids)
                or not isinstance(reason, str) or not reason.strip()
                or not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids)):
            raise ValueError("identity judgment contains unknown, duplicate, overlapping, or unsupported mentions")
        admitted_evidence = {item for mention_id in ids for item in by_id[mention_id].evidence_ids}
        if not set(evidence_ids).issubset(admitted_evidence) or any(not set(by_id[item].evidence_ids).intersection(evidence_ids) for item in ids):
            raise ValueError("identity judgment must cite evidence from every merged mention")
        if len({by_id[item].type.casefold() for item in ids}) != 1:
            raise ValueError("identity judgment cannot merge incompatible entity types")
        if receipt_id is None:
            raise ValueError("identity merge requires an admitted model receipt")
        used.update(ids)
        groups.append((sorted(ids), reason.strip(), sorted(set(evidence_ids))))
    groups.extend(([item.id], "source mention has no admitted cross-source identity merge", item.evidence_ids) for item in mentions if item.id not in used)
    groups.sort(key=lambda group: group[0])

    previous = {}
    previous_entities = {}
    if base_snapshot:
        previous_entities = {entity.id: entity for entity in base_snapshot.entities}
        for entity in base_snapshot.entities:
            for mention_id in entity.metadata.get("mention_ids", [entity.id]):
                previous[mention_id] = entity.id
    assigned: set[str] = set()
    canonical: list[KnowledgeEntity] = []
    decisions: list[IdentityDecision] = []
    remap: dict[str, str] = {}
    for ids, reason, evidence_ids in groups:
        predecessors = sorted({previous[item] for item in ids if item in previous})
        available = [item for item in predecessors if item not in assigned]
        entity_id = available[0] if available else "entity:" + stable_digest([project_id, ids[0]]).split(":")[1][:32]
        if entity_id in assigned:
            entity_id = "entity:" + stable_digest([project_id, "split", ids]).split(":")[1][:32]
        assigned.add(entity_id)
        members = [by_id[item] for item in ids]
        names = sorted({member.canonical_name for member in members} | {alias for member in members for alias in member.aliases})
        previous_name = previous_entities[entity_id].canonical_name if entity_id in previous_entities else None
        canonical_name = previous_name if previous_name in names else names[0]
        canonical.append(KnowledgeEntity(
            id=entity_id, canonical_name=canonical_name, type=members[0].type,
            aliases=[name for name in names if name != canonical_name],
            evidence_ids=sorted({item for member in members for item in member.evidence_ids}),
            status="accepted" if len(ids) > 1 else members[0].status,
            metadata={"mention_ids": ids, "source_ids": sorted({item for member in members for item in member.metadata.get("source_ids", [])})},
        ))
        for mention_id in ids:
            remap[mention_id] = entity_id
        if len(ids) > 1 or predecessors:
            decision_type = "split" if predecessors and not available else "merge" if len(ids) > 1 else "accept"
            decision = IdentityDecision(
                id="identity:" + stable_digest([ids, entity_id, decision_type]).split(":")[1][:32],
                decision_type=decision_type, from_entity_ids=ids, to_entity_id=entity_id,
                evidence_ids=evidence_ids, reason=reason,
                metadata={"model_receipt_id": receipt_id, "previous_entity_ids": predecessors},
            )
            decisions.append(decision)
    return canonical, remap, decisions
