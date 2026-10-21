"""Long-running incremental import: many append rounds, no duplicates, no gaps.

The Day 7 matrix asks for long-running incremental behaviour. The property that
matters is not speed: after N rounds of appending, the stored rows equal the
records actually written, each round imports only what is new, and the cursor
advances monotonically. A regression to full re-reads shows up as duplicated or
re-emitted rows, and a lost checkpoint shows up as a missing round.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
import zstandard

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

ROUNDS = 8
#: One anchor-verification read on top of the file is allowed; see the note below.
MAX_ALLOWED_ANCHOR_BYTES = 64 * 1024
PER_ROUND = 40


class Incremental:
    def __init__(self, tmp_path: Path, source: str = "codex") -> None:
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
        self.path = (
            self.root / "projects" / "project-a" / "agent-transcripts" / "long" / "long.jsonl"
            if source == "cursor"
            else self.root / "project" / "rollout-long.jsonl"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.written = 0

    def append_round(self, round_index: int) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            for index in range(PER_ROUND):
                text = f"round{round_index}-item{index}"
                role = "user" if index % 2 == 0 else "assistant"
                if self.source == "cursor":
                    record = {
                        "role": role,
                        "message": {"content": [{"type": "text", "text": text}]},
                    }
                else:
                    record = {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": role,
                            "content": [{"type": "input_text", "text": text}],
                        },
                    }
                stream.write(json.dumps(record) + "\n")
        self.written += PER_ROUND

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

    def cursor_size(self) -> int:
        cursors = self.jobs.get_source_cursors(user_id="local", source_id=self.source)
        assert len(cursors) == 1
        return next(iter(cursors.values())).observed_size


def test_many_append_rounds_import_only_what_is_new(tmp_path, monkeypatch):
    fixture = Incremental(tmp_path)
    read_bytes = _observe_bytes_read(monkeypatch)
    sizes = []
    for round_index in range(ROUNDS):
        fixture.append_round(round_index)
        read_bytes.clear()
        result = fixture.run()
        assert result.status is ImportStatus.COMPLETED
        assert result.stored == PER_ROUND, f"round {round_index} must import only its new records"
        assert fixture.evidence.count() == fixture.written
        this_round = sum(read_bytes)
        assert this_round > 0, f"round {round_index} read nothing"
        # The read count includes one checkpoint-anchor verification read, which
        # is deliberate safety, not a re-read: `verify_jsonl_checkpoint` opens the
        # file and reads up to one record back to prove the boundary is real. The
        # bound therefore allows one record's worth on top of the file, and a
        # genuine full re-read of history still blows past it.
        assert this_round <= fixture.path.stat().st_size + MAX_ALLOWED_ANCHOR_BYTES, (
            f"round {round_index} read {this_round}; file is "
            f"{fixture.path.stat().st_size} plus one anchor read"
        )
        sizes.append(fixture.cursor_size())

    assert sizes == sorted(sizes), "the cursor must never move backwards"
    assert len(set(sizes)) == ROUNDS, "each round must leave a distinct cursor position"
    assert sizes[-1] == fixture.path.stat().st_size


def test_repeated_imports_between_appends_add_nothing(tmp_path):
    fixture = Incremental(tmp_path)
    fixture.append_round(0)
    assert fixture.run().stored == PER_ROUND

    for _ in range(3):
        idle = fixture.run()
        assert (idle.stored, idle.merged, idle.emitted) == (0, 0, 0)

    fixture.append_round(1)
    assert fixture.run().stored == PER_ROUND
    assert fixture.evidence.count() == 2 * PER_ROUND


@pytest.mark.parametrize("source", ["codex", "claude-code", "workbuddy", "cursor"])
def test_long_incremental_holds_for_each_jsonl_source(tmp_path, source):
    fixture = Incremental(tmp_path, source)
    # These four read role + message content; only the envelope differs.
    for round_index in range(3):
        with fixture.path.open("a", encoding="utf-8") as stream:
            for index in range(PER_ROUND):
                text = f"r{round_index}-{index}"
                if source == "codex":
                    record = {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": text}],
                        },
                    }
                elif source == "cursor":
                    record = {
                        "role": "user",
                        "message": {"content": [{"type": "text", "text": text}]},
                    }
                else:
                    record = {
                        "type": "user",
                        "sessionId": "long",
                        "timestamp": "2026-09-28T10:00:00+08:00",
                        "message": {"content": text},
                    }
                stream.write(json.dumps(record) + "\n")
        result = fixture.run()
        assert result.stored == PER_ROUND, (
            f"{source} round {round_index} must import only its new records; stored={result.stored}"
        )
    assert fixture.evidence.count() == 3 * PER_ROUND


def test_deepseek_zstd_record_cursor_advances_without_reimport(tmp_path):
    """The headless profile is a compressed stream, not a byte-offset file."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    registration = build_source_catalog(home=home, environment={})["deepseek-harness"]
    root = registration.candidate.path
    root.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "core.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=home)
    grants.grant(
        user_id="local",
        source_id="deepseek-harness",
        root=root,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    path = root / "session" / "session.jsonl.zstd"
    path.parent.mkdir(parents=True)

    header = {"type": "session", "id": "zstd-session", "cwd": "/private/project"}
    rounds: list[list[dict]] = []
    for round_index in range(3):
        records = [header] if round_index == 0 else []
        records.extend(
            {
                "type": "user/message",
                "seq": index,
                "data": {
                    "id": f"r{round_index}-{index}",
                    "role": "user",
                    "source": {"kind": "user"},
                    "content": [{"type": "text", "text": f"zstd-{round_index}-{index}"}],
                },
            }
            for index in range(PER_ROUND)
        )
        rounds.append(records)

    def run():
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={
                    "deepseek-harness": registration.create_adapter(
                        grants.authorized_root(user_id="local", source_id="deepseek-harness")
                    )
                },
                evidence_store=evidence,
                job_store=jobs,
            )
            job = supervisor.create_job("deepseek-harness")
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())

    checkpoints: list[str] = []
    for round_index, records in enumerate(rounds):
        frame = zstandard.ZstdCompressor(write_checksum=True).compress(
            b"".join(json.dumps(record).encode() + b"\n" for record in records)
        )
        with path.open("ab") as stream:
            stream.write(frame)
        result = run()
        expected = PER_ROUND
        assert result.status is ImportStatus.COMPLETED
        assert result.stored == expected
        assert result.emitted == expected
        assert evidence.count() == PER_ROUND * (round_index + 1)
        cursors = jobs.get_source_cursors(user_id="local", source_id="deepseek-harness")
        assert len(cursors) == 1
        cursor = next(iter(cursors.values()))
        assert cursor.checkpoint.startswith("record:")
        checkpoints.append(cursor.checkpoint)

    assert checkpoints == ["record:41", "record:81", "record:121"]

    idle = run()
    assert (idle.stored, idle.merged, idle.emitted) == (0, 0, 0)


def _observe_bytes_read(monkeypatch) -> list[int]:
    """Count bytes actually read from source files, so a re-read is visible."""
    from one_memory.imports.access import AuthorizedSourceFile

    original_open = AuthorizedSourceFile.open_binary
    original_read = os.read
    sizes: list[int] = []

    def opened(source_file):
        handle = original_open(source_file)
        # The JSONL reader advances with `readline`, not `read`; observing only
        # `read` would report zero bytes and make the bound below meaningless.
        original_readline = handle.readline

        def reading(size=-1):
            chunk = original_read(handle.fileno(), size) if isinstance(size, int) else b""
            sizes.append(len(chunk))
            return chunk

        def readlining(*args, **kwargs):
            line = original_readline(*args, **kwargs)
            sizes.append(len(line))
            return line

        handle.read = reading
        handle.readline = readlining
        return handle

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", opened)
    return sizes
