# Explicit parsed reader index references

## Native owner and defect

Inspected canonical dirty main at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
`ParsedSourceRef` owns build source admission and
`semantic_source_artifact._source_reader_request` owns native reader binding.
Parser and bind owners already return independent artifact and reader-index
paths/digests. Build references dropped the latter and guessed a sibling index,
which fails when the host stages both files by their independent content digests.
No new storage or reader owner is needed.

## Current contract and consumers

`ParsedSourceRef` now requires absolute `readerIndexPath` and sha256
`readerIndexDigest`. The reader uses exactly that path and verifies its bytes
with the existing cancellation-aware, bounded-buffer digest owner before
creating installation identity. Missing, stale or mismatched indexes fail;
there is no sibling guess, file copy, link or alternate reader. Header admission
ValueErrors become the existing SemanticArtifactError with the cause preserved.

Shared builder fixtures, Office/document-quality/index tests, native worker
acceptance and paid-model acceptance scripts all retain these mandatory fields.
The host must pass both fields and bind readerIndexDigest into input identity;
machine-local installation paths are not semantic input identity. Native builder
consumes caller-provided inputRevision and does not independently recompute it.
Normal reads support only the current contract; rebuild/restage is the migration
boundary for old references. Original materials are unaffected.

## Evidence

`/tmp/g4-explicit-reader-reference-red.log`: 4 failures on independent index
naming before the fix, all FileNotFoundError for a nonexistent guessed sibling.
`/tmp/g4-explicit-reader-reference-green.log`: 123 passed. Coverage includes
complete worker publication with independently named artifact/index files and no
sibling, cross-window Unicode evidence hydration, post-admission mutation,
wrong supplied digest, missing required fields, relative paths and invalid digest.

Additional consumer regressions: 46 passed in
`/tmp/g4-explicit-reader-consumers-green.log`. The identity-oracle test initially
failed because its spy intercepted the old OxigraphStore facade while the
builder directly calls the canonical PublicationRecords.stage_canonical owner;
its observed dictionary stayed empty. Restoring the old reader binding in an
isolated process reproduced the failure
(`/tmp/g4-native-identity-oracle-preexisting.log`). Moving only the spy to the
current owner makes the full oracle pass
(`/tmp/g4-native-identity-oracle-green.log`): topology IDs/names, representative,
complete membership, all field and property selectors, both sources and repeat
build remain checked with their original expectations. No production semantic
change or relaxed assertion was made. No paid model, real ESG capacity,
fixed artifact or product lifecycle acceptance is claimed by these source tests.
Upstream applicability: general independently staged parser outputs benefit from
explicit reader-index provenance; upstream integration assessment remains open.
