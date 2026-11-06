"""Address-only reader of native content; tables remain native cells, not text mirrors."""
from __future__ import annotations

import math
from typing import Any

def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, dict) or not all(isinstance(value.get(key), (int, float)) for key in ("l", "t", "r", "b")):
        return None
    return [float(value[key]) for key in ("l", "t", "r", "b")]


def _docling_locations(document: dict[str, Any], text: str, *, sink=None, address_only=False) -> list[dict[str, Any]]:
    """Project native reading order and source structure during index production."""
    from ..semantic_artifact_schema import stable_digest
    if document.get("format") == "pdf-text":
        pages = document.get("pages", [])
        if "\n".join(page["text"] for page in pages) != text:
            raise ValueError("native PDF page text does not match the representation")
        locations = []
        cursor = 0
        for page in pages:
            quote = page["text"]
            if quote.strip():
                ref = f"#/pages/{page['page_number']}"
                record = {"start": cursor, "end": cursor + len(quote),
                    "quote": quote, "page": page["page_number"], "bbox": None,
                    "section_path": [], "source_ref": ref, "source_kind": "page",
                    "table_id": None, "cell": None, "ref": ref, "structure": {}}
                if address_only:
                    record.pop('quote')
                    record['quoteAddress'] = dict(kind='source', start=cursor, end=cursor+len(quote))
                (sink or locations.append)(record)
            cursor += len(quote) + 1
        return locations
    raw = document.get("document") if document.get("format") == "docling" else None
    if not isinstance(raw, dict):
        return []
    projected, native_ranges, chunks, _ = native_scalar_projection(document)
    if projected != text:
        raise ValueError('native Docling scalar view does not match the representation')
    ranges: dict[str, list[tuple[int, int, dict[str, Any] | None]]] = {}
    whole_ranges: dict[str, tuple[int, int]] = {}
    descriptors = {chunk['ref']: chunk['locator'] for chunk in chunks}
    rich_cell_items = {}
    for locator in descriptors.values():
        context = locator.get('tableCell')
        if context and context.get('contentRef'):
            rich_cell_items.setdefault((context['tableRef'], context['cellIndex']), []).append(locator)
    for span in native_ranges:
        scalar_ref = '#/' + span['nativeRef'].removeprefix('#/document/document/')
        locator = descriptors[span['nativeRef']]
        item_ref = locator['doclingRefs'][0]
        item = raw
        for key in item_ref[2:].split('/'):
            item = item[int(key)] if isinstance(item, list) else item[key]
        key = scalar_ref if locator.get('tableCell') else item_ref
        a, b = span['windowStart'], span['windowEnd']
        previous = whole_ranges.get(key)
        whole_ranges[key] = (previous[0] if previous else a, b)
        provs = item.get('prov', [])
        if locator.get('tableCell') and scalar_ref.startswith('#/tables/'):
            cell = item['data']['table_cells'][locator['tableCell']['cellIndex']]
            # A single table provenance establishes the cell's page even when
            # its precise box is absent. Never reuse the whole-table box or
            # guess a cell page from a table spanning multiple provenances.
            provs = [{**provs[0], 'bbox': cell.get('bbox'), 'charspan': [0, span['end']]}] if len(provs) == 1 else []
        if not provs:
            ranges.setdefault(key, []).append((a, b, None))
        for prov in provs:
            lo, hi = prov.get('charspan', [0, span['end']])
            lo, hi = max(span['start'], lo), min(span['end'], hi)
            if lo < hi:
                ranges.setdefault(key, []).append((a + lo - span['start'], a + hi - span['start'], prov))
    indexed = {
        item["self_ref"]: item
        for collection in ("groups", "texts", "tables", "pictures", "key_value_items", "form_items")
        for item in raw.get(collection, [])
        if isinstance(item, dict) and isinstance(item.get("self_ref"), str)
    }
    locations: list[dict[str, Any]] = []
    section_path: list[str] = []
    section_addresses: list[dict] = []
    seen: set[str] = set()

    def address(ref, value, *, strip=False):
        lo = len(value)-len(value.lstrip()) if strip else 0
        hi = len(value.rstrip()) if strip else len(value)
        return dict(kind='native', ref='#/document/document/' + ref[2:], start=lo, end=hi)

    def emit(record, *, scalar_ref, original):
        if address_only:
            record = dict(record)
            record.pop('quote')
            record['quoteAddress'] = (dict(kind='source', start=record['start'], end=record['end'])
                if record['start'] is not None else address(scalar_ref, original, strip=True))
            record.pop('section_path')
            record['sectionPathAddresses'] = list(section_addresses)
            record['structure'] = dict(record['structure'])
            if 'original_text' in record['structure']:
                value = record['structure'].pop('original_text')
                record['originalTextAddress'] = address(record['source_ref'] + '/orig', value)
        (sink or locations.append)(record)

    def add(quote: Any, item: dict[str, Any], *, table_id: str | None = None,
            cell: str | None = None, cell_bbox: Any = None, locate_text: bool = True, structure=None,
            scalar_key: str | None = None) -> None:
        if not isinstance(quote, str) or not quote.strip():
            return
        provenances = [value for value in item.get('prov', []) if isinstance(value, dict)]
        pages = {value.get('page_no') for value in provenances}
        prov = provenances[0] if len(pages) == 1 else {}
        record = {
            "start": None,
            "end": None,
            "quote": quote.strip(),
            "page": prov.get('page_no'),
            "bbox": _bbox(cell_bbox) or _bbox(prov.get('bbox')),
            "section_path": list(section_path),
            "source_ref": item.get("self_ref"),
            "source_kind": item.get("label"),
            "table_id": table_id,
            "cell": cell,
            "ref": item.get("self_ref") + ("/" + cell if cell else ""),
            "structure": structure or {},
        }
        key = scalar_key or item['self_ref']
        scalar_ref = key if key.endswith('/text') else key + '/text'
        spans = ranges.get(key, []) if locate_text else []
        if not spans or len(spans) > 1:
            # Preserve the whole native reference used by paid extraction across pages.
            whole = whole_ranges.get(key) if locate_text else None
            if whole:
                record.update(start=whole[0], end=whole[1], quote=text[whole[0]:whole[1]])
            emit(record, scalar_ref=scalar_ref, original=quote)
        for start, end, provenance in spans:
            provenance = provenance or {}
            emit({**record, 'start': start, 'end': end,
                'quote': text[start:end], 'page': provenance.get('page_no'),
                'bbox': _bbox(provenance.get('bbox')),
                'ref': record['ref'] if len(spans) == 1 else f"{record['ref']}/chars/{start}:{end}"},
                scalar_ref=scalar_ref, original=quote)

    def visit(ref: str) -> None:
        if ref in seen:
            return
        seen.add(ref)
        item = indexed.get(ref)
        if not item or item.get("content_layer") == "furniture":
            return
        label = item.get("label")
        if label == "section_header" and isinstance(item.get("text"), str):
            level = item.get("level") if isinstance(item.get("level"), int) and item["level"] > 0 else 1
            section_path[:] = section_path[:level - 1] + [item["text"].strip()]
            section_addresses[:] = section_addresses[:level - 1] + [address(ref + '/text', item['text'], strip=True)]
        if ref.startswith("#/tables/") or label == "table":
            spans = ranges.get(ref, [])
            if spans:
                add('\n\n'.join(text[start:end] for start, end, _ in spans), item,
                    table_id=f"table:{stable_digest(ref).split(':')[1][:24]}")
            cells = item.get("data", {}).get("table_cells", []) if isinstance(item.get("data"), dict) else []
            for cell_index, value in sorted(enumerate(cells),
                                key=lambda pair: (pair[1].get("start_row_offset_idx", 0), pair[1].get("start_col_offset_idx", 0))):
                row, col = value.get("start_row_offset_idx"), value.get("start_col_offset_idx")
                if isinstance(row, int) and isinstance(col, int):
                    structure = {**{key: value[key] for key in (
                            "start_row_offset_idx", "end_row_offset_idx", "start_col_offset_idx", "end_col_offset_idx",
                            "row_span", "col_span", "column_header", "row_header", "row_section") if key in value},
                            "captions": item.get("captions", []), "footnotes": item.get("footnotes", [])}
                    if 'ref' not in value:
                        add(value.get("text"), item, table_id=f"table:{stable_digest(ref).split(':')[1][:24]}",
                            cell=f"r{row}:c{col}", cell_bbox=value.get("bbox"),
                            scalar_key=f'{ref}/data/table_cells/{cell_index}/text', structure=structure)
                    else:
                        # The reader has already resolved rich-cell child refs.
                        # Use its exact scalar mapping, not a flattened cell body.
                        for locator in rich_cell_items.get((ref, cell_index), []):
                            child = raw
                            for key in locator['doclingRefs'][0][2:].split('/'):
                                child = child[int(key)] if isinstance(child, list) else child[key]
                            add(child['text'], child, table_id=f"table:{stable_digest(ref).split(':')[1][:24]}",
                                cell=f"r{row}:c{col}/{locator['doclingRefs'][0][2:]}",
                                scalar_key=locator['doclingRefs'][0], structure=structure)
            for note in [*item.get("captions", []), *item.get("footnotes", [])]:
                if isinstance(note, dict) and isinstance(note.get("$ref"), str):
                    visit(note["$ref"])
        else:
            structure = {}
            if label in ("formula", "code"):
                if isinstance(item.get("orig"), str) and item["orig"] != item.get("text"):
                    structure["original_text"] = item["orig"]
                for key in ("code_language", "captions", "footnotes", "references"):
                    if item.get(key):
                        structure[key] = item[key]
            add(item.get("text"), item, structure=structure)
        # Content-bearing items (not just groups) may also own child structure.
        for child in item.get("children", []):
            child_ref = child.get("$ref") if isinstance(child, dict) else child
            if isinstance(child_ref, str):
                visit(child_ref)

    body = raw.get("body")
    for child in body.get("children", []) if isinstance(body, dict) else []:
        ref = child.get("$ref") if isinstance(child, dict) else child
        if isinstance(ref, str):
            visit(ref)
    return locations

