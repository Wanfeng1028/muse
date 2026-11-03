"""SQLite-backed sources: damage and unknown schema must be reported, not swallowed.

The JSONL sources have a damage matrix already. The SQLite-backed ones
(hermes `state.db`, opencode `opencode.db`) fail differently: a missing table or
a wrong column is a *schema* problem, and the contract says an unknown schema
returns a machine code instead of reading business rows. This asserts both:
the job completes, nothing invented lands, and the failure is visible.
"""

import asyncio
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


@pytest.mark.parametrize("source", ["hermes", "opencode"])
def test_a_damaged_database_does_not_invent_evidence(tmp_path, source):
    """A database that is not valid SQLite must not become silent success."""
    fixture = Source(tmp_path, source)
    name = "state.db" if source == "hermes" else "opencode.db"
    (fixture.root / name).write_bytes(b"this is not a sqlite database at all")

    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED, "one bad database must not fail the job"
    assert fixture.evidence.count() == 0, "nothing may be invented from a damaged file"
    # Mirrors the JSONL damage matrix: silence is the bug. A job that reports
    # success with no rows and no error hides a source that silently stopped
    # working, which is exactly the failure this matrix exists to catch.
    assert result.errors >= 1, "a damaged database must be reported, not swallowed"


@pytest.mark.parametrize("source", ["hermes", "opencode"])
def test_a_wrong_column_schema_is_not_read_as_conversation(tmp_path, source):
    """Right table name, wrong columns: unknown schema, so read nothing."""
    fixture = Source(tmp_path, source)
    name = "state.db" if source == "hermes" else "opencode.db"
    connection = sqlite3.connect(fixture.root / name)
    try:
        if source == "hermes":
            connection.executescript(
                """
                CREATE TABLE messages (id INTEGER PRIMARY KEY, surprise TEXT);
                INSERT INTO messages VALUES (1, 'SECRET_NOT_CONVERSATION');
                """
            )
        else:
            connection.executescript(
                """
                CREATE TABLE message (id TEXT PRIMARY KEY, surprise TEXT);
                CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, surprise TEXT);
                INSERT INTO message VALUES ('m', 'SECRET_NOT_CONVERSATION');
                INSERT INTO part VALUES ('p', 'm', 'SECRET_NOT_CONVERSATION');
                """
            )
        connection.commit()
    finally:
        connection.close()

    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == 0, "an unknown schema must not become Evidence"
    assert result.errors >= 1, "an unknown schema must be visible, not silently skipped"


@pytest.mark.parametrize("source", ["hermes", "opencode"])
def test_a_repaired_database_imports_after_a_damaged_attempt(tmp_path, source):
    """Damage first, repair, then import: the good rows still arrive, once."""
    fixture = Source(tmp_path, source)
    name = "state.db" if source == "hermes" else "opencode.db"
    database = fixture.root / name
    database.write_bytes(b"broken")
    assert fixture.run().stored == 0

    _write_valid(database, source)
    result = fixture.run()
    assert result.stored == 1
    assert fixture.evidence.count() == 1
    # And a second run adds nothing: the cursor survived the damaged attempt.
    assert fixture.run().stored == 0


def _write_valid(path: Path, source: str) -> None:
    path.unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    try:
        if source == "hermes":
            connection.executescript(
                """
                CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, cwd TEXT);
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                    timestamp INTEGER, tool_calls TEXT, active INTEGER
                );
                INSERT INTO sessions VALUES ('h', 'cli', '/private/project');
                INSERT INTO messages VALUES (1, 'h', 'user', 'repaired', 1000, NULL, 1);
                """
            )
        else:
            connection.executescript(
                """
                CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT);
                CREATE TABLE message (
                    id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
                );
                CREATE TABLE part (
                    id TEXT PRIMARY KEY, message_id TEXT, time_created INTEGER, data TEXT
                );
                INSERT INTO session VALUES ('o', '/private/project');
                INSERT INTO message VALUES ('m', 'o', 1000, '{"role":"user"}');
                INSERT INTO part VALUES ('p', 'm', 1000, '{"type":"text","text":"repaired"}');
                """
            )
        connection.commit()
    finally:
        connection.close()


def _cursor_store_path(root: Path) -> Path:
    return root / "chats/workspace/damaged/store.db"


def test_cursor_store_damage_is_reported_without_inventing_evidence(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = _cursor_store_path(fixture.root)
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"this is not a sqlite database at all")

    result = fixture.run()

    assert result.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == 0
    assert result.errors >= 1, "a damaged Cursor store must be visible"


def test_cursor_store_wrong_schema_is_not_read_as_conversation(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = _cursor_store_path(fixture.root)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE surprise (value TEXT)")
        connection.execute("INSERT INTO surprise VALUES ('SECRET_NOT_CONVERSATION')")
        connection.commit()
    finally:
        connection.close()

    result = fixture.run()

    assert result.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == 0
    assert result.errors >= 1, "an unknown Cursor store schema must be visible"


def test_cursor_store_recovers_after_damage(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = _cursor_store_path(fixture.root)
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b"broken")
    assert fixture.run().stored == 0

    database.unlink()
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-0", '{"role":"user","content":"repaired cursor row"}'),
        )
        connection.commit()
    finally:
        connection.close()

    repaired = fixture.run()
    assert repaired.status is ImportStatus.COMPLETED
    assert repaired.stored == 1
    assert fixture.evidence.count() == 1
    assert fixture.run().stored == 0


def test_cursor_store_binary_blobs_are_skipped_without_failing_the_job(tmp_path):
    """Real store.db files keep protobuf/tool blobs beside JSON message blobs."""
    fixture = Source(tmp_path, "cursor")
    database = _cursor_store_path(fixture.root)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data BLOB)")
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("binary", sqlite3.Binary(b"\xff\xfe\x00not-json")),
        )
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("message", b'{"role":"user","content":"after binary blob"}'),
        )
        connection.commit()
    finally:
        connection.close()

    result = fixture.run()

    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 1
    assert result.errors == 0
    assert fixture.evidence.count() == 1
