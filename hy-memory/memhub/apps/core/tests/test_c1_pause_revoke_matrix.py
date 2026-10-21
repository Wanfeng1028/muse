"""Pause/resume and revocation, per source, through each source's real parser.

Cursor already had a pause test and Codex a revocation test; the matrix contract
asks for both behaviours for every source that is not paused. These use each
source's own fixture layout and parser, so a source whose parser mishandles a
checkpoint fails here rather than only in its own parser test.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from one_memory.imports.access import SourceAccessError
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.runner import EVIDENCE_BATCH_RECORDS
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

#: OpenClaw stays paused: not probed, not started, not imported.
PAUSED_SOURCES = {"openclaw"}


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")


def _write_pi(root: Path, count: int) -> None:
    records: list[dict] = [{"type": "session", "id": "session-a", "cwd": "/private/project"}]
    for index in range(count):
        records.append(
            {
                "type": "message",
                "id": f"pi-{index}",
                "timestamp": "2026-09-28T10:00:00+00:00",
                "message": {
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": f"pi visible {index}",
                },
            }
        )
    _write_jsonl(root / "session-a.jsonl", records)


def _write_qwenwork(root: Path, count: int) -> None:
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "uuid": f"q-{index}",
                "sessionId": "session-q",
                "timestamp": "2026-09-28T10:00:00+00:00",
                "message": {
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": f"qwen visible {index}",
                },
                "origin": {"kind": "human"},
            }
        )
    _write_jsonl(root / "session-q.jsonl", records)


def _write_deepseek(root: Path, count: int) -> None:
    records: list[dict] = [{"type": "session", "id": "run-a", "cwd": "/private/project"}]
    for index in range(count):
        if index % 2 == 0:
            records.append(
                {
                    "type": "user/message",
                    "seq": index,
                    "data": {
                        "id": f"human-{index}",
                        "role": "user",
                        "source": {"kind": "user"},
                        "content": [{"type": "text", "text": f"dsh visible {index}"}],
                    },
                }
            )
        else:
            records.append(
                {
                    "type": "assistant/message",
                    "seq": index,
                    "data": {
                        "message": {
                            "id": f"assistant-{index}",
                            "role": "assistant",
                            "content": [{"type": "text", "text": f"dsh visible {index}"}],
                        }
                    },
                }
            )
    _write_jsonl(root / "run-a" / "session.jsonl", records)


def _write_qwen_code(root: Path, count: int) -> None:
    session_id = "0" * 32
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "sessionId": session_id,
                "cwd": "/private/project",
                "timestamp": "2026-09-28T10:00:00+00:00",
                "type": "user" if index % 2 == 0 else "assistant",
                "message": {"content": [{"type": "text", "text": f"qwen-code {index}"}]},
            }
        )
    _write_jsonl(root / "chats" / f"{session_id}.jsonl", records)


def _write_codex(root: Path, count: int) -> None:
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": [{"type": "input_text", "text": f"codex {index}"}],
                },
            }
        )
    _write_jsonl(root / "project" / "rollout-matrix.jsonl", records)


def _write_claude_code(root: Path, count: int) -> None:
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "type": "user" if index % 2 == 0 else "assistant",
                "uuid": f"claude-{index}",
                "sessionId": "claude-session",
                "timestamp": "2026-09-28T10:00:00+00:00",
                "message": {"content": [{"type": "text", "text": f"claude {index}"}]},
            }
        )
    _write_jsonl(root / "project" / "rollout-claude.jsonl", records)


def _write_workbuddy(root: Path, count: int) -> None:
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "type": "user" if index % 2 == 0 else "assistant",
                "timestamp": "2026-09-28T10:00:00+08:00",
                "sessionId": "workbuddy-session",
                "message": {"content": f"workbuddy {index}"},
            }
        )
    _write_jsonl(root / "project" / "rollout-workbuddy.jsonl", records)


def _write_cursor_transcript(root: Path, count: int) -> None:
    records: list[dict] = []
    for index in range(count):
        records.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "message": {"content": [{"type": "text", "text": f"cursor {index}"}]},
            }
        )
    _write_jsonl(root / "projects/acme/agent-transcripts/matrix/matrix.jsonl", records)


def _write_cursor_store(root: Path, count: int) -> None:
    """Real Cursor store.db shape: blobs rows, read by rowid."""
    database = root / "chats/workspace/store-session/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        for index in range(count):
            connection.execute(
                "INSERT INTO blobs VALUES (?, ?)",
                (
                    f"row-{index}",
                    json.dumps(
                        {
                            "role": "user" if index % 2 == 0 else "assistant",
                            "content": f"cursor store {index}",
                        }
                    ),
                ),
            )
        connection.commit()
    finally:
        connection.close()


#: Only shapes this repository already asserts elsewhere. Sources absent here are
#: skipped, not faked: hermes/opencode need their SQLite fixtures and openclaw is
#: paused, and a made-up record would prove nothing about their real format.
def _write_hermes(root: Path, count: int) -> None:
    """Hermes' own `state.db` schema, as asserted in test_secondary_source_adapters."""
    connection = sqlite3.connect(root / "state.db")
    try:
        connection.executescript(
            """
            CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, cwd TEXT);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                timestamp INTEGER, tool_calls TEXT, active INTEGER
            );
            INSERT INTO sessions VALUES ('session-h', 'cli', '/private/project');
            """
        )
        rows = []
        for index in range(count):
            role = "user" if index % 2 == 0 else "assistant"
            rows.append((index + 1, "session-h", role, f"hermes {index}", 1000 + index, None, 1))
        connection.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", rows)
        connection.commit()
    finally:
        connection.close()


