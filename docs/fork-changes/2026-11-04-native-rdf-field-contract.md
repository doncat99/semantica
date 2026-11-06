# Native RDF field and joint-publication contract

Status: G1 field-contract freeze for the OntoScience integration. This is the
target contract for replacing current aggregate producers/consumers, not a
claim that production has migrated. No other project's data or API is in scope.
The selected canonical fact owner is the existing native Oxigraph store.

## Terms, scope and validation

`f:` means `urn:semantica:field:`; `pub:` means `urn:publication:`.
`rdf:` and `xsd:` use their standard namespaces. All product record IDs are
stable absolute IRIs; names and URLs supplied as text remain literals. A URL
literal must never silently become an entity IRI. `rdf:type` identifies record
kinds below, not a serialized class name or opaque record body.

Canonical records are scoped by the authorized project named graph. Every
source-derived contribution has an explicit Source and material revision.
Statement/evidence identity never depends on the current index filename or an
in-memory array position. References outside the authorized project fail
admission. The writer validates required/optional fields, scalar types,
cardinality, reference integrity and limits before native activation. RDF by
itself does not enforce those application constraints.

In the table, `1` is required once, `?` optional at most once, and `*` an
explicitly bounded collection. Missing optional means no triple, never an
empty string, fabricated default or JSON null. Set-valued references are
deduplicated. Ordered values use explicit integer positions, preserving
duplicates. All floats must be finite; confidence is in [0,1]. Decimal/integer
values must not pass through a JavaScript double when precision matters.

## Frozen semantic fields

| Record (`rdf:type f:…`) | Actual predicates, value types and cardinality | Write / read owner responsibility |
| --- | --- | --- |
| Source | `f:sourceId` string 1; `f:materialRevision` digest string 1; `f:state` enum IRI 1 | Source admission binds project/material; build and source consumers retrieve by exact identity |
| Representation | `f:source` Source IRI 1; `f:materialRevision` string 1; `f:contentDigest` string 1; `f:parser`, `f:parserVersion`, `f:recipeDigest`, `f:mediaType` strings 1; `f:nativeContent` immutable content IRI 1 | Parse owner writes one native document; reader fetches requested native refs/ranges, not another text mirror |
| Entity | `f:name`, `f:entityType` strings 1; `f:alias` strings *; `f:description` generated string ?; `f:status` enum IRI 1; `f:attribute` AttributeValue IRIs *; `f:evidence` Evidence IRIs * | Existing entity extraction/identity owner validates type/spec, merge/split and contributions; graph/search/report hydrate selected IDs |
| Assertion | `f:subject` Entity IRI 1; `f:predicate` vocabulary IRI 1; exactly one of `f:objectEntity` Entity IRI or `f:objectValue` typed scalar; `f:status` enum IRI 1; qualifier/evidence/support predicates below | Existing extraction/grounding owner writes qualified assertion identity; native fact reads preserve that identity and cannot collapse assertions with differing qualifiers |
| Relation | `f:sourceEntity`, `f:targetEntity` Entity IRIs 1; `f:relationType` vocabulary IRI 1; `f:status` enum IRI 1; qualifier/evidence/support predicates below | Relation owner writes the admitted edge; Explorer/report read the edge itself rather than infer edges from common evidence |
| SourceRelation | `f:source`, `f:targetSource` Source IRIs 1; `f:relationType` IRI 1; `f:entityRelation` Relation IRIs *; `f:evidence` Evidence IRIs *; `f:status` enum IRI 1; `f:unresolvedReason` string ? | Existing source-relation owner produces it; host must not reconstruct it by joining all entities |
| Evidence | `f:representation` Representation IRI 1; `f:itemRef` native ref string 1; `f:start`, `f:end` nonnegative xsd:integer ? together; `f:page` positive xsd:integer ?; `f:precision` enum IRI 1; `f:origin` enum IRI 1; `f:confidence` xsd:decimal ? | Grounding/provenance validates reference, range and actual native location. Quote text is a bounded read from the unique native source, not another permanent quote/full-text field. Missing physical provenance remains explicitly coarse/unknown |
| Support | `f:fact` Assertion/Relation IRI 1; `f:evidence` Evidence IRI 1; `f:source` Source IRI 1; `f:materialRevision` string 1; `f:status` active/retracted IRI 1 | Grounding owner admits an actual support contribution. Withdrawal removes/retracts this contribution; shared fact remains only while independently supported. It is not another evidence-text object |
| Mention | `f:representation` IRI 1; `f:itemRef` string 1; `f:start`, `f:end` integers 1; `f:entity` Entity IRI 1; `f:mergeOperation` operation IRI ? | Identity owner preserves located mention identity and explicit selected merge/split, without inventing a second resolver |
| Conflict | `f:conflictType` enum IRI 1; `f:status` open/resolved/ignored IRI 1; `f:reason` string 1; `f:resolution` string ?; `f:entity`, `f:assertion`, `f:relation`, `f:evidence` corresponding IRIs * | Existing conflict owner supplies detection/transition semantics; native persistence preserves them |
| ClassificationDimension / ClassificationItem | Dimension: `f:cardinality` single/multi IRI 1. Item: `f:dimension` IRI 1, `f:parent` item IRI ? | Classification configuration owner validates acyclic hierarchy and dimension identities |
| ClassificationAssignment | `f:source`, `f:dimension`, `f:item` IRIs 1; `f:confidence` decimal ?; `f:evidence` Evidence IRIs * | Native classification owner enforces single/multi cardinality before publication. Unclassified dimensions use `Source f:unclassifiedDimension Dimension`, not an invented assignment |
| Community / Topic | `f:title` generated string 1; `f:memberEntity`, `f:memberRelation`, `f:memberAssertion`, `f:memberCommunity`, `f:evidence` corresponding IRIs * as applicable; Community `f:level` nonnegative integer 1 and `f:parent` Community IRI ? | Existing native organization algorithms compute memberships. Store bounded records and source-scoped contribution links, not full member bodies. Withdrawal invalidates unsupported titles/memberships explicitly |

