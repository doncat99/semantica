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

## Upstream merge assessment

Pending: reuse the upstream retry owner if it supplies equivalent corrective
context. Recheck bounded retries, whole-response admission and diagnostic privacy.
