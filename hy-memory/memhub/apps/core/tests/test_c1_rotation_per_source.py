"""File rotation, per source: the rotated-away name must not be read anymore.

Rotation was only covered for Codex in the failure-injection suite. Real hosts
rotate: the live file is renamed (for example `x.jsonl` -> `x.jsonl.1`) and a new
file takes its name. Two things must hold for every source:

1. the rotated-away copy is not imported again under its new name, and
2. the new file with the live name is imported from the start, exactly once.
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
        return root / "projects/acme/agent-transcripts/rot/matrix.jsonl"
    if source == "qwen-code":
        return root / "chats" / f"{'0' * 32}.jsonl"
    if source == "deepseek-harness":
        return root / "rot" / "session.jsonl"
    return root / "project" / "rollout-rot.jsonl"


def _write(path: Path, source: str, texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for text in texts:
            stream.write(json.dumps(_record(source, text)) + "\n")


@pytest.mark.parametrize("source", _jsonl_sources())
def test_the_rotated_away_copy_is_not_imported_again(tmp_path, source, monkeypatch):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["before rotation"])
    assert fixture.run().stored == 1

    # The host renames the live file away; the same bytes now sit under a new name.
    rotated = path.with_name(path.name + ".1")
    path.rename(rotated)
    _write(path, source, ["after rotation"])

    reads = _observe_bytes_read(monkeypatch)
    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 1, "only the new file's record is new"
    assert fixture.evidence.count() == 2
    # Counts alone cannot catch a lost per-file cursor: re-reading the rotated
    # copy produces rows that dedup absorbs, so stored/total look identical.
    # The read volume is what differs — a rotation must not re-read both files.
    assert sum(reads) < rotated.stat().st_size + path.stat().st_size, (
        f"rotation re-read both files: {sum(reads)} of "
        f"{rotated.stat().st_size + path.stat().st_size}"
    )

    stored = _stored(fixture)
    assert {row["verbatim"] for row in stored} == {"before rotation", "after rotation"}
    # A second run must be silent: nothing new anywhere.
    assert fixture.run().stored == 0

    # Direct property check. The rotated-away copy is NOT discovered: each source
    # only finds files matching its own suffix/path rule, so a host's archived
    # `.1` copy never becomes a second conversation. That is the safer behaviour,
    # and it is why only one cursor exists here.
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id=source)
    assert len(cursors) == 1, (
        f"a rotated-away copy must not become a second source file, got {len(cursors)}"
    )
    assert next(iter(cursors.values())).observed_size == path.stat().st_size
    assert rotated.exists(), "the rotated copy still exists; it is simply not imported"


def test_cursor_store_moved_to_a_new_session_directory_does_not_duplicate(tmp_path):
    """Moving a store.db changes its path, not the conversation's identity."""
    fixture = Source(tmp_path, "cursor")
    source_database = fixture.root / "chats/workspace/original/store.db"
    source_database.parent.mkdir(parents=True, exist_ok=True)
    agent_id = "stable-cursor-agent"
    connection = sqlite3.connect(source_database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        connection.execute(
            "INSERT INTO meta VALUES (?, ?)",
            ("0", json.dumps({"agentId": agent_id}).encode().hex()),
        )
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-0", json.dumps({"role": "user", "content": "moved store text"})),
        )
        connection.commit()
    finally:
        connection.close()
    assert fixture.run().stored == 1

    moved_database = fixture.root / "chats/workspace/moved/store.db"
    moved_database.parent.mkdir(parents=True, exist_ok=True)
    source_database.replace(moved_database)
    again = fixture.run()

    assert again.stored == 0
    assert again.merged == 1
    assert fixture.evidence.count() == 1


def test_deepseek_session_directory_move_uses_the_header_id(tmp_path):
    """The harness header id is stable when its containing folder is renamed."""
    fixture = Source(tmp_path, "deepseek-harness")
    session_id = "session-stable"
    original = fixture.root / "original" / "session.jsonl"
    original.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "session", "id": session_id, "cwd": "/private/project"},
        {
            "type": "user/message",
            "seq": 1,
            "data": {
                "id": "message-1",
                "role": "user",
                "source": {"kind": "user"},
                "content": [{"type": "text", "text": "stable dsh text"}],
            },
        },
    ]
    original.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    assert fixture.run().stored == 1

    moved = fixture.root / "moved" / "session.jsonl"
    moved.parent.mkdir(parents=True, exist_ok=True)
    original.replace(moved)
    again = fixture.run()

    assert again.stored == 0
    assert again.merged == 1
    assert fixture.evidence.count() == 1


def _observe_bytes_read(monkeypatch) -> list[int]:
    from one_memory.imports.access import AuthorizedSourceFile

    original_open = AuthorizedSourceFile.open_binary
    sizes: list[int] = []

    def opened(source_file):
        handle = original_open(source_file)
        original_readline = handle.readline

        def readlining(*args, **kwargs):
            line = original_readline(*args, **kwargs)
            sizes.append(len(line))
            return line

        handle.readline = readlining
        return handle

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", opened)
    return sizes


def _stored(fixture) -> list[dict]:
    import sqlite3

    with sqlite3.connect(fixture.database) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT source_id, conversation_id, verbatim FROM evidence"
            )
        ]
