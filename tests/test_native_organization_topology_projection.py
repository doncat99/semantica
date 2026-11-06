"""Organization must validate topology without forwarding unused fact bodies."""
import hashlib
import itertools
import json

import pytest

from semantica import semantic_publication_builder as builder
from semantica.kg import GraphBuilder
from semantica.semantic_artifact_schema import (
    EvidenceSpan, KnowledgeAssertion, KnowledgeEntity, KnowledgeRelation,
    KnowledgeReport, ReportSection,
)
from semantica.utils.exceptions import ProcessingError


@pytest.mark.parametrize("reason", ["memory", "deadline", "cancelled", "child_exit",
                                  "startup", "transport", "monitor"])
def test_community_failure_does_not_publish(tmp_path, monkeypatch, reason):
    from semantica.pipeline.parallelism_manager import ParallelismManager
    from tests.test_native_build_body_budget import project_request

    request = project_request(tmp_path, count=1, repeats=1)
    published = []
    def fail(self, task, **limits):
        assert task.task_id == "greedy_modularity"
        assert limits["timeout_seconds"] == 120
        assert limits["max_rss_bytes"] == 1024**3
        raise ProcessingError("operation stopped", processing_context={"reason": reason})
    monkeypatch.setattr(ParallelismManager, "execute_isolated_task", fail)
    monkeypatch.setattr(builder, "_publish_native_indexes", lambda *args: published.append(args))
    with pytest.raises(builder.SemanticArtifactError) as caught:
        builder.build_semantic_artifacts(request)
    assert caught.value.code == "NATIVE_COMMUNITY_EXECUTION_FAILED"
    assert caught.value.diagnostic == {"reason": reason}
    assert published == []


def _inputs():
    evidence = [EvidenceSpan(
        id="support", representation_id="source", quote="A supports B.",
        locator={"representation_id": "source", "origin": "native", "quote": "A supports B.",
                 "start_char": 0, "end_char": 13, "quality": "precise"},
    )]
    entities = [KnowledgeEntity(
        id="entity:" + name, canonical_name=name.upper(), type="Concept", evidence_ids=["support"],
        metadata={"identity_profile": {"evidence": ["full native identity evidence"]}},
    ) for name in ("a", "b", "c", "d", "isolated")]
    relations = [KnowledgeRelation(
        id=ref, source_entity_id="entity:" + source, target_entity_id="entity:" + target, type="supports",
        qualifiers={"polarity": "positive", "time": "2025", "condition": "only on approval"},
        evidence_ids=["support"], support_ids=["support"], status="accepted",
        metadata={"support_observations": [{"quote": "A supports B.", "source_id": "source"}]},
    ) for ref, source, target in (
        ("ab", "a", "b"), ("ab-again", "a", "b"), ("ba", "b", "a"),
        ("loop", "b", "b"), ("cd", "c", "d"),
    )]
    assertions = [KnowledgeAssertion(
        id="claim", subject_id="entity:a", predicate="supports", object="B", object_entity_id="entity:b",
        qualifiers={"polarity": "positive", "time": "2025"}, evidence_ids=["support"],
    )]
    reports = [KnowledgeReport(
        id="overview", report_type="overview", title="Overview",
        content_hash="sha256:" + "1" * 64, evidence_ids=["support"],
        sections=[ReportSection(title="Support", text="A supports B.", evidence_ids=["support"])],
    )]
    return entities, assertions, relations, evidence, reports


def _dump_organization(inputs):
    entities, assertions, relations, evidence, reports = inputs
    groups = builder._semantic_organization(_topology(entities, relations))
    topics = builder._grounded_topics(entities, assertions, evidence, groups, reports)
    return [[item.model_dump(mode="json", by_alias=True) for item in values]
            for values in (groups, topics)]


