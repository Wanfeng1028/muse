"""History import is live sync from an empty cursor: stat, skip unchanged, read forward.

Every fixture is a temporary native-format tree. No host history is read.
"""

import asyncio
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from one_memory.imports import runner as runner_module
from one_memory.imports.access import AuthorizedSourceFile
from one_memory.imports.adapters import ScannedEvidence, ScanOptions, ScanPhase
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources import cursor_unified
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor
from tests.test_source_upload_intents import upload_app, upload_client

OLD_MTIME = 1_600_000_000_000_000_000
RECENT_MTIME = OLD_MTIME + 1_000_000_000


class Source:
    def __init__(self, tmp_path: Path, source: str = "codex") -> None:
        self.source = source
        home = tmp_path / "home"
        (home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.registration = build_source_catalog(
            home=home, environment={}, import_root=tmp_path / "exports"
        )[source]
        self.root = self.registration.candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        self.data = tmp_path / "data"
        database = self.data / "core.sqlite3"
        self.jobs = ImportJobStore(database)
        self.evidence = EvidenceStore(database)
        self.grants = SourceGrantStore(database, home=home)
        self.grants.grant(
            user_id="local",
            source_id=source,
            root=self.root,
            candidate_kind=self.registration.candidate.kind,
        )

    def adapter(self):
        grant = self.grants.authorized_root(user_id="local", source_id=self.source)
        assert grant is not None
        return self.registration.create_adapter(grant)

    def supervisor(self, on_evidence=None) -> ImportSupervisor:
        return ImportSupervisor(
            adapters={self.source: self.adapter()},
            evidence_store=self.evidence,
            job_store=self.jobs,
            on_evidence=on_evidence,
        )

    def run(self, *, on_evidence=None):
        async def scenario():
            supervisor = self.supervisor(on_evidence)
            job = supervisor.create_job(self.source)
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())

    def conversation(self, name: str, texts: list[str], *, mtime: int | None = None) -> Path:
        path = self.root / (
            f"projects/acme/agent-transcripts/{name}/{name}.jsonl"
            if self.source == "cursor"
            else f"project/rollout-{name}.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            for text in texts:
                stream.write(json.dumps(self.record(text)) + "\n")
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))
        return path

    def record(self, text: str, role: str = "user") -> dict:
        if self.source == "codex":
            return {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        if self.source == "cursor":
            return {"role": role, "message": {"content": [{"type": "text", "text": text}]}}
        return {"type": role, "message": {"content": text}}


def observe_opens(monkeypatch, root: Path) -> list[str]:
    opened: list[str] = []
    original = AuthorizedSourceFile.open_binary

    def observed(source_file):
        if source_file.path.is_relative_to(root):
            opened.append(source_file.relative_path.as_posix())
        return original(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observed)
    return opened


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_rescan_opens_only_files_whose_stat_changed(tmp_path, monkeypatch, source):
    fixture = Source(tmp_path, source)
    first = fixture.conversation("first", ["alpha one", "alpha two"])
    fixture.conversation("second", ["beta one"])
    opened = observe_opens(monkeypatch, fixture.root)

    initial = fixture.run()
    assert initial.status is ImportStatus.COMPLETED and initial.stored == 3
    # The observer does see reads: both files were opened for the first import.
    assert {Path(path).stem.removeprefix("rollout-") for path in opened} == {"first", "second"}

    opened.clear()
    fixture.conversation("first", ["alpha three"])
    appended = fixture.run()
    assert appended.stored == 1
    assert opened and {Path(path).stem.removeprefix("rollout-") for path in opened} == {"first"}

    opened.clear()
    unchanged = fixture.run()
    assert unchanged.status is ImportStatus.COMPLETED
    assert (unchanged.stored, unchanged.emitted, unchanged.skipped) == (0, 0, 0)
    assert opened == []
    assert first.exists()


def test_appended_line_is_the_only_record_read(tmp_path):
    fixture = Source(tmp_path)
    fixture.conversation("session", [f"original {index}" for index in range(5)])
    assert fixture.run().stored == 5
    fixture.conversation("session", ["appended later"])
    again = fixture.run()
    assert (again.emitted, again.stored, again.merged, again.skipped) == (1, 1, 0, 0)
    assert fixture.evidence.count() == 6


def test_replaced_or_shrunk_file_is_reread_but_never_stored_twice(tmp_path):
    fixture = Source(tmp_path)
    texts = [f"kept {index}" for index in range(4)]
    path = fixture.conversation("session", texts)
    assert fixture.run().stored == 4
    before = path.stat().st_ino

    replacement = path.with_suffix(".tmp")
    replacement.write_text("".join(json.dumps(fixture.record(text)) + "\n" for text in texts))
    os.replace(replacement, path)
    assert path.stat().st_ino != before
    replaced = fixture.run()
    # Reread from the top is what makes this a test of dedupe, not of skipping.
    assert replaced.emitted == 4
    assert (replaced.stored, replaced.merged) == (0, 4)

    path.write_text("".join(json.dumps(fixture.record(text)) + "\n" for text in texts[:2]))
    shrunk = fixture.run()
    assert shrunk.emitted == 2
    assert (shrunk.stored, shrunk.merged) == (0, 2)
    assert fixture.evidence.count() == 4


def test_a_file_that_shrinks_behind_a_still_valid_checkpoint_is_reread(tmp_path):
    fixture = Source(tmp_path)
    texts = [f"kept {index}" for index in range(3)]
    body = "".join(json.dumps(fixture.record(text)) + "\n" for text in texts)
    path = fixture.conversation("session", [])
    path.write_text(body + '{"unfinished":')
    assert fixture.run().stored == 3
    # Dropping only the unfinished tail leaves the checkpoint's anchor intact,
    # so the size is the one sign that the file was rewritten.
    with path.open("r+") as stream:
        stream.truncate(len(body.encode()))
    assert path.stat().st_size < len((body + '{"unfinished":').encode())
    rewritten = fixture.run()
    assert (rewritten.emitted, rewritten.stored, rewritten.merged) == (3, 0, 3)


def test_revocation_stops_within_one_batch_and_no_later_file_is_opened(tmp_path, monkeypatch):
    fixture = Source(tmp_path)
    total = runner_module.EVIDENCE_BATCH_RECORDS * 3
    fixture.conversation(
        "recent", [f"recent {index}" for index in range(total)], mtime=RECENT_MTIME
    )
    fixture.conversation("older", ["older only"], mtime=OLD_MTIME)
    opened = observe_opens(monkeypatch, fixture.root)

    control = Source(tmp_path / "control")
    control.conversation("recent", [f"recent {index}" for index in range(total)])
    control.conversation("older", ["older only"])
    completed = control.run()
    # Without revocation every record lands, so the bound below is not vacuous.
    assert completed.stored == total + 1

    def revoke_on_first(_record):
        fixture.grants.revoke(user_id="local", source_id="codex")

    stopped = fixture.run(on_evidence=revoke_on_first)
    assert stopped.status is ImportStatus.PAUSED
    assert 1 <= stopped.stored <= 2 * runner_module.EVIDENCE_BATCH_RECORDS
    assert not any("older" in path for path in opened)


@pytest.mark.parametrize("revoke", [False, True])
def test_revocation_between_small_files_stops_before_the_next_is_opened(
    tmp_path, monkeypatch, revoke
):
    # Small files are all read before the first write batch commits, so only
    # the grant check at each file's start can stop the reader here.
    fixture = Source(tmp_path)
    for index in range(4):
        fixture.conversation(f"small-{index}", [f"small {index}"], mtime=RECENT_MTIME - index)
    opened: list[str] = []
    original = AuthorizedSourceFile.open_binary

    def observed(source_file):
        opened.append(source_file.relative_path.name)
        if revoke and len(opened) == 1:
            fixture.grants.revoke(user_id="local", source_id="codex")
        return original(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observed)
    result = fixture.run()
    if not revoke:
        assert result.status is ImportStatus.COMPLETED and len(set(opened)) == 4
        return
    assert result.status is not ImportStatus.COMPLETED
    assert set(opened) == {"rollout-small-0.jsonl"}
    assert fixture.evidence.count() == 0


@pytest.mark.parametrize("swap", ["symlink", "hardlink", "moved-out-and-linked"])
def test_symlinks_leaving_the_root_are_refused_even_when_swapped_in_after_listing(
    tmp_path, monkeypatch, swap
):
    fixture = Source(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "rollout-secret.jsonl"
    secret.write_text(json.dumps(fixture.record("outside secret")) + "\n")
    (fixture.root / "project").mkdir(parents=True)
    (fixture.root / "project/rollout-linked.jsonl").symlink_to(secret)
    (fixture.root / "linked-dir").symlink_to(outside, target_is_directory=True)
    fixture.conversation("recent", ["recent inside"], mtime=RECENT_MTIME)
    swapped = fixture.conversation("swapped", ["swapped inside"], mtime=OLD_MTIME)
    opened = observe_opens(monkeypatch, fixture.root)

    def swap_in() -> None:
        if swap == "symlink":
            swapped.unlink()
            swapped.symlink_to(secret)
        elif swap == "hardlink":
            # A different regular file: only the inode check can tell.
            swapped.unlink()
            os.link(secret, swapped)
        else:
            # The listed inode itself, now reached through a link out of the
            # root: only refusing to follow the link can tell.
            moved = outside / "moved.jsonl"
            os.replace(swapped, moved)
            swapped.symlink_to(moved)

    async def scan(swapping: bool):
        texts = []
        async for event in fixture.adapter().scan(ScanOptions()):
            if isinstance(event, ScannedEvidence):
                texts.append(event.evidence.verbatim)
                if swapping and event.evidence.verbatim == "recent inside":
                    swap_in()
        return texts

    # Before any swap, the later file is read: the swap below is what stops it.
    assert asyncio.run(scan(swapping=False)) == ["recent inside", "swapped inside"]
    # Links present when the folder is listed are never even opened.
    assert not any("linked" in path or "secret" in path for path in opened)
    texts = asyncio.run(scan(swapping=True))
    assert texts == ["recent inside"]
    assert "outside secret" not in texts


def _store(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE IF NOT EXISTS blobs (id TEXT, data TEXT)")
    return connection


def _add_rows(connection: sqlite3.Connection, start: int, count: int) -> None:
    for index in range(start, start + count):
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            (f"row-{index}", json.dumps({"role": "user", "content": f"store row {index}"})),
        )


def test_cursor_store_reads_only_new_rows_and_skips_an_unchanged_database(tmp_path, monkeypatch):
    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/session/store.db"
    writer = _store(database)
    try:
        _add_rows(writer, 0, 3)
        opened: list[str] = []
        original = cursor_unified.open_sqlite_readonly

        def observed(source_file, **kwargs):
            opened.append(source_file.relative_path.as_posix())
            return original(source_file, **kwargs)

        monkeypatch.setattr(cursor_unified, "open_sqlite_readonly", observed)
        first = fixture.run()
        assert first.stored == 3 and opened

        opened.clear()
        assert fixture.run().stored == 0
        assert opened == []

        # Rows that exist only in the write-ahead log still count as a change.
        _add_rows(writer, 3, 1)
        assert database.with_name("store.db-wal").stat().st_size > 0
        later = fixture.run()
        assert opened
        assert (later.emitted, later.stored) == (1, 1)
    finally:
        writer.close()
    assert fixture.evidence.count() == 4
    assert not (fixture.data / "import-snapshots").exists()


def test_cursor_import_paused_midway_resumes_from_its_cursor(tmp_path):
    fixture = Source(tmp_path, "cursor")
    rows = runner_module.EVIDENCE_BATCH_RECORDS * 3
    with closing(_store(fixture.root / "chats/workspace/session/store.db")) as writer:
        _add_rows(writer, 0, rows)
    fixture.conversation("transcript", ["transcript one", "transcript two"])
    total = rows + 2
    seen = []

    async def scenario():
        supervisor = fixture.supervisor()
        job = supervisor.create_job("cursor")

        def pause_on_first(record):
            seen.append(record)
            if len(seen) == 1:
                fixture.jobs.transition(job.job_id, ImportStatus.PAUSED)

        supervisor.on_evidence = pause_on_first
        supervisor.enqueue(job.job_id)
        paused = await supervisor.wait(job.job_id)
        assert paused.status is ImportStatus.PAUSED
        assert 0 < fixture.evidence.count() < total
        supervisor.resume(job.job_id)
        return await supervisor.wait(job.job_id)

    completed = asyncio.run(scenario())
    assert completed.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == total
    assert len({record.evidence_id for record in seen}) == len(seen) == total


def test_progress_moves_from_discover_to_read_with_the_file_total(tmp_path, monkeypatch):
    fixture = Source(tmp_path)
    for name in ("one", "two", "three"):
        fixture.conversation(name, [f"{name} text"])
    phases: list[ScanPhase] = []
    record = ImportJobStore.record_progress

    def observed(self, job_id, *, runner_token, phase, discovered_increment):
        phases.append(phase)
        return record(
            self,
            job_id,
            runner_token=runner_token,
            phase=phase,
            discovered_increment=discovered_increment,
        )

    monkeypatch.setattr(ImportJobStore, "record_progress", observed)
    job = fixture.run()
    assert job.discovered_targets == 3
    assert phases[0] is ScanPhase.DISCOVER
    assert ScanPhase.READ in phases
    assert phases.index(ScanPhase.READ) > phases.index(ScanPhase.DISCOVER)
    assert phases[-1] is ScanPhase.DONE
    # One discovery update per listing, not one database write per file.
    assert phases.count(ScanPhase.DISCOVER) == 1


def test_a_failed_batch_advances_no_cursor_and_the_rerun_stores_each_record_once(
    tmp_path, monkeypatch
):
    fixture = Source(tmp_path)
    total = runner_module.EVIDENCE_BATCH_RECORDS * 3
    fixture.conversation("session", [f"line {index}" for index in range(total)])
    put = EvidenceStore.put
    calls = {"count": 0}

    def failing_put(self, evidence, **kwargs):
        calls["count"] += 1
        if calls["count"] >= runner_module.EVIDENCE_BATCH_RECORDS + 5:
            raise sqlite3.OperationalError("injected write failure")
        return put(self, evidence, **kwargs)

    monkeypatch.setattr(EvidenceStore, "put", failing_put)
    failed = fixture.run()
    assert failed.status is ImportStatus.FAILED
    committed = fixture.evidence.count()
    # A bounded batch committed; the batch containing the injected failure
    # left neither rows nor cursor. The 200 ms limit may flush before the
    # record-count limit on a loaded machine, so its exact size is not fixed.
    assert 0 < committed < runner_module.EVIDENCE_BATCH_RECORDS + 5
    monkeypatch.setattr(EvidenceStore, "put", put)
    rerun = fixture.run()
    # The failed job keeps its slot, so the rerun resumes it and its counts add up.
    assert rerun.job_id == failed.job_id
    assert rerun.status is ImportStatus.COMPLETED
    assert (rerun.stored, rerun.merged) == (total, 0)
    assert fixture.evidence.count() == total


def test_live_and_history_both_read_the_most_recently_modified_file_first(tmp_path):
    fixture = Source(tmp_path)
    fixture.conversation("a-old", ["old text"], mtime=OLD_MTIME)
    fixture.conversation("z-recent", ["recent text"], mtime=RECENT_MTIME)

    async def texts():
        return [
            event.evidence.verbatim
            async for event in fixture.adapter().scan(ScanOptions())
            if isinstance(event, ScannedEvidence)
        ]

    assert asyncio.run(texts()) == ["recent text", "old text"]


def test_history_import_through_the_api_does_not_capture_a_snapshot(tmp_path, monkeypatch):
    async def scenario():
        app = upload_app(tmp_path, monkeypatch)
        root = app.state.settings.source_home / ".claude/projects/project"
        root.mkdir(parents=True)
        (root / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "read in place"}}) + "\n"
        )
        async with upload_client(app) as client:
            found = await client.post("/api/v1/sources/claude-code/location")
            assert found.status_code == 200, found.text
            connected = await client.post(
                "/api/v1/sources/connect",
                json={
                    "source_ids": ["claude-code"],
                    "source_roots": {"claude-code": found.json()["root_id"]},
                    "request_id": str(uuid4()),
                    "enable_sync": True,
                },
            )
            assert connected.status_code == 200, connected.text
            job_id = connected.json()["jobs"][0]["job_id"]
            job = await app.state.import_supervisor.wait(job_id)
            assert job.status is ImportStatus.COMPLETED and job.stored == 1
            snapshots = app.state.settings.data_dir / "import-snapshots"
            assert not (snapshots / job_id).exists()

    asyncio.run(scenario())


def test_startup_reopens_a_history_whose_snapshot_was_cancelled(tmp_path):
    jobs = ImportJobStore(tmp_path / "core.sqlite3")
    job = jobs.create(user_id="local", source_id="cursor")
    jobs.claim(job.job_id)
    for reason in ("snapshot_cancelled", "snapshot_incomplete"):
        with jobs._connect(writing=True) as connection:
            connection.execute(
                "INSERT INTO import_issues (job_id, kind, reason, created_at) "
                "VALUES (?, 'error', ?, '2026-09-24T00:00:00+00:00')",
                (job.job_id, reason),
            )
    jobs.transition(job.job_id, ImportStatus.FAILED)
    leftover = tmp_path / "import-snapshots" / job.job_id
    leftover.mkdir(parents=True)
    (leftover / "attempt").write_text("interrupted")

    opened = jobs.replace_never_published_snapshot_failures()
    assert len(opened) == 1 and opened[0].status is ImportStatus.PENDING
    assert jobs.require(job.job_id).status is ImportStatus.CANCELLED