### Attributes, qualifiers and support are different fields

Attribute definitions come from `ExtractionSpecification` / `ExtractionAttribute`,
which already admits exactly `string`, `number`, `integer`, `boolean`,
`string_list`, `number_list`. Each configured definition gets an IRI bound to
the specification digest, entity type and attribute name. An AttributeValue
has `f:definition` IRI 1 and either `f:value` scalar 1, or `f:element` IRIs *.
An element has `f:position` nonnegative integer 1 and `f:value` scalar 1.
String → xsd:string; integer → xsd:integer; boolean → xsd:boolean; number →
finite xsd:decimal or xsd:double according to the configured producer type.
The choice is fixed per definition, not guessed on every read. Requiredness
comes from the same native specification. Empty list is a present list-valued
attribute with zero elements; absence is no AttributeValue. List positions are
unique and contiguous. Unknown names/types, arbitrary dictionaries, nested
lists and implicit coercion are rejected, never stringified as JSON.

Qualifier predicates are on Assertion/Relation directly: `f:polarity` positive/
negative IRI **1**; `f:condition`, `f:time`, `f:unit`, `f:qualifiedValue`
nonempty xsd:string **?**. This matches current `validate_fact_qualifiers`:
even `value` and `time` are strings, not inferred numbers/dates. Missing
qualifier is absent. Other qualifier keys fail admission.

`fact f:evidence evidence` preserves the full located evidence set.
`fact f:support supportRecord` preserves the admitted supporting subset with
source/material lineage. Every support's evidence must also occur in the
fact's evidence set, matching the current `support_ids ⊆ evidence_ids` rule.
They must not be aliased into one edge merely because current extraction often
sets both lists equal. Repeated support from two sources has two support
identities; withdrawing one must not delete the other's support.

## Exact joint publication contract

The immutable dependency tuple is `(project, source, material, representation,
recipe, schema, facts_epoch, embedding_model, embedding_revision, dimension,
metric, keyword_recipe, vector_recipe)`. These exact column/predicate names are
used by `tests/test_native_publication_audit.py::JOINT_PROBE`. Publication uses
`pub:state`, each `pub:<tuple-field>`, `pub:keyword`, `pub:keyword_digest`,
`pub:vector`, `pub:vector_digest`. Tuple strings in this synthetic publication
probe are identity encodings; production dimension is typed positive integer.

Keyword and vector feature/reference indexes must bind the **same complete
tuple** as the current native owner. The keyword index stores only terms and
record refs; the vector owner stores only vector features, refs and required
binding. No fact/evidence/document body resides in either. The native activation
point changes to ready only after both installed index identities are validated.
Read checks tuple/required asset availability, executes bounded index lookups,
hydrates only hit native IDs and fences against an owner change before return.
Install-time hashing tiny fixture indexes does not authorize query-time full
hashing of production indexes.

Failure before authoritative mutation can leave an existing valid reference
readable; the fixture proves that exact case. Once invalidation/fact mutation
has begun, pending or failed is explicit and previous refs are not served.
Successful replacement makes previous tuple refs stale. Withdrawal is explicit
and prevents both keyword and vector access; no keyword-only fallback. Native
facts are not copied into a historical knowledge graph to preserve old refs.
Historical reports retain required cited input identities/audit evidence, with
availability represented truthfully; failed updates do not fabricate old reads.

## Implementation boundary and remaining unknown-shaped fields

Write/read owner is existing `OxigraphStore` using its native typed RDF terms,
SPARQL query/update and durable flush capability. Generic Triplet convenience
conversion is not a lossless representation of these records. The integration
must extend that owner in place and keep one production path, not add a second
fact database. Source/extraction/provenance/classification/organization owners
retain their actual business semantics; these predicates do not replace them.