SCALAR_SEGMENT = 16 * 1024
SOURCE_WINDOW_CHARS = 12_288


def native_scalar_projection(document):
    """Transient extraction view of the same addresses the native reader serves.

    This is a build operation, not a persisted content representation. Joining
    adjacent segments of one scalar must not insert synthetic whitespace.
    """
    values, ranges, chunks, pages = [], [], [], []
    previous, offset = None, 0
    def accept(kind, record):
        nonlocal previous, offset
        if kind == 'pages':
            pages.append(record)
            return
        chunks.append(record)
        if record['start'] == record['end']:
            return
        ref = record['ref']
        value = {'document': document}
        for key in ref[2:].split('/'):
            key = key.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) else value[key]
        value = value[record['start']:record['end']]
        separator = '\n\n' if previous is not None and previous != ref else ''
        if separator:
            values.append(separator)
            offset += len(separator)
        ranges.append(dict(nativeRef=ref, start=record['start'], end=record['end'],
            windowStart=offset, windowEnd=offset + len(value),
            **({'joinBefore': separator} if separator else {})))
        values.append(value)
        offset += len(value)
        previous = ref
    project_document_reader(document, sink=accept)
    return ''.join(values), ranges, chunks, pages


def native_text_projection(document):
    """Return the builder's canonical flattened text and address map."""
    kind = document.get('format')
    if kind == 'docling':
        text, ranges, _, _ = native_scalar_projection(document)
        mappings = []
        cursor = 0
        for item in ranges:
            if cursor < item['windowStart']:
                mappings.append(dict(start=cursor, end=item['windowStart'], kind='newline',
                    joinBeforeLength=len(item.get('joinBefore', ''))))
            mappings.append(dict(start=item['windowStart'], end=item['windowEnd'], kind='native',
                nativeRef=item['nativeRef'], nativeStart=item['start'],
                joinBeforeLength=len(item.get('joinBefore', ''))))
            cursor = item['windowEnd']
        return text, mappings
    if kind == 'text':
        parts, separator = [(document['text'], '#/document/text')], ''
    elif kind == 'pdf-text':
        parts = [(page['text'], f"#/document/pages/{index}/text")
            for index, page in enumerate(document['pages'])]
        separator = '\n'
    elif kind in {'epub', 'flat-odf'}:
        parts = [(section['text'], f"#/document/sections/{index}/text")
            for index, section in enumerate(document['sections'])]
        separator = '\n\n'
    else:
        raise ValueError('unsupported native source text format')
    values, mappings, cursor, previous = [], [], 0, None
    for value, ref in parts:
        if previous is not None:
            values.append(separator)
            if separator:
                mappings.append(dict(start=cursor, end=cursor+len(separator), kind='newline',
                    joinBeforeLength=len(separator)))
                cursor += len(separator)
        if value:
            values.append(value)
            mappings.append(dict(start=cursor, end=cursor+len(value), kind='native',
                nativeRef=ref, nativeStart=0,
                joinBeforeLength=len(separator) if previous is not None and
                    mappings and mappings[-1]['kind'] == 'newline' else 0))
            cursor += len(value)
        previous = ref
    return ''.join(values), mappings


