# Organization reports use their product owner

- Date: 2026-11-04
- Base: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus shared G1–G4 working changes.
- Scope: `_explanation_reports`, adjacent product-boundary helpers and their fixtures.

The existing native grounded report generator remains the computation owner.
Before generating a selected report, the builder reads its exact product draft
from OntoScience's existing project-artifact storage through the authenticated
build relay. It does not store another report body in the fork or checkpoint.
Newly generated reports return only after the product owner acknowledges durable
adoption. Read failures and invalid responses fail closed.

The operation identity binds project, input revision, processing recipe, model
and selected target. It is a fixed string array hashed using native
`stable_digest`; the host has a Unicode/escape parity fixture. The content digest
is an opaque host integrity receipt over the complete report and model receipts,
not a claim that Python and JavaScript serialize arbitrary numbers identically.
Adoption checks the returned operation and complete validated payload, including
boolean-versus-number distinction. Read reuse rechecks the current context and
locator input digest, target type, evidence membership and report content hash.

No source body, generic task snapshot, LLM response archive or second knowledge
store is introduced. The host publishes a formal business report draft, not a
fork result cache. Request and response bytes are bounded to 256 KiB; product
requests have a 30 second deadline.

Verification: authenticated real HTTP plus independent worker subprocesses
exercise adoption, abrupt `os._exit(73)` after adoption and reuse with no second
model-fixture call; changing the saved grounding digest rejects reuse without
regeneration. Four ACK fault cases reject wrong operation, malformed digest,
modified receipt and boolean substitution. Host report persistence tests cover
complete stored payload integrity and actor/input/model/recipe/target isolation.

The guarantee starts after successful adoption. A provider completion followed
by worker death before product adoption can still lose that paid result; this
change does not claim exactly-once model execution across that window. The test
uses a fixture product server across worker restarts, not a host-process crash;
host database durability is separately verified in the host owner tests. No real
provider calls, official-profile migration, commit, artifact release or packaged
ESG acceptance are claimed by this record.
