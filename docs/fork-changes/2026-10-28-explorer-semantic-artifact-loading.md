# Explorer native semantic artifact loading

- Date: 2026-10-28
- Status: implemented; focused verification passed; release acceptance pending
- Fork base revision: 823048faf502ce1f7a0fe3e26073aadc8c2011ea
- Upstream reference: not refreshed

## Reason and native capability assessment

Explorer's `GraphSession.from_file` delegates to `ContextGraph.load_from_file`.
The native worker emits `entities` and `relations`, with `source_entity_id` and
`target_entity_id`. ContextGraph already accepts entities and several edge aliases,
but silently drops these native relations. A focused Explorer regression reproduced
two nodes and zero edges before repair.

## Approach and actual changes

Extend the existing ContextGraph JSON loader and endpoint coercion with the native
semantic artifact field names. No alternate graph, UI, layout or consumer adapter.
Existing JSON aliases retain precedence. Callers include GraphSession.from_file
and the semantica-explorer CLI. No model calls. The native worker common extra
now includes the existing Explorer extra; CPU target constraints were regenerated.
The release wheel command builds the entire native Vite app before building the
wheel, using the existing package-data static asset inclusion. Installed native
acceptance checks that the complete HTML app and native graph APIs are available.

## Verification and limitations

`tests/explorer/test_semantic_artifact_loading.py`: red before repair (edge_count
was zero). The regression, Explorer authentication and ContextGraph Markdown
suite passed: 36 passed, 2 skipped. Native Vite production build passed. Full native
bundle acceptance and mounted UI verification remain pending.

## Upstream merge assessment

Pending: retain only until upstream's ContextGraph supports the native semantic
artifact keys. Re-run Explorer loading and ContextGraph JSON persistence tests.
