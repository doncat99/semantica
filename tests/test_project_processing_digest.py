"""Processing identities follow native implementation bytes, never checkout paths."""
from pathlib import Path

import pytest

from semantica.semantic_publication_builder import _project_processing_digest


@pytest.mark.parametrize('owner', ['triplet_store', 'pipeline', 'conflicts', 'vector_store', 'explorer', 'utils'])
def test_native_processing_owner_change_invalidates_recipe(tmp_path, owner):
    module = tmp_path / owner / 'native_owner.py'
    module.parent.mkdir()
    module.write_text('CURRENT = 1\n')
    before = _project_processing_digest(tmp_path)
    module.write_text('CURRENT = 2\n')
    assert _project_processing_digest(tmp_path) != before


def test_processing_digest_is_relocation_invariant_and_ignores_nonruntime_files(tmp_path):
    roots = [tmp_path / 'one', tmp_path / 'other' / 'checkout']
    for root in roots:
        (root / 'triplet_store').mkdir(parents=True)
        (root / 'semantic_publication_builder.py').write_text('OWNER = True\n')
        (root / 'triplet_store' / 'publication_records.py').write_text('SCHEMA = 3\n')
    expected = _project_processing_digest(roots[0])
    assert _project_processing_digest(roots[1]) == expected
    for relative in ['tests/test_owner.py', 'docs/design.py', 'triplet_store/__pycache__/owner.pyc', 'triplet_store/notes.md']:
        file = roots[1] / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('irrelevant content')
    assert _project_processing_digest(roots[1]) == expected
