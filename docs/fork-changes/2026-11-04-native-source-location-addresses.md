# Native source location addresses and bounded context hydration

- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Inspected revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing dirty remediation work
- Upstream assessment: pending; no incoming upstream revision inspected

## Native owner and actual changes

The current `parse.document_reader` location projector and
`semantic_document_reader.write_reader_artifact` remain the owners. The writer
streams the existing exact location projection into its existing SQLite index.
Descriptors contain source/native scalar addresses for quotes, section headings
and formula/code original text, rather than copied content. Native `orig` scalar
segments are indexed alongside text segments in the existing source map.

Location ordinal, interval, page, table and reference indexes support bounded
pages, shortest containing-location selection with stable producer-order ties,
and the original source-context closure: overlapping records, same pages,
tables spanning pages, and explicit caption/footnote/reference dependencies.
An Rtree interval index avoids scanning every preceding location. Native scalar
range paging preserves original extents and separator semantics without reading
the canonical content.

`read_source_locations` supports address-only pages and selected hydration;
`locate_source_range` selects one original locator; `read_source_native_ranges`
pages the existing source map. `read_source_window_ranges` pages the current
window schedule without hydrating any body, preserving the original exact
window cuts in all four supported formats. They delegate to current reader binding,
cancellation/deadline and installation checks. Pages are limited to 128 records,
context windows and individual hydrated spans to 12,288 characters, descriptors
to 16 KiB, physical body reads to at most 256 KiB and the requested byte budget.
Location SQL has a bounded work budget. Indivisible oversized objects reject
with a typed budget error; no content is silently truncated. Interval addresses
outside the signed 32-bit index range reject explicitly.
Missing address tables and malformed/incomplete admission headers produce
`DocumentReaderIndexError` requiring explicit rebuild. Duplicate location refs
preserve the old last-producer dependency lookup and ref-selected table closure.

## Verification

The red specification initially failed collection because the new native API
did not exist (`ImportError: read_source_locations`). The focused test now
passes: `.venv/bin/python -m pytest -q tests/test_native_source_locations.py`:
9 passed, without model or network calls.

The tests compare restored output against the original full location and
context projection, including Unicode headings, captions, notes, multipage
tables, rich cells, formula original text, multiprovenance records and stable
locator selection. They verify body-free index descriptors, all four current
format range oracles, cancellation, binding rejection, explicit oversized
hydration rejection, and a 2,000-node sample with zero-byte deep metadata pages
and a selected hydration below 1,000 bytes.

After adding window scheduling, explicit missing-index rejection and exact
duplicate-reference closure, combined reader/header/window/structure/index and
semantic grounding/native-extraction suites: 87 passed in 9.67 seconds.
Touched production/test files pass `git diff --check`.

During the coordinated consumer cutover, the original builder context oracle
became an indexed consumer; the test now freezes the original list-based oracle
locally rather than testing an indexed consumer against itself. After adding
explicit malformed SQLite-index rejection, reader/header/window/structure/index
and grounding suites: 64 passed in 7.54 seconds. The expanded concurrent run
identified four old tuple-based extraction fixtures requiring consumer-fixture
migration; its native-extraction result is not a current green gate.

Consumer-fixture migration also updates the Office and document-quality suites
to admitted native range views and the current quality owner. Structural fact
tests now exercise serialized/admitted indexed locations: a real unrelated
page-99 table with repeated short cell text, explicit formula references,
multipage same-table closure, and changed structure affecting extraction cache
identity. No production compatibility aliases were restored. These three
consumer suites passed together (33 tests in 2.73 seconds).

The lazy source consumer now selects native scalar addresses by a bounded
`start`/`end` window in `read_source_native_ranges`, retaining original scalar
extents for consumer clipping. Ordinary location reads use overlap-only Rtree
selection, while `cells_only` filters descriptors in SQL before any body
hydration. Context closure remains an explicit separate selection mode.
Four-format frozen window/scalar oracles, indexed overlap/cell filtering,
header admission and migrated native search/scalar grounding passed together:
38 tests in 3.54 seconds. The context/dependency and warning-page consumer
fixtures now use installed Docling schema objects and admitted indexed locations;
the warning fixture reports the current bounded `rejected_count` receipt field.
The unrelated typed-output/extraction call-boundary fixtures are owned by the
coordinated source-consumer migration, not this reader change.

## Limits and delivery boundary

This does not claim G4 completion or product/release acceptance. The writer
still runs while the parsed native document exists; this change does not make
parsing globally incremental. Unsupported installed indexes require explicit
rebuild, without a compatibility reader. Source consumers, packaged artifacts,
real ESG acceptance, repository-wide checks, formal data and release pins are
separate work. No dependency or alternative storage owner was added.

Upstream disposition remains pending. Reuse an equivalent upstream owner when
available and rerun exact location/context oracles after merge.
