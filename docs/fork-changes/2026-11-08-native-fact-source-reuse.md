# Native fact decisions and source reuse

- Record ID: 2026-11-08-native-fact-source-reuse
- Date / author: 2026-11-08 / repository contributor
- Status: verified-in-stated-scope
- Fork base revision: 76c81d2ea57542c02778559a9de019743a68b6d0
- Upstream reference: not refreshed; no new upstream capability claim
- Related issue / commits: pending commit; OntoScience deep relationship remediation

## Reason and scope

Completed source work and fact decisions were being reconstructed on normal reads and new publication generations. Fine-grained reads, repeated endpoint restoration, and transport-sized durability checkpoints amplified cold processing. Repair the existing native owners without changing qualified-fact semantics or copying paid results.

## Native capability assessment

Existing owners inspected: EntityMerger.merge_qualified_fact_group, ExtractionRecords, ClassificationRecords, QualifiedFactIndex and PublicationRecords. Actual semantic_publication_builder callers, canonical page consumers, source classification context preparation and connected tests were checked. Decision: repair these owners in place. No alternate reducer, engine, dependency or fallback is introduced.

## Approach and actual changes

- Source projection stores bounded address-only records in ExtractionRecords; no quote/body or paid-fact copies. Exact completed identity bypasses projection work.
- ClassificationRecords indexes its accepted source reduction before context construction. Cold context batching uses geometric search rather than repeatedly serializing every prefix.
- QualifiedFactIndex stages selected native entry references, status and evidence; canonical reads restore the selected observation once and never invoke the reducer. Forward partition traversal and bounded endpoint lookups replace repeated broader queries.
- PublicationRecords preserves completed fact decisions independently of generation; mismatched input resets only derived fact state. Sealing checks selected entry provenance, kind, observation and decision coverage. Staging retains membership, endpoint and unique-assignment checks.
- Each mutation remains bounded to 256KiB. Streaming durability checkpoints occur every 128 writes (at most 32MiB serialized input) and at normal scope exit. Completion markers follow flush; cancellation or exceptions leave pending output, never a reusable partial completion.
- Removed unused mutation extra-filter argument and obsolete read-time reducer calls/duplicate support bodies. No new public export or dependency.
- Existing paid results and receipts are unchanged; no live migration or user-data mutation performed. Older incomplete derived stages are rebuilt within their existing owner on demand. New completion indexes initially miss and populate once.

## Verification and limitations

- Connected focused selection: 110 passed in 77.64s; /tmp/native-repair-final-focused.log. Covers classification budgets/completion, projection corruption, fact semantics, cancellation, restart and publication activation, plus native consumers.
- Persistent target-scale fixture: 56,700 observations / 21,620 groups. Index 38.148s, reduce/stage 69.682s, seal 26.449s, completed lookup 0.000336s; total measured stages 134.278s. 180s gate passed; test including setup/teardown 151.09s. /tmp/fact-scale-checkpoints.log.
- Earlier same-scale attempt before checkpoint correction: 222.77s; transport-sized flush checkpoints were a measured amplification. Native-load experiment was discarded because it did not address this root cause.
- Target-scale fixture uses synthetic native observations and a lightweight projection reader; it does not measure live ESG storage hydration, model quality, whole-App duration, process RSS limits or a latency distribution. No claimed live performance acceptance.
- Real model calls, real-user build, migration and final App/Case acceptance not run at this record point.

## Upstream merge assessment

- Disposition: pending; current fork-specific qualified semantics and native persistence consumers must remain aligned.
- Incoming upstream revision: not reviewed in this change.
- Overlapping owners: entity_merger and triplet_store/publication/extraction/classification/index.
- Retain only while single native ownership and exact provenance constraints hold; adapt to equivalent upstream capabilities rather than retain parallel paths.
- After merge run the connected 110-test selection and serial target-scale fixture before packaging.

## Dated follow-ups

2026-11-08: performance evidence applies only to isolated native storage/reduction; packaged and real-data outcomes must be recorded separately.


## 2026-11-08 completion ownership and demand reads follow-up

Inspected base: `aabae908` on fork `main`. Repaired the same owners and actual builder consumers; no additional engine, body store or dependency.

- Fact index updates compare native observation identity, canonical conflict partition, representation, evidence and raw status. Only changed/removed old and new partitions lose decisions. Dirty decision references survive interrupted replacement; unrelated decisions remain physically unchanged. Functional-predicate policy has its own bounded identity and dirties only predicates whose policy changed.
- `begin` preserves fact completion and dirty state independently of identity-stage completion, including an interrupted later identity attempt. Red regression failed with missing fact completion; both completed/interrupted identity variants now pass after reopen.
- Canonical pagination removed the obsolete reducer callback entirely. Native reopened-store reads consume selected observation fields and saved decisions only.
- Warm source projection uses a position-zero header seek and lazy address references. Evidence subsets use bounded indexed seeks; passage iteration uses its position index. Missing address indexes fail explicitly and require the existing maintenance CLI `--index-source-projection`. That offline operation writes reference indexes only, never paid facts or bodies; interrupted indexing leaves no completion marker. Ordinary verification remains read-only.
- Classification assembly consumes only requested evidence IDs after one cold preflight. Completed classification lookup still precedes context/prompt construction. Fact projections return plain field dictionaries rather than constructing and dumping two Pydantic DTOs before use.
- Entity-backed object identities are unchanged. Literal-only assertion identities now encode literal type and value separately from entity IDs. Historical literal-only derived decisions require explicit recomputation within the fact owner before reuse; no paid extraction or receipt changes. The current native relation builder is entity-backed, so this distinction does not rewrite its existing fact IDs.

Evidence: connected selection 124 passed and one new offline CLI test failed from a test observer retaining the Oxigraph handle; corrected isolated CLI test passed in 0.87s (`/tmp/native-offline-cli.log`). Cancellation/generation and canonical publication selection: 41 passed in 16.64s (`/tmp/fact-generation-green.log`). Typed object identity and classification records: 20 passed in 6.05s (`/tmp/fact-typed-green.log`). Another connected selection: 70 passed, one new typed fixture failed ID validation; only the fixture IDs changed before the 20-test passing run. Skipped tests are not counted as passes.

Latest persistent target-scale fixture: 56,700 observations / 21,620 groups; index 54.392s, reduce/stage 73.341s, seal 26.943s, completed lookup 0.000367s. Measured stages total 154.677s; existing 180s gate passed. Test with fixture lifecycle 174.47s. Process time: real 175.03s, user 263.34s, system 23.02s; max RSS 1,316,077,568 bytes, peak footprint 1,614,205,504 bytes (`/tmp/native-final-scale.log`). These are synthetic lightweight-reader results, not live ESG hydration, activation p95 or whole-App resource acceptance.

Remaining scope: initial grouping reads minimum native index fields, then dirty-group consumption rereads selected native observation fields; the strict single-physical-read requirement is not proved. Existing report reuse still prepares grounding context before its report lookup. Real historical projection indexes have not been migrated; live ESG has not been restarted. The current request schema has no user functional-policy/withdrawal configuration, so no nonexistent input wiring is claimed. Final packaged Case outcome must be recorded separately.
