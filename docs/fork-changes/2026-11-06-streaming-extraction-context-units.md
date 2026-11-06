# Stream native evidence addresses and complete extraction context units

- Date: 2026-11-06
- Status: implemented; focused and all-source no-model verification complete; installed real ESG build acceptance remains separate
- Inspected fork revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus current G4 changes; installed c8cd9c16e9f91564b7517709d3f47e6c4921a3be7bbca6849751f35ceae860bf baseline

## Reason and native assessment

Real ESG source 6 failed before a model request because `_GroundingContext.addresses`
retained the entire selected address closure and applied a cumulative 262144-byte
transport limit (262568 bytes observed). The native immutable reader already owns
source locations, scalar ranges, table metadata and dependency closure. Repair its
consumption; do not enlarge a limit, drop evidence, change immutable source content,
or regenerate embeddings.

Inspected owners and consumers: `semantic_document_reader.read_source_locations`,
`semantic_source_artifact._NativeSourceLocations`, builder `_GroundingContext`,
`_extraction_context_batches`, `_extract_window`, and native grounding regressions.

## Implementation and deletion boundary

`_GroundingContext.addresses` streams native pages. `_extraction_context_batches`
retains only the active admitted request and complete current structural unit.
Successful contexts which fit remain byte/order identical. Oversized contexts use
the reader query submodule `semantic_document_context.iter_source_context_units`.
It builds the closure once in a short-lived native SQLite session and stores only
ordinal/ref/table/row/header/dependency metadata in file-backed TEMP tables; it
never stores quotes, full descriptors or extracted business objects. Indexed row
bounds, shared-header and note lookups stream complete row units in source order,
including row spans and referenced captions/footnotes. Individual oversized units
fail explicitly without truncation or upstream calls.

TEMP page cache is 512 KiB, disk allocation is capped at 8192 pages (32 MiB at
4096-byte pages); each SQL operation has a 30-second deadline/200000 VM-step cap,
and the session has a 2000000-step cap. Consumer/model waits do not consume the
query deadline. Cancellation, close and failures dispose of the temporary session.
Auditing disables the progress handler before cleanup sampling.

Removed the proposed per-row closure-rebuilding/OFFSET API during implementation.
Only the current session implementation ships. The existing parser-producing
`semantic_document_reader.py` and `semantic_source_artifact.py` are byte-identical
to the c8cd baseline, preserving processing identity and all immutable artifact
bytes. No parser, reader-index format, model, embedding input or dependency change.

## Evidence

- Red: native 540-cell context reproduces the installed cumulative metadata-cap
  failure. Host receipt `.tmp/g4-context-units-red.log`.
- Green: 28 targeted reader/context-budget checks pass. Whole rows, headers,
  captions, notes, spans, original batch order, bounded oversized failure,
  one-hour simulated consumer pause and cancellation covered. Host receipt
  `.tmp/g4-context-session-green.log`.
- Query plans use `(table_id,shared)` equality, row RTree, ref and ordinal indexes.
  180/360 rows (540/1080 cells) consume 219000/451000 total VM steps and
  188416/315392 TEMP bytes, respectively. Shared-header truthiness initially
  prevented the second index key; explicit `shared=1` corrected that scan.
- Actual source-6 failure window 179061–180180: 60 units, 993 returned addresses
  including necessary repeated shared evidence, one closure, 129000 VM steps,
  122880 TEMP bytes, approximately 20 ms. Host receipt
  `.tmp/g4-source6-context-session.json`.
- All 38 admitted sources and all 8349 native windows pass no-model entity
  prompt/schema/context-budget validation in 487.69 seconds. Source 6 passes
  191/191 windows; maximum full prompt is 420691 bytes within the admitted
  467232-byte input budget. No network/model calls. Host receipts
  `.tmp/g4-all-context-preflight.json`, `.jsonl`, `.log`.
- Separate paid preservation probe verifies all 875 prior entity inputs,
  707 relation inputs and 830 embedding inputs exactly, including ordered
  contexts, ranges and operation identities. The integration owner retains
  the exact certificate and adoption evidence.
- Frozen function/module identities: host `.tmp/g4-context-session-ast.json`.

## Limitations and upstream assessment

The all-window preflight returns no entities and therefore does not validate
entity-dependent relation prompts; real installed build remains necessary.
All real windows fit the current admitted model budget, so the structural
partition path is additionally covered by the explicit real-window native-unit
probe and smaller-budget regressions. Source-6 full preflight took 396.45 seconds;
repeated hydration is a separate performance concern, not hidden as completion.
This record does not close G4 or authorize publication.

Upstream assessment pending: retain complete source evidence and a single native
query owner when evaluating future upstream functionality. No upstream revision
was merged or reviewed in this change.
