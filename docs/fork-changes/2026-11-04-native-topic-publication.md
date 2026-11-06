# Grounded topic publication

- Date: 2026-11-04
- Status: implemented; source verified, installed qualification pending
- Inspected revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus existing dirty reconstruction changes.

## Native owner and reason

`semantic_artifact_builder._grounded_topics` already derives topics from cited
Overview sections. `semantic_organization` calls it, but `artifact_writing` drops
the result. `PublicationRecords` already owns current reference membership and
bounded native scenes. Extend these owners; do not add a semantic organizer.
Callers include OxigraphStore, the worker's native_scene delegation and host/UA
scene consumers (the latter are not integrated yet).

## Current contract and deletion boundary

Stage topic title, report/input digest and canonical entity/native evidence refs
in the existing publication graph. Keep source facts, quotes and bodies in their
native extraction owner. Translate temporary build EvidenceSpan offsets through
`_native_grounding_ranges`, `_window_native_ranges` and the existing pending
`read_grounded_reference_page`; unknown or unmapped evidence fails publication.
Both batches and output pages are bounded by 128 rows/256 KiB; chunked staging
records expected member/evidence counts and activation verifies completeness.
Read topics by keyset and selected canonical members by topicId, preserving the
generation fence. No model/network call is added. No synthetic evidence IDs,
ua_facts copy or host topic computation is allowed. Superseded UA inputs must be
deleted in the coordinated UA/host delivery; no fallback will be supplied here.

## Verification and limitations

Planned: real persistent owner red specification; canonical/evidence admission,
incomplete activation, restart, stale generation, byte budgets and real build
coverage. Immutable worker qualification and coordinated host/UA integration are
pending. This record does not claim product or release completion.

## Upstream merge assessment

This extends the existing publication codec, not the native semantic algorithm.
Review upstream publication/topic APIs on upgrade and delegate to an equivalent
bounded native owner if introduced, removing superseded code in the same change.

## 2026-11-04 implementation and boundary verification

The planned publication codec and producer integration are implemented in
`semantic_artifact_builder`, `PublicationRecords` and `OxigraphStore`. Native
scene reads expose grounded topics and topic-selected canonical members. The
existing worker delegates these selections without another semantic owner.

The collision regression was red (1 failed, 1 passed): a topic could reuse a
canonical identity and share membership predicates. Staging now rejects mixed
canonical/community/topic identities, conflicting metadata within one batch,
and malformed references before applying the atomic batch. Tests also verify
130 topics and 130 members/evidence references across 128+2 pages, restart,
incomplete activation, stale generation, byte failure and missing citation proof.

Seven native publication/producer/pipeline/worker/document-reader suites pass:
80 passed in 17.23s (`/tmp/semantica-g4-topic-complete.log`). The three producer
failure cases initially had invalid test IDs; fixing their schema-conforming
representation ID yields typed grounding failures, not a production relaxation.
Installed loopback acceptance now checks theme/member scenes and a fresh-process
reopen. It is not yet run. The host's existing dev-dependency builder is creating
a frozen native artifact; source-only results do not qualify it or close G4.
UA/host integration and exact published pins remain pending.
