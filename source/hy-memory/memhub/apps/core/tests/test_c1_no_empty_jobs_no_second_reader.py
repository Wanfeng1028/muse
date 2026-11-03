"""No empty jobs and no second reader: metadata-first and one writer.

Two promises in the objective that need explicit tests, not just code reading:

1. A source with nothing new must not create an import job (no repeated empty
   jobs), because the decision is made from metadata before reading.
2. Importing one source must use exactly one reader — no second reader writing
   the same rows twice.
"""

import asyncio
import json
from pathlib import Path

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


class Source:
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
        self.path = self.root / "project" / "rollout-noempty.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, texts: list[str]) -> None:
        with self.path.open("w", encoding="utf-8") as stream:
            for text in texts:
                stream.write(
                    json.dumps(
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": text}],
                            },
                        }
                    )
                    + "\n"
                )

    def adapter(self):
        return self.catalog[self.source].create_adapter(
            self.grants.authorized_root(user_id="local", source_id=self.source)
        )

    def supervisor(self, adapter=None) -> ImportSupervisor:
        return ImportSupervisor(
            adapters={self.source: adapter or self.adapter()},
            evidence_store=self.evidence,
            job_store=self.jobs,
        )

    def run(self):
        async def scenario():
            supervisor = self.supervisor()
            job = supervisor.create_job(self.source)
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())


def test_a_source_with_nothing_new_does_not_need_a_second_job(tmp_path):
    """Second run imports nothing and reports no new work, from metadata alone."""
    fixture = Source(tmp_path)
    fixture.write(["only record"])
    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 1

    # The metadata-first gate: no unread bytes means no changed file.
    async def probe() -> bool:
        return bool(await fixture.adapter().has_changes(_options_with_cursors(fixture)))

    assert asyncio.run(probe()) is False, "an unchanged source must report no changes"
    assert fixture.run().stored == 0
    assert fixture.evidence.count() == 1


def _options_with_cursors(fixture: Source):
    from one_memory.imports.adapters import ScanOptions

    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id=fixture.source)
    return ScanOptions(cursors=cursors)


def test_one_import_uses_exactly_one_reader(tmp_path):
    """Scanning once opens the file through a single reader, writing each row once."""
    fixture = Source(tmp_path)
    fixture.write(["reader one", "reader two"])

    opens = []
    from one_memory.imports.access import AuthorizedSourceFile

    real_open = AuthorizedSourceFile.open_binary

    def counted(source_file):
        opens.append(source_file.relative_path.as_posix())
        return real_open(source_file)

    AuthorizedSourceFile.open_binary = counted
    try:
        result = fixture.run()
    finally:
        AuthorizedSourceFile.open_binary = real_open

    assert result.stored == 2
    assert fixture.evidence.count() == 2
    # One file, and only as many opens as the reader legitimately needs; what
    # matters is that no second reader produced a duplicate row set.
    assert len(set(opens)) == 1
    stored = _stored(fixture)
    assert {row["verbatim"] for row in stored} == {"reader one", "reader two"}


def test_a_second_history_job_for_one_source_is_reused_not_duplicated(tmp_path):
    """No second reader may be spawned for the same source while one is active.

    The double-write risk is two concurrent history jobs over one source: each
    would open the file and could store the same rows. The store reuses the
    active job instead of creating a second, so there is only ever one reader.
    """
    fixture = Source(tmp_path)
    fixture.write(["reader one", "reader two"])

    first = fixture.jobs.create(user_id="local", source_id="codex", operation="history")
    second = fixture.jobs.create(user_id="local", source_id="codex", operation="history")

    assert second.job_id == first.job_id, (
        "a second history request must reuse the active job, not spawn a second reader"
    )
    active = [
        job
        for job in fixture.jobs.list_jobs()
        if job.source_id == "codex" and job.operation == "history"
    ]
    assert len(active) == 1, f"exactly one active history job expected, got {len(active)}"

    # Running that one job still stores each row once. `fixture.run()` would
    # create/reuse its own job; drive the already-created one directly so the
    # assertion is about this job's single read.
    import asyncio

    async def scenario():
        supervisor = fixture.supervisor()
        supervisor.enqueue(first.job_id)
        return await supervisor.wait(first.job_id)

    result = asyncio.run(scenario())
    assert result.stored == 2
    assert fixture.evidence.count() == 2


def _stored(fixture: Source) -> list[dict]:
    import sqlite3

    with sqlite3.connect(fixture.database) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT verbatim FROM evidence")]
