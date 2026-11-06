# Accepted result density within the native byte budget

- Date: 2026-11-06
- Status: implemented; focused regression verified; artifact qualification pending
- Inspected fork revision: b147a53a293e940bd1fdcb46b1bead53a046e120
- Upstream assessment: pending; no incoming upstream revision inspected

## Reason and native owner

Real ESG extraction returned HTTP 200 but cache.py rejected the result at its
independent 8,192-node limit. SqliteCacheBackend.accept and ExtractionCache's
accepted-result methods all delegate to _check_accepted_value. This remains the
only validation and persistence owner; no alternate store or retry is added.

## Change and callers

Remove the independent node count and embedding-specific exception. Every
visited JSON value already consumes the existing 1 MiB byte allowance, bounding
traversal work as well as encoded size. Preserve the depth-32 limit, unsupported
type checks, SQLite progress/lock deadlines, cancellation and accepted receipts.
No schema, recipe, model, exports, configuration or persisted codec changes.
Update the former node-limit fixture to actually exceed the byte allowance.

## Evidence and limitations

The new 512-entity regression failed before the fix at entity 409 despite being
within the byte budget. After repair, all 31 tests across accepted handoff, paid
native rebind and projection handoff pass. Dense results round-trip exactly;
oversized and overdeep inputs fail without leaving accepted rows. The existing
preflight test still verifies rejection before a full copy with peak allocation
below 256 KiB. No network/model calls were made by these checks.

The failed real response was rejected before persistence; preservation of that
individual result is not established. Previously persisted results remain valid.
Installed-artifact and complete real ESG acceptance remain outstanding. On an
upstream merge inspect the same cache owner and retain byte/depth validation and
receipt semantics, adopting an equivalent upstream implementation if available.
