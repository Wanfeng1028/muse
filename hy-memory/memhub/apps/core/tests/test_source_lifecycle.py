from one_memory.imports.adapters import SourceCapabilities
from one_memory.imports.lifecycle import (
    SourceObservationState,
    resolve_source_deletions,
)

CAPABILITIES = SourceCapabilities(
    can_append=True,
    can_observe_edits=True,
    can_observe_deletes=True,
    can_reconcile_complete_set=True,
)


def test_unavailable_source_never_implies_deletion() -> None:
    assert (
        resolve_source_deletions(
            capabilities=CAPABILITIES,
            state=SourceObservationState.UNAVAILABLE,
            existing_evidence_ids={"one", "two"},
            observed_evidence_ids=set(),
            explicit_deleted_ids={"one"},
        )
        == set()
    )


def test_complete_healthy_snapshot_can_reconcile_missing_evidence() -> None:
    assert resolve_source_deletions(
        capabilities=CAPABILITIES,
        state=SourceObservationState.COMPLETE,
        existing_evidence_ids={"one", "two"},
        observed_evidence_ids={"two"},
        explicit_deleted_ids=set(),
    ) == {"one"}
