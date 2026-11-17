# Native document query references

OntoScience's packaged protocol gate and citation reader require each
`source_text` result to retain its material revision, representation revision
and every original scalar range, including serializer boundary joins.

The canonical `_document_hit` producer now emits `documentReference` through
the query schema. Its stable ID binds the source and complete reference.
Changing a range or join therefore changes the result identity. Original
materials and persisted indexes are unchanged; no migration is required.

Consumers use this reference for exact historical citation reads. No host
reconstruction or alternate identity contract is introduced.

Verification: `tests/test_native_query.py` passed (7 tests), including multiple
ranges, boundary joins and identity changes; scoped `git diff --check` passed.
Three-platform relocated acceptance and host packaging remain release gates.
