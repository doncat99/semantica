# Native record query plan and deadline ownership

## Reason and inspected owner

At `4ece1d8ca54afb4e1b3bf9fd6d00d80df5662835`,
`semantica/vector_store/sqlite_vec_store.py::SQLiteVecStore.search_native_records`
already owns source-scoped native vector retrieval. KnowledgeHub Summary calls
it through the existing query worker. The association join could scan the
generation's entire association index once per vector, and an internal
three-second timer rejected legitimate requests before the caller deadline.

## Implementation

Repair the existing owner in place: drive the join from the candidate-vector
batch and use the existing association primary key `(project, vector_id)`.
No schema change, new index, migration or alternate retriever is added. Remove
only this method's independent three-second deadline; retain cancellation,
source/generation filtering, result limits, byte/scratch bounds and cleanup.
The host's existing query-session deadline terminates/reaps overdue workers.
Other native range/evidence methods are outside this change.

Affected files are the native owner and
`tests/vector_store/test_native_range_publication.py`. Host compiler code also
removes a synthetic readiness search; actual planned queries use the same native
owner. Development packaging must snapshot the fork before App verification;
a source-checkout test does not prove the installed App contains the repair.

## Regression evidence and limits

Two tests reproduced the defects before repair: no caller cancellation despite
an advanced internal clock, and excessive SQLite VM work on a 300-vector,
4,800-association query. After repair, the native publication, native query and
native vector owner audit selection passed 20 tests, including cancellation and
scratch reuse. A read-only real ESG native query using an existing stored vector
returned six hits in 0.787 seconds; no embedding/model call or data rebuild.
Full Summary authorship and packaged acceptance are separate host validations.

## Upstream merge assessment

Pending at the next upstream merge: inspect equivalent association schema and
query-plan changes and retain one native owner. The index hint references the
current table's existing primary-key autoindex; a schema change must update
this query and regression together. Do not restore a parallel implementation
or independent deadline as compatibility behavior.

## Document-query follow-through

The same join and independent deadline defect existed in
`search_native_ranges`, now used by Summary through the existing `documents`
target. Repair it in place with the current primary-key join and caller-owned
cancellation. Keep its source/generation, result, byte and candidate bounds.
`semantic_query._document_hit` now emits the complete ordered reader ranges,
including bounded whitespace joins and material/representation revisions, in
`QueryHit.documentReference`. The existing first locator remains a focus hint;
it is not the complete citation. Document identity hashes the source and full
reference, rather than a single locator. Consumers must validate the immutable
revisions and preserve all ranges. No data rebuild or second retrieval owner.

Tests in `test_native_query.py` and
`vector_store/test_native_range_publication.py` passed 21 tests, including
multi-range identity and absence of the independent range timer. Packaged
consumer verification and real Summary completion belong to the host report;
fork tests alone are not product acceptance.
