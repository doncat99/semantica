"""The real native context reader must not pin every page quote during extraction."""
import gc
import weakref
from types import SimpleNamespace

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import ProvenanceItem

from semantica import semantic_publication_builder as builder
from semantica import semantic_document_reader as reader
from semantica.semantic_source_artifact import _NativeSourceLocations
from tests.test_native_document_reader import payload, request


def test_current_extraction_batch_does_not_retain_complete_page_quotes(tmp_path, monkeypatch):
    native = DoclingDocument(name='large-page')
    native.add_page(page_no=1, size=Size(width=600, height=800))
    count = 80
    for index in range(count):
        text = f'Passage {index}: ' + 'descriptive context ' * 20
        native.add_text(label='text', text=text, prov=ProvenanceItem(page_no=1,
            charspan=(0, len(text)), bbox=BoundingBox(l=1, t=10, r=100, b=1,
                coord_origin=CoordOrigin.BOTTOMLEFT)))
    path = tmp_path / 'page.json'
    digests = reader.write_reader_artifact(path, payload({'format': 'docling',
        'document': native.export_to_dict(), 'pages': []}))
    locations = _NativeSourceLocations(request(path, digests, 'source_windows'))
    read = reader.read_source_locations
    refs, consumed = [], []

    class TrackedQuote(str):
        pass

    def observe(*args, **kwargs):
        result = read(*args, **kwargs)
        for item in result['items']:
            if 'quote' in item:
                item['quote'] = TrackedQuote(item['quote'])
                refs.append(weakref.ref(item['quote']))
        return result

    def extract(text, relay, spec, item, context, formula, **kwargs):
        gc.collect()
        live = sum(ref() is not None for ref in refs)
        assert live < count // 2, f'complete page quotes retained: {live}/{count}'
        consumed.extend(record['ref'] for record in context)
        return {'entities': [], 'relations': []}, [], False

    monkeypatch.setattr(reader, 'read_source_locations', observe)
    monkeypatch.setattr(builder, '_extract_window_context', extract)
    builder._extract_window('Passage', SimpleNamespace(context_window_tokens=7000,
        max_output_tokens=1000), None, locations, (0, 7, 'Passage'))
    assert set(consumed) == {f'#/texts/{index}' for index in range(count)}
