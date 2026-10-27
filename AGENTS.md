# Development requirements for doncat99/semantica

These requirements apply to all contributors and coding agents across this fork,
including library code, workers, adapters, scripts, examples and tests. Local
instructions may add requirements but must not weaken these rules.

## Main-only development

Develop and commit on `main`; the fork's remote default and sole development
branch is `main`. Before removing old branches, verify their history is included
and preserve uncommitted drafts recoverably. Publication is not deployment.

## Mandatory: native first, no duplicate implementations

Before proposing a design or writing implementation code:

1. Identify the capability being changed and inspect the current fork's native
   implementation, exports, actual callers, configuration and tests. Check recent
   removals and refactors so an obsolete checkout or consumer pin does not lead
   to rebuilding a capability that already exists or was deliberately removed.
2. Record the native owner (file and symbol), the relevant callers/tests, and
   whether the capability can be reused as-is, needs repair, or is genuinely
   absent. Include the inspected revision and concrete evidence in the change
   description or an existing design/review record. A similar API name alone is
   not evidence of capability; a placeholder alone is not evidence that no other
   native owner exists.
3. If the capability exists, reuse it. If it is defective or incomplete, fix or
   extend that native owner and update its callers and regression tests. Creating
   a second implementation of an existing capability is prohibited.
4. Only a demonstrated absence permits new capability development. Add it to the
   appropriate native module with one implementation owner and tests; do not
   introduce a competing subsystem.

Moving code into this fork, renaming it, calling it an adapter, or using a native
provider underneath does not make a duplicate implementation native reuse.
Prohibited duplicates include alternate algorithms, rule engines, prompts,
scorers, identity registries, pipelines and fallback implementations performing
the same job as an existing native capability. In particular, do not add a new
LLM decision path to replace or shadow an existing native decision owner.

Adapters may translate contracts and delegate; they must not independently redo
the delegated decision. Preserve necessary boundary validation and error handling.
On unsupported inputs or dependency failure, expose the limitation through the
existing error/unknown mechanism; do not silently switch to a parallel algorithm
or fabricate a successful result.

## PDF parsing ownership

- `PDFParser` uses PyMuPDF. Do not import, install as a direct project
  dependency, or restore pdfplumber, including inside this owner. Historical
  `use_text_flow` experiments do not authorize a backend rollback. Preserve
  the established PyMuPDF `sort` default and its explicit caller override.
- Direct PDF reader imports/calls (PyMuPDF/fitz, pdfplumber, pypdf, PDFium,
  pdfminer, Poppler and equivalent tools) belong only in
  `semantica/parse/pdf_parser.py::PDFParser`. Metadata and page counting are
  parsing too; workers, builders, ingestion, examples and integrations must
  delegate to this owner, never open PDFs with another reader or subprocess.
- Structured document conversion/OCR retains the existing
  `semantica/parse/docling_parser.py::DoclingParser` owner. Only this adapter may
  construct Docling converters or select their PDF backends; callers use the
  adapter, not Docling's reader APIs. Docling manages its own internal reader.
  Do not add a preliminary PDFParser extraction, reimplement Docling internals,
  or claim that changing PDFParser changes Docling's backend.
- Tests may create fixtures and exercise backend contracts directly. This does
  not authorize production reader use outside its owner. New dependencies,
  reader commands, dynamic loading and upstream merges require the same review.
- Run `pytest -q tests/test_pdf_reader_ownership.py` when changing these paths.
  Its static gate supplements review; constructed runtime imports still require
  inspection. Do not extend exceptions to accommodate a bypass.

## Regression and review requirements

- Reproduce defects with a regression test against the existing owner before
  fixing them. Reuse the existing evaluation and test harnesses.
- Verify affected callers and relevant existing regressions, not only new tests.
  Preserve no-network/no-model-call guarantees where the native path has them.
- For consolidation, list obsolete implementations and their consumers, migrate
  consumers to the native owner, and remove the duplicates in the same change.
  Do not restore deliberately retired implementations as compatibility fallbacks.
- Missing native-capability evidence or an unjustified second implementation is
  a review blocker. Do not present focused test success as full release acceptance.

## Mandatory fork change records

- Every change, including documentation and upstream merge resolutions, must add
  or update a record in [docs/fork-changes](docs/fork-changes/README.md) in the same
  change. Follow its template; link the record in the PR.
- Record the reason, inspected native owner, implementation approach, affected
  files/callers, regression evidence, limitations and upstream merge assessment.
  Distinguish planned, implemented and verified work; never invent missing history.
- Preserve previous decisions and results. Append dated corrections and merge
  assessments instead of replacing history; unresolved evidence stays explicit.
- A missing or stale change record is a review blocker, not optional release notes.
