"""The three import scenarios, on a real Core at a real volume.

`test_import_three_scenarios.py` covers the same three scenarios with two or
three turns per conversation. That proves the cursor logic is correct; it does
not prove it holds at the volume a machine actually carries — and the two
failure modes that matter here (a rescan that re-reads everything, an append
that duplicates) are exactly the ones that only bite at scale.

So this file is the same three scenarios against a running Core:
real adapters, real SQLite, real import jobs, at a volume large enough that
"it re-read the settled files" and "it duplicated a turn" are both visible as
numbers rather than as a couple of rows.

Designed to be falsifiable: every assertion names a number that would be wrong
if the behaviour regressed, and the two incremental cases assert the *absence*
of work (no re-read, no duplicate) rather than merely the presence of new rows.

Not collected by default (see `pytestmark`): it writes a few thousand records
and takes seconds, which is too slow for the standing suite. Run it with:

    .venv/bin/python -m pytest tests/test_import_three_scenarios_real.py -m real_volume
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from one_memory.imports.jobs import ImportStatus
from tests.test_file_cursor_import import Source, observe_opens

pytestmark = [pytest.mark.real_volume, pytest.mark.performance, pytest.mark.serial]

# Enough conversations and turns that a rescan or a duplicate is a number you
# cannot mistake for noise. Production carries ~313k evidence rows; this is a
# scaled-down but structurally equivalent shape (many sessions, many turns).
CONVERSATIONS = 40
TURNS_PER_CONVERSATION = 25
EXPECTED_TURNS = CONVERSATIONS * TURNS_PER_CONVERSATION

OLD_MTIME = 1_600_000_000_000_000_000
RECENT_MTIME = OLD_MTIME + 1_000_000_000


def _seed(fixture: Source, *, conversations: int, turns: int, mtime: int | None = None) -> None:
    for index in range(conversations):
        fixture.conversation(
            f"session-{index:04d}",
            [f"turn {index:04d}-{turn:02d}" for turn in range(turns)],
            mtime=mtime,
        )


def _stored_turns(fixture: Source) -> list[str]:
    with sqlite3.connect(fixture.data / "core.sqlite3") as connection:
        rows = connection.execute("SELECT verbatim FROM evidence").fetchall()
    return [row[0] for row in rows]


def _observe_bytes_read(monkeypatch, fixture: Source) -> list[int]:
    """Bytes actually read from the source root, per open.

    Counting opens is not enough to tell a resumed read from a full re-read:
    both open the grown file once. The difference is how much of it they read,
    and that is the only place a lost checkpoint is visible — evidence identity
    absorbs the duplicates, and the final cursor is the end of the file either
    way, so row counts and cursors both come out identical.
    """
    from one_memory.imports.access import AuthorizedSourceFile

    read: list[int] = []
    original = AuthorizedSourceFile.open_binary

    def observed(source_file):
        handle = original(source_file)

        class _Counting:
            def __init__(self) -> None:
                self._total = 0

            def read(self, *args):
                chunk = handle.read(*args)
                self._total += len(chunk)
                return chunk

            def readline(self, *args):
                chunk = handle.readline(*args)
                self._total += len(chunk)
                return chunk

            def __getattr__(self, name):
                return getattr(handle, name)

            def __enter__(self):
                handle.__enter__()
                return self

            def __exit__(self, *args):
                result = handle.__exit__(*args)
                read.append(self._total)
                return result

        return _Counting()

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observed)
    return read


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_existing_history_lands_every_turn(tmp_path, source: str) -> None:
    """Scenario 1 at volume: everything already on disk must land.

    Falsifiable: `EXPECTED_TURNS` is 1000. A cursor that started "already
    caught up" would import 0; a slice that lost a batch would land 744 or
    similar. Only a correct full read gives exactly 1000.
    """
    fixture = Source(tmp_path, source)
    _seed(fixture, conversations=CONVERSATIONS, turns=TURNS_PER_CONVERSATION)

    job = fixture.run()

    assert job.status is ImportStatus.COMPLETED, job.last_error_code
    assert job.stored == EXPECTED_TURNS, f"only {job.stored} of {EXPECTED_TURNS} turns landed"
    assert job.errors == 0
    assert len(_stored_turns(fixture)) == EXPECTED_TURNS


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_a_new_session_does_not_reread_the_settled_ones(tmp_path, monkeypatch, source: str) -> None:
    """Scenario 2 at volume: one new session must not re-read forty old ones.

    The absence assertion is the point. Re-opening the settled files is the
    difference between an incremental cursor and a rescan, and at this volume
    it is 40 files of difference rather than 1.
    """
    fixture = Source(tmp_path, source)
    _seed(
        fixture,
        conversations=CONVERSATIONS,
        turns=TURNS_PER_CONVERSATION,
        mtime=OLD_MTIME,
    )

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == EXPECTED_TURNS

    opened = observe_opens(monkeypatch, fixture.root)
    fixture.conversation("session-new", ["turn new-00"], mtime=RECENT_MTIME)

    second = fixture.run()
    assert second.status is ImportStatus.COMPLETED
    assert second.stored == 1, f"only the new turn is new, got {second.stored}"
    assert opened, "nothing was opened at all — the measurement is blind"
    assert all("session-new" in path for path in opened), (
        f"a settled session was re-read: {sorted(opened)[:5]}"
    )
    assert len(_stored_turns(fixture)) == EXPECTED_TURNS + 1


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_appending_to_a_live_file_adds_only_the_new_turns(
    tmp_path, monkeypatch, source: str
) -> None:
    """Scenario 3 at volume: a growing session must not duplicate its history.

    Duplicated evidence makes the same conversation appear twice in every
    recall, so the assertion is not just "the new turn arrived" but "the
    history did not come again".
    """
    fixture = Source(tmp_path, source)
    path = fixture.conversation(
        "session-live",
        [f"live-{turn:02d}" for turn in range(TURNS_PER_CONVERSATION)],
        mtime=OLD_MTIME,
    )

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED
    assert first.stored == TURNS_PER_CONVERSATION

    # Count what the second run opens. A correct incremental read opens only
    # the grown file; a reader that lost its resume point re-reads the whole
    # thing, which is visible here as work rather than as duplicate rows only.
    opened = observe_opens(monkeypatch, fixture.root)
    bytes_read = _observe_bytes_read(monkeypatch, fixture)
    appended = ["live-appended-00", "live-appended-01"]
    with path.open("a", encoding="utf-8") as stream:
        for text in appended:
            stream.write(json.dumps(fixture.record(text)) + "\n")
    os.utime(path, ns=(RECENT_MTIME, RECENT_MTIME))

    second = fixture.run()
    assert second.status is ImportStatus.COMPLETED
    assert second.stored == len(appended), f"only the appended turns are new, got {second.stored}"
    assert opened, "nothing was opened at all — the measurement is blind"
    assert all("session-live" in path for path in opened), (
        f"a file other than the grown one was read: {sorted(opened)[:5]}"
    )

    turns = _stored_turns(fixture)
    expected = [f"live-{turn:02d}" for turn in range(TURNS_PER_CONVERSATION)] + appended
    assert sorted(turns) == sorted(expected)
    assert len(turns) == len(expected), (
        f"{len(turns)} rows for {len(expected)} turns: the history came again"
    )

    # The resume point must have moved, not merely the row count. `stored`
    # alone cannot tell a resumed read from a full re-read that happened to
    # dedupe: evidence identity absorbs the duplicates either way, so a reader
    # that lost its checkpoint still reports the right number while doing many
    # times the work. The cursor is where that difference is visible.
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id=fixture.source)
    assert cursors, "no cursor was recorded for the grown file"
    assert any(
        value.checkpoint.startswith("byte:") and value.checkpoint != "byte:0"
        for value in cursors.values()
    ), f"the cursor never advanced past the start: {[v.checkpoint for v in cursors.values()]}"

    # And the work itself: a resumed read of two appended turns reads roughly
    # those two lines, while a reader that lost its checkpoint reads the whole
    # file. That gap is the only place this regression is observable at all.
    assert bytes_read, "no bytes were read — the measurement is blind"
    biggest = max(bytes_read)
    assert biggest < path.stat().st_size, (
        f"the second run read {biggest} bytes of a {path.stat().st_size}-byte file: "
        "the checkpoint was lost and the whole session was re-read"
    )
