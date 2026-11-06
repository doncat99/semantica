# Isolated operation total RSS envelope

Inspected dirty main based on 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe. Native owner is `ParallelismManager.execute_isolated_task`; caller is the semantic builder exact community operation. The existing budget sampled only its worker and omitted retained parent inputs and transport allocations.

The same budget now samples the calling process and current worker subtree, before input encoding, during encoding, execution and after output decoding. Deadline, cancellation, bounded JSON transport and direct worker reaping are preserved. No new budget knob or alternate execution path.

Red specs reproduce parent-only overflow before spawn and combined overflow when neither process individually exceeds the budget. `/tmp/g4-total-rss-red.log`: 2 failed. `/tmp/g4-total-rss-green.log`: full isolated-task suite 19 passed.

This is a 50 ms sampled envelope, not an OS hard memory limit. JSON decoding and synchronous process startup can temporarily allocate or delay between checks. It does not qualify full-project identity, fact reconciliation, community capacity or the complete builder. Canonical DTO outputs are still retained by organization/report consumers; those require separate native owner work.