def source_text_windows(text):
    """Yield exact offsets used by the semantic builder's source windows."""
    if (len(text) > SOURCE_WINDOW_CHARS and not any(char.isspace() or char in '.!?#`:' for char in text)
            and not (len(text) > 1 and text[:2] in ('- ', '* ', '+ '))):
        for start in range(0, len(text), SOURCE_WINDOW_CHARS):
            yield start, min(start + SOURCE_WINDOW_CHARS, len(text))
        return
    from ..split.structural_chunker import StructuralChunker
    from ..split.sliding_window_chunker import SlidingWindowChunker
    cursor = 0
    for chunk in StructuralChunker(respect_headers=True, respect_sections=True,
            max_chunk_size=SOURCE_WINDOW_CHARS).chunk(text):
        start = cursor
        end = min(len(text), chunk.end_index)
        if end > start and text[start:end].strip():
            if end - start <= SOURCE_WINDOW_CHARS:
                yield start, end
            else:
                part_cursor = start
                for part in SlidingWindowChunker(chunk_size=SOURCE_WINDOW_CHARS, overlap=0).chunk(text[start:end]):
                    part_start = part_cursor
                    part_end = start + min(end-start, part.end_index)
                    if part_end > part_start and text[part_start:part_end].strip():
                        yield part_start, part_end
                        part_cursor = part_end
                if part_cursor < end and text[part_cursor:end].strip():
                    yield part_cursor, end
            cursor = end
    if cursor < len(text) and text[cursor:].strip():
        yield cursor, len(text)