Current `KnowledgeAssertion.object: Dict`, `metadata: Dict[str,Any]`, community
`metrics`, and copied identity-profile metadata are **not** blanket admitted
fields. Current actual assertion builder produces an entity reference plus
name; that path maps to `f:objectEntity`, with name read from Entity. No inspected
current assertion producer demonstrates a required arbitrary object payload.
Before G2 removes a consumed metadata field, inventory its actual producer and
consumer and add a named typed predicate contract (for example identity profile
fields with located support) or delete the producer and unused field together.
Unknown consumed structures are integration blockers, not permission for an
opaque JSON literal, generic recursive property bag or silent field loss.

### G3 admitted extraction and classification fields

The native `Entity` / `Relation` dataclasses remain extraction's domain model.
`OxigraphStore` maps them in place; there is no serialized domain-object body in
RDF. Operation-local contribution identities are derived by its owner from the
complete binding, stage and located mention identity. They do not implement an
additional entity resolver. The existing identity/merge owner remains responsible
for cross-window resolution.

Entity extraction records additionally use typed `f:provider`, `f:model`,
`f:extractionMethod`, `f:confidenceSource` strings when supplied;
`f:mentionId` string, `f:spanOccurrence` nonnegative integer and a `f:mention`
Mention IRI. An optional `f:identityProfile` points to an IdentityProfile with
`f:description`, `f:referentKind`, `f:identityOwner`, `f:identityInstance`
strings, `f:evidenceOccurrence` nonnegative integer and the same located
representation/ref/start/end fields as evidence. Profile `evidence` is rebuilt
transiently from that input range, never persisted as a quote. Extraction
window references are explicitly coarse (`window-range`, `origin=unknown`)
until the provenance owner admits actual physical location; they must not be
presented as PDF-native coordinates. Source-global window bounds are on the
operation; evidence offsets are local to that exact window. AttributeValue also
keeps its configured `f:attributeName` and `f:attributeType` string identity.

Relations retain `f:predicateName`, `f:subjectId`, `f:objectId` strings and
`f:evidenceOccurrence` integer for reconstructing the native typed model.
`f:supportingRef` strings preserve the extractor's supplied structural refs;
these refs are not asserted to be final Support records. A raw model quote,
prompt, response, grounding-context body or arbitrary metadata dictionary is
not an admitted field. Unknown metadata fails adoption before any mutation.

An ExtractionOperation receipt contains `f:operationIdentity`,
`f:acceptedDigest`, `f:factsDigest` strings; `f:resultCount`, `f:ownedCount`,
`f:quadCount` nonnegative integers; explicit typed binding fields and bounded
`f:ownedRecord` / `f:modelReceipt` IRIs. The native atomic update inserts this
receipt and facts together. Final native read verifies referenced facts and
their digest; successful flush precedes accepted-cache body release. The
cache retains only a small acceptance identity after release, so missing paid
work cannot become a new cache miss. It is not a stage manifest or body store.
One operation is bounded to 2,048 result values, 8,192 owned records, 32,768
quads and 2 MiB of atomic RDF; accepted bodies are separately bounded to 1 MiB.

ModelReceipt uses named strings `f:receiptId`, `f:receiptOperation`,
`f:provider`, `f:model`, `f:inputDigest`, `f:outputDigest`, optional
`f:createdAt`. Numeric parameters are only `f:temperature`, `f:topP`,
`f:maxTokens`, `f:maxOutputTokens`. Metadata is only `f:extractionStage`,
`f:rejectedCount` plus finite nonnegative usage numbers `f:promptTokens`,
`f:completionTokens`, `f:totalTokens`, `f:inputTokens`, `f:outputTokens`.
Runtime relay URLs, rejected candidate bodies and arbitrary nested parameters
are not persisted. Model identity must equal the operation's admitted model.

SourceClassification is the existing typed classification result, persisted
with `f:source`, `f:profileId`, `f:profileVersion`, `f:assignment` and
`f:unclassifiedDimension` references. Dimensions additionally preserve
`f:dimensionId`; items preserve `f:itemId`; assignments use the table's typed
dimension/item/evidence/confidence fields. The owner verifies actual profile
digest, item membership, single/multi cardinality, admitted evidence references,
complete unclassified dimensions and receipt identities before atomic adoption.
It retains no classification input passage or model-response body.

This freezes explicit field meanings; it does not certify that current builders,
queries, reports or DTOs already use them. G2 owns native parsed-document
carrier and demand-driven reader admission; G3 owns paid-result acceptance and
native typed fact adoption. G4 must close consumer mapping, source withdrawal,
precision and actual joint publication/admission/retirement before UI/CLI can
be accepted. These boundaries do not make an earlier gate a full-build pass.
