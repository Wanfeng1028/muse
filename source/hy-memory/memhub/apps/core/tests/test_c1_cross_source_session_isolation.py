"""Same session name in two sources must stay two conversations.

`SessionIdentity` mixes the harness id into the internal session id, so Cursor's
"standup" and Codex's "standup" can never merge. This asserts it end to end
through the real parsers, not only in the sessionizer unit, and checks that a
re-import of both still adds nothing.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


class TwoSources:
    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        (self.home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.catalog = build_source_catalog(home=self.home, environment={})
        self.database = tmp_path / "core.sqlite3"
        self.jobs = ImportJobStore(self.database)
        self.evidence = EvidenceStore(self.database)
        self.grants = SourceGrantStore(self.database, home=self.home)

    def add(self, source: str, session: str, texts: list[str]) -> None:
        root = self.catalog[source].candidate.path
        root.mkdir(parents=True, exist_ok=True)
        self.grants.grant(
            user_id="local",
            source_id=source,
            root=root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )
        path = root / f"project/rollout-{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for text in texts:
                stream.write(json.dumps(self._record(source, session, text)) + "\n")

    def _record(self, source: str, session: str, text: str) -> dict:
        if source == "codex":
            return {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        return {
            "type": "user",
            "sessionId": session,
            "timestamp": "2026-09-28T10:00:00+08:00",
            "message": {"content": text},
        }

    def run(self, source: str):
        async def scenario():
            supervisor = ImportSupervisor(
                adapters={
                    source: self.catalog[source].create_adapter(
                        self.grants.authorized_root(user_id="local", source_id=source)
                    )
                },
                evidence_store=self.evidence,
                job_store=self.jobs,
            )
            job = supervisor.create_job(source)
            supervisor.enqueue(job.job_id)
            return await supervisor.wait(job.job_id)

        return asyncio.run(scenario())


def test_same_external_session_name_in_two_sources_stays_separate(tmp_path):
    fixture = TwoSources(tmp_path)
    fixture.add("codex", "standup", ["codex standup one", "codex standup two"])
    fixture.add("workbuddy", "standup", ["workbuddy standup one"])

    first = fixture.run("codex")
    second = fixture.run("workbuddy")
    assert first.status is ImportStatus.COMPLETED and second.status is ImportStatus.COMPLETED
    assert fixture.evidence.count() == 3

    rows = _stored(fixture)
    by_source: dict[str, set[str]] = {}
    for row in rows:
        by_source.setdefault(row["source_id"], set()).add(row["verbatim"])
    assert by_source == {
        "codex": {"codex standup one", "codex standup two"},
        "workbuddy": {"workbuddy standup one"},
    }
    # The point of the test: the same external session name in two sources must
    # produce two different conversation identities. Grouping by source alone
    # would still hold if the identities had been merged, so assert it directly.
    #
    # Scope note: this covers the *parse-time* identity each source adapter
    # writes (Codex from its file path, WorkBuddy from `sessionId`). The
    # `SessionIdentity` mix of harness_id is covered by
    # `test_scanner_sessionizer.py::test_harness_id_participates_in_identity`,
    # which does turn red when harness_id stops participating.
    conversation_ids = {row["source_id"]: row["conversation_id"] for row in rows}
    assert len(set(conversation_ids.values())) == 2, (
        f"same-named sessions collapsed into one identity: {conversation_ids}"
    )
    # Nothing merged across sources, so re-running both adds nothing.
    assert fixture.run("codex").stored == 0
    assert fixture.run("workbuddy").stored == 0
    assert fixture.evidence.count() == 3


def test_a_second_file_in_one_session_continues_round_numbers(tmp_path):
    from one_memory.memory_server.scanner.sessionizer import sessionize
    from tests.test_scanner_sessionizer import _message

    first = sessionize(
        [_message(0), _message(1, "assistant")],
        harness_id="cursor",
        source_file_key="f" * 64,
    )
    committed = {first[0].internal_session_id: first[-1].round_number}
    second = sessionize(
        [_message(2), _message(3, "assistant")],
        harness_id="cursor",
        source_file_key="f" * 64,
        last_committed_round_by_session=committed,
    )
    assert second[0].round_number == first[-1].round_number + 1


def test_cursor_store_and_workbuddy_same_name_stay_separate(tmp_path):
    """Cursor store identity comes from its parent directory, not the file name."""
    fixture = TwoSources(tmp_path)
    fixture.add("workbuddy", "shared-name", ["workbuddy words"])

    cursor_root = fixture.catalog["cursor"].candidate.path
    cursor_root.mkdir(parents=True, exist_ok=True)
    fixture.grants.grant(
        user_id="local",
        source_id="cursor",
        root=cursor_root,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    database = cursor_root / "chats/workspace/shared-name/store.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        connection.execute(
            "INSERT INTO blobs VALUES (?, ?)",
            ("row-0", json.dumps({"role": "user", "content": "cursor words"})),
        )
        connection.commit()
    finally:
        connection.close()

    assert fixture.run("workbuddy").status is ImportStatus.COMPLETED
    assert fixture.run("cursor").status is ImportStatus.COMPLETED
    rows = _stored(fixture)

    assert {row["verbatim"] for row in rows} == {"workbuddy words", "cursor words"}
    assert {(row["source_id"], row["conversation_id"]) for row in rows} == {
        ("workbuddy", "shared-name"),
        ("cursor", "shared-name"),
    }, "the same name is isolated by the source-scoped identity, not by lucky naming"
    assert fixture.evidence.count() == 2


def _stored(fixture) -> list[dict]:
    """Read stored rows directly; business readers filter and could hide a merge."""
    import sqlite3

    with sqlite3.connect(fixture.database) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT source_id, conversation_id, verbatim FROM evidence"
            )
        ]
