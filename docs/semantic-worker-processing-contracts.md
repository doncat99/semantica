# Semantic worker processing contracts

Package revision and artifact digest identify provenance, not processing semantics.
Checkpoint reuse is fenced by source bytes, account/project inputs, recipe,
extraction specification, document processing settings, model/embedding binding,
artifact schema compatibility and `project_checkpoint.PROCESSING_CONTRACTS`.

Before changing a prompt, chunk boundary/overlap policy, grounding interpretation,
or an embedding transport/space assumption, reviewers must classify the change:

- An output-preserving fix uses the existing stage contract and adds a regression
  proving that previous admitted output remains valid.
- A semantic change increments the affected stage contract or recipe/specification
  version and adds a regression proving incompatible output is not reused.
- A new serialized shape declares explicit schema compatibility only when the old
  output has the same meaning; unknown legacy schemas remain incompatible.

Never increment a stage contract merely because the worker was rebuilt. Never
accept a legacy release by wildcard. The two known legacy extraction schemas are
listed explicitly and retain the structural-grounded-v1 processing contract.
Tests in `test_checkpoint_compatibility.py` cover source, model, recipe, schema and
stage changes. Contract declarations require review; these tests do not infer
semantic equivalence of arbitrary code or prompt edits.

The gateway adapter retains account-authorized loopback transport, billing
receipts and checkpoints. It is not a replacement model provider. Typed generation
and contextual output admission use BaseProvider; gateway batch embeddings retain
the existing transport because generic SDK embedding stores do not preserve this
receipt and batch contract. Vector space validation belongs to native VectorStore.
