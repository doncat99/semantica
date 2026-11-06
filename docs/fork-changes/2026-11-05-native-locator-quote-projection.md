# Native locator projection: avoid unused paragraph body hydration

## Native assessment and scope

Inspected fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
with existing uncommitted G4 work. Native owner is
`semantic_document_reader.py::locate_source_range` / `_read_source_locations`;
its production caller is `semantic_source_artifact.py::_NativeSourceLocations.locate`,
consumed only by `semantic_artifact_builder.py::_located_document_fields`.
Repository-wide Python caller search also found the existing shortest-location
oracle test. The consumer uses coordinates, section headings and structural
metadata; it never consumes the containing location's quote.

The existing reader can locate the correct record but previously hydrated its
entire quote before returning the needed metadata. A 20-character lookup inside
a 15,950-character Docling paragraph consequently failed the 12,288-character
scalar budget. Raising the budget would retain the unnecessary read.

The same native reader now supports excluding the quote from a hydrated locate
result. Only the metadata consumer requests that projection; section paths and
structural original text retain their existing hydration and budgets. The
default complete-location API and context reads preserve exact quote behavior.
No alternate reader, body copy, truncation, fallback, schema or index was added.
There is no persisted-data migration/reset requirement.

## Regression evidence

Added two tests to `tests/test_native_source_locations.py`: the actual builder
metadata consumer locates the first 20 characters of a 15,950-character native
paragraph with zero body `readBytes` and no quote/address returned; the existing
rich Docling fixture independently checks shortest-location coordinates,
section paths and structural metadata, including formula original text.

Before the fix, the initial red run was **1 failed, 1 passed**: the oversized
paragraph failed at `hydrate_address` with `native location scalar extent
exceeds budget`. The first red fixture used a slightly larger paragraph; the
checked-in regression fixes its length explicitly at 15,950 characters.

Focused verification:

```text
.venv/bin/python -m pytest -q tests/test_native_source_locations.py tests/test_native_document_reader.py tests/test_native_source_windows.py tests/test_native_source_admission_budget.py tests/test_structural_fact_evidence.py tests/test_native_producer_publication.py
56 passed in 71.88s
```

These cover exact existing location/context oracles, complete-quote rejection,
native reader/window bounds, lazy admission, structural evidence and complete
offline native publication. Source diff whitespace checks also passed.

## Limits and upstream disposition

This closes unused quote hydration for location metadata only. It does not
bound complete context-closure accumulation, global build memory, required
structural metadata, or complete-quote clients. Existing oversized complete
location reads must still fail explicitly rather than truncate.
No paid model, real ESG build, immutable release or consumer pin was run.
Upstream disposition remains pending; preserve projection and locator-fidelity
regressions during any reader merge.
