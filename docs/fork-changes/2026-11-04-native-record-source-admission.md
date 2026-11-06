# Native record source admission and RDF literal fidelity

## Reason and inspected owner

Inspected fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` and the
in-progress native publication changes. The existing Oxigraph publication owner
in `semantica/triplet_store/publication_records.py` admits project/generation
membership. Exact-ID consumers also need to constrain reads to their selected
sources; project membership alone is insufficient. Its RDF output omitted literal
language despite retaining datatype.

## Implementation

Extend the same owner's exact-ID read with an optional 1–128 unique source-ID
grant. Use deterministic native source IRIs and a bounded VALUES join against
current publication ownership; never enumerate the source catalog. Extend the
existing query request/worker delegation, not a second authorization store.
Source grants apply only to exact IDs. Return native literal language alongside
datatype without normalizing or translating the value.

Affected consumers are `semantic_query_schema.py`, `semantic_query.py`, and the
existing native record worker protocol. Host admission and decoding remain a
separate integration obligation. No source text or knowledge body is copied.

## Verification (2026-11-04)

` .venv/bin/python -m pytest -q tests/triplet_store/test_publication_records.py tests/test_native_record_worker.py `:
**25 passed / 4.14s**. Covers same-project wrong-source rejection, valid source
grants, invalid empty/duplicate grants, native numeric datatype and language
round-trip. No model/network calls or production data changes.

## Limitations and upstream merge assessment

This proves the exact-ID field/authorization seam, not complete G4/G5 query or
release acceptance. Source paging's physical storage work remains to be measured;
LIMIT is not evidence of bounded traversal. Keep the existing native owner when
merging upstream and adapt/drop this extension if upstream supplies equivalent
source-scoped typed point reads. No alternate implementation or fallback added.
