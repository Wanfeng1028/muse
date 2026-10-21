"""Recent-file priority survives restart through a selection-bound frozen copy.

No separate database manifest digest is required.
"""

import asyncio
import json
import os
import sqlite3
from datetime import UTC, datetime

import pytest

from one_memory.imports.access import AuthorizedSourceFile
from one_memory.imports.adapters import (
    ScanFailure,
    ScanIssueCode,
    ScannedEvidence,
    ScanOptions,
    ScanPhase,
    ScanProgressEvent,
)
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.runner import ImportRunner
from one_memory.imports.snapshots import SnapshotError, SnapshotErrorCode, SourceSnapshotStore
from tests.test_snapshot_adapter import Fixture, evidence, scan
from tests.test_snapshot_adapter import cleanup_readonly_fixtures as cleanup_readonly_fixtures

# Import the snapshot fixture's explicit read-only-tree cleanup, not a second copier.
pytestmark = pytest.mark.usefixtures("cleanup_readonly_fixtures")

SOURCES = ("workbuddy", "claude-code", "codex", "cursor")
OLD_MTIME = 1_600_000_000_000_000_000
RECENT_MTIME = OLD_MTIME + 1_000_000_000


def conversation(fixture, name, mtime, *, timestamp="2001-01-01T00:00:00Z"):
    source = fixture.job.source_id
    path = fixture.root / (
        f"projects/isolated/agent-transcripts/{name}/{name}.jsonl"
        if source == "cursor"
        else f"project/rollout-{name}.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, role in enumerate(("user", "assistant", "user")):
        text = f"Synthetic {name} turn {index}: exact original, no completion claim."
        if source == "codex":
            row = {
                "type": "response_item",
                "timestamp": timestamp,
                "payload": {
                    "type": "message",
                    "id": f"{name}-{index}",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        elif source == "cursor":
            row = {"role": role, "message": {"content": [{"type": "text", "text": text}]}}
        else:
            row = {
                "type": role,
                "sessionId": name,
                "uuid": f"{name}-{index}",
                "timestamp": timestamp,
                "message": {"content": text},
            }
        rows.append(row)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    os.utime(path, ns=(mtime, mtime))
    return path


@pytest.mark.parametrize("source", SOURCES)
def test_recent_conversation_yields_whole_before_older_with_exact_originals(
    tmp_path, monkeypatch, source
):
    fixture = Fixture(tmp_path, source)
    old = conversation(fixture, "a-old", OLD_MTIME, timestamp="2020-01-01T00:00:00Z")
    recent = conversation(fixture, "z-recent", RECENT_MTIME, timestamp="2026-09-22T00:00:00Z")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (old, recent)}
    grant_before = fixture.grants.require_receipt(user_id="local", source_id=source)
    expected = evidence(asyncio.run(scan(fixture.registration.create_adapter(fixture.grant))))
    expected.sort(key=lambda event: event.cursor.observed_modified_ns, reverse=True)
    opened_copies = []
    open_binary = AuthorizedSourceFile.open_binary

    def observed_open(file):
        if file.root != fixture.root and file.path.suffix == ".jsonl":
            opened_copies.append(file.relative_path.as_posix())
        return open_binary(file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observed_open)

    async def scenario():
        stream = fixture.adapter().scan(ScanOptions())
        actual = []
        try:
            async for event in stream:
                if not isinstance(event, ScannedEvidence):
                    continue
                actual.append(event)
                if len(actual) == 3:
                    assert not any("a-old" in path for path in opened_copies)
            return actual
        finally:
            await stream.aclose()

    actual = asyncio.run(scenario())
    assert actual == expected
    assert len(actual) == 6
    assert len({row.evidence.conversation_id for row in actual[:3]}) == 1
    assert actual[0].evidence.conversation_id != actual[3].evidence.conversation_id
    assert all("z-recent" in row.evidence.verbatim for row in actual[:3])
    assert [row.evidence.role for row in actual] == ["user", "assistant", "user"] * 2
    assert fixture.grants.require_receipt(user_id="local", source_id=source) == grant_before
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before
    assert {entry.relative_path for entry in fixture.manifest().files} == {
        path.relative_to(fixture.root).as_posix() for path in before
    }
    # Cursor rows in this fixture carry no timestamp, so the adapter assigns
    # file mtime as their stable chronology.
    if source == "cursor":
        assert actual[0].evidence.created_at is not None
    else:
        assert actual[0].evidence.created_at.year == 2026


def test_history_window_advances_old_records_without_storing_or_dispatching_them(
    tmp_path,
):
    fixture = Fixture(tmp_path, "claude-code")
    conversation(
        fixture,
        "old",
        OLD_MTIME,
        timestamp="2026-10-10T00:00:00Z",
    )
    conversation(
        fixture,
        "recent",
        RECENT_MTIME,
        timestamp="2026-10-15T00:00:00Z",
    )
    cutoff = datetime(2026, 10, 13, tzinfo=UTC)
    with fixture.jobs._connect(writing=True) as connection:
        connection.execute(
            "UPDATE import_jobs SET history_after=? WHERE job_id=?",
            (cutoff.isoformat(), fixture.job.job_id),
        )
    stored = []
    result = asyncio.run(
        ImportRunner(
            evidence_store=fixture.evidence,
            job_store=fixture.jobs,
            on_evidence=stored.append,
        ).run(adapter=fixture.adapter(), job_id=fixture.job.job_id)
    )

    assert result.status is ImportStatus.COMPLETED
    assert (result.stored, result.skipped) == (3, 3)
    assert len(stored) == 3
    assert all(record.created_at >= cutoff for record in stored)
    assert {record.conversation_id for record in stored} == {"recent"}


@pytest.mark.parametrize("source", ("workbuddy", "claude-code", "codex"))
def test_newer_conversation_imports_before_a_later_touched_older_one(tmp_path, source):
    fixture = Fixture(tmp_path, source)
    conversation(fixture, "touched-later", RECENT_MTIME, timestamp="2020-01-01T00:00:00Z")
    conversation(fixture, "spoken-later", OLD_MTIME, timestamp="2026-09-22T00:00:00Z")

    async def scenario():
        stream = fixture.adapter().scan(ScanOptions())
        names = []
        try:
            async for event in stream:
                if isinstance(event, ScannedEvidence):
                    names.append(event.evidence.conversation_id)
                    if len(names) == 4:
                        break
            return names
        finally:
            await stream.aclose()

    names = asyncio.run(scenario())
    assert names[0] != names[3]
    assert "spoken-later" in names[0]
    assert "touched-later" not in names[0]


@pytest.mark.parametrize("source", SOURCES)
def test_same_job_pause_restart_keeps_original_cursors_and_imports_every_record_once(
    tmp_path, monkeypatch, source
):
    fixture = Fixture(tmp_path, source)
    old = conversation(fixture, "a-old", OLD_MTIME)
    recent = conversation(fixture, "z-recent", RECENT_MTIME)
    seen = []

    def pause_after_second(record):
        seen.append(record)
        if len(seen) == 2:
            fixture.jobs.transition(fixture.job.job_id, ImportStatus.PAUSED)

    runner = ImportRunner(
        evidence_store=fixture.evidence,
        job_store=fixture.jobs,
        on_evidence=pause_after_second,
    )
    paused = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    # The pause lands between write batches; the recent file's batch is whole.
    assert paused.status is ImportStatus.PAUSED and paused.stored == 3
    assert all("z-recent" in record.verbatim for record in seen)
    selection_id = fixture.binding()["selection_id"]
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id=source)
    original = fixture.grant.authorize_file(recent)
    assert set(cursors) == {original.safe_id}
    assert cursors[original.safe_id].file_identity == original.file_identity
    assert cursors[original.safe_id].observed_modified_ns == RECENT_MTIME
    # Original timestamps/new files can change after capture without moving or
    # widening this job's immutable sequence.
    os.utime(old, ns=(RECENT_MTIME + 10, RECENT_MTIME + 10))
    conversation(fixture, "zz-outside-snapshot", RECENT_MTIME + 20)

    def no_recapture(*args, **kwargs):
        pytest.fail("resume must reopen the exact existing manifest")

    monkeypatch.setattr(SourceSnapshotStore, "capture", no_recapture)
    fixture.jobs = ImportJobStore(fixture.jobs.database_path)
    fixture.grant = fixture.grants.authorized_root(user_id="local", source_id=source)
    fixture.jobs.queue_for_resume(fixture.job.job_id)
    resumed = ImportRunner(
        evidence_store=fixture.evidence, job_store=fixture.jobs, on_evidence=seen.append
    )
    complete = asyncio.run(resumed.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert complete.status is ImportStatus.COMPLETED
    assert (complete.stored, complete.emitted, complete.merged, complete.errors) == (6, 6, 0, 0)
    assert fixture.evidence.count() == 6 and len(seen) == 6
    assert len({record.evidence_id for record in seen}) == 6
    assert all(record.revision == 1 for record in seen)
    assert all("z-recent" in record.verbatim for record in seen[:3])
    assert all("a-old" in record.verbatim for record in seen[3:])
    assert fixture.binding()["selection_id"] == selection_id
    assert not evidence(
        asyncio.run(
            scan(
                fixture.adapter(),
                ScanOptions(
                    cursors=fixture.jobs.get_source_cursors(user_id="local", source_id=source)
                ),
            )
        )
    )


def test_mtime_ties_are_stable_and_sync_also_reads_recent_first(tmp_path):
    fixture = Fixture(tmp_path)
    conversation(fixture, "z-tied", RECENT_MTIME)
    conversation(fixture, "a-tied", RECENT_MTIME)
    actual = evidence(asyncio.run(scan(fixture.adapter())))
    assert "a-tied" in actual[0].evidence.verbatim
    assert actual == evidence(asyncio.run(scan(fixture.adapter())))
    sync = Fixture(tmp_path / "sync", operation="sync")
    conversation(sync, "a-old", OLD_MTIME)
    conversation(sync, "z-recent", RECENT_MTIME)
    assert "z-recent" in evidence(asyncio.run(scan(sync.adapter())))[0].evidence.verbatim
    assert not list(sync.directory.iterdir())


def test_modified_copy_cannot_override_frozen_manifest_priority(tmp_path):
    fixture = Fixture(tmp_path)
    old = conversation(fixture, "a-old", OLD_MTIME)
    conversation(fixture, "z-recent", RECENT_MTIME)
    asyncio.run(scan(fixture.adapter()))
    copy = fixture.directory / fixture.job.job_id / "files" / old.relative_to(fixture.root)
    os.utime(copy, ns=(RECENT_MTIME + 10, RECENT_MTIME + 10))
    with pytest.raises(SnapshotError) as rejected:
        asyncio.run(scan(fixture.adapter()))
    assert rejected.value.code is SnapshotErrorCode.INVALID_MANIFEST


def test_recent_order_keeps_discovery_limit_explicit_without_narrowing_snapshot(tmp_path):
    fixture = Fixture(tmp_path)
    conversation(fixture, "a-old", OLD_MTIME)
    conversation(fixture, "z-recent", RECENT_MTIME)
    limited = asyncio.run(scan(fixture.adapter(), ScanOptions(max_scan_targets=1)))
    assert any(
        isinstance(event, ScanFailure) and event.reason_code is ScanIssueCode.BUDGET_EXCEEDED
        for event in limited
    )
    assert len(fixture.manifest().files) == 2
    complete = evidence(asyncio.run(scan(fixture.adapter())))
    assert len(complete) == 6 and "z-recent" in complete[0].evidence.verbatim


def test_revocation_does_not_interrupt_already_bound_recent_snapshot(tmp_path):
    fixture = Fixture(tmp_path)
    conversation(fixture, "a-old", OLD_MTIME)
    conversation(fixture, "z-recent", RECENT_MTIME)

    async def scenario():
        stream = fixture.adapter().scan(ScanOptions())
        seen = []
        try:
            async for event in stream:
                if isinstance(event, ScannedEvidence):
                    seen.append(event)
                if len(seen) == 1:
                    assert "z-recent" in event.evidence.verbatim
                    fixture.grants.revoke(user_id="local", source_id="claude-code")
            return seen
        finally:
            await stream.aclose()

    result = asyncio.run(scenario())
    assert len(result) == 6
    assert all("z-recent" in event.evidence.verbatim for event in result[:3])
    assert all("a-old" in event.evidence.verbatim for event in result[3:])
    assert fixture.grants.authorized_root(user_id="local", source_id="claude-code") is None


def test_cursor_sqlite_row_order_and_resume_are_explicitly_unchanged(tmp_path):
    fixture = Fixture(tmp_path, "cursor")
    database = fixture.root / "chats/isolated/session/store.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        for index in range(3):
            db.execute(
                "INSERT INTO blobs VALUES (?, ?)",
                (str(index), json.dumps({"role": "user", "content": f"Row {index}"})),
            )
    first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0]
    assert first.evidence.verbatim == "Row 0"
    remaining = asyncio.run(
        scan(fixture.adapter(), ScanOptions(cursors={first.cursor.file_key: first.cursor}))
    )
    assert [event.evidence.verbatim for event in evidence(remaining)] == ["Row 1", "Row 2"]
    assert any(
        isinstance(event, ScanProgressEvent) and event.phase is ScanPhase.DONE
        for event in remaining
    )
