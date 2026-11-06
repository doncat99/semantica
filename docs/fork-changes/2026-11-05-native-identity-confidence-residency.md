# Native identity confidence residency

Inspected revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus existing working changes.

Native owner: `DuplicateDetector._calculate_group_confidence` in
`semantica/deduplication/duplicate_detector.py`. Its caller is
`detect_duplicate_groups`; `EntityResolver` consumes these native groups.
The owner already computes the required mean and group-size multiplier.
No replacement decision algorithm, persistence owner, fallback or input cap is needed.

The confidence calculation copied the complete retained pair-score map into a
second list only to calculate its sum. Reuse its values view directly, preserving
iteration order, confidence arithmetic, empty behavior and every admitted score.

Red regression: `test_group_confidence_does_not_copy_all_pair_scores` failed with
524456 bytes allocated for 65536 scores (limit 16384 bytes), before the fix.
The focused identity partition, candidate budget, contextual identity and review
regression suite passes: 120 tests. This removes one redundant allocation; it
does not establish a global build memory budget or claim G4 acceptance.
