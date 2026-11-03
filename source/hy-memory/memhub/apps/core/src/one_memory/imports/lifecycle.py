from enum import StrEnum

from one_memory.imports.adapters import SourceCapabilities


class SourceObservationState(StrEnum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    COMPLETE = "complete"


def resolve_source_deletions(
    *,
    capabilities: SourceCapabilities,
    state: SourceObservationState,
    existing_evidence_ids: set[str],
    observed_evidence_ids: set[str],
    explicit_deleted_ids: set[str],
) -> set[str]:
    if state is SourceObservationState.UNAVAILABLE:
        return set()

    deletions = (
        explicit_deleted_ids & existing_evidence_ids if capabilities.can_observe_deletes else set()
    )
    if state is SourceObservationState.COMPLETE and capabilities.can_reconcile_complete_set:
        deletions |= existing_evidence_ids - observed_evidence_ids
    return deletions
