# Native typed-output ownership

- Record ID: 2026-10-29-native-typed-output-owner
- Date / author: 2026-10-29 / repository contributor
- Status: implemented; focused verification completed, product release not verified
- Fork base revision: ed2af3a561122827a9315343dcd8496175628df2
- Upstream reference: not refreshed; this is a current fork ownership repair.
- Related record: OntoScience `semantica-native-consolidation-20261027.md`, TODO 1.

## Reason and native capability assessment

`semantic_extract/providers.py::BaseProvider.generate_typed` already owns typed
validation and retries, but `semantic_artifact_builder.py::_ProjectModelProvider`
overrides it with an independent loop. Both expose response-rejection hooks.
`semantic_extract/grounded_window.py::extract_grounded_window` additionally turns
an exhausted ModelOutputError into successful empty/partial output. Inspected
callers include strict extractors in `semantic_extract/methods.py`, native
CommunitySummarizer, classification and report generation in the builder.
Existing provider scheduling, diagnostics, grounding and checkpoint tests apply.

## Approach and deletion targets

Repair the native typed owner, delete the builder override, and fail closed on
exhausted whole-response validation in grounded windows. The relay adapter keeps
transport, model identity, receipts and checkpoint rejection. Preserve existing
candidate-level grounding policy; that is distinct from failed whole responses.
No checkpoint identity migration, data deletion, paid model call or new dependency.
Unrelated reading-report and contextual-identity worktree changes are out of scope.

## Verification and limitations

The original seven regression specifications failed before the source repair.
The expanded native-owner specification now has ten passing cases, including
failed-relations resume: accepted entities are reused, failed relations are not
cached as success, and a completed retry performs no further model requests.
All responses are local fixtures; no provider budget was consumed.

Production delta for this item is 52 additions / 243 deletions (net -191):
the builder override loses 41 lines; providers +44/-196, methods +6/-4,
grounded_window +2/-2. No file move is counted as consolidation.

The complete-dependency focused run finished with 354 passed / 1 failed. The
failure was a concurrent version-policy test edited while the process was
running (expected v4, the already-loaded builder still emitted v3). A fresh
process rerun of that test plus all owner cases passed (11 passed). Separate
minimal-environment owner tests passed (10). Broader checkpoint specifications
have nine existing failures, reproduced by loading HEAD sources in memory;
these concern legacy migration/evidence retention, outside this repair.
An additional provider/cache/performance selection was not green (137 passed,
6 failed): three verbose-mode specs also fail with HEAD; remaining failures
involve mocked OpenAI/spaCy import state. They are not claimed as passes.

Product Case
`capability-library-prepare` / primary `journey-library`: keep; supporting Python
specifications change only, no pass-criteria, hard-gate or baseline changes.
App acceptance, change-verification, immutable artifact publication and packaged
ESG acceptance are not yet verified. No acceptance baseline was promoted.

## Upstream merge assessment

Compared with local upstream/main 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
(not freshly fetched). BaseProvider already owns typed generation upstream;
the product relay and grounded-window boundary are fork additions. This repair
extends that native owner instead of preserving a relay override. Retain one
native typed-output owner and transport
adapter; adapt against changes to BaseProvider and strict extractors, never restore
the deleted builder loop. Re-run typed, grounding, relay and checkpoint regressions.
