# Native pending-build identity candidate index

## Reason and native owner assessment

Inspected fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`, preserving
the existing G4 work. `DuplicateDetector._contextual_candidates` is the canonical
candidate retrieval owner; `EntityResolver` remains the merge authority.
`PublicationRecords` owns pending generation membership and native storage.
The former candidate buckets kept every project mention addressable in Python.
Native extraction had no complete contextual candidate component cursor.

## Implementation

`IdentityCandidateIndex` stores only native mention references, input ordinals
and hashed candidate keys in the pending publication graph. It delegates all
key semantics to `DuplicateDetector.candidate_keys` and global context
preparation to the existing disambiguator. Connected components preserve
candidate bridges and input order. A sealed count proves every staged Entity
was indexed before reads. Generation fences reject stale/withdrawn builds;
scope-bound cursors reject reuse across components. Pages bound rows and bytes;
component materialization rejects its member budget before yielding a partial
group. The index does not store entity DTOs or make identity decisions.

## Verification and limitations

`tests/triplet_store/test_identity_candidate_index.py`: 3 passed. Coverage
includes alias bridges, identifier keys, exact input ordering, incomplete index
rejection, stale generation rejection, cursor scope isolation, oversized
components and a 131-member component spanning physical pages after storage
restart. This verifies the new owner interface; builder integration belongs to
the parent change and is not claimed here. Context preparation still uses its
canonical semantic indexes. Oxigraph property-path traversal capacity needs
target-scale measurement; bounded Python pages alone do not prove bounded
native engine allocation. Oversized components explicitly fail rather than
silently dropping candidates or changing merge semantics. No release artifact,
dependency pin, model invocation or ESG product acceptance is claimed.

## Upstream merge assessment

This extends the fork's native publication/index boundary and depends on its
contextual candidate semantics. An upstream merge must preserve the single
resolver owner, complete candidate coverage and pending-generation fences;
there is no compatibility reader or second resolver.
