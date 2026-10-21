"""Read-only and unreadable source files, per source.

The failure-injection matrix lists read-only files as a case. It was only
checked for Codex. Both behaviours must hold for every source: a read-only file
is still imported and never written to, and a file we cannot open is a visible
failure rather than a silent skip.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from one_memory.imports.access import (
    AuthorizedSourceFile,
    SourceAccessError,
    SourceAccessErrorCode,
)
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

PAUSED = {"openclaw"}


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


def _jsonl_sources() -> list[str]:
    catalog = build_source_catalog(home=Path.home(), environment={})
    return sorted(source for source in catalog if source not in PAUSED | {"hermes", "opencode"})


def _record(source: str, text: str) -> dict:
    if source == "codex":
        return {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
    if source == "cursor":
        return {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}
    if source == "pi":
        return {"type": "message", "id": text, "message": {"role": "user", "content": text}}
    if source == "deepseek-harness":
        return {
            "type": "user/message",
            "seq": 1,
            "data": {
                "id": text,
                "role": "user",
                "source": {"kind": "user"},
                "content": [{"type": "text", "text": text}],
            },
        }
    return {
        "type": "user",
        "sessionId": f"{source}-session",
        "timestamp": "2026-09-28T10:00:00+08:00",
        "message": {"content": text},
    }


def _path(root: Path, source: str) -> Path:
    if source == "cursor":
        return root / "projects/acme/agent-transcripts/perm/matrix.jsonl"
    if source == "qwen-code":
        return root / "chats" / f"{'0' * 32}.jsonl"
    if source == "deepseek-harness":
        return root / "perm" / "session.jsonl"
    return root / "project" / "rollout-perm.jsonl"


def _write(path: Path, source: str, texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for text in texts:
            stream.write(json.dumps(_record(source, text)) + "\n")


@pytest.mark.parametrize("source", _jsonl_sources())
def test_a_read_only_file_is_imported_without_being_written(tmp_path, source):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["readonly one", "readonly two"])
    before = path.stat()
    path.chmod(0o400)
    try:
        result = fixture.run()
    finally:
        path.chmod(0o600)
    assert result.status is ImportStatus.COMPLETED and result.stored == 2
    after = path.stat()
    assert (after.st_size, after.st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    ), "importing must never write to a source file"


@pytest.mark.parametrize("source", _jsonl_sources())
def test_an_unreadable_file_is_reported_and_keeps_earlier_rows(tmp_path, monkeypatch, source):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["first pass"])
    assert fixture.run().stored == 1
    _write(path, source, ["first pass", "new unreadable row"])

    original_open = AuthorizedSourceFile.open_binary

    def unavailable(source_file):
        if source_file.path == path:
            raise SourceAccessError(SourceAccessErrorCode.SOURCE_UNAVAILABLE)
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", unavailable)
    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert result.errors >= 1, "an unreadable file must be visible, not silently skipped"
    assert fixture.evidence.count() == 1, "already stored rows survive an unreadable file"


def test_importing_does_not_change_source_permissions(tmp_path):
    """The read-only case must leave the file's mode as the user set it."""
    fixture = Source(tmp_path, "codex")
    path = _path(fixture.root, "codex")
    _write(path, "codex", ["perm check"])
    path.chmod(0o440)
    try:
        fixture.run()
        assert (os.stat(path).st_mode & 0o777) == 0o440
    finally:
        path.chmod(0o600)


def test_cursor_store_import_does_not_write_the_source_database(tmp_path):
    """SQLite readers must not leave a journal, mode or mtime change behind."""
    import sqlite3

    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/session/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-1", json.dumps({"role": "user", "content": "sqlite untouched"})),
        )
        connection.commit()
    finally:
        connection.close()
    database.chmod(0o440)
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_mode & 0o777)
        for path in (
            database,
            database.with_name("store.db-wal"),
            database.with_name("store.db-shm"),
        )
        if path.exists()
    }
    result = fixture.run()
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_mode & 0o777)
        for path in (
            database,
            database.with_name("store.db-wal"),
            database.with_name("store.db-shm"),
        )
        if path.exists()
    }
    database.chmod(0o600)

    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 1
    assert after == before


def test_cursor_store_import_does_not_write_an_active_wal_shm(tmp_path):
    """A host-owned -shm must not be opened or silently rewritten."""
    import hashlib
    import sqlite3

    def fingerprint(path: Path) -> tuple[int, str, int]:
        payload = path.read_bytes()
        details = path.stat()
        return len(payload), hashlib.sha256(payload).hexdigest(), details.st_mtime_ns

    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/active/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    writer = sqlite3.connect(database, isolation_level=None)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        for index in range(3):
            writer.execute(
                "INSERT INTO blobs VALUES (?, ?)",
                (
                    f"row-{index}",
                    json.dumps({"role": "user", "content": f"live wal {index}"}),
                ),
            )
        wal = database.with_name("store.db-wal")
        shm = database.with_name("store.db-shm")
        assert wal.stat().st_size > 32 and shm.stat().st_size > 0
        before = {path.name: fingerprint(path) for path in (database, wal, shm)}
        before_shm = shm.read_bytes()

        result = fixture.run()

        after = {path.name: fingerprint(path) for path in (database, wal, shm)}
        after_shm = shm.read_bytes()
    finally:
        writer.close()

    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 3
    assert result.errors == 0
    assert after == before
    assert after_shm == before_shm, "importing a live WAL must not touch the host's -shm lock bytes"


def test_direct_sqlite_ro_read_changes_the_active_wal_shm_positive_control(tmp_path):
    """The test above is discriminating: a direct mode=ro read changes -shm."""
    import sqlite3

    database = tmp_path / "store.db"
    writer = sqlite3.connect(database, isolation_level=None)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        for index in range(3):
            writer.execute(
                "INSERT INTO blobs VALUES (?, ?)",
                (f"row-{index}", json.dumps({"role": "user", "content": f"live {index}"})),
            )
        writer.commit()

        shm = database.with_name("store.db-shm")
        before = shm.read_bytes()
        reader = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            reader.execute("PRAGMA query_only = ON")
            assert reader.execute("SELECT count(*) FROM blobs").fetchone() == (3,)
        finally:
            reader.close()
        after = shm.read_bytes()
    finally:
        writer.close()

    assert after != before, (
        "a direct read-only SQLite open must be observed changing the active -shm; "
        "otherwise the no-write assertion above is vacuous"
    )


def test_cursor_store_wal_symlink_is_rejected(tmp_path):
    """A sidecar swap must not make the reader follow a link outside the grant."""
    import sqlite3

    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/linked/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside-wal"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.commit()
    finally:
        connection.close()
    outside.write_bytes(b"not a wal")
    database.with_name("store.db-wal").symlink_to(outside)

    result = fixture.run()

    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 0
    assert outside.read_bytes() == b"not a wal"
