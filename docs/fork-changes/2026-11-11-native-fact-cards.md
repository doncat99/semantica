# Bounded completed fact cards

PublicationRecords.scene delegates facts to the existing completed fact owner.
Projects fact ID, canonical endpoints, predicate, status and endpoint names; never
hydrates support members, evidence or selectors. Cursor and exact-ID reads enforce
publication scope, row and byte budgets, cancellation and generation fencing.
Native node catalog projection also supplies entityType alongside source IDs.
OntoScience UA consumes these references for navigation; it does not store semantic
facts or infer types. Existing relation/topology and canonical fact records remain
the single semantic source. Literal assertions, formula and conflict records are
not manufactured by this endpoint.

Validation: tests/triplet_store/test_canonical_fact_publication.py covers exact
selection, scalar output and member-free reads. No production data migration.
