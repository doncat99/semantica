# Bound grounding repair requests without echoing rejected output

- Record ID: 2026-10-25-grounding-retry-budget
- Date / author: 2026-10-25 / OntoScience engineering
- Status: verified locally; packaged delivery pending
- Fork base revision: 5bbf5516898048bd9341a58fd71374b3f10bdef2
- Upstream reference: not inspected for this repair
- Related evidence: OntoScience ESG job bb1312a4-4673-4a3f-a297-220a86542e5b

## Reason and scope

An initial relation request occupied 64,787 serialized UTF-8 bytes. Grounding
repair echoed the entire rejected result, exceeding the local 80,000-byte limit.
The exception discarded the budget code/size; JSON-loaded window lists also
caused the wrong source/window coordinates to be reported.

## Native capability assessment

Repair existing owners: semantic_extract/methods.py entity/relation retry loops,
semantic_artifact_builder.py::_relay_uncached and _native_parallel_map.
Callers are grounded_window.py and project/source builders. Existing grounded
extraction, scheduling and reduction-boundary tests cover these owners.
No alternate extractor, cache or transport is introduced.

## Approach and actual changes

Retry the complete original evidence and schema with bounded validation feedback,
requesting a complete replacement for the unadmitted response. Do not echo model
output or accumulate retry prompts. Only diagnostic feedback is bounded; source
text, structure, entities and schema are preserved. Completed cache keys and
stored results are unchanged. The final serialized request still passes the
existing byte gate; oversize requests fail with exact bytes and a typed code.
Window diagnostic normalization accepts JSON lists and tuples.

## Verification and limitations

Red regression: large rejected output grew a 62,208-byte prompt to 102,660 bytes;
JSON-list coordinates and typed budget diagnostics also failed before repair.
Extended native regression: 50 passed, 5 failed; the unchanged fork base has the
same 5 failures (47 passed). Existing failures concern schema-retry expectations,
an incomplete cache fixture, and three model-configuration cache expectations.
OntoScience worker boundary: 57 passed; repository guard and typecheck passed.
Library change-verification passed (run 3f75753f-4703-4d00-bdb3-a45f4bda1a70).
Offline replay of the actual failed relation window restored 258 entities and
measured 64,787 initial / 65,072 repair request bytes with synthetic rejected
output; no model requests or production cache writes occurred.
No live model or full production build success claimed.
The request byte limit is unchanged; indivisible oversize inputs remain explicit
failures, never truncated. A repair attempt still costs one model request.

## Upstream merge assessment

Disposition: keep pending review of incoming upstream. Native retry and relay
owners may overlap. Retain only while upstream lacks equivalent bounded repair;
rerun grounding, cache recovery and transport-boundary checks after merges.

## Capacity and restore follow-up (2026-10-25)

Supersedes the historical fixed byte gate and five-test gap above. Removed both
80,000-request-byte and 48,000-context-byte constants. Native generation uses the
admitted model context minus output reservation, with full-payload/schema sizing
and an explicitly conservative UTF-8-byte upper bound for byte-based tokenizers.
There is no invented provider transport ceiling or default capacity. Embedding
does not inherit generation reservation. Classification/report packers derive
their budget from this policy. Extraction refines only unsatisfied context
batches, retains complete evidence groups and completed batch business keys,
and fails explicitly for indivisible oversize input without truncation.

Saved-progress extraction hashes a source once, emits immutable progress outside
the scheduling lock, coalesces ordinary progress and retains exact final counts,
warning receipts, retry/failure reporting and reporter errors. No checkpoint
identity or persisted data migration is introduced.

Focused capacity, reduction, grounding, long-context, artifact, scheduling and
grounded-extraction selection: 117 passed. Stale fixtures were aligned with the
already existing candidate-rejection and model-independent reuse policies.
Cache-only comparison on 16 real windows: both variants restored 16/16 with no
model calls or production writes; progress 47 -> 6 events, 25,076 -> 3,159 bytes;
0.274 -> 0.213 seconds. Embedding was stubbed, so this is not an end-to-end claim.
OntoScience focused daemon/web tests and root guard/typecheck passed; Library
Auto Test run 540d608f-8eba-4fa3-916d-65cb32a025a4 passed. Packaged/full production
verification is tracked separately in the consuming project's verification doc.
