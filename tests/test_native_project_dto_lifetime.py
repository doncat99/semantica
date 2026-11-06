"""Project organization reopens admitted knowledge, never the whole DTO set."""
import weakref

from semantica import semantic_publication_builder as builder
from semantica.conflicts.conflict_detector import ConflictDetector
from semantica.semantic_artifact_schema import SemanticArtifactBuildRequest
from tests.test_semantic_artifact import _request


def test_reconciled_fact_dtos_are_released_before_organization(tmp_path, monkeypatch):
    references = []
    reduce = ConflictDetector.reconcile_qualified_facts
    organize = builder._semantic_organization

    def capture(*args, **kwargs):
        result = reduce(*args, **kwargs)
        references.extend(weakref.ref(item) for group in result[:2] for item in group)
        return result

    def check(*args):
        assert references, 'fixture must produce canonical facts'
        assert all(ref() is None for ref in references), 'global canonical DTO survives into organization'
        assert len(args) == 1 and isinstance(args[0], dict)
        assert all(set(item) == {'id', 'name'} for item in args[0]['entities'])
        assert all(set(item) == {'id', 'source', 'target', 'type'} for item in args[0]['relationships'])
        return organize(*args)

    monkeypatch.setattr(ConflictDetector, 'reconcile_qualified_facts', capture)
    monkeypatch.setattr(builder, '_semantic_organization', check)
    from tests.test_native_extraction_handoff import build_child
    build_child(tmp_path, stop_before_publication=False)
