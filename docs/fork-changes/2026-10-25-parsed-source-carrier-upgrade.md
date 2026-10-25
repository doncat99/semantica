# Lossless parsed-source carrier upgrade

- Record ID: 2026-10-25-parsed-source-carrier-upgrade
- Date / author: 2026-10-25 / OntoScience maintenance
- Status: source regression and packaged profile carrier acceptance verified
- Fork base revision: 2d20ba37d2ca1bd77e197322292081d005661a85
- Upstream reference: not inspected; fork-local format migration
- Related records: OntoScience version-and-data-compatibility-governance

## Reason and scope

App startup rejects complete historical v1 parsed-source artifacts. Convert their
envelope without parsing, OCR, network, model calls or changing representation
identity. Unknown provenance stays absent, never filled from current code.

## Native capability assessment

- Owner: semantic_source_artifact.py parse_source_artifact, bind_parsed_source_artifact,
  _write_parsed_source_artifact, _load_parsed_source.
- Callers: semantic_worker.py, semantic_artifact_builder; schemas and
  test_semantic_worker_imports.py inspected. No existing migration operation found.
- Decision: extend native owner with one explicit import operation. Runtime loaders
  continue accepting v2 only; no alternate parser or legacy runtime reader.

## Approach and actual changes

- Add digest/identity-verified upgrade_parsed_source worker method.
- Preserve the complete document, representation and existing producer provenance.
- Allow absent historical processingRevision in writer output and rebound artifacts.
- Host owns durable storage/reference publication; this operation writes staging only.
- No model/network/dependency cost. No content regeneration.

## Verification and limitations

- Red specification: tests/test_parsed_source_upgrade.py reproduced missing operation before implementation.
- Native regression: 92 tests passed across upgrade, worker import, artifact contract,
  native extraction and artifact suites. Cold-process upgrade/binding stays isolated
  from parser, torch, spacy and Docling imports. App/profile acceptance belongs to host.
- Packaged consumer artifact `sha256:922a9586059e312e3f4e0e80a148e1b72de851098e113ffc535c8b981c39e9cb`
  started against the migrated profile. All 40 phase-1 references read as v2 and
  their representation identity digest remained
  `50724c5df4c76c2b1528f7f8fe04f17df81ca694352a2bb91600cdd1e7bdc4e8`.
  Existing parsed documents were loaded without reparsing. This validates the
  carrier migration, not completion of the separate ESG extraction build.
- Unknown historical structures must fail explicitly. Two receipt indexes for
  one unselected force-OCR variant group remain explicitly conflicted; they are
  outside the 158 extraction-key selection and are not silently resolved here.

## Upstream merge assessment

- Disposition: keep, until upstream provides equivalent lossless carrier migration.
- Incoming revision: not reviewed.
- Overlap: semantic_source_artifact/schema/worker. Recheck no-network import isolation,
  identity preservation, strict runtime v2 loading and host reference migration after merge.

## Dated follow-ups

Implementation and verification results will be appended below.
