"""S4.1: what an uploaded export is, decided before anything parses it.

Two jobs, kept apart on purpose.

The first is safety. Accepting an archive from a person and unpacking it is
the one genuinely dangerous thing this feature does, and it has to hold before
any vendor parser exists: an entry named `../../.ssh/authorized_keys` writes
outside the destination, and a 40KB zip can expand to gigabytes. Neither is
hypothetical and neither is the parser's problem.

The second is recognition, by entry name only. Nothing here reads a payload's
schema, because the schemas are what we do not have real samples of yet.
Structure we can be sure of from the vendors' own documented file names;
content we cannot, so this module refuses to guess and says UNKNOWN instead.
An honest UNKNOWN sends someone to ask for a sample. A wrong guess sends the
wrong parser at real data and silently produces wrong memories.
"""

import stat
import zipfile
from pathlib import Path

import pytest

from one_memory.imports.archive import (
    ArchiveRejection,
    ExportKind,
    detect_export,
    safe_entry_names,
)


def _zip(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return path


# --- recognition ----------------------------------------------------------


def test_tells_claude_from_chatgpt_by_the_file_only_claude_ships(
    tmp_path: Path,
) -> None:
    # Both vendors ship `conversations.json`. Claude's export also carries
    # `memories.json`, which is the archive-level memories it saved for the
    # user, and which we route to the existing memory-content channel rather
    # than re-extracting as chat.
    claude = _zip(
        tmp_path / "claude.zip",
        {"conversations.json": "[]", "memories.json": "[]"},
    )
    assert detect_export(claude).kind is ExportKind.CLAUDE


def test_recognises_chatgpt_by_its_own_companions(tmp_path: Path) -> None:
    chatgpt = _zip(
        tmp_path / "chatgpt.zip",
        {"conversations.json": "[]", "chat.html": "<html></html>"},
    )
    assert detect_export(chatgpt).kind is ExportKind.CHATGPT


def test_prefers_the_structured_payload_over_the_page(tmp_path: Path) -> None:
    # ChatGPT ships both. `conversations.json` is structured and stable;
    # `chat.html` is a rendering. Reading the page when the JSON is right
    # there costs a parser we would have to keep in step with their markup.
    chatgpt = _zip(
        tmp_path / "chatgpt.zip",
        {"conversations.json": "[]", "chat.html": "<html></html>"},
    )
    assert detect_export(chatgpt).payload == "conversations.json"


def test_says_ambiguous_rather_than_picking_one(tmp_path: Path) -> None:
    # A directory someone assembled by hand, or two exports zipped together.
    # Choosing for them means running one vendor's parser over another's
    # data, and the wrongness would land in memories, not in an error.
    both = _zip(
        tmp_path / "both.zip",
        {
            "conversations.json": "[]",
            "memories.json": "[]",
            "chat.html": "<html></html>",
        },
    )
    found = detect_export(both)
    assert found.kind is ExportKind.AMBIGUOUS
    assert set(found.candidates) == {ExportKind.CLAUDE, ExportKind.CHATGPT}


def test_recognises_a_bare_deepseek_payload(tmp_path: Path) -> None:
    bare = tmp_path / "deepseek_conversations.json"
    bare.write_text("[]", encoding="utf-8")
    assert detect_export(bare).kind is ExportKind.DEEPSEEK


def test_recognises_a_takeout_by_its_activity_path(tmp_path: Path) -> None:
    takeout = _zip(
        tmp_path / "takeout.zip",
        {"Takeout/My Activity/Gemini Apps/MyActivity.html": "<html></html>"},
    )
    found = detect_export(takeout)
    assert found.kind is ExportKind.GOOGLE_TAKEOUT
    # Named but out of scope for this release: telling someone we recognise
    # their file and do not support it yet is a different message from not
    # knowing what it is, and it saves them looking for a mistake they did
    # not make.
    assert found.supported is False


def test_supported_actually_distinguishes_something(tmp_path: Path) -> None:
    # Without this the assertion above passes for a `supported` that is
    # simply always False, which is the shape of a guard that guards nothing.
    claude = _zip(
        tmp_path / "claude.zip",
        {"conversations.json": "[]", "memories.json": "[]"},
    )
    assert detect_export(claude).supported is True


def test_says_unknown_for_an_archive_with_no_signature(tmp_path: Path) -> None:
    stranger = _zip(tmp_path / "stranger.zip", {"notes/whatever.txt": "hi"})
    found = detect_export(stranger)
    assert found.kind is ExportKind.UNKNOWN
    assert found.payload is None


def test_takes_a_single_markdown_conversation(tmp_path: Path) -> None:
    single = tmp_path / "a-chat.md"
    single.write_text("# a chat\n", encoding="utf-8")
    assert detect_export(single).kind is ExportKind.MARKDOWN


# --- safety, which has to hold before any parser exists -------------------


def test_refuses_an_entry_that_climbs_out_of_the_destination(
    tmp_path: Path,
) -> None:
    evil = tmp_path / "slip.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../../escaped.txt", "no")
    with pytest.raises(ArchiveRejection, match="outside"):
        safe_entry_names(evil)


def test_refuses_an_absolute_entry(tmp_path: Path) -> None:
    evil = tmp_path / "absolute.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("/etc/passwd", "no")
    with pytest.raises(ArchiveRejection, match="absolute"):
        safe_entry_names(evil)


def test_refuses_a_stored_symbolic_link(tmp_path: Path) -> None:
    # A zip can carry a symlink, and unpacking one is how a write lands
    # somewhere the destination check already approved.
    evil = tmp_path / "link.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        info = zipfile.ZipInfo("innocent-looking")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(ArchiveRejection, match="symbolic link"):
        safe_entry_names(evil)


def test_refuses_an_archive_that_expands_past_its_budget(
    tmp_path: Path,
) -> None:
    # A small archive of one very compressible member. The budget is checked
    # against the declared sizes before reading, so a bomb is refused without
    # being written anywhere.
    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big", "0" * 5_000_000)
    with pytest.raises(ArchiveRejection, match="budget"):
        safe_entry_names(bomb, max_total_bytes=1_000_000)


def test_lets_an_ordinary_archive_through(tmp_path: Path) -> None:
    # The positive control. Without it the three refusals above would still
    # pass if the function simply rejected everything.
    ordinary = _zip(
        tmp_path / "fine.zip",
        {"conversations.json": "[]", "memories.json": "[]"},
    )
    assert safe_entry_names(ordinary) == ["conversations.json", "memories.json"]


def test_reports_a_file_that_is_not_an_archive_as_such(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "truncated.zip"
    not_a_zip.write_bytes(b"PK\x03\x04 and then nothing useful")
    with pytest.raises(ArchiveRejection, match="not a readable archive"):
        safe_entry_names(not_a_zip)
