# Reuse admitted native query preparation

- Record ID: 2026-10-29-query-preparation-reuse
- Date: 2026-10-29
- Status: implemented; local artifact verified, not published
- Fork base revision: 53a860172d52efdfd7e7315dc8313516f0cf144b
- Upstream reference: not inspected

## Reason and scope

Real ESG artifact replay using immutable release 972a907452b91fb56da0365a2be5c95fdc40aa8a
returned keyword results in 34.051 seconds cold and 4.985/5.115 seconds warm.
The daemon reused one worker and warm queries read zero artifact bytes, isolating
the remaining repeated work to the native worker. No embedding calls occurred.

## Native capability assessment

The owner is `semantica/semantic_query.py::query_semantic_artifact`, called by
`semantic_query_worker.py::serve`; regressions are in
`tests/test_semantic_query_worker.py`. It already delegates keyword scoring to
`ContextRetriever._keyword_match_entities` and vectors to `VectorRetriever`.
JSON admission and Pydantic validation are cached by digest and filesystem identity,
but every query dumps all models and rebuilds candidate/source maps. Repair this
owner by reusing its immutable preparation; introduce no alternate scorer or
serialized dataset. Native Explorer node search is a separate owner and is not
covered by these query-worker measurements.

## Approach and actual changes

Bound prepared snapshot state to two filesystem-identity/digest keys;
retain per-request source admission and native scoring; construct only requested
hits after ranking. No contract, dependency, stored-data or model-call change.

## Verification and limitations

The new preparation-reuse/source-scope/tamper regression failed before the fix
(34 source-map preparations instead of 17), then passed. Query-worker suite:
25 passed. Existing native Explorer search API checks: 7 passed.

The host's canonical local dependency builder produced immutable artifact
`sha256:1a67c9b2362b557823ed5ecb20d2ca2dfa8d48e7abef9fd6199efc45bfdcce18`.
Relocated acceptance passed, including parser dependency closure, native/OCR
formats, fresh worker model receipts against a loopback provider, keyword and
semantic query modes, native Explorer and post-run inventory verification.
The build receipt records the dirty-source snapshot before this documentation
update; this is not an artifact published from a clean fork revision.

Read-only ESG replay through that artifact and the host adapter took 22,618 ms
cold and 272/231 ms warm, returned 10 contexts each, read zero artifact bytes
on warm requests and made zero embedding calls. An earlier concurrent run's
70,556 ms cold outlier did not reproduce sequentially. Large-artifact cold
admission, real-provider semantic latency and installed-App acceptance remain
unqualified. Host focused suites passed 167 tests, but product acceptance had
10 passes and one missing Sidechat evidence-receipt failure before its prepared
worker stage; it is not a product pass. Existing published artifact remains
unchanged; no release or deployment is claimed.

A verified independent copy of the old published artifact measured 62,728 ms
cold and 3,984/4,704 ms warm in a later replay. Its serialized context digests
matched all three changed-artifact responses exactly (ordering, scores and
evidence included). Cold timings varied across relocated runs; this is a
diagnostic comparison, not a percentile latency qualification.

## Upstream merge assessment

Pending upstream review. Retain only while upstream query preparation repeats this
work; rerun evidence/scope/tamper and keyword/vector regressions after merging.

## 2026-10-29 pre-push verification

The combined checkpoint preflight/upgrade, semantic query worker, Explorer
workspace data and PDF ownership selection passed 91 tests. This is focused
source verification; no new release artifact was published or pinned here.
