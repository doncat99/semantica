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
