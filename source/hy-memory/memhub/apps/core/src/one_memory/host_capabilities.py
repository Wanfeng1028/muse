"""Versioned host ceilings. Unknown versions must not claim a realtime boundary."""

from dataclasses import dataclass
from enum import IntEnum

from one_memory.call_event_store import HostId


class HostLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


@dataclass(frozen=True)
class HostCapability:
    host_id: HostId
    plugin_id: str
    host_version: str | None
    max_level: HostLevel
    claims_realtime: bool


# WorkBuddy 5.5.6 is the only ceiling with a named package investigation:
# SessionStart / UserPromptSubmit / PostToolUse can carry additionalContext.
# That is an L2 boundary, not an L3 wake. Other hosts stay L1 until their own
# version is registered. The same plugin id does not transfer across hosts.
_KNOWN_CEILING: dict[tuple[str, str, str], HostLevel] = {
    ("workbuddy", "one-memory", "5.5.6"): HostLevel.L2,
}


def resolve_host_capability(
    host_id: HostId,
    plugin_id: str,
    host_version: str | None,
) -> HostCapability:
    if plugin_id != "one-memory" or host_version is None:
        level = HostLevel.L0 if plugin_id != "one-memory" else HostLevel.L1
    else:
        level = _KNOWN_CEILING.get((host_id, plugin_id, host_version), HostLevel.L1)
    return HostCapability(
        host_id,
        plugin_id,
        host_version,
        level,
        claims_realtime=level >= HostLevel.L2,
    )
