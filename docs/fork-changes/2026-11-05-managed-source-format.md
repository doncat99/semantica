# Managed source format admission

- Date: 2026-11-05
- Status: planned
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main)
- Upstream reference: not inspected; merge disposition pending.

## Reason and native assessment

Auto Test CV a80ec9c8 failed because Library stores original bytes at extensionless
content-hash paths. DocumentParser admitted MIME but dispatched only by physical
suffix. Production runtime.ts passes the same paths, names and MIME types.
Repair DocumentParser and existing document_contract admission, not host copying.
DoclingParser remains the sole local converter; PDFParser remains native PDF owner.
Callers inspected: source.parse_source, semantic_source_artifact._parse_source,
DocumentParser._parse_conversion, project_remote_docling and DoclingParser.parse.

## Contract and scope

Resolve declared format from known physical/logical suffixes and MIME; reject
conflicting declared formats and unsupported MIME. Retain original path and bytes.
Thread admitted suffix into conversion/OCR provenance decisions. No model calls,
network, new dependencies, persistent format or migration. Update parser regressions
and host fixed artifact; existing page-knowledge-deep-relationship Case stays unchanged.
Delete suffix-only dispatch at this boundary; no alternative parser or fallback.

## Verification and limitations

Planned: red regression for extensionless text/PDF and conflicting MIME, affected
parser tests, PDF reader ownership, rebuilt artifact relocation and host CV.
Real ESG model capacity and published artifact pins remain unverified.
Upstream overlap: DocumentParser admission and DoclingParser provenance; retain only
until upstream handles immutable managed filenames with equivalent validation.

## 2026-11-05 implementation follow-up

Red actual-PDF test additionally exposed PDFParser's filename-only rejection.
Repair this same native owner by validating the opened document is PDF rather than
its storage suffix. DOCXParser has equivalent filename admission; delegate actual
DOCX package validation to python-docx. These are additional affected consumers.

## 2026-11-05 scoped verification

Implemented native declaration admission/routing, remote upload format filename,
local OCR provenance suffix and actual PDF/package admission. Original bytes are
never renamed/copied. Initial text/PDF/conflicting declaration regression: 4 failed,
6 passed. Actual PDF additionally reproduced PDFParser suffix rejection.
Targeted source/native-owner/Docling-content/PDF-lifecycle suite: 48 passed.
Tests use source checkout with dependency-only site-packages from qualified dev
bundle via PYTHONPATH, not product runtime acceptance. Evidence /tmp/g4-managed-*
logs (local). Ordinary venv lacks python-docx and has older PyMuPDF table behavior;
its two dependency failures are not native bundle failures. Fixed rebuilt artifact
and CV remain pending. No upstream merge reviewed.

## Additional native Office consumer found in independent review

The dedicated project_office.parse_office owner still admitted and selected its
output target using only the physical suffix. Extensionless managed .xls/.ppt/.wpd
therefore failed after DocumentParser admission. Thread the admitted source suffix
into this owner, retaining the original path and bytes; verify all three target
formats with the executable boundary substituted. No additional adapter or copy.

## Processing identity and final consumer closure

Independent review found source_processing_revision still chose parser owners and
Office capability identity by storage suffix. Resolve the same admitted format
from logical name and MIME for every build/write/rebind/read identity consumer;
keep recipe construction independent of OCR execution admission. Regressions bind
actual parser owners, managed Office receipt changes and physical/logical format
equivalence. Docling metadata.format also uses the admitted source_suffix instead
of reporting an empty format for managed originals (main agent write set).

Processing-identity red specification: six failures for omitted native parser
owners, absent managed Office receipt binding and missing logical-name identity.
After repair, document-reader-index, project-office, source-native-parser-owner and
project-source suites passed 57 tests. Existing force-OCR text recipe identity
check remains green; execution admission still rejects that request. Office
managed-target red specifications were three failures before the owner fix; the
complete Office suite passed 13 tests. Logs /tmp/g4-managed-recipe-{red,green}.log
and /tmp/g4-managed-office-{red,green}.log are local supporting evidence.

All four production processing-revision calls (builder and parsed-source
write/rebind/load) plus artifact_helpers now pass logical names. Format-dependent
physical suffix scan across source/builder/artifact and parser/Office owners found
no further canonical build-chain consumer: remaining physical suffix reads are
standalone parser defaults or metadata initialization overwritten by admitted
format. Standalone library extract_text/metadata convenience APIs accept physical
paths without a managed source contract; product parsing uses parse_document.
