"""Upgrade/migration matrix: an older database keeps importing incrementally.

Day 7 asks for an upgrade-migration matrix. This proves the part that can be
proved now: a database written before the newest schema is still usable, the
missing column is added idempotently, and the upgraded database continues to
import append-only instead of re-reading or duplicating history.
"""

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import SCHEMA, EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


def _legacy_database(path: Path, rows: list[tuple[str, str]]) -> None:
    """A database as an older build left it: no `source_ordinal` column."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA.replace("    source_ordinal TEXT,\n", ""))
        connection.executemany(
            "INSERT INTO evidence (evidence_id, idempotency_key, user_id, source_id, "
            "conversation_id, content_kind, role, written_by, verbatim, content_hash, "
            "revision, imported_at, updated_at) "
            "VALUES (?, ?, 'local', 'codex', 'legacy-session', 'raw_conversation', "
            "'user', 'person', ?, ?, 1, '2026-09-28T10:00:00+00:00', "
            "'2026-09-28T10:00:00+00:00')",
            [
                (evidence_id, f"legacy:{evidence_id}", verbatim, f"hash:{evidence_id}")
                for evidence_id, verbatim in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()
    # Leave no -wal/-shm behind: a stale sidecar makes the store's first WAL
    # open fail with a disk I/O error, which would look like a product bug.
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _columns(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute("PRAGMA table_info(evidence)")}


def _legacy_message_key(evidence) -> str:
    return hashlib.sha256(
        "\0".join(
            (
                "message-v1",
                evidence.user_id,
                evidence.source_id,
                evidence.conversation_id,
                evidence.message_id or evidence.correlation_id or "",
            )
        ).encode()
    ).hexdigest()


def test_upgrade_v2_does_not_duplicate_a_legacy_v1_message(tmp_path):
    """A pre-fix v1 Evidence row must be recognized when the same message returns.

    The workspace-aware v2 key is required for new identities, but an upgraded
    database still contains rows keyed by the old message-v1 material. Replaying
    the same source message must not create a second Evidence row for it.
    """
    from datetime import UTC, datetime
    from uuid import UUID, uuid5

    from one_memory.imports.models import (
        EVIDENCE_NAMESPACE,
        EvidenceInput,
        EvidenceOrigin,
        OriginMetadata,
        WrittenBy,
    )

    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    replay = EvidenceInput(
        source_id="cursor",
        workspace="workspace:v1:project-a",
        project="project-a",
        conversation_id="same-conversation",
        message_id="same-message",
        role="user",
        written_by=WrittenBy.PERSON,
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        verbatim="project A",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
    )
    legacy_key = _legacy_message_key(replay)
    legacy_id = str(uuid5(UUID(str(EVIDENCE_NAMESPACE)), legacy_key))
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence (evidence_id,idempotency_key,user_id,source_id,"
            "workspace,project,conversation_id,message_id,role,written_by,created_at,"
            "verbatim,content_hash,revision,imported_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                legacy_id,
                legacy_key,
                replay.user_id,
                replay.source_id,
                replay.workspace,
                replay.project,
                replay.conversation_id,
                replay.message_id,
                replay.role,
                replay.written_by,
                replay.created_at.isoformat(),
                replay.verbatim,
                replay.content_hash,
                now,
                now,
            ),
        )

    result = store.put(replay)

    assert result.was_created is False
    assert result.record.evidence_id == legacy_id
    assert store.count() == 1


def test_legacy_v1_identity_does_not_merge_a_different_workspace(tmp_path):
    from datetime import UTC, datetime

    from one_memory.imports.models import (
        EvidenceInput,
        EvidenceOrigin,
        OriginMetadata,
        WrittenBy,
    )

    def record(workspace: str, text: str) -> EvidenceInput:
        return EvidenceInput(
            source_id="cursor",
            workspace=workspace,
            project=workspace.rsplit(":", 1)[-1],
            conversation_id="same-conversation",
            message_id="same-message",
            role="user",
            written_by=WrittenBy.PERSON,
            created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
            verbatim=text,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )

    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    first = record("workspace:v1:project-a", "project A")
    first_legacy_key = _legacy_message_key(first)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence (evidence_id,idempotency_key,user_id,source_id,"
            "workspace,project,conversation_id,message_id,role,written_by,created_at,"
            "verbatim,content_hash,revision,imported_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                "legacy-project-a",
                first_legacy_key,
                first.user_id,
                first.source_id,
                first.workspace,
                first.project,
                first.conversation_id,
                first.message_id,
                first.role,
                first.written_by,
                first.created_at.isoformat(),
                first.verbatim,
                first.content_hash,
                now,
                now,
            ),
        )

    result = store.put(record("workspace:v1:project-b", "project B"))

    assert result.was_created is True
    assert result.record.workspace == "workspace:v1:project-b"
    assert store.count() == 2


def test_upgrade_v2_correlation_replay_reuses_a_unique_legacy_hook_row(tmp_path):
    from datetime import UTC, datetime

    from one_memory.imports.models import (
        EvidenceInput,
        EvidenceOrigin,
        OriginMetadata,
        WrittenBy,
    )

    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    replay = EvidenceInput(
        source_id="cursor",
        conversation_id="hooked-conversation",
        message_id="same-message",
        correlation_id="same-message",
        role="user",
        written_by=WrittenBy.PERSON,
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        verbatim="hooked",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
    )
    legacy_key = _legacy_message_key(replay)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence (evidence_id,idempotency_key,user_id,source_id,"
            "conversation_id,message_id,correlation_id,role,written_by,created_at,"
            "verbatim,content_hash,revision,imported_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                "legacy-hook",
                legacy_key,
                replay.user_id,
                replay.source_id,
                replay.conversation_id,
                None,
                replay.correlation_id,
                replay.role,
                replay.written_by,
                replay.created_at.isoformat(),
                replay.verbatim,
                replay.content_hash,
                now,
                now,
            ),
        )

    result = store.put(replay)

    assert result.was_created is False
    assert result.record.evidence_id == "legacy-hook"
    assert store.count() == 1


def test_upgrade_v2_derived_replay_reuses_the_legacy_row(tmp_path):
    from datetime import UTC, datetime

    from one_memory.imports.models import (
        EvidenceInput,
        EvidenceOrigin,
        OriginMetadata,
        WrittenBy,
    )

    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    replay = EvidenceInput(
        source_id="codex",
        workspace="workspace:v1:project-a",
        project="project-a",
        conversation_id="derived-conversation",
        source_ordinal="line:7",
        role="user",
        written_by=WrittenBy.PERSON,
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        verbatim="derived old record",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
    )
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence (evidence_id,idempotency_key,user_id,source_id,"
            "workspace,project,conversation_id,source_ordinal,role,written_by,created_at,"
            "verbatim,content_hash,revision,imported_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                "legacy-derived",
                replay.legacy_derived_idempotency_key,
                replay.user_id,
                replay.source_id,
                replay.workspace,
                replay.project,
                replay.conversation_id,
                replay.source_ordinal,
                replay.role,
                replay.written_by,
                replay.created_at.isoformat(),
                replay.verbatim,
                replay.content_hash,
                now,
                now,
            ),
        )

    result = store.put(replay)

    assert result.was_created is False
    assert result.record.evidence_id == "legacy-derived"
    assert store.count() == 1


class Upgraded:
    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        (self.home / ".cursor").mkdir(parents=True, exist_ok=True)
        self.catalog = build_source_catalog(home=self.home, environment={})
        self.root = self.catalog["codex"].candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = tmp_path / "core.sqlite3"
        self.jobs = ImportJobStore(self.database)
        self.evidence = EvidenceStore(self.database)
        self.grants = SourceGrantStore(self.database, home=self.home)

    def write(self, name: str, texts: list[str]) -> Path:
        path = self.root / f"project/rollout-{name}.jsonl"
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
            self.grants.grant(
                user_id="local",
                source_id="codex",
                root=self.root,
                candidate_kind=RootCandidateKind.DEFAULT,
            )
            supervisor = ImportSupervisor(
                adapters={
                    "codex": self.catalog["codex"].create_adapter(
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


def test_an_older_database_is_upgraded_and_then_imports_incrementally(tmp_path):
    # Built straight at the store's own path: renaming a database leaves its
    # -wal/-shm behind and the next open then fails with a disk I/O error.
    database = tmp_path / "core.sqlite3"
    _legacy_database(database, [("old-1", "old row one"), ("old-2", "old row two")])
    assert "source_ordinal" not in _columns(database), "the legacy build left the column out"

    # Opening the store is the upgrade path: the column is added, once.
    EvidenceStore(database)
    assert "source_ordinal" in _columns(database)
    EvidenceStore(database)
    assert "source_ordinal" in _columns(database)

    fixture = Upgraded(tmp_path)

    target = fixture.write("session", ["new one", "new two"])
    first = fixture.run()
    assert first.status is ImportStatus.COMPLETED and first.stored == 2
    assert fixture.evidence.count() == 4, "old rows survive and new ones land"

    with target.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "appended after upgrade"}],
                    },
                }
            )
            + "\n"
        )
    second = fixture.run()
    assert second.stored == 1
    assert fixture.evidence.count() == 5


def test_upgrade_does_not_duplicate_or_reimport_legacy_rows(tmp_path):
    database = tmp_path / "core.sqlite3"
    _legacy_database(database, [("old-1", "old row one")])
    EvidenceStore(database)
    fixture = Upgraded(tmp_path)
    fixture.write("session", ["new one"])
    first = fixture.run()
    assert first.stored == 1 and fixture.evidence.count() == 2

    again = fixture.run()
    assert (again.stored, again.merged, again.emitted) == (0, 0, 0)
    assert fixture.evidence.count() == 2

    with sqlite3.connect(fixture.database) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM evidence WHERE verbatim = 'old row one'"
            ).fetchone()[0]
            == 1
        )