def test_complete_organization_characterization():
    inputs = _inputs()
    before = [[item.model_dump(mode="json", by_alias=True) for item in values] for values in inputs]
    output = [_dump_organization(inputs)]
    pairs = list(itertools.combinations(range(4), 2))
    for included in itertools.product((False, True), repeat=len(pairs)):
        entities = [KnowledgeEntity(id=f"entity:{index}", canonical_name=f"Node {index}", type="Concept")
                    for index in range(4)]
        relations = [KnowledgeRelation(
            id=f"{source}-{target}", source_entity_id=f"entity:{source}", target_entity_id=f"entity:{target}",
            type="related", qualifiers={"polarity": "positive"},
        ) for (source, target), keep in zip(pairs, included) if keep]
        output.append(_dump_organization((entities, [], relations, [], [])))
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    # Captured from the unmodified production projection before its red-spec fix.
    assert digest == "1f75e04dd349f60471b066c7802128c575d0598f46d925ada1f50536901493ef"
    assert output[0][0][0]["entity_ids"] == ["entity:a", "entity:b"]
    assert output[0][0][0]["relation_ids"] == ["ab", "ab-again", "ba", "loop"]
    assert output[0][0][-1]["entity_ids"] == ["entity:isolated"]
    assert output[0][1][0]["assertion_ids"] == ["claim"]
    assert [[item.model_dump(mode="json", by_alias=True) for item in values] for values in inputs] == before


def _topology(entities, relations):
    return {"entities": [{"id": item.id, "name": item.canonical_name} for item in entities],
            "relationships": [{"id": item.id, "source": item.source_entity_id,
                               "target": item.target_entity_id, "type": item.type} for item in relations]}


def test_graph_builder_receives_only_required_topology(monkeypatch):
    original = GraphBuilder.build
    captured = []

    def inspect(self, sources, *args, **kwargs):
        captured.append(sources)
        return original(self, sources, *args, **kwargs)

    monkeypatch.setattr(GraphBuilder, "build", inspect)
    entities, _, relations, _, _ = _inputs()
    projected = builder._canonical_graph_projection(_topology(entities, relations))
    assert [row["id"] for row in projected["relationships"]] == [item.id for item in relations]
    assert captured[0]["entities"] == [{"id": item.id, "name": item.canonical_name} for item in entities]
    assert captured[0]["relationships"] == [
        {"id": item.id, "source": item.source_entity_id, "target": item.target_entity_id, "type": item.type}
        for item in relations
    ]


def test_projection_keeps_native_fail_closed_unknown_endpoint():
    entities, _, relations, _, _ = _inputs()
    relations[0].target_entity_id = "missing"
    with pytest.raises(ProcessingError, match="reference unknown endpoints"):
        builder._canonical_graph_projection(_topology(entities, relations))


@pytest.mark.parametrize("field", ["entities", "relationships"])
def test_projection_keeps_exact_identity_check(monkeypatch, field):
    original = GraphBuilder.build

    def lose_candidate(self, *args, **kwargs):
        graph = original(self, *args, **kwargs)
        graph[field] = graph[field][:-1]
        return graph

    monkeypatch.setattr(GraphBuilder, "build", lose_candidate)
    entities, _, relations, _, _ = _inputs()
    with pytest.raises(builder.SemanticArtifactError, match="changed publication identities"):
        builder._canonical_graph_projection(_topology(entities, relations))


def test_graph_validation_runs_inside_the_monitored_operation(monkeypatch):
    from semantica.pipeline.parallelism_manager import ParallelismManager

    entities, assertions, relations, evidence, _ = _inputs()
    invoked = []

    def parent_projection_forbidden(*args, **kwargs):
        raise AssertionError("GraphBuilder projection ran outside the monitored operation")

    def isolated(self, task, **limits):
        invoked.append(task)
        assert task.handler is builder._native_community_operation
        assert task.args[0] == {
            "entities": [{"id": item.id, "name": item.canonical_name} for item in entities],
            "relationships": [{"id": item.id, "source": item.source_entity_id,
                               "target": item.target_entity_id, "type": item.type} for item in relations],
        }
        return {"communities": [[item.id] for item in entities]}

    monkeypatch.setattr(builder, "_canonical_graph_projection", parent_projection_forbidden)
    monkeypatch.setattr(ParallelismManager, "execute_isolated_task", isolated)
    communities = builder._semantic_organization(_topology(entities, relations))
    assert len(invoked) == 1
    assert {ref for group in communities for ref in group.entity_ids} == {item.id for item in entities}
