# Synchronize upstream while preserving native fork owners

- Record ID: 2026-10-22-upstream-sync
- Date / author: 2026-10-22 / fork maintainer tooling
- Status: verified-in-stated-scope
- Fork base revision: `62180d75a875d6cdeff156df97d2d067a6561121`
- Upstream reference: `0a2731c8223426efaa0dd9e9b345a8411ff3d4f0`
- Related records: [Docling dependency consistency](2026-10-21-docling-dependency-consistency.md),
  [optional formula semantics](2026-10-21-optional-formula-semantics.md)

## Reason and scope

Synchronize the 13 incoming upstream commits without replacing native project,
PDF, structured-document, or semantic-artifact ownership. This is source-fork
integration, not a semantic-worker release or an installed App update.

## Native capability assessment

Inspected upstream changes in `semantica/parse/image_parser.py`, `cli.py`,
`export/endpoint_names.py`, `export/lpg_exporter.py`, `llms/llms_provenance.py`,
and `mcp_server/__init__.py`, their existing callers and upstream regression
tests. These remain their native owners. The fork's PDFParser, DoclingParser,
native persistent center, artifact scheduling, and optional formula semantics
are retained. No alternate parsing or extraction implementation is introduced.

## Approach and actual changes

Merge upstream without source conflicts. Retain upstream image parsing,
provenance failures, export handling, CLI provider propagation and MCP fixes,
plus its CI/security dependency updates. The merged universal lock passes
locked validation.

Repair two existing test doubles in `test_semantic_artifact_scheduling.py` and
`test_semantic_artifact_grounding_budget.py` to accept the current sixth
`formula_semantics` argument and assert its default is false. Keep context
reference assertions anchored to the context argument, not the last argument.
No production workaround or weakened assertion is added.

Sparse checkout initially omitted the tracked `semantica_mcp` package. Restore
that checkout path rather than changing source imports. Install BeautifulSoup
for the optional HTML parser tests in the local verification environment.

No stored-data migration, new model call, parallel decision owner, consumer pin
change, or dependency release is introduced. The separately preserved old draft
checkpoint is not replayed over newer remote main.

## Verification and limitations

- Upstream affected suite: **611 passed, 1 skipped, 3 xpassed, 26 subtests passed**.
  Scope: image parsing, endpoint names/LPG export, provenance, MCP persistence,
  CLI, and LLM provider propagation.
- Native/parser suite: **206 passed, 8 skipped**. Scope: comprehensive parsing,
  scanned-PDF detection, grounding/wire contracts, checkpoint/fact identity,
  extras, semantic artifacts, native sources/center/snapshots, and structured LLM.
- `pytest -q tests/test_pdf_reader_ownership.py`: **14 passed**.
- `uv lock --locked` and staged/unstaged `git diff --check`: passed.
- Local logs: `/tmp/semantica-sync-upstream-tests-20261022.log` and
  `/tmp/semantica-sync-native-tests-20261022.log`.
- Full repository suite, three-platform native relocation, and installed App
  acceptance are not run here. Skips and xpasses are reported separately from
  passes. Existing Docling dependency pins remain unchanged; publication must
  follow `docs/semantic-worker-release.md` before any consumer upgrade.

## Upstream merge assessment

Disposition: **keep** fork native owners, **adapt** outdated test doubles,
**reuse** the incoming upstream fixes. Incoming revision is the SHA above.
No overlapping upstream owner supersedes the fork's PDF lifecycle, optional
formula semantics, project storage, or Docling configuration. Those remain
single-owner implementations. See the linked dependency record for release
coordination requirements; a source merge does not publish new artifacts.