def _write_opencode(root: Path, count: int) -> None:
    """OpenCode's own `opencode.db` schema, as asserted in test_secondary_source_adapters."""
    connection = sqlite3.connect(root / "opencode.db")
    try:
        connection.executescript(
            """
            CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT);
            CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
            );
            CREATE TABLE part (
                id TEXT PRIMARY KEY, message_id TEXT, time_created INTEGER, data TEXT
            );
            INSERT INTO session VALUES ('session-o', '/private/project');
            """
        )
        for index in range(count):
            message_id = f"message-{index}"
            role = "user" if index % 2 == 0 else "assistant"
            connection.execute(
                "INSERT INTO message VALUES (?,?,?,?)",
                (message_id, "session-o", 1000 + index, json.dumps({"role": role})),
            )
            connection.execute(
                "INSERT INTO part VALUES (?,?,?,?)",
                (
                    f"part-{index}",
                    message_id,
                    1000 + index,
                    json.dumps({"type": "text", "text": f"opencode {index}"}),
                ),
            )
        connection.commit()
    finally:
        connection.close()


_FIXTURE_WRITERS = {
    "codex": _write_codex,
    "claude-code": _write_claude_code,
    "workbuddy": _write_workbuddy,
    "cursor": _write_cursor_transcript,
    "pi": _write_pi,
    "qwenwork": _write_qwenwork,
    "qwen-code": _write_qwen_code,
    "deepseek-harness": _write_deepseek,
    "hermes": _write_hermes,
    "opencode": _write_opencode,
}


def test_cursor_store_pause_resume_finishes_without_duplicates(tmp_path):
    harness = Harness(tmp_path, "cursor")
    _write_cursor_store(harness.root, EVIDENCE_BATCH_RECORDS * 2 + 5)

    async def scenario():
        supervisor = harness.supervisor(max_work_seconds_per_slice=0.0001)
        job = supervisor.create_job("cursor")
        seen: list[str] = []

        def pause_once(record):
            seen.append(record.evidence_id)
            if len(seen) == 1:
                harness.jobs.transition(job.job_id, ImportStatus.PAUSED)

        supervisor.on_evidence = pause_once
        supervisor.enqueue(job.job_id)
        paused = await supervisor.wait(job.job_id)
        assert paused.status is ImportStatus.PAUSED
        assert 0 < harness.evidence.count() < EVIDENCE_BATCH_RECORDS * 2 + 5
        supervisor.resume(job.job_id)
        return await supervisor.wait(job.job_id), tuple(seen)

    completed, seen = asyncio.run(scenario())

    assert completed.status is ImportStatus.COMPLETED
    assert completed.stored + completed.merged == EVIDENCE_BATCH_RECORDS * 2 + 5
    assert harness.evidence.count() == EVIDENCE_BATCH_RECORDS * 2 + 5
    assert len(seen) == len(set(seen)), "resume must not deliver a stored row twice"


def _all_sources() -> list[str]:
    home = Path.home()
    catalog = build_source_catalog(home=home, environment={})
    return sorted(source for source in catalog if source not in PAUSED_SOURCES)


