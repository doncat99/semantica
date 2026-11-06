"""G1 capability probe, not a production reader or a text serializer.

Native models own content. The disposable index holds only JSON byte addresses.
Sparse scalar addresses remain a test-only capability, not a production reader.
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tracemalloc
import pytest

from pydantic import BaseModel
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem, TableCell, TableData
from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.document import RichTableCell
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer


def _publish(document, target):
    """Probe publication while the parser already owns the native model."""
    index = target.with_suffix(".sqlite")
    with target.open("wb") as output, sqlite3.connect(index) as db:
        db.execute("CREATE TABLE addresses(ref TEXT PRIMARY KEY, offset INTEGER, length INTEGER, digest BLOB) WITHOUT ROWID")
        db.execute("CREATE TABLE scalar_segments(ref TEXT, codepoint_start INTEGER, codepoint_end INTEGER, offset INTEGER, length INTEGER, digest BLOB, PRIMARY KEY(ref, codepoint_start)) WITHOUT ROWID")
        active_digests = []

        def emit(raw):
            output.write(raw)
            for digest in active_digests:
                digest.update(raw)

        def write(value, path=(), large_cell=False):
            start = output.tell()
            selected = (len(path) == 1 and path[0] in ("schema_name", "version", "name", "origin")) or (
                len(path) == 2 and path[0] == "pages") or (
                len(path) == 3 and path[0] == "texts" and path[2] == "text") or (
                len(path) == 2 and path[0] == "texts") or (
                len(path) == 3 and path[0] in ("tables", "pictures", "groups") and path[2] in
                ("self_ref", "label", "parent", "prov", "captions", "footnotes")) or (
                len(path) == 4 and path[0] == "tables" and path[2] == "data" and path[3] in ("num_rows", "num_cols")) or (
                path[0:1] == ("tables",) and path[2:4] == ("data", "table_cells") and
                (len(path) == 5 or (len(path) == 6 and large_cell)))
            if selected:
                active_digests.append(hashlib.sha256())
            # Traverse native fields directly: model_dump would recursively copy
            # every cell in a large table before the streaming writer sees it.
            if isinstance(value, (BaseModel, dict)):
                entries = ((field.serialization_alias or field.alias or name, value.__dict__[name])
                           for name, field in type(value).model_fields.items()
                           if not field.exclude and value.__dict__[name] is not None) if isinstance(value, BaseModel) else value.items()
                emit(b"{")
                for position, (key, child) in enumerate(entries):
                    if position:
                        emit(b",")
                    emit(json.dumps(str(key)).encode() + b":")
                    write(child, (*path, str(key)), large_cell=(len(path) == 5 and
                          path[0:1] == ("tables",) and path[2:4] == ("data", "table_cells") and len(value.text) > 16384))
                emit(b"}")
            elif isinstance(value, (list, tuple)):
                emit(b"[")
                for position, child in enumerate(value):
                    if position:
                        emit(b",")
                    write(child, (*path, str(position)))
                emit(b"]")
            elif isinstance(value, str):
                # Each fragment is encoded by the standard encoder. Removing its
                # quotes joins escaped interiors into one valid native scalar.
                emit(b'"')
                for position in range(0, len(value), 16384):
                    raw = json.dumps(value[position:position+16384], ensure_ascii=False).encode("utf-8")[1:-1]
                    offset = output.tell()
                    emit(raw)
                    if len(value) > 16384 and path[-1:] == ("text",) and (path[0] == "texts" or path[0] == "tables"):
                        db.execute("INSERT INTO scalar_segments VALUES (?,?,?,?,?,?)", (
                            "#/" + "/".join(path), position, min(position+16384, len(value)),
                            offset, len(raw), hashlib.sha256(raw).digest()))
                emit(b'"')
            else:
                emit(json.dumps(value, ensure_ascii=False).encode("utf-8"))
            if selected:
                end = output.tell()
                digest = active_digests.pop().digest()
                db.execute("INSERT INTO addresses VALUES (?,?,?,?)", ("#/" + "/".join(path), start, end-start, digest))

        write(document)
    return index


_READ_PROCESS = r'''
import hashlib, json, sqlite3, sys, tracemalloc
from docling_core.types.doc.document import TableCell, TextItem
source, index, request = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
tracemalloc.start()
with sqlite3.connect(index) as db:
    offset, length, digest = db.execute("SELECT offset,length,digest FROM addresses WHERE ref=?", (request['ref'],)).fetchone()
    tail = db.execute('SELECT codepoint_end FROM scalar_segments WHERE ref=? ORDER BY codepoint_start DESC LIMIT 1', (request['ref'],)).fetchone() if request['ref'].endswith('/text') else None
    segmented = tail is not None
    if segmented:
        total = tail[0]
        start = request['start']
        end = total if request['end'] is None else min(total, request['end'])
        assert 0 <= start <= end
        # The first overlapping fixed segment is found by the primary key;
        # no all-segment fetch, count or scan precedes the range read.
        rows = db.execute('SELECT codepoint_start,codepoint_end,offset,length,digest FROM scalar_segments WHERE ref=? AND codepoint_start>=? AND codepoint_start<? ORDER BY codepoint_start', (request['ref'], start//16384*16384, end))
        chunks, read_bytes = [], 0
        with open(source, 'rb') as data:
            for cp_start, cp_end, byte_offset, byte_length, segment_digest in rows:
                assert read_bytes + byte_length <= request['budget']
                data.seek(byte_offset)
                raw = data.read(byte_length)
                assert hashlib.sha256(raw).digest() == segment_digest
                text = json.loads(b'"' + raw + b'"')
                assert len(text) == cp_end - cp_start
                chunks.append(text[max(start-cp_start,0):min(end-cp_start,len(text))])
                read_bytes += len(raw)
        value = ''.join(chunks)
        print(json.dumps({'state':'ready','value':value,'readBytes':read_bytes,'objectBytes':len(json.dumps(value).encode()),'peakAllocationBytes':tracemalloc.get_traced_memory()[1]}))
        sys.exit(0)
if length > request['budget']:
    print(json.dumps({'state':'oversized_scalar_gap','readBytes':0,'length':length}))
else:
    with open(source, 'rb') as data:
        data.seek(offset)
        raw = data.read(length)
    assert hashlib.sha256(raw).digest() == digest
    value = json.loads(raw)
    if '/table_cells/' in request['ref'] and len(request['ref'].split('/')) == 6:
        value = TableCell.model_validate(value).model_dump(mode='json', exclude_none=True)
    elif request['ref'].endswith('/text'):
        value = value[request['start']:request['end']]
    elif request['ref'].startswith('#/texts/'):
        value = TextItem.model_validate(value).model_dump(mode='json', by_alias=True, exclude_none=True)
    print(json.dumps({'state':'ready','value':value,'readBytes':len(raw),'objectBytes':len(json.dumps(value).encode())}))
'''


def _read(target, index, ref, budget=4096, start=0, end=None):
    result = subprocess.run([sys.executable, "-c", _READ_PROCESS, str(target), str(index),
                             json.dumps(dict(ref=ref, budget=budget, start=start, end=end))],
                            capture_output=True, text=True, check=True, timeout=20)
    return json.loads(result.stdout)


_CLOSURE_PROCESS = r'''
import hashlib, json, sqlite3, sys, time
from pydantic import TypeAdapter
from docling_core.types.doc.document import TextItem, TableItem, TableCell, RichTableCell, PictureItem, GroupItem
source, index, request = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
db = sqlite3.connect(index)
data = open(source, 'rb')
loaded, nodes, containers, cells, active, done = {}, {}, {}, {}, set(), set()
read_bytes = 0
deadline = time.monotonic() + 2
class ClosureFailure(Exception):
    pass
def check_depth(depth):
    if depth > request['maxDepth']:
        raise ClosureFailure('depth_limit')
def read(ref, optional=False):
    global read_bytes
    if time.monotonic() > deadline:
        raise ClosureFailure('time_limit')
    if ref in loaded:
        return loaded[ref]
    row = db.execute('SELECT offset,length,digest FROM addresses WHERE ref=?', (ref,)).fetchone()
    if row is None:
        if optional:
            return None
        raise ClosureFailure('missing_ref')
    if len(loaded) >= request['maxObjects']:
        raise ClosureFailure('object_limit')
    offset, length, digest = row
    if read_bytes + length > request['maxBytes']:
        raise ClosureFailure('byte_limit')
    data.seek(offset)
    raw = data.read(length)
    read_bytes += len(raw)
    if len(raw) != length or hashlib.sha256(raw).digest() != digest:
        raise ClosureFailure('digest_mismatch')
    value = json.loads(raw)
    loaded[ref] = value
    return value
def metadata(ref, depth, ancestors=()):
    check_depth(depth)
    if ref == '#/body':
        return
    if ref in ancestors:
        raise ClosureFailure('parent_cycle')
    if ref in containers:
        return
    collection = ref.split('/')[1]
    model = {'tables':TableItem, 'pictures':PictureItem, 'groups':GroupItem, 'texts':TextItem}.get(collection)
    if model is None:
        raise ClosureFailure('unsupported_ref')
    value = {}
    native_text = TextItem.model_validate(read(ref)) if collection == 'texts' else None
    for field in ('self_ref', 'label', 'parent', 'prov', 'captions', 'footnotes'):
        if field in model.model_fields:
            if native_text is not None:
                value[field] = getattr(native_text, field)
            else:
                raw = read(ref+'/'+field, optional=field not in ('self_ref', 'label'))
                if raw is None:
                    continue
                value[field] = TypeAdapter(model.model_fields[field].annotation).validate_python(raw)
    if value['self_ref'] != ref:
        raise ClosureFailure('identity_mismatch')
    containers[ref] = value
    if collection == 'tables':
        value['data'] = {field:read(ref+'/data/'+field) for field in ('num_rows', 'num_cols')}
    parent = value.get('parent')
    if parent:
        metadata(parent.cref, depth+1, (*ancestors, ref))
    for field in ('captions', 'footnotes'):
        for dependency in value.get(field, []):
            node(dependency.cref, depth+1)
def node(ref, depth):
    check_depth(depth)
    if ref in active:
        raise ClosureFailure('dependency_cycle')
    if ref in done:
        return
    active.add(ref)
    raw = read(ref)
    value = TextItem.model_validate(raw)
    if value.self_ref != ref:
        raise ClosureFailure('identity_mismatch')
    nodes[ref] = value.model_dump(mode='json', by_alias=True, exclude_none=True)
    # Parents are metadata only. Do not follow their children back to this node
    # or to unrelated siblings; a normal parent/child pair is not a cycle.
    if value.parent:
        metadata(value.parent.cref, depth+1)
    for child in value.children:
        node(child.cref, depth+1)
    active.remove(ref)
    done.add(ref)
try:
    for ref in request['roots']:
        if '/data/table_cells/' in ref:
            raw = read(ref)
            model = RichTableCell if 'ref' in raw else TableCell
            value = model.model_validate(raw)
            cells[ref] = value.model_dump(mode='json', by_alias=True, exclude_none=True)
            metadata(ref.split('/data/')[0], 0)
            if isinstance(value, RichTableCell):
                node(value.ref.cref, 1)
        else:
            node(ref, 0)
    # Convert only requested structured model fields, not a fake DoclingDocument.
    def encoded(v):
        if hasattr(v, 'model_dump'):
            return v.model_dump(mode='json', by_alias=True, exclude_none=True)
        raise TypeError(type(v).__name__)
    print(json.dumps({'state':'ready','nodes':nodes,'containers':containers,'cells':cells,
                      'readBytes':read_bytes,'objectsRead':len(loaded)}, default=encoded))
except ClosureFailure as failure:
    print(json.dumps({'state':str(failure),'readBytes':read_bytes,'objectsRead':len(loaded)}))
finally:
    db.close()
    data.close()
'''


def _closure(target, index, roots, max_objects=64, max_bytes=8192, max_depth=8):
    result = subprocess.run([sys.executable, "-c", _CLOSURE_PROCESS, str(target), str(index),
        json.dumps(dict(roots=roots, maxObjects=max_objects, maxBytes=max_bytes, maxDepth=max_depth))],
        capture_output=True, text=True, check=True, timeout=20)
    return json.loads(result.stdout)


def _provenance(page, start, end):
    return ProvenanceItem(page_no=page, charspan=(start, end), bbox=BoundingBox(l=1, t=1, r=10, b=10))


def test_native_fields_survive_restart_without_reader_body_mirror(tmp_path):
    doc = DoclingDocument(name="native-only")
    for page in (1, 2):
        doc.add_page(page_no=page, size=Size(width=600, height=800))
    for _ in range(1800):
        doc.add_text(label="text", text="preceding content " * 20)
    text = 'A😀漢e\u0301\\" ESG'
    item = doc.add_text(label="text", text=text, prov=_provenance(1, 1, 4))
    picture = doc.add_picture(prov=_provenance(2, 0, 0))
    ocr = doc.add_text(label="text", text="OCR 漢😀 ESG", parent=picture, prov=_provenance(2, 0, 10))
    table = doc.add_table(data=TableData(num_rows=2, num_cols=1, table_cells=[
        TableCell(text="same ESG 😀|\\\n", start_row_offset_idx=row, end_row_offset_idx=row+1,
                  start_col_offset_idx=0, end_col_offset_idx=1,
                  bbox=BoundingBox(l=1, t=1, r=10, b=10))
        for row in range(2)]), prov=_provenance(1, 0, 0))
    table.prov.append(_provenance(2, 0, 0))
    target = tmp_path / "document.json"
    index = _publish(doc, target)
    assert DoclingDocument.model_validate_json(target.read_bytes()).export_to_dict() == doc.export_to_dict()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["document.json", "document.sqlite"]
    with sqlite3.connect(index) as db:
        assert [column[1] for column in db.execute("PRAGMA table_info(addresses)")] == ["ref", "offset", "length", "digest"]
    found = _read(target, index, item.self_ref + "/text", start=1, end=4)
    assert found["value"] == "😀漢e"
    assert found["readBytes"] < 100 < target.stat().st_size // 100
    assert found["objectBytes"] < 100
    assert _read(target, index, ocr.self_ref + "/text")["value"] == ocr.text
    located_ocr = _read(target, index, ocr.self_ref)
    assert located_ocr["value"]["prov"][0]["page_no"] == 2
    assert located_ocr["value"]["parent"]["$ref"] == picture.self_ref
    assert located_ocr["readBytes"] < 1024
    page = _read(target, index, "#/pages/2")
    assert page["value"]["size"] == {"width": 600.0, "height": 800.0}
    assert page["readBytes"] < 1024
    for row in range(2):
        cell = _read(target, index, table.self_ref + f"/data/table_cells/{row}")
        assert cell["value"] == table.data.table_cells[row].model_dump(mode="json", exclude_none=True)
        assert cell["readBytes"] < 1024
    # The native schema has no cell page. Equal bboxes/text cannot select a page.
    assert "page_no" not in TableCell.model_fields
    table_prov = _read(target, index, table.self_ref + "/prov")["value"]
    assert [prov["page_no"] for prov in table_prov] == [1, 2]
    physical_precision = "coarse" if len(table_prov) != 1 else "table_page"
    assert physical_precision == "coarse"
    print(json.dumps({"sourceBytes": target.stat().st_size, "indexBytes": index.stat().st_size,
                      "textReadBytes": found["readBytes"], "textObjectBytes": found["objectBytes"],
                      "ocrItemReadBytes": located_ocr["readBytes"], "cellReadBytes": cell["readBytes"]}))


def test_sparse_native_scalar_ranges_are_bounded_across_restart(tmp_path):
    metrics = []
    for repeats in (4_000, 200_000):
        doc = DoclingDocument(name="oversized-native-scalar")
        original = ('😀漢e\u0301\\"\n\tESG' * repeats)
        item = doc.add_text(label="text", text=original)
        target = tmp_path / f"document-{repeats}.json"
        tracemalloc.start()
        index = _publish(doc, target)
        publication_peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert DoclingDocument.model_validate_json(target.read_bytes()).export_to_dict() == doc.export_to_dict()
        # Cross a segment boundary containing Unicode, escapes and combining marks.
        result = _read(target, index, item.self_ref + "/text", budget=262144, start=16370, end=16400)
        assert result["state"] == "ready"
        assert result["value"] == original[16370:16400]
        assert result["readBytes"] <= 262144
        assert result["objectBytes"] < 512
        for start, end in ((0, 1), (16383, 16385), (16384, 16384), (len(original)-12, len(original))):
            boundary = _read(target, index, item.self_ref + "/text", budget=262144, start=start, end=end)
            assert boundary["value"] == original[start:end]
            assert boundary["readBytes"] <= 262144
        with sqlite3.connect(index) as db:
            plan = db.execute("EXPLAIN QUERY PLAN SELECT codepoint_start,codepoint_end,offset,length,digest FROM scalar_segments WHERE ref=? AND codepoint_start>=? AND codepoint_start<? ORDER BY codepoint_start", (item.self_ref + "/text", 0, 512)).fetchall()
            assert any("SEARCH scalar_segments USING PRIMARY KEY" in row[3] for row in plan)
            assert not any("SCAN" in row[3] or "TEMP" in row[3] for row in plan)
        metrics.append(dict(sourceBytes=target.stat().st_size, indexBytes=index.stat().st_size,
                            publicationPeakBytes=publication_peak, **result))
    assert metrics[1]["sourceBytes"] > metrics[0]["sourceBytes"] * 40
    assert metrics[1]["readBytes"] == metrics[0]["readBytes"]
    # Model/parser memory exists before tracing. The audit measures additional
    # Python allocation, not RSS, SQLite's C allocations, or filesystem reads.
    assert metrics[1]["publicationPeakBytes"] < metrics[0]["publicationPeakBytes"] + 100_000
    assert metrics[1]["peakAllocationBytes"] < metrics[0]["peakAllocationBytes"] + 20_000
    print(json.dumps(metrics))


def test_large_table_publication_avoids_nested_native_model_dump(tmp_path, monkeypatch):
    metrics = []
    for rows in (20, 2000):
        doc = DoclingDocument(name="stream-native-table")
        table = doc.add_table(data=TableData(num_rows=rows, num_cols=2, table_cells=[
            TableCell(text="native table value " * 4,
                      start_row_offset_idx=row, end_row_offset_idx=row+1,
                      start_col_offset_idx=col, end_col_offset_idx=col+1)
            for row in range(rows) for col in range(2)]))
        target = tmp_path / f"table-{rows}.json"
        # Any recursive dump would duplicate the existing native table in memory.
        def reject_dump(*args, **kwargs):
            raise AssertionError("publication must traverse native fields directly")
        with monkeypatch.context() as patch:
            patch.setattr(BaseModel, "model_dump", reject_dump)
            tracemalloc.start()
            index = _publish(doc, target)
            publication_peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        assert DoclingDocument.model_validate_json(target.read_bytes()).export_to_dict() == doc.export_to_dict()
        found = _read(target, index, table.self_ref + f"/data/table_cells/{rows*2-1}")
        assert found["value"]["text"] == "native table value " * 4
        assert found["readBytes"] < 1024
        metrics.append(dict(rows=rows, sourceBytes=target.stat().st_size,
                            indexBytes=index.stat().st_size, publicationPeakBytes=publication_peak))
    assert metrics[1]["sourceBytes"] > metrics[0]["sourceBytes"] * 80
    assert metrics[1]["publicationPeakBytes"] < metrics[0]["publicationPeakBytes"] + 100_000
    print(json.dumps({"tablePublication": metrics}))


def test_native_table_serializer_subset_capability_probe(monkeypatch):
    """Use native serialization only; expose closure/global layout dependence."""
    doc = DoclingDocument(name="native-table-bounds")
    for _ in range(1500):
        doc.add_text(label="text", text="unrelated")
    caption = doc.add_text(label="caption", text="Native caption")
    footnote = doc.add_text(label="footnote", text="Native footnote")
    cells = [
        TableCell(text="Merged", column_header=True, col_span=2,
                  start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=2),
        TableCell(text="1", start_row_offset_idx=1, end_row_offset_idx=2,
                  start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text="short", start_row_offset_idx=1, end_row_offset_idx=2,
                  start_col_offset_idx=1, end_col_offset_idx=2),
        TableCell(text="non numeric very long", start_row_offset_idx=2, end_row_offset_idx=3,
                  start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text="last", start_row_offset_idx=2, end_row_offset_idx=3,
                  start_col_offset_idx=1, end_col_offset_idx=2),
    ]
    table = doc.add_table(data=TableData(num_rows=3, num_cols=2, table_cells=cells), caption=caption)
    table.footnotes.append(footnote.get_ref())
    rich = doc.add_text(label="text", text="rich | 😀\ncell", parent=table)
    table.data.table_cells[2] = RichTableCell(**cells[2].model_dump(), ref=rich.get_ref())
    native_iterate = DoclingDocument.iterate_items
    visited = []

    def counted_iterate(self, *args, **kwargs):
        for item, level in native_iterate(self, *args, **kwargs):
            visited.append(item.self_ref)
            yield item, level

    monkeypatch.setattr(DoclingDocument, "iterate_items", counted_iterate)
    serializer = MarkdownDocSerializer(doc=doc)
    complete = serializer.serialize(item=table).text
    assert "Native caption" in complete and "rich &#124; 😀" in complete and "cell" in complete
    assert "Merged" in complete
    assert len(visited) > 1500
    print(json.dumps({"nativeTable": complete, "nativeVisited": len(visited),
                      "tableFootnote": serializer.serialize_footnotes(item=table).text}))

    subset = DoclingDocument(name="native-copy")
    subset.add_node_items(node_items=[table], doc=doc)
    copied = subset.tables[0]
    print(json.dumps({"copyTexts": len(subset.texts), "captionRefs": [r.cref for r in copied.captions],
                      "footnoteRefs": [r.cref for r in copied.footnotes],
                      "richRef": copied.data.table_cells[2].ref.cref}))
    assert len(subset.texts) == 1
    assert copied.captions[0].cref == caption.self_ref
    assert copied.footnotes[0].cref == footnote.self_ref
    assert copied.data.table_cells[2].ref.cref == rich.self_ref
    with pytest.raises(IndexError):
        MarkdownDocSerializer(doc=subset).serialize(item=copied)

    # Native serialization of an independently bounded table: no handwritten
    # formatter. This fixture selects the header and first body row.
    row_doc = DoclingDocument(name="row")
    row_caption = row_doc.add_text(label="caption", text=caption.text)
    row_footnote = row_doc.add_text(label="footnote", text=footnote.text)
    row_table = row_doc.add_table(data=TableData(num_rows=2, num_cols=2,
        table_cells=[cell.model_copy(deep=True) for cell in cells[:3]]), caption=row_caption)
    row_table.footnotes.append(row_footnote.get_ref())
    row_rich = row_doc.add_text(label="text", text=rich.text, parent=row_table)
    row_table.data.table_cells[2] = RichTableCell(**cells[2].model_dump(), ref=row_rich.get_ref())
    visited.clear()
    row_result = MarkdownDocSerializer(doc=row_doc).serialize(item=row_table).text
    subset_visits = len(visited)
    assert subset_visits < 50
    assert "Native caption" in row_result and "rich &#124; 😀" in row_result
    assert row_table.data.grid[0][0].col_span == 2
    assert row_table.data.grid[0][1].col_span == 2
    assert "Native footnote" == MarkdownDocSerializer(doc=row_doc).serialize_footnotes(item=row_table).text
    # Native tabulate widths and numeric alignment depend on omitted rows.
    complete_first_row = next(line for line in complete.splitlines() if line.startswith("| 1"))
    partial_first_row = next(line for line in row_result.splitlines() if "rich &#124;" in line)
    assert complete_first_row != partial_first_row
    assert "Native footnote" not in complete and "Native footnote" not in row_result
    print(json.dumps({"rowTable": row_result, "copyFailure": "IndexError",
                      "fullFirstRow": complete_first_row, "subsetFirstRow": partial_first_row,
                      "boundedNativeVisits": subset_visits}))


def test_structured_native_closure_keeps_original_refs_without_whole_document(tmp_path):
    doc = DoclingDocument(name="structured-native-closure")
    doc.add_page(page_no=2, size=Size(width=600, height=800))
    for _ in range(1500):
        doc.add_text(label="text", text="unselected body " * 50)
    caption = doc.add_text(label="caption", text="Caption 😀")
    footnote = doc.add_text(label="footnote", text="Footnote 漢")
    table = doc.add_table(data=TableData(num_rows=1000, num_cols=2, table_cells=[
        TableCell(text="Header", column_header=True, col_span=2,
                  start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=2),
        TableCell(text="original rich field", row_span=2,
                  start_row_offset_idx=1, end_row_offset_idx=3,
                  start_col_offset_idx=0, end_col_offset_idx=1),
        TableCell(text="unselected oversized cell " * 10000,
                  start_row_offset_idx=4, end_row_offset_idx=5,
                  start_col_offset_idx=0, end_col_offset_idx=1),
    ]), caption=caption, prov=_provenance(2, 0, 0))
    table.footnotes.append(footnote.get_ref())
    rich = doc.add_text(label="text", text="Rich 😀\\\"\n", parent=table, prov=_provenance(2, 0, 8))
    table.data.table_cells[1] = RichTableCell(**table.data.table_cells[1].model_dump(), ref=rich.get_ref())
    picture = doc.add_picture(prov=_provenance(2, 0, 0))
    ocr = doc.add_text(label="text", text="OCR 🧪", parent=picture, prov=_provenance(2, 0, 5))
    target = tmp_path / "structured.json"
    index = _publish(doc, target)
    selected = [table.self_ref + "/data/table_cells/0", table.self_ref + "/data/table_cells/1", ocr.self_ref]
    result = _closure(target, index, selected)
    assert result["state"] == "ready"
    assert set(result["nodes"]) == {caption.self_ref, footnote.self_ref, rich.self_ref, ocr.self_ref}
    assert set(result["cells"]) == set(selected[:2])
    assert set(result["containers"]) == {table.self_ref, picture.self_ref}
    assert result["cells"][selected[0]]["col_span"] == 2
    assert result["cells"][selected[1]]["row_span"] == 2
    assert result["cells"][selected[1]]["ref"]["$ref"] == rich.self_ref
    assert result["nodes"][ocr.self_ref]["parent"]["$ref"] == picture.self_ref
    assert result["containers"][picture.self_ref]["prov"][0]["page_no"] == 2
    assert result["containers"][table.self_ref]["data"]["num_rows"] == 1000
    assert result["readBytes"] < 8192 < target.stat().st_size // 100
    assert result["objectsRead"] <= 64
    print(json.dumps(dict(sourceBytes=target.stat().st_size, structuredReadBytes=result["readBytes"], objectsRead=result["objectsRead"])))
    # Oversized unselected scalar is not read during closure. Its selected text
    # range independently uses the same scalar addresses, without a body mirror.
    scalar = table.self_ref + "/data/table_cells/2/text"
    partial = _read(target, index, scalar, budget=262144, start=16370, end=16400)
    assert partial["value"] == table.data.table_cells[2].text[16370:16400]
    assert partial["readBytes"] < 262144
    metadata = _read(target, index, scalar.removesuffix('/text') + '/start_row_offset_idx')
    assert metadata["value"] == 4 and metadata["readBytes"] == 1
    # Full oversized-cell closure is an explicit bound failure, never truncation.
    assert _closure(target, index, [scalar.removesuffix('/text')])["state"] == "byte_limit"
    assert _closure(target, index, selected, max_objects=2)["state"] == "object_limit"
    assert _closure(target, index, selected, max_bytes=32)["state"] == "byte_limit"
    assert _closure(target, index, selected, max_depth=0)["state"] == "depth_limit"
    with sqlite3.connect(index) as db:
        db.execute("DELETE FROM addresses WHERE ref=?", (footnote.self_ref,))
    assert _closure(target, index, selected)["state"] == "missing_ref"


def test_structured_native_closure_rejects_cycles(tmp_path):
    doc = DoclingDocument(name="invalid-native-cycle")
    node = doc.add_text(label="text", text="not a valid hierarchy")
    node.children.append(node.get_ref())
    target = tmp_path / "cycle.json"
    index = _publish(doc, target)
    result = _closure(target, index, [node.self_ref])
    assert result["state"] == "dependency_cycle"
    assert result["readBytes"] < 4096
