"""C1 owned matrix: existing history, new file, append, truncate/replace, restart, revoke.

Every source writes its own real record shape (Codex response_item/payload, Cursor
transcript, Claude Code user/assistant, WorkBuddy wrapped user query). Discovery
directories are only fixtures; a discovered-but-empty install directory is asserted
to stay unimported. Bytes read are counted so "incremental" is falsifiable: a
regression to full re-read raises the count instead of passing silently.
"""

import asyncio
import json
import os
import sqlite3
from pathlib import Path

import pytest

from one_memory.imports.access import AuthorizedSourceFile
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

OLD_MTIME = 1_600_000_000_000_000_000


class MatrixSource:
    def __init__(self, tmp_path: Path, source: str) -> None:
        self.source = source
        home = tmp_path / "home"
        (home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.registration = build_source_catalog(
            home=home, environment={}, import_root=tmp_path / "exports"
        )[source]
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

    def path(self, name: str) -> Path:
        if self.source == "cursor":
            return self.root / f"projects/acme/agent-transcripts/{name}/{name}.jsonl"
        return self.root / f"project/rollout-{name}.jsonl"

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
        if self.source == "workbuddy":
            return {
                "type": role,
                "timestamp": "2026-09-28T10:00:00+08:00",
                "message": {"content": text},
            }
        return {"type": role, "message": {"content": text}}

    def write(self, name: str, texts: list[str], *, mtime: int | None = None) -> Path:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            for text in texts:
                stream.write(json.dumps(self.record(text)) + "\n")
        if mtime is not None:
            os.utime(path, ns=(mtime, mtime))
        return path

    def authorized_root(self):
        return self.grants.authorized_root(user_id="local", source_id=self.source)

    def run(self) -> object:
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={self.source: self.registration.create_adapter(self.authorized_root())},
                evidence_store=self.evidence,
                job_store=self.jobs,
            )
            job = supervisor.create_job(self.source)
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())


def observe_bytes_read(monkeypatch) -> list[int]:
    read_sizes: list[int] = []
    original_open = AuthorizedSourceFile.open_binary
    original_read = os.read

    def opened(source_file):
        handle = original_open(source_file)
        original_close = handle.close

        def reading(size):
            chunk = original_read(handle.fileno(), size)
            read_sizes.append(len(chunk))
            return chunk

        def closing():
            original_close()

        handle.read = reading
        handle.close = closing
        return handle

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", opened)
    return read_sizes


@pytest.mark.parametrize("source", ["workbuddy", "cursor", "codex", "claude-code"])
def test_existing_history_then_append_then_unchanged_is_zero(tmp_path, monkeypatch, source):
    fixture = MatrixSource(tmp_path, source)
    target = fixture.write("session", ["existing one", "existing two"], mtime=OLD_MTIME)
    fixture.write("other", ["other one"], mtime=OLD_MTIME)

    reads = observe_bytes_read(monkeypatch)
    history = fixture.run()
    assert history.status is ImportStatus.COMPLETED and history.stored == 3
    assert fixture.evidence.count() == 3

    reads.clear()
    unchanged = fixture.run()
    assert (unchanged.stored, unchanged.emitted) == (0, 0)
    assert reads == [], "unchanged files must not be opened or read again"

    reads.clear()
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(fixture.record("appended later")) + "\n")
    appended = fixture.run()
    assert appended.stored == 1
    assert fixture.evidence.count() == 4
    total = target.stat().st_size
    assert 0 < sum(reads) < total, (
        f"append must read the tail, not the whole file: read {sum(reads)} of {total}"
    )
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id=source)
    assert cursors, "an incremental import must leave a per-file cursor behind"
    assert any(cursor.observed_size == total for cursor in cursors.values()), (
        f"the appended file's cursor must reach {total}; got "
        f"{[cursor.observed_size for cursor in cursors.values()]}"
    )


@pytest.mark.parametrize("source", ["workbuddy", "codex", "claude-code"])
def test_truncate_and_replace_never_duplicate_and_never_preserve_stale_text(tmp_path, source):
    fixture = MatrixSource(tmp_path, source)
    path = fixture.write("session", ["kept one", "kept two", "dropped tail"])
    assert fixture.run().stored == 3

    body = "".join(json.dumps(fixture.record(text)) + "\n" for text in ["kept one", "kept two"])
    path.write_text(body, encoding="utf-8")
    truncated = fixture.run()
    assert truncated.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == 3, "truncation is not an append of new evidence"

    replacement = path.with_suffix(".tmp")
    replacement.write_text(
        "".join(
            json.dumps(fixture.record(text)) + "\n" for text in ["replaced one", "replaced two"]
        ),
        encoding="utf-8",
    )
    os.replace(replacement, path)
    replaced = fixture.run()
    assert replaced.stored == 2
    assert fixture.evidence.count() == 5
    stored = {record.verbatim for record in fixture.evidence.list_extractable(limit=50)}
    assert stored == {
        "kept one",
        "kept two",
        "dropped tail",
        "replaced one",
        "replaced two",
    }


def test_new_file_after_first_import_is_found_without_a_rescan(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("first", ["first text"])
    assert fixture.run().stored == 1
    fixture.write("second", ["second text"])
    later = fixture.run()
    assert later.stored == 1
    assert fixture.evidence.count() == 2


def test_a_discovered_but_empty_install_directory_imports_nothing(tmp_path):
    fixture = MatrixSource(tmp_path, "cursor")
    (fixture.root / "projects/acme/agent-transcripts/empty-install").mkdir(parents=True)
    (fixture.root / "projects/acme/agent-transcripts/empty-install/state.vscdb").write_bytes(b"")
    discovered = fixture.run()
    assert discovered.status is ImportStatus.COMPLETED
    assert (discovered.stored, fixture.evidence.count()) == (0, 0)


def test_restart_after_completion_and_after_revocation(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("session", ["alpha"], mtime=OLD_MTIME)
    assert fixture.run().stored == 1

    reopened = MatrixSource.__new__(MatrixSource)
    reopened.source = "codex"
    reopened.root = fixture.root
    reopened.data = tmp_path / "data"
    reopened.jobs = ImportJobStore(tmp_path / "data" / "core.sqlite3")
    reopened.evidence = EvidenceStore(tmp_path / "data" / "core.sqlite3")
    reopened.grants = SourceGrantStore(tmp_path / "data" / "core.sqlite3", home=tmp_path / "home")
    reopened.registration = fixture.registration
    assert reopened.run().stored == 0, "a restart must not re-import committed history"
    assert reopened.evidence.count() == 1

    reopened.grants.revoke(user_id="local", source_id="codex")
    assert reopened.authorized_root() is None, (
        "revocation survives restart and never silently restores a read grant"
    )
    with sqlite3.connect(tmp_path / "data" / "core.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1
