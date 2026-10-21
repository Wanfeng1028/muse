"""Truncate, replace and rebuild, per source: no duplicates and no stale text.

The event matrix covers three JSONL sources. The matrix asks for every source.
The property is uniform: a file that shrank or was replaced is re-read rather
than appended to, nothing already stored is duplicated, and a rebuilt file with
the same name starts a fresh read without inventing a second copy.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore
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
        return root / "projects/acme/agent-transcripts/replace/matrix.jsonl"
    if source == "qwen-code":
        return root / "chats" / f"{'0' * 32}.jsonl"
    if source == "deepseek-harness":
        return root / "replace" / "session.jsonl"
    return root / "project" / "rollout-replace.jsonl"


def _write(path: Path, source: str, texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for text in texts:
            stream.write(json.dumps(_record(source, text)) + "\n")


@pytest.mark.parametrize("source", _jsonl_sources())
def test_a_truncated_file_is_reconciled_from_the_start(tmp_path, source, monkeypatch):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["kept one", "kept two", "dropped tail"])
    assert fixture.run().stored == 3

    # Shrink to the first two records: the tail is gone, so re-reading must not
    # resurrect it, and the kept rows must not be stored twice.
    _write(path, source, ["kept one", "kept two"])
    reads = _observe_bytes_read(monkeypatch)
    result = fixture.run()
    assert result.stored == 0, "truncation is not an append"
    assert fixture.evidence.count() == 3, "existing rows are kept exactly once"
    # Row counts alone cannot catch this: keeping the old checkpoint and treating
    # the shrink as an append produces identical counts (dedup absorbs it). Only
    # the read position shows the difference — a shrunk file is re-read from 0.
    assert sum(reads) >= path.stat().st_size, (
        f"a truncated file must be reconciled from the start; read {sum(reads)} of "
        f"{path.stat().st_size}"
    )


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


@pytest.mark.parametrize("source", _jsonl_sources())
def test_a_replaced_file_is_read_as_new_records(tmp_path, source):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["original one"])
    assert fixture.run().stored == 1

    _write(path, source, ["replacement one", "replacement two"])
    result = fixture.run()
    assert result.stored == 2, "a replaced file brings its new records"
    assert fixture.evidence.count() == 3


@pytest.mark.parametrize("source", _jsonl_sources())
def test_deleting_and_recreating_the_same_file_does_not_duplicate(tmp_path, source):
    fixture = Source(tmp_path, source)
    path = _path(fixture.root, source)
    _write(path, source, ["rebuilt text"])
    assert fixture.run().stored == 1

    path.unlink()
    _write(path, source, ["rebuilt text"])
    result = fixture.run()
    assert result.stored in (0, 1)
    assert fixture.evidence.count() == 1, "the same text must not become two rows"


def test_cursor_store_replaced_under_the_same_path_is_not_treated_as_unchanged(tmp_path):
    fixture = Source(tmp_path, "cursor")
    database = fixture.root / "chats/workspace/replaced/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)

    def write_store(text: str) -> None:
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-0", json.dumps({"role": "user", "content": text})),
        )
        connection.commit()
        connection.close()

    write_store("before replacement")
    assert fixture.run().stored == 1
    before = database.stat().st_ino

    replacement = database.with_suffix(".replacement")
    connection = sqlite3.connect(replacement)
    connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
    connection.execute(
        "INSERT INTO blobs VALUES (?, ?)",
        ("row-0", json.dumps({"role": "user", "content": "after replacement"})),
    )
    connection.commit()
    connection.close()
    replacement.replace(database)
    assert database.stat().st_ino != before

    replaced = fixture.run()
    assert replaced.status.name == "COMPLETED"
    assert (replaced.stored, replaced.revised) == (0, 1), (
        "a rebuilt store.db keeps the same message identity, so changed text is revised"
    )
    stored = [
        row[0] for row in sqlite3.connect(fixture.database).execute("SELECT verbatim FROM evidence")
    ]
    assert stored == ["after replacement"], "the old text must not remain as stale Evidence"
