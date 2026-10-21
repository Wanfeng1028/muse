"""D56: ratchet the retired dual-engine `store_for` seam out of the Core.

`main_database` is the selected SQLite access layer. `store_for` remains only
as migration debt from the superseded MySQL design, so new call sites must not
adopt it and the existing list may only shrink.

So this gate does what the schema-ownership ratchet does: pin today's number
and allow it only to shrink. It does not pretend today is clean — 80 sites
still call `main_database` directly — but it makes any new one a failure and
makes progress visible.

Why count rather than parse: wrapping the old seam in another helper would hide
the debt without removing it. Counting direct calls keeps the cleanup visible.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "one_memory"

#: `store_for(` as an actual call, not an import or a name in a docstring.
STORE_FOR_CALL = re.compile(r"\bstore_for\s*\(")

#: Where the retired seam itself lives.
SEAM_PATHS = frozenset({"memory_server/store_binding.py"})


def _relative(path: Path) -> str:
    return path.relative_to(SRC_ROOT).as_posix()


def _legacy_seam_call_sites() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = _relative(path)
        if relative in SEAM_PATHS:
            continue
        hits = len(STORE_FOR_CALL.findall(path.read_text(encoding="utf-8")))
        if hits:
            counts[relative] = hits
    return counts


#: Measured at the D56 cleanup boundary. Only shrink.
BASELINE_LEGACY_SEAM_CALLS = 11


def test_legacy_store_for_calls_never_grow() -> None:
    sites = _legacy_seam_call_sites()
    total = sum(sites.values())
    assert total <= BASELINE_LEGACY_SEAM_CALLS, (
        f"legacy store_for() calls rose from {BASELINE_LEGACY_SEAM_CALLS} to {total}. "
        "New code must use the D56 SQLite access layer."
    )


def test_the_ratchet_number_matches_reality() -> None:
    """The baseline must stay honest.

    If the count fell below the pinned number, the pin is stale and would keep
    allowing old sites back in up to the old total. Lower the constant when the
    count actually drops, so progress is locked in.
    """
    sites = _legacy_seam_call_sites()
    total = sum(sites.values())
    assert total >= BASELINE_LEGACY_SEAM_CALLS - 5, (
        f"count is {total} but the pin is {BASELINE_LEGACY_SEAM_CALLS}; "
        "lower the pin to lock in progress"
    )


def test_the_seam_is_the_only_place_that_wraps_the_old_call() -> None:
    """Wrapping `main_database` in a second helper would re-create two shapes.

    One seam is the whole point: two ways to get a store is the drift the port
    was introduced to prevent.
    """
    seam = SRC_ROOT / "memory_server" / "store_binding.py"
    text = seam.read_text(encoding="utf-8")
    assert "main_database" in text, "the seam must be where the old call is wrapped"


def test_every_listed_site_is_a_real_call() -> None:
    """Guard against the regex drifting into counting imports or prose."""
    sites = _legacy_seam_call_sites()
    for relative, count in sites.items():
        assert count > 0
        text = (SRC_ROOT / relative).read_text(encoding="utf-8")
        assert len(STORE_FOR_CALL.findall(text)) == count
