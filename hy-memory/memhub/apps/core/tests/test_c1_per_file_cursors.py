"""Each file in a source keeps its own cursor, not one cursor for the source.

The contract asks for per-directory / per-file cursors. A single source-level
cursor would still import correctly on a quiet tree, so the property has to be
asserted directly: two files must produce two cursors, each tracking its own
byte offset, and appending to one must not move the other.
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
    def __init__(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        (home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.registration = build_source_catalog(home=home, environment={})["codex"]
        self.root = self.registration.candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        database = tmp_path / "data" / "core.sqlite3"
        database.parent.mkdir(parents=True, exist_ok=True)
        self.jobs = ImportJobStore(database)
        self.evidence = EvidenceStore(database)
        self.grants = SourceGrantStore(database, home=home)
        self.grants.grant(
            user_id="local",
            source_id="codex",
            root=self.root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )

    def write(self, name: str, texts: list[str]) -> Path:
        path = self.root / "project" / f"rollout-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
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
        return path

    def run(self):
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={
                    "codex": self.registration.create_adapter(
                        self.grants.authorized_root(user_id="local", source_id="codex")
                    )
                },
                evidence_store=self.evidence,
                job_store=self.jobs,
            )
            job = supervisor.create_job("codex")
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())

    def cursors(self) -> dict[str, object]:
        return self.jobs.get_source_cursors(user_id="local", source_id="codex")


def test_two_files_keep_independent_cursors(tmp_path):
    fixture = Source(tmp_path)
    first = fixture.write("alpha", ["alpha one", "alpha two"])
    second = fixture.write("beta", ["beta one"])

    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED and result.stored == 3

    cursors = fixture.cursors()
    assert len(cursors) == 2, (
        "one cursor per file is required; a single source-level cursor would "
        f"conflate the two files. got {len(cursors)}: "
        f"{[c.observed_size for c in cursors.values()]}"
    )
    sizes = sorted(cursor.observed_size for cursor in cursors.values())
    assert sizes == sorted([first.stat().st_size, second.stat().st_size]), (
        "each cursor must record its own file's size, not the source's total"
    )

    # Appending to one file must move only that file's cursor.
    before = {key: cursor.observed_size for key, cursor in fixture.cursors().items()}
    with first.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "alpha three"}],
                    },
                }
            )
            + "\n"
        )
    appended = fixture.run()
    assert appended.stored == 1
    after = {key: cursor.observed_size for key, cursor in fixture.cursors().items()}

    moved = [key for key in after if after[key] != before[key]]
    assert len(moved) == 1, (
        f"exactly the appended file's cursor may move; moved={moved} before={before} after={after}"
    )
    assert fixture.evidence.count() == 4
