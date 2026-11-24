# Saved v2 source startup migration

- Record ID: 2026-11-25-saved-source-startup-upgrade
- Date / author: 2026-11-25 / OntoScience maintainers
- Status: verified in stated scope
- Fork base revision: 25b7df520decd0f61beaae8a079090f372904364
- Upstream reference: not inspected

## Native owner and reason

Packaged startup found three historical v2 artifacts without reader indexes.
`native_maintenance.rebuild_reader_index` accepts only an installed current
reader; `semantic_source_artifact._write_parsed_source_artifact` is the single
current serialization/index owner. Add explicit offline `--upgrade-saved-source`
admission, delegating to that writer; normal reads still reject v2.

## Approach and boundary

Verify immutable digest and installation stability, read one representation at
a time (64MiB), validate the known v2 processing profile, normalize its current
profile, preserve historical material/source/representation identity, and record
the historical processing provenance by digest. Keep the installed original
untouched. Remove only redundant Docling text/DocTags mirrors in the new carrier;
text/plain receives the canonical `text` format. Unknown historical formats or
profiles fail explicitly. Caller installs by digest before atomically adopting
references; interrupted migration is repeatable. No PDF reads, parser calls,
model work or external requests occur. Host must preserve paid results and
original parser provenance in published receipts.

## Evidence and limits

Red test reproduced the absent migration entry. 52 native keyword/reader/PDF
ownership tests passed. Read-only local trials on the three actual historical
artifacts produced indexes for 38 pages, 555 pages and one text scalar, with
unchanged historical representation revisions. Packaged qualification and host
startup acceptance remain subsequent gates. Only known v2 local/remote profiles
and Docling/plain-text carriers are supported; unsupported data stays blocked.

## Upstream merge assessment

Keep pending upstream review; no incoming revision assessed. Preserve explicit
offline admission and the sole current writer if maintenance/source artifact
owners change upstream.
