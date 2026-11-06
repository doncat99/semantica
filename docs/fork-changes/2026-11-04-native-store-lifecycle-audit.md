# Native Oxigraph exclusive ownership and crash capability

## Reason and native owner

G1 must establish whether the existing embedded `triplet_store/oxigraph_store.py::OxigraphStore`
can remain the unique fact owner across worker failures. Inspected fork main
`24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus current local changes.
This is a temporary, no-model capability probe, not another service or schema.

## Approach and affected files

`tests/test_native_store_lifecycle_audit.py` holds the native store in one process,
requires a second writer to fail with its native lock error, kills the first
process after a durable atomic update, and verifies the typed literal from a new
process. No copied graph or recovery payload is used.

## Integration requirements and limitations

The product worker must own the directory exclusively; opening it independently
from each query process is invalid. Existing host `worker-session.ts` already
owns child cancellation and SIGTERM/SIGKILL escalation. Its current 2-second
cooperative grace plus 5-second kill grace does not meet the proposed 1-second
cancellation contract. G4 must integrate the native owner into that existing
lifecycle and enforce the agreed total deadline, not introduce a query service.
The native Python query API has no cooperative cancellation argument; process
termination capability is separately measured in `test_native_persistence_audit.py`.

This test does not establish concurrent product publication or packaged process
ownership. Upstream assessment: the lock/durability behavior comes from native
PyOxigraph; no upstream algorithm or production code is replaced.

## Verification

Lifecycle plus semantic field fidelity probes: **6 passed in 5.46s**. Final combined
native store/query/field/publication/range/vector/lifecycle run: **127 passed in
88.27s**. Two repositories' `git diff --check` passed. Early probe assertions were corrected to consume the existing SPARQL
`bindings` result shape. They did not identify a store defect.

## 2026-11-04 admission and deadline recipe probes

Two additional test-only recipes close capability questions before G4 integration:

- An incoming RDF scalar is first checked by codepoint length, then by UTF-8
  bytes, with a 64KiB field cap. The first test rejects a pre-existing 2Mi-codepoint
  emoji string before constructing a native literal or encoding that large
  input; additional Python allocation peak is **2,824B**. Boundary Unicode tests
  distinguish 64KiB of four-byte characters from one character beyond it.
  This is not permission to reject required long evidence: evidence text remains
  in the unique parsed-content carrier with the independently tested stable
  range interface. Required oversized knowledge fields need a declared range
  contract; G4 must not silently omit them or store an opaque document literal.
- A native CPU-expensive read exceeds a 200ms test deadline. The existing
  process mechanism uses SIGTERM, waits at most 250ms, then SIGKILL with a 500ms
  reap budget. Measured stop is **3.437ms**, below 1s; the unique store reopens
  with its committed data intact. This recipe has no copied recovery data.
  G4 must wire explicit deadline/cancellation errors into the existing worker
  owner, not return a partial successful page. This test does not claim the
  current host's 2s+5s lifecycle has been repaired.

`pytest -q -s tests/test_native_store_lifecycle_audit.py`: **3 passed / 3.02s**.
No product process, profile or model was touched. The new recipes are test-only,
not exported APIs; the field and process admission belong to G4's existing
producer/worker when consumers are switched. Native engine cache size remains
outside Python tracemalloc measurements and must be measured independently;
there is no unsupported claim of a configurable RocksDB cache cap in PyOxigraph.

Vector cost boundary: sqlite-vec exact KNN can read all eligible vectors. A
deadline can bound elapsed work and return an explicit over-budget result; it
does not make exact KNN a bounded-read query or satisfy G5 recall/performance.
G5 must select a scoped native index plan with measured candidate/read budgets;
no top-k truncation, hidden prewarm or lower recall is authorized by this probe.

## G4 production point-reader process measurement

`tests/triplet_store/test_publication_records.py::test_reopened_production_point_read_reports_native_process_cost`
uses the actual Entity adoption, publication activation and `read_native_records`
owners. The writer closes before a new reader process opens the same directory;
no aggregate, mocked storage wrapper, extra database or production API is added.
Unselected native facts in the same fact graph increase from 1,000 to 50,000.
The test measures process RSS high-water growth using OS `getrusage`, including
native Rust/RocksDB allocations, instead of claiming Python tracemalloc covers
the engine. Open growth is capped at 64MiB and query growth at 16MiB; the actual
selected record is verified and its response is below 8KiB.

Local macOS evidence: open-plus-query **12.34 / 14.41ms**, open high-water growth
**10,797,056 / 10,878,976 bytes**, query high-water growth **1,671,168 / 2,850,816
bytes**, identical **1,310-byte** responses. Input blocks were **0 / 0**, major
faults **1 / 0**, minor faults **1,091 / 1,138**. This is a fresh engine process
with a warm OS cache: zero reported input blocks must **not** be interpreted as
proof of zero storage reads or a cold-disk budget. Physical cold-device bytes
remain unqualified; no cache flushing or formal-profile operation is performed.
The existing subject-and-graph constrained owner-call regression complements
this measurement, but is not a substitute for native I/O evidence.

This closes the missing native-process allocation evidence for point-record
reads only. It does not qualify the query service's head-of-line blocking,
semantic candidate/read budgets, full scenes, packaged runtime or real ESG SLA.
The shared host `runNative` still encloses embedding work; keyword can therefore
wait behind unrelated slow semantic embedding. Move that external preparation
outside the exclusive store operation without opening a second store owner;
the acquired/read/revision-check section must remain serialized consistently.

Focused verification: extraction-record fidelity, publication records, worker
records, native producer publication and native query suites: **44 passed in
10.23s**. No models, network calls or formal profile data were used.


## 2026-11-05 fixed-artifact field subprocess correction

The existing test-only `tests/test_native_semantic_field_fidelity_audit.py::phase`
launched `sys.executable -c` without isolation or bytecode suppression. The parent
oracle used `-I -B`, but those flags do not propagate to a separately launched
interpreter. Five field tests could therefore import source packages from cwd
and write `.pyc` into the installed artifact. A previous 46-pass combined run
proved assertions locally but did not close installed-owner provenance for these
child phases. It must not be cited as 46 fixed-artifact-qualified passes.

The shared phase owner now launches `-I -B`; its child code asserts bytecode
suppression before imports. For fixed-artifact runs, the dedicated
`ONTOSCIENCE_FROZEN_ORACLE_BUNDLE_ROOT` environment value also requires the
child's `semantica.__file__` to resolve inside that exact bundle. Normal source
runs retain the same native RDF assertions and no production behavior changes.
The ignored host oracle passes that dedicated root and checks its own bytecode
suppression before production imports.

Red evidence: adding the child suppression assertion first failed the first
existing field test in 0.13s (`Native field audit subprocess must use -B`).
After fixing the single shared launch, all five field tests passed in 0.99s.
Host logs: `.tmp/g4-field-subprocess-bytecode-{red,green}.log`.
Strict full-inventory verification rejected both polluted installed artifacts;
no generated bytecode was deleted and no manifest was patched to mask the
failure. Host evidence is preserved separately. A fresh complete artifact and
all 46 installed-owner oracles plus lifecycle/change-verification must be rerun;
this source-only result does not qualify those gates. No algorithm, field
expectation, skip policy, model call or release budget changed. Upstream
assessment: test harness correction only, not an upstream semantic behavior fix.
