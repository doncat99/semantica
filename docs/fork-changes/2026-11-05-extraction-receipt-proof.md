# Accepted extraction receipt proof lifecycle

The native extraction owner previously enumerated and hashed every owned record
several times for each hydrated entity/relation, including complete ownedRecord
lists merely to test membership. The builder therefore paid whole-window integrity
work for every point address.

Oxigraph now retains at most 1024 verified operation receipt tuples (operation id,
accepted digest and count), without RDF facts, DTOs or source text. Admission,
reopen, eviction and arbitrary native mutations still require complete integrity
validation. All public native mutators invalidate these proofs under the existing
publication lock, including failed mutations. Direct raw native corruption stays
visible. Point membership uses the exact subject/predicate/object/graph index.

Publication/projection codecs use the owner's graph-scoped mutation constructor.
It validates the target graph and constructs INSERT/DELETE targets explicitly;
accepted extraction graphs cannot be mutation targets. These derived writes
preserve proofs for immutable accepted operations. Arbitrary SPARQL updates retain
conservative invalidation. Publication generation and completion checks remain.

Validation: identity read-count regression was red with 12 full subject scans for
one hydration; it is green with zero scans after proof validation, including a
publication begin, rejected accepted-graph write, and raw mutation corruption.
59 extraction, projection, publication and qualified fact index tests passed.
This evidence is focused owner correctness and does not establish G4 completion.
