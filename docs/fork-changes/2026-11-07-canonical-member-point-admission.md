# Canonical member admission by native reverse index

- Record ID: 2026-11-07-canonical-member-point-admission
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 802d67249
- Upstream reference: not inspected
- Related issue / PR / commits / records: G4 remediation; PR pending

## Reason and scope

The existing per-member canonical uniqueness ASK joins all current canonical
records to a fixed member. An isolated in-memory native microbenchmark showed
128 missing-member queries increasing from 32.54 ms at 512 canonical records to
393.49 ms at 8192; explicit reverse lookups stayed below 0.070 ms per 128 queries.
This establishes the query's amplification, not its share of real build time.
Only this admission lookup is in scope; selector checks and counts stay unchanged.

## Native capability assessment

- Existing owner: `PublicationRecords.stage_canonical` in
  `semantica/triplet_store/publication_records.py`.
- Caller: `semantic_publication_builder.py::entity_resolution.stage`, through
  the existing publication owner; tests in `tests/triplet_store/test_publication_records.py`.
- Decision: repair the existing native owner using its store's indexed
  `quads_for_pattern`; no second implementation or cache.

## Approach and actual changes

- Replaced the per-member ASK with reverse member references followed by
  exact current-head canonical membership checks.
- Contract/data impact: none; duplicate current canonical ownership still fails,
  unrelated noncanonical references do not block admission. No migration.
- Deletion target: the old project-join ASK, replaced in place.
- No model/network calls, dependencies, recipe or schema changes.

## Verification and limitations

- Red specification added for duplicate rejection, noncanonical references,
  forbidden project join and bounded returned rows at 64/2048 unrelated records.
- Red: `nice -n 19 .venv/bin/python -B -m pytest -q
  tests/triplet_store/test_publication_records.py -k
  canonical_member_admission_uses_reverse_point_reads` failed both parameters
  at the forbidden original ASK (2 failed, 33 deselected, 0.73 s).
- Green: the same two parameters plus existing canonical uniqueness/restart,
  130-record topic pagination, pending/ready/restart/withdraw/digest and
  more-than-128-source publication tests passed (6 passed, 29 deselected, 5.21 s).
  Test command uses `-k 'canonical_member_admission_uses_reverse_point_reads or
  community_references_restart_and_canonical_membership_uniqueness or
  topic_catalog_and_memberships_page_past_128_without_loss or
  pending_ready_restart_withdraw_and_original_digest_unchanged or
  more_than_128_sources_and_records_publish_in_bounded_batches'`.
- Returned reverse-reference rows were 2 for admission and at most 3 further
  rows for duplicate rejection at both unrelated sizes; every referring node
  was checked by an exact head/canonical/subject lookup. This measures native
  API reads, not physical I/O or complete process capacity.
- No network/model calls; stores are newly created pytest temporary fixtures.
  Frozen bundle/pin, existing databases and real build untouched.
- This patch does not qualify a new artifact or prove complete build capacity.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Potential overlap: publication staging membership validation.
- Retain or adapt only if the native owner still has the same query issue;
  rerun focused publication regressions after merge.

## Dated follow-ups

2026-11-07: source implementation and focused red/green verified as above;
artifact integration and product acceptance remain with the parent delivery.
