# Bounded projection reads over fragmented native sources

- Record ID: 2026-11-05-fragmented-source-projection
- Date / author: 2026-11-05 / Codex
- Status: implemented-unverified at artifact boundary
- Fork base revision: see current checkout `git rev-parse HEAD`; inspected 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected
- Related issue / PR / commits / records: OntoScience G4 unique closure checklist

## Reason and scope

Real ESG projection requested 12,288 characters containing 331 source mappings.
The native reader correctly rejected the request at its 258 mapping budget.
Paid extraction and embedding had already succeeded. Fix source-only hydration,
preserving every already-valid producer window, extraction semantics and reader budgets. Oversized producer addresses are partitioned before hydration.

## Native capability assessment

- Owner: semantic_document_reader `_read_source_windows`, indexed native maps and producer windows.
- Consumers: builder source projection, passage traversal, evidence-reference quote and entity hydration.
- Tests inspected: native source windows, traversal, evidence reference, body budgets.
- Repair builder consumption using existing native reader APIs; reader/parser source bytes stay identical to the prior installed artifact. No second parser or projection.

## Approach and actual changes

Builder projection and producer consumption share a splitter constrained by characters, 128 native ranges and 258 mapping rows (including empty-section separators). Producer address metadata is read from the same identity-validated native index in bounded pages; valid producer windows stay unchanged. Both consumers delegate each body segment to
the existing reader. The total requested extent stays at 12,288 characters;
physical bytes share one cumulative budget, identity and cancellation checks.
No index-format migration, new dependency or model call. Existing range-with-native-
mappings API retains its strict limits. No truncation or fallback.

Stored paid operation identity currently includes full native processing bytes.
Reusing unchanged paid results across this artifact change requires an explicit
verified offline owner adoption; no normal-read compatibility dispatch is allowed.

## Verification and limitations

Fragmented Docling source red specification reproduced mapping overflow before
repair. Expanded source traversal, reader, extraction, identity/build handoff and evidence regressions: 92 passed in 34.68 seconds. Three empty-section specifications reproduced failure before repair. Cumulative byte and full-call deadline checks pass. Evidence: host `.tmp/g4-projection-expanded-green.log`. Evidence in host
`.tmp/g4-projection-{red,green}.log`. Real failed source now traverses77,321 characters and829 passages without model calls; all 365 extraction-window text values are checked against the unchanged range API. All38 ESG sources passed strict window hydration without models:8,349 windows in17.47s; firstsource365 windows unchanged. Producer expanded regression74passed19.43s; evidence host `.tmp/g4-all-window-check.json` and `.tmp/g4-producer-expanded-green.log`. Final fixed-artifact verification pending.

## Upstream merge assessment

- Disposition: keep pending upstream review; no upstream revision reviewed.
- Conflicts: canonical reader range/window interfaces and source consumers.
- Retain exact text, mappings, identity, cancellation and budget regression checks.
