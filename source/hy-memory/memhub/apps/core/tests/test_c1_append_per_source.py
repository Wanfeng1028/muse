"""Append, per source, including the SQLite-backed ones.

The matrix asks for append behaviour for every source. JSONL sources append by
growing a file; the SQLite-backed ones append by gaining rows (hermes, opencode)
or WAL content (Cursor store). Those are different mechanisms, so a passing
JSONL append says nothing about them.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


class Source:
    def __init__(self, tmp_path: Path, source: str) -> None:
        self.source = source
        self.home = tmp_path / "home"
        (self.home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.catalog = build_source_catalog(home=self.home, environment={})
        self.root = self.catalog[source].candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = tmp_path / "core.sqlite3"
        self.jobs = ImportJobStore(self.database)
        self.evidence = EvidenceStore(self.database)
        self.grants = SourceGrantStore(self.database, home=self.home)
        self.grants.grant(
            user_id="local",
            source_id=source,
            root=self.root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )

    def run(self):
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={
                    self.source: self.catalog[self.source].create_adapter(
                        self.grants.authorized_root(user_id="local", source_id=self.source)
                    )
                },
                evidence_store=self.evidence,
                job_store=self.jobs,
            )
            job = supervisor.create_job(self.source)
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())


def _hermes(root: Path, rows: int, *, offset: int = 0) -> None:
    connection = sqlite3.connect(root / "state.db")
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, source TEXT, cwd TEXT);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                timestamp INTEGER, tool_calls TEXT, active INTEGER
            );
            INSERT OR IGNORE INTO sessions VALUES ('h', 'cli', '/private/project');
            """
        )
        connection.executemany(
            "INSERT INTO messages VALUES (?, 'h', 'user', ?, ?, NULL, 1)",
            [
                (offset + index + 1, f"hermes-{offset + index}", 1000 + offset + index)
                for index in range(rows)
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _opencode(root: Path, rows: int, *, offset: int = 0) -> None:
    connection = sqlite3.connect(root / "opencode.db")
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS session (id TEXT PRIMARY KEY, directory TEXT);
            CREATE TABLE IF NOT EXISTS message (
                id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
            );
            CREATE TABLE IF NOT EXISTS part (
                id TEXT PRIMARY KEY, message_id TEXT, time_created INTEGER, data TEXT
            );
            INSERT OR IGNORE INTO session VALUES ('o', '/private/project');
            """
        )
        for index in range(rows):
            key = offset + index
            connection.execute(
                "INSERT OR IGNORE INTO message VALUES (?, 'o', ?, ?)",
                (f"m{key}", 1000 + key, json.dumps({"role": "user"})),
            )
            connection.execute(
                "INSERT OR IGNORE INTO part VALUES (?, ?, ?, ?)",
                (
                    f"p{key}",
                    f"m{key}",
                    1000 + key,
                    json.dumps({"type": "text", "text": f"opencode-{key}"}),
                ),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize("source", ["hermes", "opencode"])
def test_sqlite_backed_sources_append_only_new_rows(tmp_path, source):
    fixture = Source(tmp_path, source)
    grow = _hermes if source == "hermes" else _opencode
    grow(fixture.root, 3)

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 3

    idle = fixture.run()
    assert (idle.stored, idle.merged, idle.emitted) == (0, 0, 0)

    grow(fixture.root, 3, offset=3)
    second = fixture.run()
    assert second.stored == 3, "only the new rows may arrive"
    assert fixture.evidence.count() == 6


def test_cursor_store_appends_from_its_write_ahead_log(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/session/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        for index in range(3):
            connection.execute(
                "INSERT INTO blobs VALUES (?, ?)",
                (f"row-{index}", json.dumps({"role": "user", "content": f"store {index}"})),
            )
    finally:
        connection.close()

    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 3

    idle = fixture.run()
    assert (idle.stored, idle.merged) == (0, 0)

    # Rows that exist only in the -wal still count as a change.
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-3", json.dumps({"role": "user", "content": "store 3"})),
        )
        assert database.with_name("store.db-wal").stat().st_size > 0
    finally:
        connection.close()

    second = fixture.run()
    assert second.stored == 1
    assert fixture.evidence.count() == 4


def test_cursor_store_append_skips_host_context_without_losing_later_rows(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/session/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    writer = sqlite3.connect(database, isolation_level=None)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        writer.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("user-0", json.dumps({"role": "user", "content": "first real request"})),
        )
        assert fixture.run().stored == 1

        # A real store append can contain only host context before the next
        # message. It must advance the cursor as a skip, not stall the stream.
        writer.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            (
                "host-1",
                json.dumps(
                    {
                        "role": "user",
                        "content": (
                            "<user_info>OS Version: darwin</user_info>\n"
                            "<dynamic_tools>host catalog</dynamic_tools>"
                        ),
                    }
                ),
            ),
        )
        writer.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("user-2", json.dumps({"role": "user", "content": "second real request"})),
        )
        appended = fixture.run()
    finally:
        writer.close()

    assert appended.status is ImportStatus.COMPLETED
    assert appended.stored == 1, "only the later real request may become Evidence"
    assert appended.skipped >= 1
    assert fixture.evidence.count() == 2
