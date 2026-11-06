"""Removed checkpoint owners cannot become a hidden content carrier again."""
from importlib.util import find_spec

import pytest


@pytest.mark.parametrize('module', ['project_checkpoint', 'project_checkpoint_upgrade'])
def test_removed_checkpoint_entrypoints_are_not_importable(module):
    assert find_spec('semantica.' + module) is None


def test_native_parser_does_not_create_checkpoint_body(tmp_path):
    from semantica import semantic_source_artifact as parser
    from semantica.semantic_artifact_schema import SourceBuildInput
    from semantica.source import source_content_revision
    source = tmp_path / 'source.txt'
    source.write_text('Already parsed content')
    admitted = SourceBuildInput(source_id='source', name=source.name, mime_type='text/plain',
        file_path=str(source), material_revision=source_content_revision(source))
    parsed = parser._parse_source(admitted, False, {'mode': 'local'})
    assert parsed[0] == 'Already parsed content'
    assert list(tmp_path.iterdir()) == [source]
