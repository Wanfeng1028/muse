"""A plugin does not become realtime on every host or every unknown version."""

from one_memory.host_capabilities import HostLevel, resolve_host_capability


def test_unknown_version_does_not_claim_realtime() -> None:
    declared = resolve_host_capability("workbuddy", "one-memory", None)
    assert declared.max_level == HostLevel.L1
    assert declared.claims_realtime is False


def test_same_plugin_is_declared_separately_per_host() -> None:
    workbuddy = resolve_host_capability("workbuddy", "one-memory", "5.5.6")
    claude = resolve_host_capability("claude-code", "one-memory", "5.5.6")
    assert workbuddy.max_level == HostLevel.L2
    assert workbuddy.claims_realtime is True
    assert claude.max_level == HostLevel.L1
    assert claude.claims_realtime is False
