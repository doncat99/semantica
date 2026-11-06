# Native scalar grounding of extraction evidence

Owner: existing parsed-source owner → grounded extractor → Oxigraph field codec.
This replaces the invalid `itemRef: window:<offset>` evidence address. It does
not add a reader, source body, graph, snapshot or persistent context projection.

The source owner proves transient extraction-text positions from native
structure and serializer order. Plain text, PDF page text and EPUB/flat-ODF
sections map to the same JSON scalar pointers as `document_reader`. PDF pages
use the parser's actual single newline; sections and Docling parts use two.
Repeated text is distinguished by its structural occurrence, without `.find`.
Window clipping uses binary search and returns at most 128 address ranges.

For Docling a part is provable only when it has one native text span and the
serializer output equals that scalar exactly. Generated table formatting and
other transformed/multi-span parts are unsupported evidence. No substring guess
can turn those bytes into a canonical scalar. Native adoption rejects such a
fact before committing its receipt (`NATIVE_GROUNDING_UNSUPPORTED`). Unaffected
native scalar text remains addressable. A future table change must establish
actual serializer span positions or extract from native cells, not fabricate
addresses or retain generated table text as another content carrier.

`urn:semantica:field:nativeRange` links Mention, IdentityProfile and Evidence
records to bounded `NativeRange` records containing `position`, `nativeRef`,
scalar-local `start`/`end`, and window-local `windowStart`/`windowEnd`. The old
window-local evidence start/end remain solely for exact extraction resume.
`joinBefore`, when present, contains only the one/two newline separator proven
by the native serializer. A report can read the bounded scalar ranges through
the existing reader and reconstruct the exact evidence without storing quotes.
Original bodies never enter RDF; names and qualified semantic fields remain
normal native domain fields.

The grounding recipe binds exact ranges and structure before paid extraction.
The codec also commits a `nativeGroundingDigest` with its operation receipt and
verifies it on repeat adoption and restart reads. Old receipts cannot silently
provide results without the new exact scalar proof.

Verification covers Unicode, repeated Docling paragraphs, all supported scalar
formats, cross-scalar separators, persistent native restart, changed address
rejection, transformed-table rejection and atomic non-adoption. The production
handoff tests also exercise real child-process crash/restart without paying
again. Product-level report/retrieval acceptance remains a separate gate.
