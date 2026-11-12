# Canonical fact member query

## Reason and native owner

At revision `eb513e036c3a1fc34db3cf9efec3d22867bca724`,
`PublicationRecords.fact_members` already provided bounded, generation-fenced
support observation pages, but the semantic query worker did not expose them.
KnowledgeHub needs these native references to inspect evidence and qualifiers.

## Change

The query worker delegates `fact_members` to that existing owner, validates the
project and resource budgets, checks cancellation around the read, and rechecks
the store lease. No additional fact store or semantic decision is introduced.

## Verification and limitations

`tests/test_semantic_query_worker.py::test_fact_members_rpc_preserves_budget_and_fences_publication`
passed with the local packaged Python and test dependencies. The full
`tests/test_semantic_query_worker.py` and
`tests/triplet_store/test_canonical_fact_publication.py` run passed 24 tests.
The new worker check uses a mock store; packaged artifact integration and
cancellation during a storage query remain to be verified. The consumer and
release pin have not yet been updated.

## Upstream merge assessment

Pending: compare the upstream query protocol and native fact ownership when
merging; reuse any equivalent upstream capability instead of retaining both.
