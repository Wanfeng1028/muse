from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CapabilityState(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    IMPLEMENTED = "implemented"


class VerificationLevel(StrEnum):
    FIXTURE_ONLY = "fixture_only"
    REAL_REPLAYED = "real_replayed"


class HostPackageCapabilities(BaseModel):
    """Static, release-evidence-backed capability declaration for one host."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    historical_import: CapabilityState
    incremental_import: CapabilityState
    live_sync: CapabilityState
    recall: CapabilityState
    installer: CapabilityState
    verification: VerificationLevel


def historical_only_capabilities(
    *,
    verification: VerificationLevel,
) -> HostPackageCapabilities:
    return HostPackageCapabilities(
        historical_import=CapabilityState.IMPLEMENTED,
        incremental_import=CapabilityState.IMPLEMENTED,
        live_sync=CapabilityState.NOT_IMPLEMENTED,
        recall=CapabilityState.NOT_IMPLEMENTED,
        installer=CapabilityState.NOT_IMPLEMENTED,
        verification=verification,
    )


def polling_live_sync_capabilities(
    *,
    verification: VerificationLevel,
) -> HostPackageCapabilities:
    return historical_only_capabilities(verification=verification).model_copy(
        update={"live_sync": CapabilityState.IMPLEMENTED}
    )


def with_recall_install_target(
    capabilities: HostPackageCapabilities,
) -> HostPackageCapabilities:
    """Declare that packages/host-bridge ships a recall install target for this host.

    This is a capability of the build, not the state of one user's machine:
    it says an installer exists, not that this user has run it. Whether recall
    is actually wired into a given host right now is read from that host's
    install journal and surfaced separately.
    """
    return capabilities.model_copy(
        update={
            "recall": CapabilityState.IMPLEMENTED,
            "installer": CapabilityState.IMPLEMENTED,
        }
    )