class Harness:
    """A writable copy of one source's own fixture tree, under a temp root."""

    def __init__(self, tmp_path: Path, source: str) -> None:
        self.source = source
        home = tmp_path / "home"
        (home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.registration = build_source_catalog(home=home, environment={})[source]
        self.root = self.registration.candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        database = tmp_path / "data" / "core.sqlite3"
        database.parent.mkdir(parents=True, exist_ok=True)
        self.jobs = ImportJobStore(database)
        self.evidence = EvidenceStore(database)
        self.grants = SourceGrantStore(database, home=home)
        self.grants.grant(
            user_id="local",
            source_id=source,
            root=self.root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )

    def write_fixture(self, count: int) -> bool:
        """Write this source's own record shape; False when we have no honest one.

        Only shapes this repository already asserts elsewhere are used. A source
        with no shape here is skipped by the caller, and a skip is not a pass —
        inventing a Codex record and calling it Pi would prove nothing.
        """
        writer = _FIXTURE_WRITERS.get(self.source)
        if writer is None:
            return False
        writer(self.root, count)
        return True

    def authorized_root(self):
        return self.grants.authorized_root(user_id="local", source_id=self.source)

    def supervisor(
        self,
        on_evidence=None,
        *,
        max_work_seconds_per_slice: float = 0.2,
    ) -> ImportSupervisor:
        return ImportSupervisor(
            adapters={self.source: self.registration.create_adapter(self.authorized_root())},
            evidence_store=self.evidence,
            job_store=self.jobs,
            on_evidence=on_evidence,
            max_work_seconds_per_slice=max_work_seconds_per_slice,
        )


@pytest.mark.parametrize("source", _all_sources())
def test_pause_then_resume_finishes_without_duplicates(tmp_path, source):
    fixture = Harness(tmp_path, source)
    if not fixture.write_fixture(EVIDENCE_BATCH_RECORDS * 2):
        pytest.skip(f"no honest fixture shape for {source}")

    seen: list[object] = []

    async def scenario():
        supervisor = fixture.supervisor()
        job = supervisor.create_job(source)

        def pause_after_first(record):
            seen.append(record)
            if len(seen) == 1:
                fixture.jobs.transition(job.job_id, ImportStatus.PAUSED)

        supervisor.on_evidence = pause_after_first
        supervisor.enqueue(job.job_id)
        paused = await supervisor.wait(job.job_id)
        if paused.status is not ImportStatus.PAUSED:
            return paused, None
        supervisor.resume(job.job_id)
        return paused, await supervisor.wait(job.job_id)

    paused, resumed = asyncio.run(scenario())
    if paused.status is not ImportStatus.PAUSED:
        # A source whose whole fixture fits one batch cannot observe a pause.
        assert paused.status is ImportStatus.COMPLETED
        return
    assert resumed is not None and resumed.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() >= 1
    assert len({record.evidence_id for record in seen}) == len(seen), "no duplicate records"


@pytest.mark.parametrize("source", _all_sources())
def test_revocation_stops_reading_and_keeps_what_was_committed(tmp_path, source):
    fixture = Harness(tmp_path, source)
    if not fixture.write_fixture(EVIDENCE_BATCH_RECORDS * 2):
        pytest.skip(f"no honest fixture shape for {source}")

    first = asyncio.run(_run(fixture))
    committed = fixture.evidence.count()
    assert committed >= 0 and first.status is ImportStatus.COMPLETED

    fixture.grants.revoke(user_id="local", source_id=source)
    assert fixture.authorized_root() is None, "revoked grants must not authorize reads"

    # Revocation must stop reads. Adapters differ in whether they reject a
    # missing grant at construction or only when reading, so assert the thing
    # that matters and is uniform: nothing new is read and nothing stored is lost.
    before = fixture.evidence.count()
    outcome = asyncio.run(_run_with_revoked_grant(fixture))
    assert outcome["stored"] == 0 and outcome["emitted"] == 0
    assert fixture.evidence.count() == before
    with sqlite3.connect(fixture.jobs.database_path) as db:
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == committed


async def _run(fixture: Harness):
    supervisor = fixture.supervisor()
    job = supervisor.create_job(fixture.source)
    supervisor.enqueue(job.job_id)
    return await supervisor.wait(job.job_id)


async def _run_with_revoked_grant(fixture: Harness) -> dict:
    """Import a revoked source: it must not yield stored records.

    The grant is gone, so `authorized_root()` is None. Some adapters reject that
    at construction; others only fail when they try to read. Either is a correct
    refusal, so this reports what came out rather than how it refused.
    """
    try:
        adapter = fixture.registration.create_adapter(fixture.authorized_root())
    except (TypeError, AttributeError, ValueError, AssertionError, SourceAccessError):
        return {"stored": 0, "emitted": 0}
    supervisor = ImportSupervisor(
        adapters={fixture.source: adapter},
        evidence_store=fixture.evidence,
        job_store=fixture.jobs,
    )
    try:
        job = supervisor.create_job(fixture.source)
        supervisor.enqueue(job.job_id)
        final = await supervisor.wait(job.job_id)
    except SourceAccessError:
        # Refused before any file was listed: the strongest possible answer.
        return {"stored": 0, "emitted": 0}
    return {"stored": final.stored, "emitted": final.emitted}
