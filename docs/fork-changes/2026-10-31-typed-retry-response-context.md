# Retain rejected response in native typed retry context

- Record ID: 2026-10-31-typed-retry-response-context
- Date: 2026-10-31
- Inspected fork revision: 55976a378291aebde16d774faf2c24c13d7ede42
- Upstream reference: not refreshed
- Status: implemented, local regression verified; product acceptance pending

## Reason and native owner

Packaged ESG run 7e1d22fc-f8c8-4a45-a1ed-b2c498a2334b restored 25 chunks,
completed 37/2994 and failed identity_owner_not_in_evidence. The existing
BaseProvider.generate_typed retry only supplies schema locations/types, losing
the rejected response and therefore the values the model must correct.
Inspected callers include methods.extract_entities_llm and _ProjectModelProvider;
the latter inherits this owner. Repair the same bounded retry, without a second
extraction path, local JSON repair, relaxed admission or increased attempts.

## Change

Supply the previous rejected response as explicitly delimited response data to
the same model in its next attempt, before safe validation feedback. It remains
ephemeral model context; durable diagnostics retain only locations/types. Reset
response context before each attempt so a transport failure cannot reuse stale
output. No checkpoint identity, data deletion or migration changes.
Retry input tokens increase by the rejected response length on invalid responses.

## Verification and limits

Six red cases reproduce missing response context. Native typed owner and focused
identity/extraction/worker diagnostic regressions are run after repair. This does
not guarantee real model compliance or a successful full ESG build.
No raw rejected model values are added to persisted diagnostics or error text.

### Follow-up after real packaged run a46f0f9f (2026-10-31)

Published bd7b6a0e77a3 passed all three native release lanes and host packaging.
Real ESG extraction restored 37 windows and reached 79/2994, then failed again
on identity_owner_not_in_evidence. Retaining the rejected response alone did not
prove model compliance. Inspection found two remaining gaps: the native schema
omitted owner/instance cross-field evidence descriptions, and the native retry
removed validator explanations along with private input/context from diagnostics.

Repair the same owners: describe exact case-sensitive evidence requirements and
null semantics in IdentityProfileOut's model-facing JSON schema; send Pydantic
validation explanations only in ephemeral model retry context. Durable diagnostic
locations/types, admission constraints and retry bounds remain unchanged. No
alternate extraction or partial whole-response success is introduced.
Four additional red specifications reproduce missing schema descriptions and
missing corrective explanations. Focused native/identity/extraction/diagnostic
regressions pass after repair. Real packaged ESG completion remains unverified.

### Candidate admission correction after 67e8b498 (2026-10-31)

Packaged runs 58528240 and 820f0ece still failed during extraction; run dadbf752
was cancelled after collecting the same evidence. Actual responses inferred a
company owner from "our" in committee/report quotes without naming that company.
Rejecting those identity facts is correct. The defect is that semantic profile
grounding ran inside the whole-response transport schema, aborting all independently
grounded entity mentions instead of using the existing per-profile rejection owner.

Inspected native owners at 67e8b498: schemas.IdentityProfileOut,
grounded_entities_wire and methods.extract_entities_llm. Existing exact-quote
admission already rejects invalid profiles while retaining located mentions and
recording rejected_candidates. Split the same profile fields into IdentityProfileWire
and its validated IdentityProfileOut subclass. Strict extraction validates semantic
identity constraints in its existing profile-admission block, alongside exact source
location. Field types/lengths/closed shapes still use whole-response admission.
No inferred fact is repaired or admitted, no alternate extraction exists, and no
retry limits increase. Non-strict EntityOut retains its original validation.

Three red regressions reproduce absent owner, absent edition and empty identity
facts through BaseProvider.generate_typed. After repair all grounded mentions
remain, all invalid profiles have rejection receipts and only one model call occurs.
The 83 focused native extraction/wire/identity/diagnostic tests pass. Existing
checkpoint regressions cover restoration of rejected_candidates and model receipts.
These results do not establish successful packaged ESG completion or zero-token
warm rebuilding; both remain required product acceptance.

Expanded native artifact/cache/checkpoint/extraction regressions: 147 passed,
including profile rejection and receipt restoration without model calls. The
separate offline-upgrade suite has two existing failures (paid cache missed on
non-preflight old-format conversion); the False-False case also fails with HEAD
schemas/methods loaded before this correction. These are not product passes and
are not bypassed by deleting or regenerating paid checkpoints.

## Upstream merge assessment

Pending: reuse the upstream retry owner if it supplies equivalent corrective
context. Recheck bounded retries, whole-response admission and diagnostic privacy.
