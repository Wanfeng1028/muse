"""DeepSeek Harness has two profiles; only the headless session form is importable.

The source matrix states it plainly: headless is `<session>/session.jsonl` with a
`type=session` header; web is not a Harness session file and must go through the
`*-export` family instead. That distinction was prose with no test behind it, so
this pins the observable boundary: a headless session imports, while a web-style
export dropped into the same `sessions/` tree imports nothing.
"""

import asyncio
import json
from pathlib import Path

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

HEADLESS_RECORDS = [
    {"type": "session", "id": "s", "cwd": "/private/project"},
    {
        "type": "user/message",
        "seq": 1,
        "data": {
            "id": "a",
            "role": "user",
            "source": {"kind": "user"},
            "content": [{"type": "text", "text": "headless person turn"}],
        },
    },
]

# The shape a browser-side export has: a `role`-keyed transcript, no Harness
# `type=session` envelope, and not named `session.jsonl`.
WEB_EXPORT_RECORDS = [
    {"role": "user", "content": "web export person turn", "time": None},
    {"role": "assistant", "content": "web export agent turn", "time": None},
]


class Source:
    def __init__(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        self.registration = build_source_catalog(home=home, environment={})["deepseek-harness"]
        self.root = self.registration.candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        database = tmp_path / "data" / "core.sqlite3"
        database.parent.mkdir(parents=True, exist_ok=True)
        self.jobs = ImportJobStore(database)
        self.evidence = EvidenceStore(database)
        self.grants = SourceGrantStore(database, home=home)
        self.grants.grant(
            user_id="local",
            source_id="deepseek-harness",
            root=self.root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )

    def write(self, relative: str, records: list[dict]) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
        return path

    def run(self):
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={
                    "deepseek-harness": self.registration.create_adapter(
                        self.grants.authorized_root(user_id="local", source_id="deepseek-harness")
                    )
                },
                evidence_store=self.evidence,
                job_store=self.jobs,
            )
            job = supervisor.create_job("deepseek-harness")
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())


def test_only_the_headless_session_form_is_importable(tmp_path):
    fixture = Source(tmp_path)
    fixture.write("headless-run/session.jsonl", HEADLESS_RECORDS)
    # A web export dropped into the same tree: different name, different shape.
    fixture.write("web-export/transcript.jsonl", WEB_EXPORT_RECORDS)

    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 1, (
        "only the headless session.jsonl may import; the web export must be "
        f"skipped, got stored={result.stored}"
    )
    stored = [row.verbatim for row in fixture.evidence.list_extractable(limit=50)]
    assert "headless person turn" in stored
    assert not any("web export" in text for text in stored), (
        "a web-style export must not be imported through the Harness profile"
    )


def test_a_web_export_alone_imports_nothing(tmp_path):
    fixture = Source(tmp_path)
    fixture.write("web-export/transcript.jsonl", WEB_EXPORT_RECORDS)

    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert result.stored == 0
    assert fixture.evidence.count() == 0


def test_the_adapter_has_two_independent_layers(tmp_path):
    """File-name gating and record-shape gating are separate defences.

    Mutation M28 (relax `file_predicate` to accept any `.jsonl`) did NOT turn the
    tests above red, and that is honest rather than a weak assertion: the parser
    rejects a record with no `data` envelope as UNKNOWN_RECORD, so the web export
    still imports nothing. This test states both layers explicitly so neither is
    mistaken for the other, and so a future change that removes one is visible.
    """
    fixture = Source(tmp_path)
    adapter = fixture.registration.create_adapter(
        fixture.grants.authorized_root(user_id="local", source_id="deepseek-harness")
    )
    headless = fixture.write("headless-run/session.jsonl", HEADLESS_RECORDS)
    web = fixture.write("web-export/transcript.jsonl", WEB_EXPORT_RECORDS)

    # Layer 1: the file predicate accepts only the headless session filename.
    predicate = adapter.file_predicate
    listed_headless = adapter.grant.listed_file(headless)
    listed_web = adapter.grant.listed_file(web)
    assert predicate(listed_headless) is True
    assert predicate(listed_web) is False, (
        "the file predicate must exclude a web-style export by name"
    )

    # Layer 2: even if a web record reached the parser, it is skipped, not stored
    # as a person's words.
    from one_memory.imports.sources.common import SourceRecordContext
    from one_memory.imports.sources.deepseek_harness import parse_deepseek_harness_record

    context = SourceRecordContext(
        file_key="k",
        relative_path="web-export/transcript.jsonl",
        ordinal="k:1",
        header=None,
    )
    parsed = parse_deepseek_harness_record(WEB_EXPORT_RECORDS[0], context)
    assert not hasattr(parsed, "verbatim"), (
        "a record without the Harness data envelope must not become Evidence"
    )
