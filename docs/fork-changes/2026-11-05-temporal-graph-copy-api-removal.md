# Remove temporal graph-copy APIs

- Date: 2026-11-05
- Fork revision inspected: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe, dirty main
- Status: implemented and focused verification; integration acceptance pending

## Native owner and reason

`GraphBuilder.create_temporal_snapshot` copied every entity and collected valid
relationships; `GraphBuilder.query_temporal` called it while ignoring its query
text. Neither is a bounded storage query. `semantica temporal snapshot` called
`TemporalGraphQuery.reconstruct_at_time`, another aggregate copier. No current
semantic worker or host build consumer was found for the builder APIs.

## Implemented removal

Delete the builder snapshot and its fake query, the unused `version_snapshots`
constructor field and `KG_VERSION_SNAPSHOTS` setting, CLI snapshot command,
orphan temporal snapshot schema, RDF snapshot metadata mapping and vocabulary
term, and tests requiring that retired command. No replacement alias, renamed
snapshot, fallback, or read-time conversion is introduced. Original knowledge
records and immutable artifacts are not modified by this source change.

Also delete `TemporalGraphQuery.reconstruct_at_time` and `query_at_time`,
CLI `temporal query`, and the convenience wrapper's `time_point` dispatch.
The wrapper retains range/pattern/evolution only; registered method failures
propagate without fallback. All executable and documentation consumers align.
`TemporalGraphRetriever` now filters only the base retriever's candidate lists
using the native owner's per-record predicates. It retains all eligible record
references, forwards retrieval limits unchanged, excludes dangling endpoints,
and never deep-copies or materializes an aggregate graph. The wrapper performs
no storage reads; its memory is proportional to already bounded base candidates,
not the full project. Base retriever scope enforcement remains its native owner.

## Verification

- Red specification first: 4 failed in 0.52 s;
  `/tmp/g4-temporal-snapshot-red.log`.
- Focused retirement, temporal CLI, CLI temporal group and KG suite:
  69 passed in 1.05 s before the additional dead-config deletion;
  `/tmp/g4-temporal-snapshot-focused.log`.
- Broad CLI exploration: 435 passed, 20 failed, 2 skipped, 2 xfailed,
  1 xpassed. Failures are MCP and optional Arrow/Parquet paths, outside this
  seam; `/tmp/g4-temporal-snapshot-green.log`. They are not reported as passes.
- Additional full-copy deletion red specification: 3 failed in 0.71 s;
  `/tmp/g4-temporal-full-copy-red.log`.
- Retirement, candidate retrieval, temporal CLI, KG, temporal reasoning and
  comprehensive semantics: 212 passed in 2.22 s;
  `/tmp/g4-temporal-full-copy-green.log`.
- Final suite including rewriter and wrapper dispatch/range/failure semantics:
  273 passed, 10 existing warnings in 2.23 s; `/tmp/g4-temporal-final.log`.
- Scoped `git diff --check`: passed.
- No model/network calls, original-material writes or immutable bundle edits.

## Upstream merge assessment

Keep these deletions when merging upstream. Do not restore temporal aggregate
copy APIs, their CLI command, schema, metadata writer, or inactive configuration.
Re-run retirement and preserved temporal CLI/KG/retrieval tests. Fixed-artifact
packaging and ESG product acceptance belong to the integration owner.
