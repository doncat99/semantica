# Canonical staging durability checkpoints

The streaming entity-resolution builder staged each singleton canonical entity with a separate publication call. Every stage called mutate, and mutate synchronously flushed RocksDB. Fixing identity candidate construction alone therefore left another per-record durability bottleneck in the same phase.

PublicationRecords now provides an explicit same-instance checkpointed pending-write scope. Native mutation validation, byte limits, read-after-write visibility and generation fences still apply on every call. The scope flushes after at most 128 mutations or 262144 serialized triple bytes, and flushes on successful scope exit before the caller seals canonical output count. The scope retains only two counters and the generation. It does not accumulate records or create another data owner. Standalone calls still flush before returning.

The builder uses this scope for the canonical traversal and stages through the same PublicationRecords instance. Cancellation or replaced generation raises before successful scope completion. Native publication remains pending with an unsealed count on reopen; activation cannot manufacture completion.

Focused evidence: full publication owner suite passed31tests13.04s. Additional cancellation, generation replacement and checkpoint/reopen tests passed3tests0.49s. Tests are in tests/triplet_store/test_publication_records.py; complete integration and product acceptance belong to the main delivery gate.
