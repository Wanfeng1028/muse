"""Unpacking an archive a stranger sent, onto this user's disk.

`safe_entry_names` reads what an archive *says* about itself. That is enough
to turn away the obvious refusals cheaply, and it is not enough to unpack
with: the central directory is written by whoever built the file, so every
number in it is a claim rather than a measurement. These tests hold
`extract_safely` to the stricter standard -- that it stays within budget even
when the archive lied about the budget, and that a refusal leaves nothing
behind on the way out.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from one_memory.imports.archive import ArchiveRejection, extract_safely


def _zip(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return path


def test_writes_the_entries_under_the_destination(tmp_path: Path) -> None:
    source = _zip(
        tmp_path / "export.zip",
        {"conversations.json": "[]", "nested/chat.html": "<html></html>"},
    )
    into = tmp_path / "unpacked"

    written = extract_safely(source, into)

    assert (into / "conversations.json").read_text() == "[]"
    assert (into / "nested" / "chat.html").read_text() == "<html></html>"
    # Returned paths are what the caller opens next, so they have to be the
    # real locations rather than the names inside the archive.
    assert {p.relative_to(into).as_posix() for p in written} == {
        "conversations.json",
        "nested/chat.html",
    }


def test_takes_only_the_entries_asked_for(tmp_path: Path) -> None:
    source = _zip(
        tmp_path / "export.zip",
        {"conversations.json": "[]", "chat.html": "x" * 5000, "user.json": "{}"},
    )
    into = tmp_path / "unpacked"

    written = extract_safely(source, into, select=["conversations.json"])

    assert [p.name for p in written] == ["conversations.json"]
    # The point of selecting is not tidiness. A ChatGPT export carries the
    # whole history twice, once as JSON and once as HTML; unpacking the half
    # we cannot read costs the user disk for nothing.
    assert not (into / "chat.html").exists()


def test_refuses_before_writing_anything(tmp_path: Path) -> None:
    source = tmp_path / "hostile.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("fine.json", "[]")
        archive.writestr("../escaped.json", "[]")
    into = tmp_path / "unpacked"

    with pytest.raises(ArchiveRejection):
        extract_safely(source, into)

    # The safe entry was listed first. Had the check run per-entry during the
    # write, it would already be on disk when the second one was refused.
    assert not (into / "fine.json").exists()


def test_refuses_an_archive_whose_declared_sizes_do_not_hold(tmp_path: Path) -> None:
    """A tampered central directory is a refusal, not a partial import.

    This started as a bomb test and the measurement corrected it. Nothing
    verifies the uncompressed sizes in a zip's central directory -- they are
    written by whoever built the file -- so the intent was to check that the
    budget is re-counted against bytes actually written. CPython's `zipfile`
    turns out to cap each read at the declared size, so an understating
    archive cannot write past it; it fails its CRC instead.

    What matters for us is downstream of that difference and is the same
    either way: a file whose own bookkeeping is inconsistent must not produce
    a truncated `conversations.json` that then imports as a short history. It
    has to be refused, and it has to leave nothing behind.
    """
    body = "a" * 20000
    source = _zip(tmp_path / "liar.zip", {"payload.txt": body})

    # Rewrite the declared uncompressed size to 10 bytes wherever it appears
    # (local header and central directory both carry it).
    raw = source.read_bytes()
    assert raw.count(struct.pack("<I", len(body))) >= 1
    source.write_bytes(raw.replace(struct.pack("<I", len(body)), struct.pack("<I", 10)))

    into = tmp_path / "unpacked"
    with pytest.raises(ArchiveRejection):
        extract_safely(source, into, max_total_bytes=1000)

    # The ten bytes it did write are gone. A truncated payload left on disk is
    # worse than none: the next step has no way to tell it is a fragment.
    assert not (into / "payload.txt").exists()


def test_stops_when_the_entries_run_past_the_budget(tmp_path: Path) -> None:
    # Satisfied by the declared-size gate inside `safe_entry_names`, not by
    # anything in the write loop -- stated here so nobody reads this as proof
    # that a runtime byte count exists. It is kept because the caller of
    # `extract_safely` should see the refusal surface from this call, whichever
    # gate produced it, and should find no partial output either way.
    body = "a" * 20000
    source = _zip(tmp_path / "big.zip", {"payload.txt": body})

    with pytest.raises(ArchiveRejection, match="past"):
        extract_safely(source, tmp_path / "unpacked", max_total_bytes=1000)

    assert not (tmp_path / "unpacked" / "payload.txt").exists()


def test_leaves_an_existing_destination_alone_when_it_refuses(tmp_path: Path) -> None:
    into = tmp_path / "unpacked"
    into.mkdir()
    keep = into / "already-here.json"
    keep.write_text("{}")

    # The failure has to happen *inside* the write loop for cleanup to run at
    # all. A hostile name would be turned away by the declared-shape gate
    # before a single directory is made, and this test would then pass without
    # `_undo` ever executing -- which is exactly what it did before a mutation
    # run caught it. A tampered CRC is the way in: the entry starts writing
    # and fails partway.
    body = "a" * 20000
    source = _zip(tmp_path / "liar.zip", {"nested/payload.txt": body})
    raw = source.read_bytes()
    source.write_bytes(raw.replace(struct.pack("<I", len(body)), struct.pack("<I", 10)))

    with pytest.raises(ArchiveRejection):
        extract_safely(source, into)

    # Cleanup removes what this call wrote, including the folder it made for
    # it, and stops at the directory it was handed. Deleting a caller's folder
    # because their archive was bad is a worse outcome than the bad archive.
    assert not (into / "nested").exists()
    assert into.is_dir()
    assert keep.read_text() == "{}"


def test_names_an_entry_that_is_not_in_the_archive(tmp_path: Path) -> None:
    source = _zip(tmp_path / "export.zip", {"conversations.json": "[]"})

    with pytest.raises(ArchiveRejection, match="chat.html"):
        extract_safely(source, tmp_path / "unpacked", select=["chat.html"])