def _ranges(ref, value, **locator):
    from ..semantic_worker_context import check_query_cancellation
    if not isinstance(value, str):
        raise ValueError('native reader scalar must be a string')
    for start in range(0, len(value), SCALAR_SEGMENT):
        check_query_cancellation()
        end = min(start + SCALAR_SEGMENT, len(value))
        yield {'ref': ref, 'start': start, 'end': end,
               'locator': {'nativeRef': ref, 'coordinateSpace': 'native-scalar',
                           'startChar': start, 'endChar': end, **locator}}


def _box(raw, page):
    from docling_core.types.doc.base import BoundingBox
    box = BoundingBox.model_validate(raw).to_top_left_origin(page['height'])
    x, y, width, height = box.l, box.t, box.r - box.l, box.b - box.t
    if not (all(math.isfinite(v) for v in (x, y, width, height)) and x >= 0 and y >= 0
            and width > 0 and height > 0 and x + width <= page['width'] + .01
            and y + height <= page['height'] + .01):
        raise ValueError('invalid native bounding box')
    return dict(x=x, y=y, width=width, height=height)


def project_document_reader(document: dict[str, Any], *, sink=None) -> dict[str, Any]:
    """Only addresses/locations, incrementally emitted into the installed index."""
    chunks, page_parts = [], []
    def push(field, record):
        if sink is None:
            (chunks if field == 'chunks' else page_parts).append(record)
        else:
            sink(field, record)
    format = document.get('format')
    if format == 'text':
        for record in _ranges('#/document/text', document['text'], locationState='coarse'):
            push('chunks', record)
        return {'chunks': chunks, 'pages': []}
    if format in {'epub', 'flat-odf'}:
        for index, section in enumerate(document['sections']):
            locator = ({'kind':'epub-section', 'sectionId':section['id'], 'href':section['href']}
                       if format == 'epub' else section['locator'])
            for record in _ranges(f'#/document/sections/{index}/text', section['text'],
                    locationState='coarse', **locator):
                push('chunks', record)
        # Structural locations are not PDF page geometry.
        return {'chunks': chunks, 'pages': []}
    if format == 'pdf-text':
        summaries = {}
        for index, page in enumerate(document['pages']):
            count = 0
            state = 'invalid_layout' if page['text'].strip() else 'no_text_content'
            for record in _ranges(f'#/document/pages/{index}/text', page['text'],
                    page=page['page_number'], locationState='coarse'):
                push('chunks', record)
                push('pages', {**record, 'pageNumber': page['page_number'], 'state': state,
                    'pagePart': count, 'blockStart': count,
                    'hasMoreParts': record['end'] < len(page['text'])})
                count += 1
            if not count:
                push('pages', {'pageNumber': page['page_number'], 'state': state,
                    'pagePart': 0, 'hasMoreParts': False})
            summaries[page['page_number']] = {'state': state, 'partCount': max(1, count)}
        return {'chunks': chunks, 'pages': page_parts, 'pageSummaries': summaries}
    if format != 'docling':
        raise ValueError('unsupported native reader format')
    native = document['document']
    if len(native.get('pages', {})) > 100_000:
        raise ValueError('native reader publication page budget exceeded')
    pages = {}
    origins = {page['page_number']: page.get('origin') for page in document.get('pages', [])}
    for number, page in native.get('pages', {}).items():
        size = page['size']
        pages[int(number)] = {'pageNumber': int(number), 'width': size['width'],
            'height': size['height'], 'state': 'no_text_content', 'parts': [], 'partCount': 0}
    active, seen = set(), set()

    def resolve(ref):
        if not isinstance(ref, str) or not ref.startswith('#/') or len(ref) > 128:
            raise ValueError('invalid native reader reference')
        result = native
        for key in ref[2:].split('/'):
            result = result[int(key)] if isinstance(result, list) else result[key]
        return result

    def visit(ref, depth=0, cell_context=None):
        from ..semantic_worker_context import check_query_cancellation
        check_query_cancellation()
        if depth > 64 or ref in active:
            raise ValueError('native reader reference cycle/depth limit')
        if len(seen) >= 1_000_000:
            raise ValueError('native reader publication item budget exceeded')
        if ref in seen:
            return
        active.add(ref)
        item = resolve(ref)
        if item.get('self_ref') != ref:
            raise ValueError('native reader item identity mismatch')
        if ref.startswith('#/texts/'):
            scalar(ref, item, item['text'], ref + '/text', cell_context)
        elif ref.startswith('#/tables/'):
            from docling_core.types.doc.document import TableCell, RichTableCell
            for index, cell in enumerate(item['data']['table_cells']):
                model = (RichTableCell if 'ref' in cell else TableCell).model_validate(cell)
                location = {'tableRef': ref, 'cellIndex': index,
                    'rowStart': model.start_row_offset_idx, 'rowEnd': model.end_row_offset_idx,
                    'colStart': model.start_col_offset_idx, 'colEnd': model.end_col_offset_idx,
                    'rowSpan': model.row_span, 'colSpan': model.col_span,
                    'columnHeader': model.column_header, 'rowHeader': model.row_header,
                    'rowSection': model.row_section, 'fillable': model.fillable}
                if isinstance(model, RichTableCell):
                    location['contentRef'] = model.ref.cref
                    visit(model.ref.cref, depth + 1, location)
                else:
                    scalar(ref, item, model.text, f'{ref}/data/table_cells/{index}/text', location,
                           cell.get('bbox'), native_cell=True)
        for child in item.get('children', []):
            visit(child['$ref'], depth + 1, cell_context)
        active.remove(ref)
        seen.add(ref)

    def scalar(item_ref, item, value, native_ref, table_cell=None, cell_box=None, native_cell=False):
        ref = '#/document/document/' + native_ref[2:]
        loc = {'doclingRefs': [item_ref], 'locationState': 'coarse'}
        for prov in item.get('prov', []):
            page = pages.get(prov['page_no'])
            try:
                if page is None:
                    raise ValueError('unknown native page')
                if native_cell:
                    if cell_box is None or len(item['prov']) != 1:
                        continue
                    _box(cell_box, page)
                else:
                    start, end = prov['charspan']
                    if not 0 <= start <= end <= len(value):
                        raise ValueError('invalid native character span')
                    _box(prov['bbox'], page)
                loc['locationState'] = 'located'
            except (ValueError, TypeError, KeyError):
                loc['locationState'] = 'invalid'
                break
        if table_cell:
            loc['tableCell'] = table_cell
            if not value:
                push('chunks', {'ref': ref, 'start': 0, 'end': 0,
                    'locator': {'nativeRef': ref, 'coordinateSpace': 'native-scalar',
                        'startChar': 0, 'endChar': 0, **loc}})
        for record in _ranges(ref, value, **loc):
            push('chunks', record)
        provs = item.get('prov', [])
        if value.strip() and not provs:
            for page in pages.values():
                page['state'] = 'invalid_layout'
        for prov in provs:
            page = pages.get(prov['page_no'])
            if page is None:
                for current in pages.values():
                    current['state'] = 'invalid_layout'
                continue
            try:
                start, end = prov['charspan']
                if native_cell:
                    # A table box cannot locate every cell. An actual native
                    # cell bbox plus one unambiguous page is required.
                    if cell_box is None or len(provs) != 1:
                        if value.strip():
                            page['state'] = 'invalid_layout'
                        continue
                    start, end = 0, len(value)
                    box = _box(cell_box, page)
                else:
                    if not 0 <= start <= end <= len(value):
                        raise ValueError('invalid native character span')
                    box = _box(prov['bbox'], page)
                for descriptor in _ranges(ref, value, **loc):
                    a, b = max(start, descriptor['start']), min(end, descriptor['end'])
                    if a >= b:
                        continue
                    descriptor = {**descriptor, 'start': a, 'end': b,
                        'locator': {**descriptor['locator'], 'startChar': a, 'endChar': b}}
                    part = {**descriptor, 'box': box}
                    if sink is None:
                        page['parts'].append(part)
                    else:
                        push('pages', {key: val for key, val in page.items() if key not in ('parts','partCount')}
                            | part | {'pagePart': page['partCount'], 'blockStart': page['partCount'], 'hasMoreParts': True})
                    page['partCount'] += 1
            except (ValueError, TypeError, KeyError):
                page['state'] = 'invalid_layout'

    visit('#/body')
    for number in sorted(pages):
        page = pages[number]
        parts = page.pop('parts')
        count = page.pop('partCount')
        if page['state'] != 'invalid_layout' and count:
            # Docling scalar provenance does not carry OCR origin. The
            # converter's page cell evidence supplies only a page-level state.
            page['state'] = {'native': 'native_text', 'ocr': 'ocr_text',
                             'mixed': 'mixed_text'}.get(origins.get(number), 'document_text')
        if not count:
            push('pages', {**page, 'pagePart': 0, 'hasMoreParts': False})
        for ordinal, part in enumerate(parts):
            push('pages', {**page, **part, 'pagePart': ordinal,
                'blockStart': ordinal, 'hasMoreParts': ordinal + 1 < len(parts)})
        page['partCount'] = max(1, count)
    result = {'chunks': chunks, 'pages': page_parts}
    if sink is not None:
        result['pageSummaries'] = pages
    return result
