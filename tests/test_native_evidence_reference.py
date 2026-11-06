"""Transient evidence references preserve accepted ranges and reject stale bodies."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantica import semantic_publication_builder as builder
from semantica import semantic_document_reader as native_reader
from semantica.semantic_artifact_schema import DocumentLocator, EvidenceSpan
from semantica.semantic_source_artifact import _native_text
from tests.test_native_document_reader import payload


def test_structural_reference_replays_native_scalar_without_linear_coordinates(tmp_path):
    from docling_core.types.doc import DoclingDocument
    from docling_core.types.doc.document import TableData, RichTableCell, RefItem
    from semantica.semantic_source_artifact import _NativeSourceLocations
    from tests.test_native_document_reader import request

    native = DoclingDocument(name='native')
    native.add_text(label='text', text='Body evidence')
    table = native.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[]))
    note = native.add_text(label='text', text='独立😀 note', parent=table)
    native.add_table_cell(table, RichTableCell(text='formatted mirror', ref=RefItem(cref=note.self_ref),
        start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1))
    path = tmp_path / 'structural.json'
    digests = native_reader.write_reader_artifact(path,
        payload({'format': 'docling', 'document': native.export_to_dict()}))
    reader = request(path, digests)
    locations = _NativeSourceLocations(reader)
    location = next(locations.pages(cells_only=True))
    assert location['start'] is None and location['end'] is None
    span = builder._structural_evidence(location, 'representation:r', 'native')
    reference = builder._EvidenceReference.from_span(span, reader)
    assert reference.model_dump(mode='json') == span.model_dump(mode='json')
    assert 'quote' not in reference.fields and 'quote' not in reference.fields['locator']
    built = dict(source=SimpleNamespace(source_id='source:authorized'),
        representation=SimpleNamespace(id='representation:r', origin='native'),
        evidence=[reference], source_locations=locations, native_scalar_ranges=[])
    assert [item.id for item in builder._docling_cell_evidence(built)] == [span.id]
    from semantica.semantic_artifact_schema import KnowledgeTopic
    positions, published = [], []
    def read(project, generation, position, **query):
        positions.append(position)
        return dict(items=[dict(evidence='urn:native:evidence')], next_cursor=None)
    store = SimpleNamespace(read_grounded_reference_page=read,
        stage_publication_topics=lambda project, generation, rows: published.extend(rows))
    topic = KnowledgeTopic(id='topic:one', title='Theme', entity_ids=['urn:entity'],
        evidence_ids=[span.id], metadata=dict(organization=dict(report_id='report:one', input_digest='sha256:input')))
    builder._publish_native_topics(SimpleNamespace(project_id='p'), store, 'g', [built], [topic])
    assert positions == [dict(source='source:authorized',
        nativeRef=f'#/document/document/{note.self_ref[2:]}/text', start=0, end=len(note.text))]
    assert published[0]['evidence_ids'] == ['urn:native:evidence']
    rejected = replace(reference, quote_digest=builder._digest_bytes(b'changed'))
    with pytest.raises(builder.SemanticArtifactError) as error:
        _ = rejected.quote
    assert error.value.code == 'NATIVE_EVIDENCE_RANGE_MISMATCH'
    missing = replace(reference, fields={**reference.fields,
        'metadata': {**reference.metadata, 'structural_ref': '#/missing'}})
    with pytest.raises(builder.SemanticArtifactError) as error:
        _ = missing.quote
    assert error.value.code == 'NATIVE_EVIDENCE_RANGE_MISSING'


def reference_fixture(tmp_path):
    document = {'format': 'pdf-text', 'pages': [
        {'page_number': 1, 'text': 'prefix ' + '😀漢e\u0301 first\n' * 1500},
        {'page_number': 2, 'text': '日本語 second 😀\n' * 1600}]}
    text = _native_text(document)
    path = tmp_path / 'evidence.json'
    digests = native_reader.write_reader_artifact(path, payload(document))
    index = tmp_path / 'indices' / 'independently-addressed.sqlite'
    index.parent.mkdir()
    path.with_suffix('.reader.sqlite').rename(index)
    reader = builder._source_reader_request(
        SimpleNamespace(source_id='source:authorized', material_revision='material:m'),
        SimpleNamespace(artifact_path=str(path), artifact_digest=digests[0],
                        representation_revision='representation:r', reader_index_path=str(index),
                        reader_index_digest=digests[1]))
    start, end = 5, len(text) - 3
    span = EvidenceSpan(id='evidence:unicode', representation_id='representation:r',
        quote=text[start:end], confidence=0.75,
        locator=DocumentLocator(representation_id='representation:r', origin='native',
            quote=text[start:end], start_char=start, end_char=end, quality='precise',
            section_path=['Evidence']), metadata={'source_id': 'source:authorized'})
    return builder._EvidenceReference.from_span(span, reader), span, path


def test_reference_hydrates_multiple_unicode_windows_and_separator_without_retaining_quote(tmp_path, monkeypatch):
    reference, span, _path = reference_fixture(tmp_path)
    calls = []
    read = builder._read_source_projection_text

    def observed(request, start, end):
        calls.append((start, end))
        return read(request, start=start, end=end)

    monkeypatch.setattr(builder, '_read_source_projection_text', observed)
    start, end = span.locator.start_char, span.locator.end_char
    expected_calls = [(offset, min(end, offset + builder.TEXT_WINDOW_CHARS))
                      for offset in range(start, end, builder.TEXT_WINDOW_CHARS)]
    assert len(expected_calls) >= 3
    assert '\n' in span.quote and '😀' in span.quote and 'e\u0301' in span.quote
    for _ in range(2):
        assert reference.model_dump(mode='json', by_alias=True) == span.model_dump(mode='json', by_alias=True)
    assert calls == expected_calls * 2
    assert 'quote' not in reference.fields
    assert 'quote' not in reference.fields['locator']
    assert set(vars(reference)) == {'fields', 'reader', 'quote_length', 'quote_digest'}


@pytest.mark.parametrize('target', ['artifact', 'reader-index'])
def test_reference_rejects_installation_mutation_even_after_successful_hydration(tmp_path, target):
    reference, span, path = reference_fixture(tmp_path)
    assert reference.quote == span.quote
    changed = path if target == 'artifact' else Path(reference.reader.reader_index.path)
    with changed.open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(ValueError, match='installation changed'):
        _ = reference.quote


def test_reference_rejects_same_length_quote_that_differs_from_accepted_digest(tmp_path):
    reference, span, _path = reference_fixture(tmp_path)
    changed = ('y' if span.quote[0] != 'y' else 'x') + span.quote[1:]
    rejected = replace(reference, quote_digest=builder._digest_bytes(changed.encode('utf-8')))
    with pytest.raises(builder.SemanticArtifactError) as error:
        _ = rejected.quote
    assert error.value.code == 'NATIVE_EVIDENCE_RANGE_MISMATCH'


def test_source_reader_rejects_supplied_reader_index_digest_mismatch(tmp_path):
    reference, _span, _path = reference_fixture(tmp_path)
    reader = reference.reader
    with pytest.raises(builder.SemanticArtifactError, match='reader index digest is invalid'):
        builder._source_reader_request(
            SimpleNamespace(source_id=reader.source_id, material_revision=reader.material_revision),
            SimpleNamespace(artifact_path=reader.artifact.path, artifact_digest=reader.artifact.digest,
                representation_revision=reader.representation_revision,
                reader_index_path=reader.reader_index.path, reader_index_digest='sha256:' + 'f' * 64))
