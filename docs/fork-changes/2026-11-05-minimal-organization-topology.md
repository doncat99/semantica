# Minimal organization topology boundary

The current `_semantic_organization` owner accepts only native entity id/name and relationship id/source/target/type rows and returns communities. It no longer accepts or holds project entity, assertion or evidence DTO collections. Grounded topics remain in the existing `_grounded_topics` owner and consume native projections separately.

The complete frozen community/topic characterization retains its original digest. Tests also enforce the minimal boundary, monitored native graph validation, single-pass relation partitioning, and release of extraction DTOs and quote bodies before community computation. Runtime limits are unchanged; this change does not establish target ESG capacity.
