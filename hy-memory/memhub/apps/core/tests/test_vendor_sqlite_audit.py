"""A1-08: the audit that says which SQLite is MemHub's and which is a vendor's."""

from __future__ import annotations

from pathlib import Path

from one_memory.memory_server.vendor_sqlite_audit import (
    MEMHUB_DB,
    Owner,
    audit,
    classify,
    host_files,
    memhub_files,
    unexplained_files,
    vendor_files,
)


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "one-memory"
    (home / "hy-memory" / "governed-v2" / "vector").mkdir(parents=True)
    (home / MEMHUB_DB).write_bytes(b"not a real db")
    (home / "hy-memory" / "governed-v2" / "history.sqlite3").write_bytes(b"x")
    (home / "hy-memory" / "governed-v2" / "vector" / "chroma.sqlite3").write_bytes(b"x")
    return home


def test_a_host_app_database_is_classified_as_the_hosts() -> None:
    """D53 keeps an Adapter's right to read the host's own SQLite.

    Calling this UNKNOWN would imply nobody owns it, which is how a borrowed
    file survives a migration and then quietly becomes the authority.
    """
    item = classify("snapshots/cursor/store.db")
    assert item.owner == Owner.HOST
    assert "host app" in item.reason


def test_host_files_are_separated_from_memhub_and_vendor(tmp_path: Path) -> None:
    home = tmp_path / "one-memory"
    (home / "snapshots").mkdir(parents=True)
    (home / "one-memory.sqlite3").write_bytes(b"x")
    (home / "snapshots" / "store.db").write_bytes(b"x")
    assert [item.relative for item in host_files(home)] == ["snapshots/store.db"]
    assert [item.relative for item in memhub_files(home)] == ["one-memory.sqlite3"]
    assert vendor_files(home) == []


def test_memhub_database_is_classified_as_memhub() -> None:
    assert classify(MEMHUB_DB).owner == Owner.MEMHUB


def test_vendor_directory_is_classified_as_vendor() -> None:
    """D53 does not make a bundled vendor's store MemHub's."""
    item = classify("hy-memory/governed-v2/history.sqlite3")
    assert item.owner == Owner.VENDOR
    assert "hy-memory" in item.reason


def test_chromas_vector_index_is_vendor_owned() -> None:
    item = classify("hy-memory/governed-v2/vector/chroma.sqlite3")
    assert item.owner == Owner.VENDOR


def test_an_unexplained_file_is_reported_not_ignored() -> None:
    """'We did not know about it' is how a file survives a migration and then
    quietly becomes the authority."""
    assert classify("stray.sqlite3").owner == Owner.UNKNOWN


def test_audit_separates_the_three_classes(tmp_path: Path) -> None:
    home = _home(tmp_path)
    assert [item.relative for item in memhub_files(home)] == [MEMHUB_DB]
    assert len(vendor_files(home)) == 2
    assert unexplained_files(home) == []


def test_audit_finds_nested_vendor_files(tmp_path: Path) -> None:
    """A vendor's own nested index must be found, not just top-level files."""
    home = _home(tmp_path)
    relatives = {item.relative for item in vendor_files(home)}
    assert "hy-memory/governed-v2/vector/chroma.sqlite3" in relatives


def test_a_missing_home_produces_no_findings(tmp_path: Path) -> None:
    assert audit(tmp_path / "absent") == []


def test_non_sqlite_files_are_not_reported(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "notes.txt").write_text("hello", encoding="utf-8")
    assert audit(home) == []


def test_every_finding_carries_a_reason(tmp_path: Path) -> None:
    """Reviewable, not just trusted: each row must say why it is classified so."""
    home = _home(tmp_path)
    for item in audit(home):
        assert item.reason


def test_the_real_home_classifies_as_measured(tmp_path: Path) -> None:
    """Pins the measurement recorded in the module docstring.

    This runs only when the real home exists, so it never fails on a clean
    machine — but on this machine it proves MemHub's db and the vendor's files
    are actually separated as claimed rather than assumed.
    """
    home = Path("~/.one-memory").expanduser()
    if not home.exists():
        return
    memhub = {item.relative for item in memhub_files(home)}
    vendor = {item.relative for item in vendor_files(home)}
    assert not (memhub & vendor), "a file was claimed by both MemHub and a vendor"
    if (home / MEMHUB_DB).exists():
        assert MEMHUB_DB in memhub
