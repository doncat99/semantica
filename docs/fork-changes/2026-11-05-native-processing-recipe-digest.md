# Bind processing recipes to native implementation owners

`_project_processing_digest` previously omitted native storage, canonical fact and identity projections, pipeline execution, conflict processing, and vector/search implementation code. These bytes participate in extraction, source classification and publication recipes, so changes could incorrectly reuse accepted work produced by older implementations.

The existing digest owner now includes `triplet_store`, `pipeline`, `conflicts`, `vector_store`, `explorer`, and `utils`, alongside its existing runtime owners. It hashes relative Python paths and content bytes; checkout relocation does not change identity. Documentation, tests and generated cache files remain excluded. There is no version dispatch or alternate reader.

Validation: six new parameterized owner-change specifications failed before the fix; relocation/exclusion characterization passed. After the fix, processing-digest and native-build-lifecycle suites pass together: 11 passed in 3.67 seconds. This invalidation fix requires rebuild under the new recipe; it does not establish fixed-artifact or real ESG product acceptance.
