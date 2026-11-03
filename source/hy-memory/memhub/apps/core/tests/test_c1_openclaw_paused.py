"""OpenClaw is paused: registered for honesty, but never probed or started.

The contract says "OpenClaw/Claw 暂停，禁止探测或启动". Registered-but-paused
means the catalog still lists the source (so the list is stable), yet nothing may
touch its path: no `stat`, no detection, no import. The failure this guards
against is silent probing — `inspect_source_location` used to `stat` the
`~/.openclaw` directory and would report `found`/`available`, which both probes
the host and offers a source the product has deliberately parked.
"""

from pathlib import Path

from one_memory.imports.locations import PAUSED_SOURCE_IDS, inspect_source_location
from one_memory.imports.sources.registry import build_source_catalog


def test_paused_source_is_still_registered(tmp_path: Path) -> None:
    """Pausing means "do not use", not "pretend it does not exist"."""
    catalog = build_source_catalog(home=tmp_path / "home", environment={})
    assert "openclaw" in PAUSED_SOURCE_IDS
    assert "openclaw" in catalog, "the catalog must stay stable while a source is paused"


def test_inspecting_a_paused_source_does_not_touch_the_filesystem(tmp_path, monkeypatch):
    """A paused source must not be probed — not even a `stat`."""
    root = tmp_path / "home" / ".openclaw"
    root.mkdir(parents=True)
    (root / "openclaw.db").write_bytes(b"")  # looks installed; must still be ignored

    touched: list[str] = []
    original_stat = Path.stat

    def counting_stat(self, *args, **kwargs):
        touched.append(str(self))
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", counting_stat)
    location = inspect_source_location("openclaw", root)

    assert location.state == "not_found", "a paused source must not be reported as found/available"
    assert location.reason == "source_paused"
    assert touched == [], (
        f"a paused source must not be stat'd at all, but these paths were: {touched}"
    )


def test_a_non_paused_source_is_still_probed_normally(tmp_path) -> None:
    """The guard must not disable probing for real sources."""
    root = tmp_path / "projects"
    root.mkdir()
    location = inspect_source_location("workbuddy", root)
    assert location.state == "found"
    assert location.root_id
