"""Evidence-admitted project identities, independent of source mention IDs."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .project_snapshot_schema import (
    IdentityDecision,
    IdentityRegistryEntry,
    KnowledgeEntity,
    ProjectSnapshot,
    stable_digest,
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def resolve_project_identities(*, project_id: str, mentions: list[KnowledgeEntity], judgments: list[dict[str, Any]],
                               base_snapshot: ProjectSnapshot | None, receipt_id: str | None
                               ) -> tuple[list[KnowledgeEntity], dict[str, str], list[IdentityDecision], list[IdentityRegistryEntry]]:
    """Resolve current mentions while retaining durable identity history."""
    by_id = {mention.id: mention for mention in mentions}
    if len(by_id) != len(mentions):
        raise ValueError("identity mentions must have unique ids")

    previous_entities = {entity.id: entity for entity in getattr(base_snapshot, "entities", [])}
    registry = {
        entry.mention_id: entry.model_copy(deep=True)
        for entry in getattr(base_snapshot, "identity_registry", [])
    }
    for entity in previous_entities.values():
        source_ids = sorted(set(entity.metadata.get("source_ids", [])))
        for mention_id in entity.metadata.get("mention_ids", [entity.id]):
            registry.setdefault(mention_id, IdentityRegistryEntry(
                mention_id=mention_id,
                entity_id=entity.id,
                canonical_name=entity.canonical_name,
                type=entity.type,
                source_ids=source_ids,
            ))

    inherited: dict[str, str] = {}
    for mention in mentions:
        exact = registry.get(mention.id)
        if exact:
            inherited[mention.id] = exact.entity_id
            continue
        source_ids = set(mention.metadata.get("source_ids", []))
        candidates = {
            entry.entity_id
            for entry in registry.values()
            if _normalized(entry.canonical_name) == _normalized(mention.canonical_name)
            and entry.type.casefold() == mention.type.casefold()
            and source_ids.intersection(entry.source_ids)
        }
        if len(candidates) == 1:
            inherited[mention.id] = candidates.pop()

    historical_decisions = [
        decision.model_copy(deep=True)
        for decision in getattr(base_snapshot, "identity_decisions", [])
    ]
    persisted_splits: list[tuple[list[list[str]], int]] = []
    for index, decision in enumerate(historical_decisions):
        partition = decision.metadata.get("partition") if decision.decision_type == "split" else None
        if (isinstance(partition, list) and len(partition) >= 2
                and all(isinstance(group, list) and group and all(isinstance(item, str) for item in group)
                        for group in partition)):
            persisted_splits.append((partition, index))

    used: set[str] = set()
    admitted: list[dict[str, Any]] = []
    for judgment in judgments:
        if not isinstance(judgment, dict):
            raise ValueError("identity judgment must be an object")
        decision_type = judgment.get("decision_type", "merge")
        ids = judgment.get("mention_ids")
        reason = judgment.get("reason")
        evidence_ids = judgment.get("evidence_ids")
        if (decision_type not in {"merge", "split"}
                or not isinstance(ids, list) or len(ids) < 2
                or any(not isinstance(item, str) or item not in by_id for item in ids)
                or len(set(ids)) != len(ids) or used.intersection(ids)
                or not isinstance(reason, str) or not reason.strip()
                or not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids)):
            raise ValueError("identity judgment contains unknown, duplicate, overlapping, or unsupported mentions")
        admitted_evidence = {item for mention_id in ids for item in by_id[mention_id].evidence_ids}
        if (not set(evidence_ids).issubset(admitted_evidence)
                or any(not set(by_id[item].evidence_ids).intersection(evidence_ids) for item in ids)):
            raise ValueError("identity judgment must cite evidence from every mention")
        if len({by_id[item].type.casefold() for item in ids}) != 1:
            raise ValueError("identity judgment cannot combine incompatible entity types")
        if receipt_id is None:
            raise ValueError("identity judgment requires an admitted model receipt")
        if decision_type == "split":
            partition = judgment.get("groups")
            flattened = [item for group in partition for item in group] if isinstance(partition, list) and all(isinstance(group, list) for group in partition) else []
            if (not isinstance(partition, list) or len(partition) < 2
                    or any(not group for group in partition)
                    or len(flattened) != len(set(flattened))
                    or set(flattened) != set(ids)):
                raise ValueError("identity split must partition every mentioned identity exactly once")
        used.update(ids)
        admitted.append({**judgment, "decision_type": decision_type, "mention_ids": sorted(ids),
                         "evidence_ids": sorted(set(evidence_ids)), "reason": reason.strip()})

    parent = {mention.id: mention.id for mention in mentions}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    inherited_groups: dict[str, list[str]] = defaultdict(list)
    for mention_id, entity_id in inherited.items():
        inherited_groups[entity_id].append(mention_id)
    for ids in inherited_groups.values():
        for mention_id in ids[1:]:
            union(ids[0], mention_id)
    for judgment in admitted:
        if judgment["decision_type"] == "merge":
            for mention_id in judgment["mention_ids"][1:]:
                union(judgment["mention_ids"][0], mention_id)

    groups_by_root: dict[str, set[str]] = defaultdict(set)
    for mention_id in by_id:
        groups_by_root[find(mention_id)].add(mention_id)
    groups = list(groups_by_root.values())

    current_merges = [set(judgment["mention_ids"]) for judgment in admitted if judgment["decision_type"] == "merge"]
    split_constraints = [
        (partition, [set(decision.from_entity_ids) for decision in historical_decisions[index + 1:]
                     if decision.decision_type == "merge"] + current_merges)
        for partition, index in persisted_splits
    ]
    split_constraints.extend(
        (judgment["groups"], current_merges)
        for judgment in admitted if judgment["decision_type"] == "split"
    )
    for partition, explicit_merges in split_constraints:
        separated: list[set[str]] = []
        for group in groups:
            live = [
                (index, members)
                for index, items in enumerate(partition)
                if (members := group.intersection(items))
            ]
            if not live:
                separated.append(group)
                continue
            partition_members = set().union(*(set(items) for items in partition))
            outsiders = group - partition_members
            link_parent = {item: item for item in group}

            def link_find(item: str) -> str:
                while link_parent[item] != item:
                    link_parent[item] = link_parent[link_parent[item]]
                    item = link_parent[item]
                return item

            for merge in explicit_merges:
                members = sorted(group.intersection(merge))
                for item in members[1:]:
                    left, right = link_find(members[0]), link_find(item)
                    if left != right:
                        link_parent[max(left, right)] = min(left, right)
            links: dict[str, set[str]] = defaultdict(set)
            for item in group:
                links[link_find(item)].add(item)
            buckets = {index: set(items) for index, items in live}
            for component in links.values():
                targets = [index for index, items in enumerate(partition) if component.intersection(items)]
                if len(targets) > 1:
                    raise ValueError("identity merge violates a persisted split")
                component_outsiders = component.intersection(outsiders)
                if not component_outsiders:
                    continue
                if targets:
                    buckets[targets[0]].update(component_outsiders)
                else:
                    separated.append(component_outsiders)
            separated.extend(buckets.values())
        groups = separated
    groups.sort(key=lambda group: sorted(group))

    assigned_entity_ids: set[str] = set()
    canonical: list[KnowledgeEntity] = []
    remap: dict[str, str] = {}
    for group in groups:
        ids = sorted(group)
        predecessors = []
        for mention_id in ids:
            entity_id = inherited.get(mention_id)
            if entity_id and entity_id not in predecessors:
                predecessors.append(entity_id)
        entity_id = next((item for item in predecessors if item not in assigned_entity_ids), None)
        if entity_id is None:
            entity_id = "entity:" + stable_digest([project_id, ids[0]]).split(":")[1][:32]
        if entity_id in assigned_entity_ids:
            entity_id = "entity:" + stable_digest([project_id, "split", ids]).split(":")[1][:32]
        assigned_entity_ids.add(entity_id)

        members = [by_id[item] for item in ids]
        names = sorted({member.canonical_name for member in members} | {alias for member in members for alias in member.aliases})
        previous_name = previous_entities.get(entity_id).canonical_name if entity_id in previous_entities else None
        if previous_name is None:
            previous_name = next((entry.canonical_name for entry in registry.values() if entry.entity_id == entity_id), None)
        canonical_name = previous_name if previous_name in names else names[0]
        canonical.append(KnowledgeEntity(
            id=entity_id,
            canonical_name=canonical_name,
            type=members[0].type,
            aliases=[name for name in names if name != canonical_name],
            evidence_ids=sorted({item for member in members for item in member.evidence_ids}),
            status="accepted" if len(ids) > 1 else members[0].status,
            metadata={
                "mention_ids": ids,
                "source_ids": sorted({item for member in members for item in member.metadata.get("source_ids", [])}),
            },
        ))
        for mention_id in ids:
            remap[mention_id] = entity_id

    for mention in mentions:
        registry[mention.id] = IdentityRegistryEntry(
            mention_id=mention.id,
            entity_id=remap[mention.id],
            canonical_name=mention.canonical_name,
            type=mention.type,
            source_ids=sorted(set(mention.metadata.get("source_ids", []))),
        )

    new_decisions: list[IdentityDecision] = []
    for judgment in admitted:
        ids = judgment["mention_ids"]
        decision_type = judgment["decision_type"]
        model_receipt_ids = judgment.get("_receipt_ids", [receipt_id])
        previous_ids = sorted({inherited[item] for item in ids if item in inherited})
        if decision_type == "merge":
            target = remap[ids[0]]
            identity_key = [ids, target, decision_type]
            partition = None
        else:
            target = None
            partition = [sorted(group) for group in judgment["groups"]]
            identity_key = [partition, decision_type]
        metadata = {
            "model_receipt_id": model_receipt_ids[0] if model_receipt_ids else None,
            "model_receipt_ids": model_receipt_ids,
            "previous_entity_ids": previous_ids,
        }
        if partition is not None:
            metadata["partition"] = partition
        new_decisions.append(IdentityDecision(
            id="identity:" + stable_digest(identity_key).split(":")[1][:32],
            decision_type=decision_type,
            from_entity_ids=ids,
            to_entity_id=target,
            evidence_ids=judgment["evidence_ids"],
            reason=judgment["reason"],
            metadata=metadata,
        ))

    decisions = {decision.id: decision for decision in historical_decisions}
    for decision in new_decisions:
        decisions.setdefault(decision.id, decision)
    return canonical, remap, list(decisions.values()), [registry[key] for key in sorted(registry)]
