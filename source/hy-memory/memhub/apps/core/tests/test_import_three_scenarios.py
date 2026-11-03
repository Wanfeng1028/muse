"""The three import scenarios a user actually meets.

Designed to be falsifiable: each test names a number that would be wrong if the
behaviour it covers regressed, and the append case asserts both that the new
turn arrived *and* that the old ones did not come again.
"""

import json
import os
import sqlite3

import pytest

from one_memory.imports.jobs import ImportStatus
from tests.test_file_cursor_import import Source, observe_opens

OLD_MTIME = 1_600_000_000_000_000_000
RECENT_MTIME = OLD_MTIME + 1_000_000_000


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_existing_conversations_import_from_an_empty_cursor(tmp_path, source):
    """Scenario 1: history already on disk before MemHub ever ran.

    Both files must be read and every turn stored. A cursor that started
    "already caught up" would silently import nothing.
    """
    fixture = Source(tmp_path, source)
    fixture.conversation("first", ["alpha one", "alpha two"])
    fixture.conversation("second", ["beta one"])

    job = fixture.run()

    assert job.status is ImportStatus.COMPLETED
    assert job.stored == 3, "every turn already on disk must land"
    assert job.errors == 0


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_a_new_conversation_imports_without_rereading_the_old_ones(tmp_path, monkeypatch, source):
    """Scenario 2: a brand-new session appears after the first import.

    Only the new file may be opened. Re-reading the settled ones is the
    difference between an incremental cursor and a rescan, and it is what makes
    a large history cheap to keep up to date.
    """
    fixture = Source(tmp_path, source)
    fixture.conversation("first", ["alpha one", "alpha two"], mtime=OLD_MTIME)

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 2

    opened = observe_opens(monkeypatch, fixture.root)
    fixture.conversation("second", ["beta one"], mtime=RECENT_MTIME)

    second = fixture.run()
    assert second.status is ImportStatus.COMPLETED
    assert second.stored == 1, "only the new session's turn is new"
    # The settled file was left alone.
    assert opened and all("second" in path or "rollout-second" in path for path in opened), opened


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_appending_to_an_existing_file_imports_only_the_new_turns(tmp_path, source):
    """Scenario 3: a session grows while MemHub is watching it.

    The appended turn must arrive, and the turns already stored must not be
    stored again — duplicate evidence would make the same conversation appear
    twice in every recall.
    """
    fixture = Source(tmp_path, source)
    path = fixture.conversation("session", ["turn one", "turn two"], mtime=OLD_MTIME)

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 2

    # The same file grows, the way a live session does.
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(fixture.record("turn three")) + "\n")
    os.utime(path, ns=(RECENT_MTIME, RECENT_MTIME))

    second = fixture.run()
    assert second.status is ImportStatus.COMPLETED
    assert second.stored == 1, "only the appended turn is new"

    turns = _verbatim(fixture)
    assert sorted(turns) == ["turn one", "turn three", "turn two"], turns
    assert len(turns) == 3, "no duplicates"


def _verbatim(fixture: Source) -> list[str]:
    """Every stored verbatim for this fixture's source, read back from SQLite."""
    with sqlite3.connect(fixture.data / "core.sqlite3") as connection:
        rows = connection.execute("SELECT verbatim FROM evidence").fetchall()
    return [row[0] for row in rows]
