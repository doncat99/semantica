# Native source consumer fixture cutover

Baseline: canonical Semantica checkout at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
with existing remediation edits. Production source admission now returns
`NativeParsedSource`, not an eager text/document tuple. Source projection requires
an explicitly admitted native source and absolute extraction offsets.

Algorithm fixtures in identity, fact evidence, classification, long-context and
native extraction tests now serialize native parsed-source v3 artifacts and run
real digest/profile/source/index admission through `tests.artifact_helpers`.
Compact tuple preparation exists only in this test helper. Missing occurrence
offsets in model fixtures are resolved only in the helper, never in production.
Existing production `_build_source` observers are retained. Original materials
with real paths keep their bytes; generated fixture materials use real digests.
Reader artifacts remain alive for the fixture's native text lifetime.

Scheduling and recovery tests substitute address ranges on actual native text;
they hydrate the real indexed reader when their active handler needs a body.
No production compatibility branch, new storage owner, model request or dependency
was introduced. Native-source production changes are recorded separately.

Initial expanded consumer/recovery run: 210 passed, 3 failed due remaining
removed-projector mocks in recovery fixtures. Those mocks were then removed and
the recovery fixtures switched to actual native admission. Recovery, checkpoint
deletion, accepted paid-result/embedding handoff, native pipeline and publication
regressions then passed: **73 passed**. The real native build → host → installed-UA
Learn → database/worker restart test also passed (1 test, 3.98 seconds test time).
Expanded collection found 4,006 tests and eight unrelated missing
`semantica_mcp` module errors; this is not a full-repository pass.

After lazy native window/scalar-address cutover, the publication lifetime probe
uses a bounded scalar-range selection rather than the deleted eager iterable.
Expanded identity, fact, source, artifact, extraction, long-context, scheduling,
body-reference and grounding selection: **196 passed** (39.00 seconds).
Recovery/checkpoint deletion/paid handoff/native publication rerun: **73 passed**
(32.90 seconds). Real native-to-host-to-installed-UA Learn and database/worker
restart rerun: **1 passed**, 4.01 seconds including startup. These groups overlap.

The reading-report directory-invariance regression no longer requests the deleted
checkpoint contract or hashes a removed semantic-graph carrier. It now compares
the complete canonical selection records passed to the real native publication
owner across two build directories, checks the same native store path, and
asserts no snapshot/semantic-graph output. Publication generations intentionally
identify distinct attempts, so they are not required to match. The regression
continues to require content identity to remain independent of a build directory.

Limits: these are supporting regression tests, not fixed-artifact qualification,
formal-profile acceptance or proof of bounded global identity/community residency.
Upstream assessment: fixture changes track this fork's native publication contract.

## 2026-11-04 current context and typed transport follow-up

Request-content and local-warning fixtures now use actual native Docling source
admission for context/page selection. The extraction-context test no longer mocks
the filter or batch selector: it proves same-page context is included and another
page is excluded by the actual reader. Typed-output relay fixtures provide current
capacity, business_context and stop fields; the first request must include the
complete exact schema in its JSON-object prompt, matching the current transport.

Deleted the obsolete expectation that relation schema failure returns entities
as successful partial output. The replacement asserts preserved ModelOutputError
cause/code, failed_extraction action and rejection count. Production is unchanged.
Recovery remains covered by test_native_extraction_handoff.py: accepted native
entities/relations survive process restart without a second paid call, including
after-accept/after-adopt boundaries. test_native_build_pipeline.py verifies a failed
stage preserves its cause, leaves publication pending and never runs artifact
publication. Current response-level failure contract also runs in
test_native_typed_output_owner.py.

Both fixture files plus those three supporting suites: **39 passed in 15.84s**;
focused diff whitespace check passed. No model/network calls, new compatibility,
baseline change or broader acceptance claim.
